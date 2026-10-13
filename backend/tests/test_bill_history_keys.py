"""Actual bill callbacks in isolated memory, without server startup."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pymongo.errors import OperationFailure
from backend.history_keys import inspect_history_keys
from backend.tests import test_bill_validation as bills
from backend.tests import test_payment_consistency as memory


class BillKeyCases:
    async def request(self, method, path, payload=None, key=None):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False), base_url='http://synthetic.invalid') as c:
            r = await c.request(method, '/api'+path, **({'json': payload} if payload is not None else {}), headers={'Idempotency-Key': key} if key else {})
        self.assertNotIn('_history', r.text)
        return r

    async def pay(self, amount=30, key='original', account='a', when='2026-10-01T12:00:00.123456+01:02:03', status=200):
        r = await self.request('POST', '/bills/bill/payments', dict(amount=amount, account_id=account, date=when, notes='Synthetic'), key)
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    async def snapshot(self):
        return {n: await getattr(self.db,n).find({}).sort('id',1).to_list(None) for n in ('bills','bill_payments','transactions','accounts','categories','recurring_payment_records','recurring_payments','recurring_templates')}

    async def tx(self,p):
        return await self.db.transactions.find_one({'id':p['transaction_id']})

    async def balance(self,a='a'):
        return (await self.db.accounts.find_one({'id':a}))['current_balance']

    async def test_ready_and_receipt_without_keys(self):
        p=await self.pay()
        t=await self.tx(p)
        self.assertEqual(inspect_history_keys(t,1),'ready')
        self.assertEqual(t['amount'],30)
        self.assertEqual(t['bill_payment_id'],p['id'])
        self.assertEqual(await self.balance(),970)
        self.assertNotIn('_history_keys',await self.db.bill_payments.find_one({'id':p['id']}))

    async def test_retry_original_and_conflict(self):
        p=await self.pay(when=None)
        before=await self.snapshot()
        self.assertEqual((await self.pay(when=None))['id'],p['id'])
        await self.pay(31,when=None,status=409)
        self.assertEqual(before,await self.snapshot())

    async def test_equal_independent_and_same_intent(self):
        a,b=await asyncio.gather(self.pay(key='one'),self.pay(key='two',account='b'))
        self.assertNotEqual(a['transaction_id'],b['transaction_id'])
        self.assertEqual((await self.balance(),await self.balance('b')),(970,970))
        before=await self.snapshot()
        await asyncio.gather(self.pay(key='one'),self.pay(key='two',account='b'))
        self.assertEqual(before,await self.snapshot())
        for p in (a,b): self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')

    async def test_overpayment_concurrent(self):
        r=await asyncio.gather(self.pay(70,key='one'),self.pay(70,key='two',account='b',status=422))
        state=await self.snapshot()
        self.assertEqual(len(state['transactions']),1)
        self.assertEqual(sum(p['amount'] for p in state['bill_payments']),70)
        self.assertEqual(sum(a['current_balance'] for a in state['accounts']),1930)

    async def test_disabled_no_generator_or_keys(self):
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=False)
        with patch.dict(self.ns,{'with_history_keys':lambda *a: self.fail('disabled generator')}): p=await self.pay()
        self.assertNotIn('_history_keys',await self.tx(p))
        self.assertEqual(await self.balance(),970)

    async def test_unverifiable_accepted_legacy_parser_date(self):
        # Existing _parse_dt accepts ISO's arbitrary single separator; C3 rejects it.
        p=await self.pay(when='2026-10-01X12:00:00')
        # Server stores a normalized ISO instant, so the final document is ready.
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')
        # Final bill dates are normalized by the existing route. Inject a
        # derivation-only inability to verify, without changing stored sources.
        from fastapi import HTTPException
        with patch('backend.history_keys.parse_instant',side_effect=HTTPException(422,'Synthetic unverified source')):
            q=await self.pay(key='second')
            self.assertEqual(inspect_history_keys(await self.tx(q),1),'unverifiable')
        self.assertEqual((await self.tx(q))['_history_keys']['state'],'unverifiable')
        self.assertEqual(await self.balance(),940)

    async def test_rollback_after_movement_and_keys(self):
        original=self.ns['recompute_account_balance']
        async def fail(*a,**kw):
            await original(*a,**kw)
            raise OperationFailure('Synthetic after movement')
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_account_balance':fail}): await self.pay(status=503)
        self.assertEqual(before,await self.snapshot())

    async def test_monthly_next_period_receipts_not_instrumented(self):
        p=await self.pay(100)
        state=await self.snapshot()
        self.assertEqual(len(state['bills']),2)
        self.assertTrue(p['next_bill_id'])
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')
        for n in ('bills','bill_payments','recurring_payment_records'):
            for d in state[n]: self.assertNotIn('_history_keys',d)

    async def test_delete_refund_once_tombstone_and_late_retry(self):
        p=await self.pay()
        for _ in range(2):
            r=await self.request('DELETE','/bills/payments/'+p['id']);self.assertEqual(r.status_code,200,r.text)
        self.assertIsNone(await self.tx(p))
        self.assertEqual(await self.balance(),1000)
        receipt=await self.db.bill_payments.find_one({'id':p['id']})
        self.assertTrue(receipt['deleted'])
        self.assertNotIn('_history_keys',receipt)
        before=await self.snapshot()
        await self.pay(status=409)
        self.assertEqual(before,await self.snapshot())

    async def test_delete_rollback_and_template_protection(self):
        p=await self.pay()
        original=self.ns['recompute_account_balance']
        async def fail(*a,**kw):
            await original(*a,**kw);raise OperationFailure('Synthetic delete failure')
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_account_balance':fail}):
            r=await self.request('DELETE','/bills/payments/'+p['id']);self.assertEqual(r.status_code,503)
        self.assertEqual(before,await self.snapshot())
        await self.ns['payment_transaction'](lambda s:self.db.recurring_templates.insert_one({'id':'template','source_transaction_id':p['transaction_id']},session=s))
        before=await self.snapshot()
        r=await self.request('DELETE','/bills/payments/'+p['id']);self.assertEqual(r.status_code,409)
        self.assertEqual(before,await self.snapshot())

    async def test_linked_recurring_receipt_and_movement_unchanged(self):
        async def fixture(session):
            await self.db.recurring_payments.insert_one(dict(_id='rp',id='rp',user_id='default-user',name='Synthetic recurring',pauses=[],end_date=None,
                versions=[dict(valid_from='2026-10-01',start_date='2026-10-20',frequency='monthly',due_day=20,amount=100)]),session=session)
            await self.db.bills.update_one({'id':'bill'},{'$set':{'recurring_payment_id':'rp'}},session=session)
        await self.ns['payment_transaction'](fixture)
        p=await self.pay()
        t=await self.tx(p)
        record=await self.db.recurring_payment_records.find_one({'id':p['recurring_record_id']})
        self.assertEqual(record['transaction_id'],t['id'])
        self.assertEqual(t['recurring_record_id'],record['id'])
        self.assertEqual(record['bill_payment_id'],p['id'])
        self.assertNotIn('_history_keys',record)
        self.assertEqual(inspect_history_keys(t,1),'ready')
        self.assertEqual(await self.balance(),970)
        r=await self.request('DELETE','/bills/payments/'+p['id'])
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(await self.balance(),1000)
        self.assertTrue((await self.db.recurring_payment_records.find_one({'id':record['id']}))['deleted'])

    async def test_helper_failure_rolls_back_prior_coordination(self):
        before=await self.snapshot()
        def fail(*args): raise OperationFailure('Synthetic derivation failure')
        with patch.dict(self.ns,{'with_history_keys':fail}): await self.pay(status=503)
        self.assertEqual(before,await self.snapshot())


class BillKeyMemoryTests(BillKeyCases,unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bills.BillValidationTests.setUp(self)
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)

    async def test_commit_uncertain_original_recovery(self):
        self.db.commit_then_error=True
        await self.pay(status=503)
        before=await self.snapshot()
        p=await self.pay()
        self.assertEqual(before,await self.snapshot())
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')
        self.db.commit_then_error=True
        r=await self.request('DELETE','/bills/payments/'+p['id']);self.assertEqual(r.status_code,503)
        before=await self.snapshot()
        r=await self.request('DELETE','/bills/payments/'+p['id']);self.assertEqual(r.status_code,200)
        self.assertEqual(before,await self.snapshot())
