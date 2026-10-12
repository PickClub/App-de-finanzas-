"""R3 regression cases. Exact route AST, no startup, dotenv or production DB."""
import ast
import calendar
import copy
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from pathlib import Path
import unittest
import uuid

from bson.decimal128 import Decimal128
from fastapi import APIRouter, FastAPI
from pymongo import ReturnDocument
from backend.tests import test_payment_consistency as memory
from backend.tests.test_bill_validation import Database as BillDatabase, Collection as BillCollection, project


class Collection(BillCollection):
    def find(self, query, projection=None, *, session=None):
        return memory.Cursor([project(d, projection) for d in self.docs(session) if memory.matches(d, query)])

    async def find_one(self, query, projection=None, *, session=None):
        doc = next((d for d in self.docs(session) if memory.matches(d, query)), None)
        return project(doc, projection) if doc is not None else None

    async def update_many(self, query, update, *, session=None):
        # One logical write for failure injection, as with MongoDB update_many.
        self.before_write(session)
        for doc in self.docs(session):
            if memory.matches(doc, query):
                doc.update(copy.deepcopy(update.get('$set', {})))
                for key in update.get('$unset', {}):
                    doc.pop(key, None)

    async def delete_many(self, query, *, session=None):
        self.before_write(session)
        self.docs(session)[:] = [d for d in self.docs(session) if not memory.matches(d, query)]

    def aggregate(self, pipeline, *, session=None):
        # Only the existing goal sum pipeline; MongoDB integration uses real aggregation.
        assert self.name == 'goal_contributions'
        assert pipeline[1] == {'$group': {'_id': '$kind', 's': {'$sum': {'$toDecimal': '$amount'}}}}
        totals = {}
        for doc in self.docs(session):
            if memory.matches(doc, pipeline[0]['$match']):
                value = doc['amount']
                amount = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
                totals[doc['kind']] = totals.get(doc['kind'], Decimal(0)) + amount
        return memory.Cursor([{'_id': kind, 's': Decimal128(value)} for kind, value in totals.items()])


class Database(BillDatabase):
    def __getattr__(self, name):
        return Collection(self, name)


