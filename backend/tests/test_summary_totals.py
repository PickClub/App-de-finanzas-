"""Actual summary function, BSON fixtures and read-only sessions; never imports server."""
import ast
import asyncio
import copy
import logging
import math
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest

from bson import Binary, Decimal128, Int64, ObjectId
from fastapi import FastAPI, HTTPException
import httpx
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern


def matches(row, query):
    for key, value in query.items():
        if isinstance(value, dict):
            if '$ne' in value and row.get(key) == value['$ne']: return False
            if '$in' in value and row.get(key) not in value['$in']: return False
        elif row.get(key) != value: return False
    return True


class Cursor:
    def __init__(self, db, rows, kind):
        self.db, self.rows, self.kind = db, rows, kind
        self.closed = False
        db.cursors.append(self)
    def max_time_ms(self, value):
        assert 0 < value <= 10000
        return self
    def batch_size(self, value):
        assert value == 100
        return self
    async def to_list(self, limit):
        assert self.kind == 'aggregate' and limit == 1
        return self.rows[:limit]
    def __aiter__(self):
        self.iterator = iter(self.rows)
        return self
    async def __anext__(self):
        if self.db.delay: await asyncio.sleep(self.db.delay)
        try: row = next(self.iterator)
        except StopIteration: raise StopAsyncIteration
        if self.db.on_row:
            fn, self.db.on_row = self.db.on_row, None
            fn()
        return row
    async def close(self):
        self.closed = True
        if self.db.close_error: raise OperationFailure('private cursor close error')


class Collection:
    def __init__(self, db, name): self.db, self.name = db, name
    def data(self, session):
        assert session is self.db.client.session and session.active
        if self.db.read_error: raise OperationFailure('private URI/credentials in driver exception')
        return session.snapshot[self.name]
    def find(self, query, projection, *, session):
        assert projection['_id'] == 0 and projection['id'] == 1
        assert '_history_keys' not in projection
        self.db.commands.append(('find', self.name, query, projection, session))
        rows = [{k: copy.deepcopy(v) for k, v in row.items() if projection.get(k)}
                for row in self.data(session) if matches(row, query)]
        return Cursor(self.db, rows, 'find')
    def aggregate(self, pipeline, **options):
        assert options['allowDiskUse'] is False and options['batchSize'] == 1
        assert 0 < options['maxTimeMS'] <= 10000
        assert options['collation'] == {'locale': 'simple'}
        assert pipeline[1] == {'$group': {'_id': '$id', 'n': {'$sum': 1}}}
        assert pipeline[2] == {'$match': {'n': {'$gt': 1}}} and pipeline[3] == {'$limit': 1}
        session = options['session']
        self.db.commands.append(('aggregate', self.name, pipeline, options, session))
        counts = {}
        for row in self.data(session):
            if matches(row, pipeline[0]['$match']):
                identifier = row.get('id')
                counts[identifier] = counts.get(identifier, 0) + 1
        return Cursor(self.db, [{'duplicate': True}] if any(n > 1 for n in counts.values()) else [], 'aggregate')
    # No mutation methods: a financial write fails immediately.


class Session:
    def __init__(self, db):
        self.db, self.active, self.ended = db, False, False
        self.commits = self.aborts = 0
    def start_transaction(self, **options):
        assert options['read_concern'].document == {'level': 'snapshot'}
        assert options['write_concern'].document == {'w': 'majority'}
        assert 0 < options['max_commit_time_ms'] <= 10000
        return self
    async def __aenter__(self):
        self.active = True
        self.snapshot = copy.deepcopy(self.db.data)
        return self
    async def __aexit__(self, kind, error, tb):
        self.active = False
        if kind: self.aborts += 1
        else:
            if self.db.commit_error: raise OperationFailure('private commit error')
            self.commits += 1
    async def end_session(self):
        self.ended = True
        if self.db.session_close_error: raise OperationFailure('private session close error')


class Client:
    def __init__(self, db): self.db = db; self.session = None
    async def start_session(self):
        self.session = Session(self.db)
        return self.session


class FakeDB:
    def __init__(self, *, accounts=(), transactions=(), debts=(), debt_payments=()):
        self.data = {k: copy.deepcopy(v) for k, v in locals().items() if k != 'self'}
        self.commands, self.cursors = [], []
        self.read_error = self.commit_error = self.close_error = self.session_close_error = False
        self.delay, self.on_row = 0, None
        self.client = Client(self)
        for name in self.data: setattr(self, name, Collection(self, name))


