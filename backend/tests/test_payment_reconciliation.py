"""Read-only reconciliation against AST routes and synthetic memory data only."""
import ast
import asyncio
import copy
import re
from pathlib import Path
import unittest
from unittest.mock import patch
from pymongo.errors import OperationFailure
from backend.tests import test_financial_context as context_fixture
A, B = context_fixture.A, context_fixture.B
from backend.tests import test_payment_consistency as harness

class ReconciliationTests(unittest.IsolatedAsyncioTestCase):
    request = harness.PaymentTests.request
    balance = harness.PaymentTests.balance
    def setUp(self):
        context_fixture.FinancialContextTests.setUp(self)
        self.ns['re'] = re
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath('server.py').read_text())
        node = next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='reconcile_debt_payment')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<reconciliation only>','exec'),self.ns)
        self.app.include_router(self.ns['api'])

    def headers(self,key='original',environment=None,user='default-user'):
        return {'Idempotency-Key':key,**({'MoneyFlow-Environment-ID':environment,'MoneyFlow-User-ID':user} if environment else {})}

    def payload(self,**changes):
        payload = dict(debt_id='d',amount=100,account_id='a')
        payload.update(changes)
        return payload

    async def create(self, key='original', **changes):
        response = await self.request('POST','/debt-payments',json=self.payload(**changes),headers=self.headers(key))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    async def reconcile(self,payload=None,headers=None,code=200):
        before = copy.deepcopy(self.db.data)
        writes = self.db.writes
        response = await self.request('POST','/debt-payments/reconcile',json=payload or self.payload(),headers=headers or self.headers())
        self.assertEqual(response.status_code,code,response.text)
        self.assertEqual(self.db.data,before)
        self.assertEqual(self.db.writes,writes)
        return response.json()

    async def test_recorded_and_normalized_original_match(self):
        p = await self.create()
        result = await self.reconcile()
        self.assertEqual(result['status'],'matched')
        self.assertEqual(result['payment_id'],p['id'])
        self.assertEqual(result['changed_fields'],[])
        self.assertIsNone(result['current_submission_matches'])
        self.assertFalse(result['generated_date_history_verifiable'])
        self.assertEqual((await self.reconcile(dict(debt_id='d',amount=100.0,account_id='a',notes=None,date=None)))['status'],'matched')

    async def test_missing_does_not_authorize_new_key(self):
        result = await self.reconcile()
        self.assertEqual(result['status'],'not_found')
        self.assertTrue(result['retry_requires_original_key_and_payload'])

    async def test_different_fields_and_same_amount_are_not_guessed(self):
        await self.create()
        for field,value in [('amount',101),('account_id','b'),('debt_id','other'),('notes','changed'),('date','2026-01-01')]:
            data = self.payload();data[field]=value
            self.assertEqual((await self.reconcile(data))['status'],'discrepancy')
        self.assertEqual((await self.reconcile(headers=self.headers('different-key')))['status'],'not_found')

    async def test_annulled_tombstone(self):
        p = await self.create()
        self.assertEqual((await self.request('DELETE','/debt-payments/'+p['id'])).status_code,200)
        self.assertEqual((await self.reconcile())['status'],'cancelled')
        data=self.payload();data['amount']=101
        self.assertEqual((await self.reconcile(data))['status'],'discrepancy')
        self.assertEqual(self.balance(),1000)

    async def test_edited_payment_still_identifies_original_request(self):
        p = await self.create()
        response = await self.request('PUT','/transactions/'+p['transaction_id'],json=dict(name='Changed',type='debt_payment',amount=150,account_id='b',notes='Edited'))
        self.assertEqual(response.status_code,200,response.text)
        result = await self.reconcile()
        self.assertEqual(result['status'],'matched')
        self.assertEqual(set(result['changed_fields']),{'amount','account_id','notes'})
        self.assertFalse(result['current_submission_matches'])
        self.assertEqual(result['current_payment']['amount'],150)
        data = self.payload();data.update(amount=150,account_id='b',notes='Edited')
        self.assertEqual((await self.reconcile(data))['status'],'discrepancy')

    async def test_explicit_original_date_edit_is_reported(self):
        p = await self.create(date='2026-01-01')
        response = await self.request('PUT','/transactions/'+p['transaction_id'],json=dict(name='Changed',type='debt_payment',amount=100,date='2026-02-01'))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((await self.reconcile(self.payload(date='2026-01-01')))['changed_fields'],['date'])

    async def test_response_lost_after_commit_can_be_verified_without_discount(self):
        self.db.commit_then_error=True
        response=await self.request('POST','/debt-payments',json=self.payload(),headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertEqual((await self.reconcile())['status'],'matched')
        self.assertEqual(len(self.db.data['debt_payments']),1)
        self.assertEqual(self.balance(),900)

    async def test_context_and_partial_headers(self):
        await self.create()
        self.assertEqual((await self.reconcile(headers=self.headers(environment=A)))['status'],'matched')
        await self.reconcile(headers=self.headers(environment=B),code=409)
        await self.reconcile(headers=self.headers(environment=A,user='other'),code=409)
        await self.reconcile(headers={**self.headers(),'MoneyFlow-Environment-ID':A},code=422)
        self.db.data['moneyflow_metadata']=[]
        self.assertEqual((await self.reconcile(headers=self.headers(environment=A)))['status'],'unverifiable')
        self.assertEqual((await self.reconcile())['status'],'matched')

    async def test_connection_failure_never_becomes_not_found(self):
        await self.create()
        original=harness.Collection.find_one
        async def fail(collection,*args,**kwargs):
            if collection.name=='debt_payments':raise OperationFailure('Synthetic read failure')
            return await original(collection,*args,**kwargs)
        with patch.object(harness.Collection,'find_one',fail):
            self.assertEqual((await self.reconcile())['status'],'unverifiable')
        self.client.supported=False
        self.assertEqual((await self.reconcile())['status'],'unverifiable')

    async def test_legacy_missing_fingerprint_and_broken_links_unverifiable(self):
        await self.create()
        self.db.data['debt_payments'][0].pop('request_fingerprint')
        self.assertEqual((await self.reconcile())['status'],'unverifiable')
        self.setUp();await self.create();self.db.data['transactions']=[]
        self.assertEqual((await self.reconcile())['status'],'unverifiable')

    async def test_concurrent_creation_query_and_annulment_have_consistent_snapshots(self):
        create,lookup=await asyncio.gather(self.create(),self.request('POST','/debt-payments/reconcile',json=self.payload(),headers=self.headers()))
        self.assertIn(lookup.json()['status'],('matched','not_found'))
        self.assertEqual((await self.reconcile())['status'],'matched')
        delete,lookup=await asyncio.gather(self.request('DELETE','/debt-payments/'+create['id']),self.request('POST','/debt-payments/reconcile',json=self.payload(),headers=self.headers()))
        self.assertEqual(delete.status_code,200)
        self.assertIn(lookup.json()['status'],('matched','cancelled'))
        self.assertEqual((await self.reconcile())['status'],'cancelled')
        self.assertEqual(self.balance(),1000)

    async def test_incorrect_context_prevents_financial_reads(self):
        original = harness.Collection.find_one
        async def metadata_only(collection,*args,**kwargs):
            if collection.name != 'moneyflow_metadata':
                raise AssertionError('Financial lookup occurred before context rejection')
            return await original(collection,*args,**kwargs)
        with patch.object(harness.Collection,'find_one',metadata_only):
            await self.reconcile(headers=self.headers(environment=B),code=409)

    async def test_generated_date_changes_are_not_claimed_verifiable(self):
        p = await self.create()
        response = await self.request('PUT','/transactions/'+p['transaction_id'],json=dict(name='Date edited',type='debt_payment',amount=100,date='2026-03-01'))
        self.assertEqual(response.status_code,200,response.text)
        result = await self.reconcile()
        self.assertEqual(result['status'],'matched')
        self.assertIsNone(result['current_submission_matches'])
        self.assertFalse(result['generated_date_history_verifiable'])
        self.assertEqual(result['current_payment']['date'],'2026-03-01')

    async def test_missing_key_rejected(self):
        before=copy.deepcopy(self.db.data)
        response=await self.request('POST','/debt-payments/reconcile',json=self.payload())
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.db.data,before)