def context(db, client, source=None):
    fixture = memory.PaymentTests()
    fixture.setUp()
    ns = fixture.ns
    ns.update(db=db, client=client, Decimal=Decimal, ROUND_HALF_UP=ROUND_HALF_UP,
              CENT=Decimal('0.01'), date=date, timedelta=timedelta, calendar=calendar,
              re=re, ReturnDocument=ReturnDocument, ROUND_CEILING=ROUND_CEILING)
    router = APIRouter(prefix='/api')
    ns['api'] = router
    names = {
        'RecurringTemplate', 'RecurringCreate', 'RecurringPaymentCreate', 'RecurringPayRecordCreate',
        'BillIn', 'BillPayIn', 'Category', 'CategoryCreate', 'Debt',
        '_parse_dt', '_local_tz', '_positive_money', '_rp_day', '_rp_today', '_rp_dates',
        '_rp_paused', '_rp_occurrences', '_rp_state', '_rp_state_name', '_rp_current',
        '_rp_public', '_rp_get', '_rp_validate', '_rp_records', '_rp_next_due',
        '_bill_rp_due', '_bill_paid_map', '_bill_for_write', '_bill_add_period', '_bill_validate',
        '_bill_public', '_bill_lookups', 'get_bill', 'list_bills', 'get_recurring_payment',
        'pay_bill', 'delete_bill', 'delete_bill_payment', 'create_bill', 'update_bill',
        'create_recurring', 'delete_recurring', 'create_recurring_payment', 'update_recurring_payment',
        'create_recurring_record', 'delete_recurring_payment', 'delete_recurring_record',
        'delete_category', 'create_category', 'update_category', 'create_debt',
        'list_accounts', 'list_categories', 'list_transactions', 'list_debts',
        'SavingGoal', 'SavingGoalCreate', 'GoalContributionCreate', 'Budget', 'BudgetCreate', 'User',
        '_goal_clean', '_goal_public', '_goal_target_date', '_validate_goal', 'recompute_goal',
        'create_goal', 'update_goal', 'delete_goal', 'create_goal_contribution',
        '_validate_budget', '_overlaps', '_dec', 'create_budget', 'update_budget',
        'ensure_user', 'init_default_categories',
    }
    names.update(name for name, value in ns.items() if getattr(getattr(value, '__code__', None), 'co_filename', None) == '<isolated backend>')
    constants = {'RP_FREQS', 'RP_REMINDERS', 'RP_LINK_FIELDS', 'BILL_REMINDERS', 'BUDGET_PERIODS', 'GOAL_HIDDEN',
                 'DEFAULT_EXPENSE_CATEGORIES', 'DEFAULT_INCOME_CATEGORIES', 'NEW_SUBCATEGORIES', 'EXPENSE_GROUPS', 'INCOME_GROUPS'}
    tree = ast.parse(source or Path(__file__).resolve().parents[1].joinpath('server.py').read_text())
    nodes = [n for n in tree.body if
             isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
    assert {n.name for n in nodes if hasattr(n, 'name')} == names
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<isolated R3 routes>', 'exec'), ns)
    fixture.app = FastAPI()
    fixture.app.include_router(router)
    return fixture


class ReferenceCases:
    async def fixture(self, recurring=False, linked=False):
        suffix = uuid.uuid4().hex
        f = {key: key + '-' + suffix for key in ('a', 'b', 'category', 'debt', 'bill', 'rp')}
        for aid in (f['a'], f['b']):
            await self.insert('accounts', dict(id=aid, user_id='default-user', name='Synthetic',
                                              initial_balance=1000, current_balance=1000))
        await self.insert('categories', dict(id=f['category'], user_id='default-user', name='Synthetic', type='expense', is_group=False))
        await self.insert('debts', dict(id=f['debt'], user_id='default-user', name='Synthetic debt', direction='i_owe',
                                        original_amount=500, remaining_amount=500, total_paid=0, status='active',
                                        start_date='2026-10-01T00:00:00+00:00', account_id=None, category_id=None))
        await self.insert('bills', dict(id=f['bill'], user_id='default-user', name='Synthetic bill', amount=100,
                                       frequency='once', due_date='2026-10-20', anchor_day=20, next_bill_id=None,
                                       series_id=f['bill'], category_id=None, account_id=None,
                                       recurring_payment_id=f['rp'] if linked else None))
        if recurring or linked:
            await self.insert('recurring_payments', dict(id=f['rp'], user_id='default-user', name='Synthetic recurring',
                  account_id=None, category_id=None, variable=False, pauses=[], end_date=None, state='active',
                  versions=[dict(valid_from='2026-10-01', start_date='2026-10-20', frequency='monthly', due_day=20, amount=100)]))
        return f

    async def request(self, method, path, data=None, key=None):
        return await self.ctx.request(method, path, **({'json': data} if data is not None else {}),
                                      headers={'Idempotency-Key': key} if key else {})

    async def billpay(self, f, key='bill-key', amount=70):
        r = await self.request('POST', '/bills/' + f['bill'] + '/payments', dict(amount=amount, account_id=f['a']), key)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    async def recurpay(self, f, mode='expense', key='recurring-key', transaction_id=None):
        r = await self.request('POST', '/recurring-payments/' + f['rp'] + '/payments',
                               dict(due_date='2026-10-20', mode=mode, amount=10, account_id=f['a'], transaction_id=transaction_id), key)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    async def doc(self, collection, id):
        return await getattr(self.db, collection).find_one({'id': id})

    async def change(self, collection, id, **fields):
        # Synthetic setup only; no application writes bypass the transaction.
        if isinstance(self.db, Database):
            next(d for d in self.db.data[collection] if d['id'] == id).update(fields)
        else:
            await getattr(self.db, collection).update_one({'id': id}, {'$set': fields})

    async def snapshot(self):
        return {n: await getattr(self.db, n).find({}).to_list(None) for n in self.collections}

    async def balance(self, f):
        return (await self.doc('accounts', f['a']))['current_balance']

    async def test_account_dependency_matrix(self):
        for name, field in [('bills','account_id'), ('recurring_payments','account_id'),
                            ('saving_goals','account_id'), ('goal_contributions','account_id'),
                            ('recurring_templates','to_account_id'), ('bill_payments','account_id'),
                            ('recurring_payment_records','account_id')]:
            f = await self.fixture()
            await self.insert(name, dict(id='ref-' + f['a'], user_id='default-user', **{field: f['a']}))
            before = await self.snapshot()
            r = await self.request('DELETE', '/accounts/' + f['a'])
            self.assertEqual(r.status_code, 409, (name, r.text))
            self.assertEqual(await self.snapshot(), before)

    async def test_category_dependency_matrix(self):
        for name, field in [('bills','category_id'), ('recurring_payments','category_id'),
                            ('recurring_payment_records','category_id'), ('categories','parent_id')]:
            f = await self.fixture()
            await self.insert(name, dict(id='ref-' + f['category'], user_id='default-user', **{field: f['category']}))
            before = await self.snapshot()
            r = await self.request('DELETE', '/categories/' + f['category'])
            self.assertEqual(r.status_code, 409, (name, r.text))
            self.assertEqual(await self.snapshot(), before)

    async def test_debt_new_and_changed_references(self):
        f = await self.fixture()
        data = dict(name='Synthetic', direction='i_owe', original_amount=500, account_id=f['a'], category_id=f['category'])
        good = await self.request('POST', '/debts', data)
        self.assertEqual(good.status_code, 200, good.text)
        for route in ('/debts', '/debts/' + f['debt']):
            method = 'POST' if route == '/debts' else 'PUT'
            for field in ('account_id','category_id'):
                before = await self.snapshot()
                r = await self.request(method, route, dict(data, **{field:'missing'}))
                self.assertEqual(r.status_code, 422, r.text)
                self.assertEqual(await self.snapshot(), before)

    async def test_debt_legacy_omitted_and_explicit_null(self):
        f = await self.fixture()
        await self.change('debts', f['debt'], account_id='legacy-missing', category_id='legacy-category')
        data = dict(name='Edited', direction='i_owe', original_amount=500)
        r = await self.request('PUT', '/debts/' + f['debt'], data)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['account_id'], 'legacy-missing')
        self.assertEqual(r.json()['category_id'], 'legacy-category')
        r = await self.request('PUT', '/debts/' + f['debt'], dict(data, account_id=None, category_id=None))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()['account_id'])

    async def test_template_missing_references_and_source_protection(self):
        f = await self.fixture()
        data = dict(name='Synthetic', amount=10, type='expense')
        for field in ('account_id','to_account_id','category_id','source_transaction_id'):
            before = await self.snapshot()
            r = await self.request('POST', '/recurring', dict(data, **{field:'missing'}))
            self.assertEqual(r.status_code, 422, r.text)
            self.assertEqual(await self.snapshot(), before)
        tx = (await self.request('POST', '/transactions', dict(data, account_id=f['a']))).json()
        r = await self.request('POST', '/recurring', dict(data, source_transaction_id=tx['id'], account_id=f['a']))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.request('DELETE', '/transactions/' + tx['id'])).status_code, 409)

    async def test_bill_delete_preserves_expense_and_recurring_tracking(self):
        f = await self.fixture(linked=True)
        p = await self.billpay(f)
        r = await self.request('DELETE', '/bills/' + f['bill'])
        self.assertEqual(r.status_code, 200, r.text)
        tx = await self.doc('transactions', p['transaction_id'])
        self.assertFalse(tx.get('bill_payment_id'))
        self.assertEqual(tx['recurring_record_id'], p['recurring_record_id'])
        rec = await self.doc('recurring_payment_records', p['recurring_record_id'])
        self.assertFalse(rec.get('bill_payment_id'))
        self.assertTrue((await self.doc('bill_payments', p['id']))['deleted'])
        self.assertEqual(await self.balance(f), 930)
        r = await self.request('POST', '/bills/' + f['bill'] + '/payments', dict(amount=70,account_id=f['a']), 'bill-key')
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(await self.balance(f), 930)

    async def test_recurrence_delete_clears_both_bill_links(self):
        f = await self.fixture(linked=True)
        p = await self.billpay(f)
        r = await self.request('DELETE', '/recurring-payments/' + f['rp'])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone((await self.doc('bills', f['bill']))['recurring_payment_id'])
        self.assertIsNone((await self.doc('bill_payments', p['id']))['recurring_record_id'])
        tx = await self.doc('transactions', p['transaction_id'])
        self.assertFalse(tx.get('recurring_record_id'))
        self.assertEqual(tx['bill_payment_id'], p['id'])
        self.assertEqual(await self.balance(f), 930)

    async def test_recurring_record_delete_keeps_bill_payment(self):
        f = await self.fixture(linked=True)
        p = await self.billpay(f)
        r = await self.request('DELETE', '/recurring-payments/payments/' + p['recurring_record_id'])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone((await self.doc('bill_payments', p['id']))['recurring_record_id'])
        self.assertTrue(await self.doc('transactions', p['transaction_id']))
        self.assertEqual(await self.balance(f), 930)

    async def test_mismatched_bill_or_recurring_links_rejected(self):
        for kind in ('bill', 'recurring'):
            f = await self.fixture(recurring=True)
            p = await self.billpay(f) if kind == 'bill' else await self.recurpay(f)
            field = 'bill_payment_id' if kind == 'bill' else 'recurring_record_id'
            await self.change('transactions', p['transaction_id'], **{field:'wrong'})
            before = await self.snapshot()
            route = '/bills/payments/' if kind == 'bill' else '/recurring-payments/payments/'
            r = await self.request('DELETE', route + p['id'])
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.snapshot(), before)

    async def test_parent_delete_rejects_mismatched_link(self):
        for kind in ('bill', 'recurring'):
            f = await self.fixture(linked=True)
            p = await self.billpay(f)
            await self.change('transactions', p['transaction_id'], recurring_record_id='wrong')
            before = await self.snapshot()
            route = '/bills/' + f['bill'] if kind == 'bill' else '/recurring-payments/' + f['rp']
            r = await self.request('DELETE', route)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.snapshot(), before)

    async def test_annulled_receipts_never_recreated(self):
        for kind in ('bill', 'recurring'):
            f = await self.fixture(recurring=True)
            p = await self.billpay(f) if kind == 'bill' else await self.recurpay(f)
            route = '/bills/payments/' if kind == 'bill' else '/recurring-payments/payments/'
            self.assertEqual((await self.request('DELETE', route + p['id'])).status_code, 200)
            self.assertEqual(await self.balance(f), 1000)
            if kind == 'bill':
                r = await self.request('POST', '/bills/' + f['bill'] + '/payments',dict(amount=70,account_id=f['a']), 'bill-key')
            else:
                r = await self.request('POST', '/recurring-payments/' + f['rp'] + '/payments',dict(due_date='2026-10-20',mode='expense',amount=10,account_id=f['a'],transaction_id=None), 'recurring-key')
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.balance(f), 1000)
            self.assertFalse(await self.doc('transactions', p['transaction_id']))

    async def test_no_internal_fields_in_public_responses(self):
        f = await self.fixture(linked=True)
        p = await self.billpay(f)
        await self.request('POST','/recurring',dict(name='Synthetic',amount=1,type='expense',source_transaction_id=p['transaction_id']))
        for route in ('/accounts','/categories','/transactions','/debts','/bills','/bills/' + f['bill'], '/recurring-payments/' + f['rp']):
            r = await self.request('GET', route)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertNotIn('_reference_revision', r.text, route)
            self.assertNotIn('_payment_revision', r.text, route)

    async def test_legacy_bill_and_recurrence_refs_are_preserved(self):
        f = await self.fixture(recurring=True)
        await self.change('bills', f['bill'], account_id='legacy', category_id='legacy-cat', recurring_payment_id='legacy-rp')
        b = dict(name='Edited', amount=100, due_date='2026-10-20', frequency='once')
        r = await self.request('PUT','/bills/' + f['bill'], b)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['account_id'],'legacy')
        self.assertEqual(r.json()['recurring_payment_id'],'legacy-rp')
        await self.change('recurring_payments', f['rp'], account_id='legacy', category_id='legacy-cat')
        rp = dict(name='Edited',amount=100,start_date='2026-10-20',frequency='monthly')
        r = await self.request('PUT','/recurring-payments/' + f['rp'],rp)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['category_id'],'legacy-cat')
        for route,data in (('/bills/' + f['bill'],b),('/recurring-payments/' + f['rp'],rp)):
            r = await self.request('PUT',route,dict(data,account_id='new-missing'))
            self.assertEqual(r.status_code,422,r.text)


    async def test_goal_and_budget_valid_and_invalid_references(self):
        f = await self.fixture()
        for route, data, field in (
            ('/goals', dict(name='Synthetic goal', target_amount=500, account_id=f['a']), 'account_id'),
            ('/budgets', dict(name='Synthetic budget', amount_limit=100, period='monthly', category_id=f['category']), 'category_id'),
        ):
            before = await self.snapshot()
            r = await self.request('POST', route, dict(data, **{field:'missing'}))
            self.assertEqual(r.status_code,422,r.text)
            self.assertEqual(await self.snapshot(),before)
            good = await self.request('POST',route,data)
            self.assertEqual(good.status_code,200,good.text)
            r = await self.request('PUT',route+'/'+good.json()['id'],dict(data,**{field:'new-missing'}))
            self.assertEqual(r.status_code,422,r.text)
            parent = f['a'] if field=='account_id' else f['category']
            delete = '/accounts/' if field=='account_id' else '/categories/'
            self.assertEqual((await self.request('DELETE',delete+parent)).status_code,409)

    async def test_category_hierarchy_reference_validation(self):
        f = await self.fixture()
        data = dict(name='Synthetic child',type='expense',parent_id=f['category'])
        good = await self.request('POST','/categories',data)
        self.assertEqual(good.status_code,200,good.text)
        before = await self.snapshot()
        r = await self.request('PUT','/categories/'+good.json()['id'],dict(data,parent_id='missing'))
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(await self.snapshot(),before)
        r = await self.request('PUT','/categories/'+good.json()['id'],dict(name='Renamed',type='expense'))
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['parent_id'],f['category'])

    async def test_linked_source_prevents_annulment(self):
        for kind in ('bill','recurring'):
            f = await self.fixture(recurring=True)
            p = await self.billpay(f) if kind=='bill' else await self.recurpay(f)
            r = await self.request('POST','/recurring',dict(name='Synthetic',amount=10,type='expense',source_transaction_id=p['transaction_id']))
            self.assertEqual(r.status_code,200,r.text)
            before = await self.snapshot()
            route = '/bills/payments/' if kind=='bill' else '/recurring-payments/payments/'
            r = await self.request('DELETE',route+p['id'])
            self.assertEqual(r.status_code,409,r.text)
            self.assertEqual(await self.snapshot(),before)

    async def test_debt_tombstone_survives_parent_removal(self):
        f = await self.fixture()
        payload = dict(debt_id=f['debt'],amount=100,account_id=f['a'])
        r = await self.request('POST','/debt-payments',payload,'debt-receipt')
        self.assertEqual(r.status_code,200,r.text)
        p = r.json()
        self.assertEqual((await self.request('DELETE','/debt-payments/'+p['id'])).status_code,200)
        self.assertEqual((await self.request('DELETE','/debts/'+f['debt'])).status_code,200)
        self.assertEqual((await self.request('DELETE','/accounts/'+f['a'])).status_code,200)
        tombstone = await self.doc('debt_payments',p['id'])
        self.assertTrue(tombstone['deleted'])
        r = await self.request('POST','/debt-payments',payload,'debt-receipt')
        self.assertEqual(r.status_code,409,r.text)
        self.assertFalse(await self.doc('transactions',p['transaction_id']))

    async def test_debt_100_then_150_exact_intentions(self):
        f = await self.fixture()
        for amount,key in ((100,'first'),(150,'second')):
            data = dict(debt_id=f['debt'],amount=amount,account_id=f['a'])
            first = await self.request('POST','/debt-payments',data,key)
            retry = await self.request('POST','/debt-payments',data,key)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.json()['id'],retry.json()['id'])
        self.assertEqual(await self.balance(f),750)
        self.assertEqual((await self.doc('debts',f['debt']))['remaining_amount'],250)
        payments = await self.db.debt_payments.find({'debt_id':f['debt'],'deleted':{'$ne':True}}).to_list(None)
        self.assertEqual(len(payments),2)

    async def test_missing_reverse_pointers_rejected_without_loss(self):
        for side in ('payment','record'):
            f = await self.fixture(linked=True)
            p = await self.billpay(f)
            if side=='payment':
                await self.change('bill_payments',p['id'],recurring_record_id=None)
                route='/bills/payments/'+p['id']
            else:
                await self.change('recurring_payment_records',p['recurring_record_id'],bill_payment_id=None)
                route='/recurring-payments/payments/'+p['recurring_record_id']
            before=await self.snapshot()
            r=await self.request('DELETE',route)
            self.assertEqual(r.status_code,409,r.text)
            self.assertEqual(await self.snapshot(),before)

    async def test_next_period_cannot_copy_a_missing_legacy_reference(self):
        f=await self.fixture()
        await self.change('bills',f['bill'],frequency='monthly',account_id='legacy-missing')
        before=await self.snapshot()
        r=await self.request('POST','/bills/'+f['bill']+'/payments',dict(amount=100,account_id=f['a']),'missing-default')
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_once_bill_payment_ignores_unused_missing_legacy_recurrence(self):
        f = await self.fixture()
        await self.change('bills', f['bill'], recurring_payment_id='legacy-missing')
        data = dict(amount=10, account_id=f['a'])
        first = await self.request('POST', '/bills/'+f['bill']+'/payments', data, 'unused-legacy')
        self.assertEqual(first.status_code, 200, first.text)
        again = await self.request('POST', '/bills/'+f['bill']+'/payments', data, 'unused-legacy')
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(first.json()['id'], again.json()['id'])
        self.assertEqual(await self.balance(f), 990)
        self.assertEqual((await self.doc('bills', f['bill']))['recurring_payment_id'], 'legacy-missing')
        tx = await self.doc('transactions', first.json()['transaction_id'])
        self.assertFalse(tx.get('recurring_payment_id'))
        self.assertIsNone(first.json()['recurring_record_id'])
        self.assertEqual(len(await self.db.bill_payments.find({'bill_id':f['bill']}).to_list(None)), 1)
        self.assertEqual(len(await self.db.transactions.find({'bill_id':f['bill']}).to_list(None)), 1)

    async def test_monthly_legacy_reference_allowed_only_until_new_period_would_copy_it(self):
        f = await self.fixture()
        await self.change('bills', f['bill'], frequency='monthly', recurring_payment_id='legacy-missing')
        partial = await self.request('POST', '/bills/'+f['bill']+'/payments', dict(amount=10, account_id=f['a']), 'partial-legacy')
        self.assertEqual(partial.status_code, 200, partial.text)
        self.assertIsNone(partial.json()['next_bill_id'])
        before = await self.snapshot()
        final = await self.request('POST', '/bills/'+f['bill']+'/payments', dict(amount=90, account_id=f['a']), 'copy-missing')
        self.assertEqual(final.status_code, 422, final.text)
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(await self.balance(f), 990)

    async def test_recurring_unlink_checks_bill_payment_amount_account_and_bill(self):
        for kind in ('record', 'recurrence'):
            for field in ('amount', 'account_id', 'bill_id'):
                with self.subTest(kind=kind, field=field):
                    f = await self.fixture(linked=True)
                    p = await self.billpay(f)
                    other = await self.fixture()
                    value = 80 if field=='amount' else f['b'] if field=='account_id' else other['bill']
                    await self.change('bill_payments', p['id'], **{field:value})
                    before = await self.snapshot()
                    route = '/recurring-payments/payments/'+p['recurring_record_id'] if kind=='record' else '/recurring-payments/'+f['rp']
                    r = await self.request('DELETE', route)
                    self.assertEqual(r.status_code, 409, r.text)
                    self.assertEqual(await self.snapshot(), before)
                    self.assertEqual(await self.balance(f), 930)

    async def test_equivalent_amount_representations_allow_verified_unlink(self):
        for kind in ('record', 'recurrence', 'bill-payment'):
            for paid, tracked in ((70, '70.00'), ('70.00', 70.0), (Decimal128('70.00'), Decimal128('70.0'))):
                with self.subTest(kind=kind, paid=repr(paid), tracked=repr(tracked)):
                    f = await self.fixture(linked=True)
                    p = await self.billpay(f)
                    await self.change('bill_payments', p['id'], amount=paid)
                    await self.change('recurring_payment_records', p['recurring_record_id'], amount=tracked)
                    route = '/recurring-payments/payments/'+p['recurring_record_id'] if kind=='record' else '/recurring-payments/'+f['rp'] if kind=='recurrence' else '/bills/payments/'+p['id']
                    r = await self.request('DELETE', route)
                    self.assertEqual(r.status_code, 200, r.text)
                    self.assertEqual(await self.balance(f), 1000 if kind=='bill-payment' else 930)

    async def test_amount_comparison_never_rounds_away_a_discrepancy(self):
        for amount in ('70.004', 'NaN', 'Infinity', 'invalid'):
            f = await self.fixture(linked=True)
            p = await self.billpay(f)
            await self.change('bill_payments', p['id'], amount=amount)
            before = await self.snapshot()
            r = await self.request('DELETE', '/recurring-payments/payments/'+p['recurring_record_id'])
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.snapshot(), before)

    async def unset(self, collection, id, fields):
        if isinstance(self.db, Database):
            doc = next(d for d in self.db.data[collection] if d['id']==id)
            for field in fields:
                doc.pop(field, None)
        else:
            await getattr(self.db, collection).update_one({'id':id}, {'$unset':{field:'' for field in fields}})

    async def test_literal_legacy_references_omitted_or_explicit_null(self):
        for entity in ('bill', 'recurring', 'goal'):
            for old in ('', None, 'legacy-missing', '__absent__'):
                with self.subTest(entity=entity, old=old):
                    f = await self.fixture(recurring=True)
                    if entity=='bill':
                        collection='bills';id=f['bill'];route='/bills/'+id
                        fields=('account_id','category_id','recurring_payment_id')
                        data=dict(name='Label edit',amount=100,frequency='once',due_date='2026-10-20')
                    elif entity=='recurring':
                        collection='recurring_payments';id=f['rp'];route='/recurring-payments/'+id
                        fields=('account_id','category_id')
                        data=dict(name='Label edit',amount=100,frequency='monthly',start_date='2026-10-20')
                    else:
                        created=await self.request('POST','/goals',dict(name='Synthetic goal '+f['a'],target_amount=500))
                        self.assertEqual(created.status_code,200,created.text)
                        collection='saving_goals';id=created.json()['id'];route='/goals/'+id
                        fields=('account_id',);data=dict(name='Label edit '+f['a'],target_amount=500)
                    if old=='__absent__':
                        await self.unset(collection,id,fields)
                    else:
                        await self.change(collection,id,**{field:old for field in fields})
                    r=await self.request('PUT',route,data)
                    self.assertEqual(r.status_code,200,r.text)
                    saved=await self.doc(collection,id)
                    for field in fields:
                        if old=='__absent__':
                            self.assertNotIn(field,saved)
                        else:
                            self.assertEqual(saved[field],old)
                    # Explicit null retains the existing permitted removal semantics.
                    r=await self.request('PUT',route,dict(data,**{field:None for field in fields}))
                    self.assertEqual(r.status_code,200,r.text)
                    saved=await self.doc(collection,id)
                    for field in fields:
                        self.assertIsNone(saved[field])

    async def test_explicit_unchanged_empty_reference_is_not_repaired(self):
        f=await self.fixture()
        await self.change('bills',f['bill'],account_id='',category_id='',recurring_payment_id='')
        data=dict(name='Label edit',amount=100,frequency='once',due_date='2026-10-20',account_id='',category_id='',recurring_payment_id='')
        r=await self.request('PUT','/bills/'+f['bill'],data)
        self.assertEqual(r.status_code,200,r.text)
        for field in ('account_id','category_id','recurring_payment_id'):
            self.assertEqual((await self.doc('bills',f['bill']))[field],'')

    async def test_empty_legacy_optional_references_allow_recurring_record_lifecycle(self):
        for mode in ('expense', 'link'):
            with self.subTest(mode=mode):
                f = await self.fixture(recurring=True)
                await self.change('recurring_payments', f['rp'], category_id='')
                data = dict(due_date='2026-10-20', mode=mode, amount=10)
                if mode=='expense':
                    data['account_id']=f['a']
                else:
                    created = await self.request('POST','/transactions',dict(name='Legacy unassigned',type='expense',amount=10))
                    self.assertEqual(created.status_code,200,created.text)
                    data['transaction_id']=created.json()['id']
                    await self.change('transactions',data['transaction_id'],account_id='',category_id='')
                created = await self.request('POST','/recurring-payments/'+f['rp']+'/payments',data,'empty-optional')
                self.assertEqual(created.status_code,200,created.text)
                p=created.json()
                tx=await self.doc('transactions',p['transaction_id'])
                self.assertEqual(tx['category_id'],'')
                self.assertIsNone(p['category_id'])
                removed=await self.request('DELETE','/recurring-payments/payments/'+p['id'])
                self.assertEqual(removed.status_code,200,removed.text)
                self.assertEqual(await self.balance(f),1000)
                if mode=='link':
                    tx=await self.doc('transactions',p['transaction_id'])
                    self.assertEqual(tx['account_id'],'')
                    self.assertEqual(tx['category_id'],'')
                self.assertEqual((await self.doc('recurring_payments',f['rp']))['category_id'],'')


    async def inverse_fixture(self, kind):
        f = await self.fixture(recurring=True)
        if kind == 'bill':
            p = await self.billpay(f)
            return f, p, 'bill_payments', 'bill_payment_id'
        if kind == 'recurring':
            p = await self.recurpay(f)
            return f, p, 'recurring_payment_records', 'recurring_record_id'
        if kind == 'debt':
            r = await self.request('POST', '/debt-payments', dict(debt_id=f['debt'], amount=100, account_id=f['a']), 'debt-'+f['debt'])
            self.assertEqual(r.status_code, 200, r.text)
            return f, r.json(), 'debt_payments', 'debt_payment_id'
        g = await self.request('POST', '/goals', dict(name='Synthetic '+f['a'], target_amount=500, account_id=f['b']))
        self.assertEqual(g.status_code, 200, g.text)
        r = await self.request('POST', '/goals/'+g.json()['id']+'/contributions',
                               dict(kind='deposit', amount=50, real_movement=True, account_id=f['a']), 'goal')
        self.assertEqual(r.status_code, 200, r.text)
        return f, r.json()['contribution'], 'goal_contributions', 'goal_contribution_id'

    async def inverse_rejected(self, kind, method):
        f, p, collection, flag = await self.inverse_fixture(kind)
        await self.unset('transactions', p['transaction_id'], (flag,))
        tx = await self.doc('transactions', p['transaction_id'])
        before = await self.snapshot()
        data = dict(name='Edited', type=tx['type'], amount=20) if method=='PUT' else None
        r = await self.request(method, '/transactions/'+tx['id'], data)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(await self.snapshot(), before)

    async def test_bill_inverse_missing_put(self):
        await self.inverse_rejected('bill', 'PUT')

    async def test_bill_inverse_missing_delete(self):
        await self.inverse_rejected('bill', 'DELETE')

    async def test_recurring_inverse_missing_put(self):
        await self.inverse_rejected('recurring', 'PUT')

    async def test_recurring_inverse_missing_delete(self):
        await self.inverse_rejected('recurring', 'DELETE')

    async def test_goal_inverse_missing_put(self):
        await self.inverse_rejected('goal', 'PUT')

    async def test_goal_inverse_missing_delete(self):
        await self.inverse_rejected('goal', 'DELETE')

    async def goal_mismatch_rejected(self, field):
        f, p, _, _ = await self.inverse_fixture('goal')
        await self.change('goal_contributions', p['id'], **{field: f['b'] if field=='account_id' else 'withdrawal'})
        before = await self.snapshot()
        r = await self.request('DELETE', '/goals/'+p['goal_id'])
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(await self.snapshot(), before)

    async def test_goal_deposit_wrong_source_rejected(self):
        await self.goal_mismatch_rejected('account_id')

    async def test_goal_withdrawal_wrong_direction_rejected(self):
        await self.goal_mismatch_rejected('kind')

    async def test_inactive_inverse_receipts_do_not_block_ordinary_writes(self):
        f = await self.fixture()
        created = await self.request('POST', '/transactions', dict(name='Ordinary', type='expense', amount=10, account_id=f['a']))
        self.assertEqual(created.status_code, 200, created.text)
        tid = created.json()['id']
        for collection in ('bill_payments', 'recurring_payment_records', 'goal_contributions', 'debt_payments'):
            await self.insert(collection, dict(id=collection+'-history', user_id='default-user', transaction_id=tid, deleted=True))
        history = {c: await self.doc(c, c+'-history') for c in ('bill_payments', 'recurring_payment_records', 'goal_contributions', 'debt_payments')}
        edited = await self.request('PUT', '/transactions/'+tid, dict(name='Ordinary edit', type='expense', amount=20))
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertNotIn('_reference_revision', edited.text)
        self.assertEqual(await self.balance(f), 980)
        deleted = await self.request('DELETE', '/transactions/'+tid)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(await self.balance(f), 1000)
        for collection, doc in history.items():
            self.assertEqual(await self.doc(collection, doc['id']), doc)

    async def test_debt_inverse_without_forward_fields_is_not_ordinary(self):
        for method in ('PUT', 'DELETE'):
            f, p, _, flag = await self.inverse_fixture('debt')
            await self.unset('transactions', p['transaction_id'], (flag, 'debt_id'))
            await self.change('transactions', p['transaction_id'], type='expense')
            before = await self.snapshot()
            data = dict(name='Edited', type='expense', amount=20) if method=='PUT' else None
            r = await self.request(method, '/transactions/'+p['transaction_id'], data)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.snapshot(), before)

    async def test_goal_historical_direction_survives_goal_account_change(self):
        f, deposit, _, _ = await self.inverse_fixture('goal')
        gid = deposit['goal_id']
        withdrawal_data = dict(kind='withdrawal', amount=10, real_movement=True, account_id=f['a'])
        r = await self.request('POST', '/goals/'+gid+'/contributions', withdrawal_data, 'withdrawal')
        self.assertEqual(r.status_code, 200, r.text)
        withdrawal = r.json()['contribution']
        await self.change('goal_contributions', deposit['id'], amount=Decimal128('50.00'))
        edited = await self.request('PUT', '/goals/'+gid, dict(name='Edited '+f['a'], target_amount=500, account_id=f['a']))
        self.assertEqual(edited.status_code, 200, edited.text)
        balances = [(await self.doc('accounts', aid))['current_balance'] for aid in (f['a'], f['b'])]
        self.assertEqual(balances, [960, 1040])
        r = await self.request('DELETE', '/goals/'+gid)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([(await self.doc('accounts', aid))['current_balance'] for aid in (f['a'], f['b'])], balances)
        for p in (deposit, withdrawal):
            self.assertTrue((await self.doc('goal_contributions', p['id']))['deleted'])
            tx = await self.doc('transactions', p['transaction_id'])
            self.assertTrue(tx)
            self.assertFalse(tx.get('goal_id'))
            self.assertFalse(tx.get('goal_contribution_id'))
        retry = await self.request('POST', '/goals/'+gid+'/contributions', withdrawal_data, 'withdrawal')
        self.assertEqual(retry.status_code, 409, retry.text)

    async def test_goal_amount_identifiers_and_extra_inverse_movement_rejected(self):
        for field, value in (('amount', '50.004'), ('kind', 'unknown'), ('transaction_id', 'missing')):
            f, p, _, _ = await self.inverse_fixture('goal')
            await self.change('goal_contributions', p['id'], **{field:value})
            before = await self.snapshot()
            r = await self.request('DELETE', '/goals/'+p['goal_id'])
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.snapshot(), before)
        f, p, _, _ = await self.inverse_fixture('goal')
        # A second inverse link with the wrong goal used to evade the outer goal query.
        tx = await self.doc('transactions', p['transaction_id'])
        await self.insert('transactions', dict(tx, id='extra-'+p['id'], goal_id='other-goal'))
        before = await self.snapshot()
        r = await self.request('DELETE', '/goals/'+p['goal_id'])
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(await self.snapshot(), before)


class ReferenceIntegrityTests(ReferenceCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database()
        self.collections = tuple(self.db.data)
        self.ctx = context(self.db, memory.Client(self.db))

    async def insert(self, collection, doc):
        self.db.data[collection].append(dict(doc, _id=doc['id']))