def load_summary(db, *, limits=None, now=None):
    node = next(n for n in ast.parse((Path(__file__).parents[1] / 'server.py').read_text()).body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == 'summary')
    node.decorator_list = []
    # Shrink only the resource ceilings in memory for boundary tests, never files.
    if limits is not None:
        assignment = next(n for n in node.body if isinstance(n, ast.Assign)
                          and isinstance(n.targets[0], ast.Tuple)
                          and n.targets[0].elts[0].id == 'timeout')
        assignment.value = ast.Tuple(elts=[ast.Constant(v) for v in limits], ctx=ast.Load())
        ast.fix_missing_locations(node)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if now is not None and tz else now if now is not None else datetime.now(tz)
    ns = dict(db=db, client=db.client, datetime=Clock, timezone=timezone, Decimal=Decimal,
              math=math, DEFAULT_USER_ID='default-user', HTTPException=HTTPException,
              ReadConcern=ReadConcern, WriteConcern=WriteConcern, PyMongoError=PyMongoError,
              logger=logging.getLogger('offline-summary'))
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual summary>', 'exec'), ns)
    return ns['summary']


NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
def tx(identifier, **fields):
    return {'id':str(identifier), 'user_id':'default-user', 'type':'expense', 'amount':1,
            'date':'2026-10-14T12:00:00Z', **fields}
def account(identifier, value=1):
    return dict(id=str(identifier), user_id='default-user', current_balance=value)
def debt(identifier, value=1, **fields):
    return {'id':str(identifier), 'user_id':'default-user', 'direction':'i_owe', 'remaining_amount':value, **fields}
def payment(identifier, **fields):
    return {'id':str(identifier), 'user_id':'default-user', 'amount':1, 'date':'2026-10-14T12:00:00Z', **fields}


