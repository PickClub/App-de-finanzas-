"""Additive context and provisioning tests; memory doubles only, no server import."""
import ast
import copy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from pymongo.errors import OperationFailure
from backend.financial_context import validate_metadata
from backend.provision_financial_context import provision
from backend.config import settings_from_mapping
from backend.tests import test_payment_consistency as harness

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'

def document(environment=A):
    return dict(_id='financial-context', version=1, environment_id=environment, created_at='2026-01-01T00:00:00+00:00')

class FinancialContextTests(unittest.IsolatedAsyncioTestCase):
    request = harness.PaymentTests.request
    balance = harness.PaymentTests.balance
    def setUp(self):
        harness.PaymentTests.setUp(self)
        self.ns['settings'] = SimpleNamespace(expected_financial_environment_id=A)
        self.db.data['moneyflow_metadata'] = [document()]
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath('server.py').read_text())
        route = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'financial_context')
        exec(compile(ast.Module(body=[route], type_ignores=[]), '<context only>', 'exec'), self.ns)
        # The payment harness already includes its router; add the new route once.
        self.app.include_router(self.ns['api'])

    def headers(self, environment=A, user='default-user'):
        return {'MoneyFlow-Environment-ID': environment, 'MoneyFlow-User-ID': user, 'Idempotency-Key':'intent'}

    async def payment(self, headers=None):
        return await self.request('POST','/debt-payments',json=dict(debt_id='d',amount=100,account_id='a'),headers=headers or {})

    async def test_context_readonly_aliases_and_backend_restart(self):
        before = copy.deepcopy(self.db.data)
        first = await self.request('GET','/financial-context',headers={'Host':'one.invalid'})
        second = await self.request('GET','/financial-context',headers={'Host':'two.invalid'})
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json(),second.json())
        self.assertEqual(first.json()['user_id'],'default-user')
        self.assertEqual(first.json()['mode'],'single_user')
        self.assertTrue(first.json()['capabilities']['debt_payment_reconciliation'])
        self.assertEqual(self.db.data,before)
        self.assertEqual(self.db.writes,0)
        # A new app/route instance uses the same metadata rather than creating an ID.
        old = copy.deepcopy(self.db.data)
        self.setUp();self.db.data = old
        third = await self.request('GET','/financial-context')
        self.assertEqual(third.json(),first.json())

    async def test_independent_contexts_and_configured_pin(self):
        self.ns['settings'].expected_financial_environment_id = B
        self.db.data['moneyflow_metadata'] = [document(B)]
        self.assertEqual((await self.request('GET','/financial-context')).json()['environment_id'],B)
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.payment(self.headers())).status_code,409)
        self.assertEqual(self.db.data,before)

    async def test_correct_headers_and_same_key_retry(self):
        first = await self.payment(self.headers())
        second = await self.payment(self.headers())
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['id'],second.json()['id'])
        self.assertEqual(len(self.db.data['debt_payments']),1)
        self.assertEqual(self.balance(),900)

    async def test_single_wrong_or_changed_user_headers_do_not_write(self):
        for headers,code in [({'MoneyFlow-Environment-ID':A},422),({'MoneyFlow-User-ID':'default-user'},422),
                             (self.headers(B),409),(self.headers(user='other'),409)]:
            before = copy.deepcopy(self.db.data)
            self.assertEqual((await self.payment(headers)).status_code,code)
            self.assertEqual(self.db.data,before)
            self.assertEqual(self.db.writes,0)
        self.ns['DEFAULT_USER_ID'] = 'changed-effective-user'
        self.assertEqual((await self.payment(self.headers())).status_code,409)
        self.assertEqual(self.db.writes,0)

    async def test_missing_invalid_or_unpinned_context_does_not_write(self):
        for docs in ([],[dict(document(),version=2)],[dict(document(),version=True)],
                     [dict(document(),environment_id='bad')],[dict(document(),created_at='bad')],[document(B)]):
            self.db.data['moneyflow_metadata'] = docs
            before = copy.deepcopy(self.db.data)
            self.assertEqual((await self.request('GET','/financial-context')).status_code,503)
            self.assertEqual((await self.payment(self.headers())).status_code,503)
            self.assertEqual(self.db.data,before)
        self.ns['settings'].expected_financial_environment_id = None
        self.assertEqual((await self.payment(self.headers())).status_code,503)
        self.assertEqual(self.db.writes,0)

    async def test_network_failure_and_legacy_compatibility(self):
        from backend.tests.test_payment_consistency import Collection
        original = Collection.find_one
        async def fail_metadata(collection,*args,**kwargs):
            if collection.name == 'moneyflow_metadata': raise OperationFailure('Synthetic network failure')
            return await original(collection,*args,**kwargs)
        with patch.object(Collection,'find_one',fail_metadata):
            self.assertEqual((await self.payment(self.headers())).status_code,503)
            self.assertEqual(self.db.writes,0)
            self.assertEqual((await self.payment()).status_code,200)
        self.db.data['moneyflow_metadata'] = []
        self.ns['settings'].expected_financial_environment_id = 'invalid optional pin'
        self.assertEqual((await self.payment()).status_code,200)

class ProvisionTests(unittest.TestCase):
    def setUp(self):
        class Collection:
            doc = None
            def with_options(inner, **kwargs):return inner
            def find_one(inner,query):return copy.deepcopy(inner.doc)
            def insert_one(inner,doc):
                if inner.doc is not None:raise ValueError('duplicate')
                inner.doc = copy.deepcopy(doc)
        self.collection = Collection()
        self.db = SimpleNamespace(moneyflow_metadata=self.collection)

    def test_explicit_creation_verification_and_no_replacement(self):
        self.assertEqual(provision(self.db,mode='create',new_id=lambda:A),A)
        before = copy.deepcopy(self.collection.doc)
        self.assertEqual(provision(self.db,mode='verify',expected_id=A),A)
        with self.assertRaises(ValueError):provision(self.db,mode='create',new_id=lambda:B)
        with self.assertRaises(HTTPException):provision(self.db,mode='verify',expected_id=B)
        self.assertEqual(self.collection.doc,before)

    def test_verify_does_not_create_and_optional_config_does_not_break_legacy(self):
        with self.assertRaises(HTTPException):provision(self.db,mode='verify',expected_id=A)
        self.assertIsNone(self.collection.doc)
        values=dict(APP_ENV='development',MONGO_URL='mongodb://localhost:27017',DB_NAME='example',MONEYFLOW_EXPECTED_ENVIRONMENT_ID='bad')
        self.assertEqual(settings_from_mapping(values).expected_financial_environment_id,'bad')
