"""Isolated bill regressions. No server import, dotenv, seed or live database."""
import ast
import calendar
import copy
import hashlib
import json
import math
import uuid
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from pymongo import ReadPreference, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from backend.tests import test_payment_consistency as memory


def bill_context(db, client):
    tree = ast.parse(Path(__file__).resolve().parents[1].joinpath('server.py').read_text())
    names = {'now_iso', 'new_id', 'Transaction', 'BillIn', 'BillPayIn', '_positive_money',
             '_parse_dt', '_local_tz', '_rp_day', '_rp_today', '_rp_dates', '_rp_paused',
             '_rp_occurrences', '_rp_state', '_rp_records', '_bill_rp_due', '_bill_add_period',
             '_bill_validate', '_bill_for_write', '_bill_paid_map', '_bill_public', '_bill_lookups',
             'create_bill', 'update_bill', 'get_bill', 'list_bills', 'bills_summary', 'pay_bill',
             'recompute_account_balance', 'payment_transaction', '_cal_str_window', '_cal_dt'}
    constants = {'CENT', 'BILL_REMINDERS', 'RP_FREQS'}
    nodes = [n for n in tree.body if
             isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
    assert {n.name for n in nodes if hasattr(n, 'name')} == names
    router = APIRouter(prefix='/api')
    ns = dict(globals(), api=router, db=db, client=client, DEFAULT_USER_ID='default-user', PROJ={'_id': 0})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<isolated bill code>', 'exec'), ns)
    app = FastAPI()
    app.include_router(router)
    return ns, app


def project(doc, projection):
    doc = copy.deepcopy(doc)
    if not projection:
        return doc
    if any(projection.values()):
        return {k: v for k, v in doc.items() if projection.get(k)}
    return {k: v for k, v in doc.items() if k not in projection}


def matches(doc, query):
    for k, wanted in query.items():
        actual = doc.get(k)
        if isinstance(wanted, dict):
            for op, value in wanted.items():
                if op == '$in' and actual not in value or op == '$gte' and actual < value or op == '$lte' and actual > value:
                    return False
        elif actual != wanted:
            return False
    return True


class Collection(memory.Collection):
    async def find_one(self, query, projection=None, *, session=None):
        doc = next((d for d in self.docs(session) if matches(d, query)), None)
        return project(doc, projection) if doc is not None else None

    def find(self, query, projection=None, *, session=None):
        return memory.Cursor([project(d, projection) for d in self.docs(session) if matches(d, query)])

    async def find_one_and_update(self, query, update, *, projection=None, return_document=None, session=None):
        assert return_document == ReturnDocument.AFTER
        self.before_write(session)
        for doc in self.docs(session):
            if matches(doc, query):
                for k, increment in update['$inc'].items():
                    doc[k] = doc.get(k, 0) + increment
                return project(doc, projection)
        return None


class Database(memory.Database):
    def __init__(self):
        super().__init__()
        self.data.update({n: [] for n in ('bills', 'bill_payments', 'recurring_payments', 'recurring_payment_records')})

    def __getattr__(self, name):
        return Collection(self, name)


def synthetic_bill(bid='bill', frequency='monthly', amount=100):
    return dict(_id=bid, id=bid, user_id='default-user', name='Synthetic bill', amount=amount,
                frequency=frequency, due_date='2026-10-20', anchor_day=20, next_bill_id=None,
                series_id=bid, category_id=None, account_id=None, recurring_payment_id=None)


class BillValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.db.data['bills'] = [synthetic_bill()]
        self.db.data['accounts'] = [dict(_id=k, id=k, user_id='default-user', name=k,
                                         initial_balance=1000, current_balance=1000) for k in ('a', 'b')]
        self.client = memory.Client(self.db)
        self.ns, self.app = bill_context(self.db, self.client)

    async def request(self, method, path, data=None, key=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://synthetic.invalid') as c:
            return await c.request(method, '/api' + path, **({'json': data} if data is not None else {}),
                                   headers={'Idempotency-Key': key} if key else {})

    async def pay(self, amount=70, key='original', account='a'):
        return await self.request('POST', '/bills/bill/payments',
                                  dict(amount=amount, account_id=account, date=None, notes=None), key)

    async def test_partial_exact_and_oversized_payments(self):
        self.assertEqual((await self.pay()).status_code, 200)
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.pay(key='too-large')).status_code, 422)
        self.assertEqual(self.db.data, before)
        self.assertEqual((await self.pay(30, 'legitimate', 'b')).status_code, 200)
        self.assertEqual(len(self.db.data['bill_payments']), 2)
        self.assertEqual(sum(p['amount'] for p in self.db.data['bill_payments']), 100)
        self.assertEqual([a['current_balance'] for a in self.db.data['accounts']], [930, 970])
        self.assertEqual(len(self.db.data['bills']), 2)

    async def test_same_key_does_not_increment_revision_or_create_again(self):
        first = await self.pay()
        before = copy.deepcopy(self.db.data)
        second = await self.pay()
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(self.db.data, before)
        self.assertEqual((await self.pay(30)).status_code, 409)
        self.assertEqual(self.db.data, before)

    async def test_amount_edit_below_paid_rejected_and_rolled_back(self):
        await self.pay()
        before = copy.deepcopy(self.db.data)
        response = await self.request('PUT', '/bills/bill', dict(name='Synthetic bill', amount=50, due_date='2026-10-20'))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.db.data, before)

    async def test_internal_revision_never_public(self):
        await self.pay()
        self.assertEqual(self.db.data['bills'][0]['_payment_revision'], 1)
        responses = [await self.request('GET', '/bills/bill'), await self.request('GET', '/bills'),
                     await self.request('GET', '/bills/summary'),
                     await self.request('PUT', '/bills/bill', dict(name='Synthetic bill', amount=100, due_date='2026-10-20'))]
        # Simulate create_bill's deterministic existing-record response after payments.
        self.db.data['bills'][0]['_id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'default-user:bill:create-key'))
        responses.append(await self.request('POST', '/bills', dict(name='Synthetic bill', amount=100, due_date='2026-10-20'), 'create-key'))
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn('_payment_revision', response.text)

    async def test_rollback_at_each_write_including_coordination_and_next_period(self):
        before = copy.deepcopy(self.db.data)
        # Guard, movement, account, payment, next bill, original bill link.
        for step in range(1, 7):
            with self.subTest(step=step):
                self.db.writes = 0
                self.db.fail_at = step
                self.assertEqual((await self.pay(100)).status_code, 503)
                self.assertEqual(self.db.data, before)

    async def test_transaction_unavailable_never_falls_back(self):
        self.client.supported = False
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.pay()).status_code, 503)
        self.assertEqual(self.db.data, before)

    async def test_uncertain_commit_recovers_original_key(self):
        self.db.commit_then_error = True
        self.assertEqual((await self.pay()).status_code, 503)
        self.assertEqual(len(self.db.data['bill_payments']), 1)
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.pay()).status_code, 200)
        self.assertEqual(self.db.data, before)

    async def test_missing_bill_does_not_write_or_create_metadata(self):
        self.db.data['bills'] = []
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.pay()).status_code, 404)
        self.assertEqual(self.db.data, before)


if __name__ == '__main__':
    unittest.main()