class SummaryTotalsTests(unittest.IsolatedAsyncioTestCase):
    async def result(self, db, **options):
        original = copy.deepcopy(db.data)
        result = await load_summary(db, now=NOW, **options)()
        self.assertEqual(db.data, original)
        self.assertTrue(db.client.session.ended)
        self.assertTrue(all(c.closed for c in db.cursors))
        self.assertEqual({c[0] for c in db.commands}, {'aggregate', 'find'})
        self.assertTrue(all(c[-1] is db.client.session for c in db.commands))
        self.assertEqual(db.client.session.commits, 1)
        self.assertEqual(set(result), {'total_balance', 'month_income', 'month_expense', 'debts', 'accounts_count'})
        return result
    async def blocked(self, db, status, **options):
        original = copy.deepcopy(db.data)
        with self.assertRaises(HTTPException) as caught:
            await load_summary(db, now=NOW, **options)()
        self.assertEqual(caught.exception.status_code, status)
        self.assertNotIn('private', caught.exception.detail)
        self.assertEqual(db.data, original)
        self.assertTrue(db.client.session.ended)
        self.assertTrue(all(c.closed for c in db.cursors))

    async def test_501_2001_20001_complete_movements(self):
        for count in (501, 2001, 20001):
            with self.subTest(count=count):
                r = await self.result(FakeDB(transactions=[tx(i) for i in range(count)]))
                self.assertEqual(r['month_expense'], count)
    async def test_current_month_after_old_history(self):
        rows = [dict(tx(i), date='2000-01-01T00:00:00Z') for i in range(20001)]
        rows += [dict(tx('income'), type='income', amount=70), dict(tx('expense'), amount=20)]
        r = await self.result(FakeDB(transactions=rows))
        self.assertEqual((r['month_income'], r['month_expense']), (70, 20))
    async def test_over_500_accounts_and_debts(self):
        r = await self.result(FakeDB(accounts=[account(i) for i in range(501)],
                                     debts=[debt(i) for i in range(501)]))
        self.assertEqual((r['total_balance'], r['accounts_count'], r['debts']['i_owe']), (501, 501, 501))
    async def test_large_decimal128_and_numeric_text(self):
        rows = [dict(tx('income'), type='income', amount=Decimal128('1000000000000.10')),
                dict(tx('income2'), type='income', amount='0.20'), dict(tx('expense'), amount='0.15')]
        r = await self.result(FakeDB(transactions=rows, accounts=[account('a', Decimal128('1000000000000.34'))]))
        self.assertEqual(Decimal(str(r['month_income'])), Decimal('1000000000000.30'))
        self.assertEqual(Decimal(str(r['total_balance'])), Decimal('1000000000000.34'))
        self.assertEqual(Decimal(str(r['month_income']))-Decimal(str(r['month_expense'])), Decimal('1000000000000.15'))
    async def test_exact_decimal_sum_before_final_rounding(self):
        r = await self.result(FakeDB(transactions=[dict(tx(i), amount='0.005') for i in range(2001)]))
        self.assertEqual(r['month_expense'], 10.0)  # 10.005 -> half-even at the final boundary.
        r = await self.result(FakeDB(transactions=[dict(tx(1), amount='.10'), dict(tx(2), amount=.20)]))
        self.assertEqual(r['month_expense'], .30)
    async def test_rules_transfer_loans_and_receipts_no_double_count(self):
        rows = [dict(tx(1), type='income', amount=100), dict(tx(2), amount=20),
                dict(tx(3), type='debt_payment', amount=30)]
        rows += [dict(tx(k), type=k, amount=999) for k in ('transfer', 'loan_given', 'loan_received', 'legacy')]
        r = await self.result(FakeDB(transactions=rows, debt_payments=[payment('p', amount=30)]))
        self.assertEqual((r['month_income'], r['month_expense'], r['debts']['paid_this_month']), (100, 50, 30))
    async def test_deleted_receipts_and_other_users_excluded(self):
        r = await self.result(FakeDB(transactions=[dict(tx(1), user_id='other')],
            debt_payments=[payment('p', deleted=True), dict(payment('other'), user_id='other')]))
        self.assertEqual(r['month_expense'], 0)
        self.assertEqual(r['debts']['paid_this_month'], 0)
    async def test_offset_calendar_month_and_naive_dates_preserved(self):
        rows = [dict(tx(1), date='2026-09-30T23:30:00-05:00', amount=10),
                dict(tx(2), date='2026-10-01T00:30:00+14:00', amount=20),
                dict(tx(3), date='2026-10-14T12:00:00', amount=30), dict(tx(4), date='2026-10-14', amount=40)]
        self.assertEqual((await self.result(FakeDB(transactions=rows)))['month_expense'], 90)
    async def test_next_payment_after_500_debts_and_stable_ties(self):
        rows = [debt(i) for i in range(501)] + [debt('future', due_date='2026-11-01', status='active', minimum_payment='70.25', name='Synthetic'),
                debt('first', due_date='2026-10-15', status='active', minimum_payment=10, name='First'),
                debt('tie', due_date='2026-10-15', status='active', minimum_payment=20, name='Second')]
        r = await self.result(FakeDB(debts=rows))
        self.assertEqual(r['debts']['next_payment'], {'date':'2026-10-15', 'amount':10, 'name':'First'})
    async def test_only_selected_next_payment_crosses_numeric_api_boundary(self):
        rows=[debt('later',due_date='2026-12-01',status='active',minimum_payment=Decimal128('1000000000000000000000000000000.01')),
              debt('earlier',due_date='2026-10-15',status='active',minimum_payment='10.25',name='Synthetic')]
        r=await self.result(FakeDB(debts=rows))
        self.assertEqual(r['debts']['next_payment']['amount'],10.25)
    async def test_two_directions_and_negative_balances_preserved(self):
        r = await self.result(FakeDB(accounts=[account('negative', '-10.25')], debts=[debt(1, '5.20'), debt(2, Decimal128('8.30'), direction='they_owe')]))
        self.assertEqual((r['total_balance'], r['debts']['i_owe'], r['debts']['they_owe']), (-10.25, 5.20, 8.30))
    async def test_physical_bson_ids_do_not_affect_totals(self):
        physical = [1, Int64(2147483648), 'legacy', Binary(b'legacy'), ObjectId()]
        self.assertEqual((await self.result(FakeDB(transactions=[dict(tx(i), _id=physical[i]) for i in range(5)])))['month_expense'], 5)
    async def test_duplicates_in_each_source_are_blocked(self):
        for name, docs in (('transactions',[tx(1),dict(tx(1),date='2000-01-01T00:00:00Z')]),
                           ('accounts',[account(1),account(1)]), ('debts',[debt(1),debt(1)]),
                           ('debt_payments',[payment(1),payment(1)])):
            with self.subTest(collection=name): await self.blocked(FakeDB(**{name:docs}),409)
    async def test_invalid_amounts_are_not_zero(self):
        for value in (None, '', 'not-money', 'NaN', 'Infinity', Decimal128('NaN'), True, {}, []):
            with self.subTest(value=str(value)): await self.blocked(FakeDB(transactions=[dict(tx(1),amount=value)]),409)
        await self.blocked(FakeDB(accounts=[account(1,None)]),409)
        await self.blocked(FakeDB(debt_payments=[payment(1,amount='bad')]),409)
    async def test_missing_identity_invalid_date_direction_and_minimum(self):
        for db in (FakeDB(accounts=[dict(account(1),id=None)]), FakeDB(transactions=[dict(tx(1),date='bad')]),
                   FakeDB(debts=[debt(1,direction='bad')]), FakeDB(debts=[debt(1,due_date='2026-10-15',status='active',minimum_payment=None)])):
            await self.blocked(db,409)
        await self.blocked(FakeDB(debts=[debt(1,due_date='bad',status='active',minimum_payment=1)]),409)
    async def test_valid_large_amount_unrepresentable_api_has_explicit_error(self):
        await self.blocked(FakeDB(transactions=[dict(tx(1),amount=Decimal128('1000000000000000000000000000000.01'))]),503)
    async def test_large_exact_integer_is_not_classified_as_corruption(self):
        value=Decimal128('10000000000000000000000000')
        r=await self.result(FakeDB(transactions=[dict(tx(1),type='income',amount=value)]))
        self.assertEqual(Decimal(str(r['month_income'])),value.to_decimal())
    async def test_resource_limits_no_partial_response(self):
        await self.blocked(FakeDB(transactions=[tx(i) for i in range(3)]),503,limits=(10,2,33554432,10000))
        await self.blocked(FakeDB(transactions=[tx(1)]),503,limits=(10,100000,1,10000))
        await self.blocked(FakeDB(transactions=[dict(tx(1),amount='1E+10001')]),503)
    async def test_timeout_closes_all_resources(self):
        db = FakeDB(transactions=[tx(1)]); db.delay = .02
        await self.blocked(db,503,limits=(.001,100000,33554432,10000))
    async def test_read_and_commit_failures_are_safe_errors(self):
        for flag in ('read_error','commit_error','close_error'):
            db = FakeDB(transactions=[tx(1)]); setattr(db,flag,True)
            await self.blocked(db,503)
    async def test_session_close_failure_does_not_expose_driver_details(self):
        db = FakeDB(); db.session_close_error = True
        with self.assertLogs('offline-summary',level='WARNING') as logs:
            r = await self.result(db)
        self.assertEqual(r['total_balance'],0)
        self.assertNotIn('private',str(logs.output))
    async def test_one_snapshot_keeps_concurrent_sources_consistent(self):
        db = FakeDB(accounts=[account(1,100)],transactions=[tx(1)])
        db.on_row = lambda: (db.data['accounts'].append(account(2,999)), db.data['transactions'].append(tx(2)))
        r = await load_summary(db,now=NOW)()
        self.assertEqual((r['total_balance'],r['accounts_count'],r['month_expense']),(100,1,1))
        self.assertTrue(db.client.session.ended)
    async def test_cancellation_closes_cursors_and_session(self):
        db=FakeDB(transactions=[tx(1)]); db.delay=10
        task=asyncio.create_task(load_summary(db,now=NOW)())
        for _ in range(100):
            await asyncio.sleep(.001)
            if any(c.kind=='find' and not c.closed for c in db.cursors):break
        else:self.fail('Read cursor did not open')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(db.client.session.ended)
        self.assertTrue(all(c.closed for c in db.cursors))
    async def test_empty_and_http_contract(self):
        db=FakeDB();fn=load_summary(db,now=NOW);app=FastAPI();app.get('/api/summary')(fn)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://offline') as client:
            response=await client.get('/api/summary')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),{'total_balance':0,'month_income':0,'month_expense':0,'debts':{'i_owe':0,'they_owe':0,'paid_this_month':0,'next_payment':None},'accounts_count':0})
        self.assertNotIn('_history',response.text)


if __name__ == '__main__': unittest.main()
