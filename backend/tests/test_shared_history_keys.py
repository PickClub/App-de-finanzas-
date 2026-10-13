"""C3 shared kernel metadata; in-memory prerequisites only, no live activation."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from backend import shared_obligations as shared
from backend.history_keys import inspect_history_keys
from backend.tests import test_shared_payments as core
from backend.tests import test_shared_dispatch as dispatch
from backend.tests.test_shared_obligations import ENVIRONMENT, USER, activation_settings


class SharedHistoryTests(unittest.IsolatedAsyncioTestCase):
    snapshot=core.PaymentCases.snapshot
    transact=core.PaymentCases.transact
    intent=core.PaymentCases.intent
    change=core.PaymentCases.change

    async def asyncSetUp(self):
        await core.SharedPaymentTests.asyncSetUp(self)
        self.history_settings=SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)

    async def pay(self,key,amount=30,origin='bill',account='account',**changes):
        return await self.transact(lambda session:shared.register_shared_payment(self.db,self.ob['_id'],
            **self.intent(key,amount,origin,account,**changes),expected_environment_id=ENVIRONMENT,effective_user=USER,session=session,
            recompute_account_balance=self.ctx.ns['recompute_account_balance'],history_settings=self.history_settings))

    async def tx(self,p):return await self.db.transactions.find_one({'id':p.transaction_id})

    async def test_insert_final_keys_only_movement_both_origins(self):
        for origin,key in (('bill','one'),('recurring','two')):
            p=await self.pay(key,origin=origin)
            t=await self.tx(p)
            self.assertEqual(inspect_history_keys(t,1),'ready')
            self.assertEqual((t['amount'],t['account_id'],t['bill_id'],t['recurring_payment_id']),(30,'account','bill','rp'))
            for collection,id in (('bill_payments',p.bill_payment['id']),('recurring_payment_records',p.recurring_record['id'])):
                self.assertNotIn('_history_keys',await getattr(self.db,collection).find_one({'id':id}))
            public=shared.public_financial_document({'nested':t,'payment':p.bill_payment,'recurring':p.recurring_record})
            self.assertNotIn('_history',str(public))
        self.assertEqual((await self.snapshot())['accounts'][0]['current_balance'],940)

    async def test_disabled_and_unsupplied_controls_no_keys(self):
        self.history_settings=SimpleNamespace(history_keys_write_enabled=False)
        def forbidden(*a):self.fail('disabled generator')
        with patch.object(shared,'with_history_keys',forbidden):
            p=await self.pay('off')
            q=await core.PaymentCases.pay(self,'no-settings',30)
        self.assertNotIn('_history_keys',await self.tx(p))
        self.assertNotIn('_history_keys',await self.tx(q))

    async def test_same_intention_and_payload_conflict(self):
        p=await self.pay('one',date=None)
        before=await self.snapshot()
        q=await self.pay('one',date=None)
        self.assertFalse(q.created)
        self.assertEqual(q.transaction_id,p.transaction_id)
        with self.assertRaises(HTTPException) as e:await self.pay('one',31)
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_equal_independent_partial_payments(self):
        a,b=await asyncio.gather(self.pay('one'),self.pay('two',origin='recurring',account='second'))
        self.assertNotEqual(a.transaction_id,b.transaction_id)
        for p in (a,b):self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')
        self.assertEqual([a['current_balance'] for a in (await self.snapshot())['accounts']],[970,970])

    async def test_concurrent_same_id_and_overpay(self):
        a,b=await asyncio.gather(self.pay('same'),self.pay('same'))
        self.assertEqual(a.transaction_id,b.transaction_id)
        self.assertEqual(len((await self.snapshot())['transactions']),1)
        before=await self.snapshot()
        with self.assertRaises(HTTPException):await self.pay('over',80,origin='recurring',account='second')
        self.assertEqual(await self.snapshot(),before)

    async def test_annul_deletes_keys_refunds_once_preserves_receipts(self):
        p=await self.pay('one')
        capsule=p.bill_payment['_shared_intent']
        await self.change('one','bill','annul');await self.change('one','bill','annul')
        self.assertIsNone(await self.tx(p))
        state=await self.snapshot()
        self.assertEqual(state['accounts'][0]['current_balance'],1000)
        for name in ('bill_payments','recurring_payment_records'):
            rec=state[name][0]
            self.assertEqual(rec['_shared_financial_state'],'annulled')
            self.assertEqual(rec['_shared_intent'],capsule)
            self.assertNotIn('_history_keys',rec)
        before=await self.snapshot()
        with self.assertRaises(HTTPException):await self.pay('one')
        self.assertEqual(await self.snapshot(),before)

    async def tracking(self,key,mode,transaction_id=None):
        payload=self.ctx.ns['RecurringPayRecordCreate'](mode=mode,amount=None if mode=='link' else 10,account_id='account',due_date=self.ob['original_due_date'],transaction_id=transaction_id,settles=True).model_dump()
        async def operation(session):
            scope=await shared._scope(self.db,ENVIRONMENT,USER,session)
            ob=await self.db.shared_obligations.find_one({'_id':self.ob['_id']},session=session)
            return await shared.register_shared_tracking(self.db,ob,scope,receipt_id='admin-'+key,payload=payload,effective_date='2026-10-01T00:00:00+00:00',session=session)
        return await self.transact(operation)

    async def test_retire_restore_preserves_keys_sources_and_money(self):
        p=await self.pay('one')
        t=await self.tx(p)
        await self.change('one','bill','retire_recurring')
        detached=await self.tx(p)
        self.assertEqual(detached['_history_keys'],t['_history_keys'])
        self.assertEqual(inspect_history_keys(detached,1),'ready')
        def forbidden(*a):self.fail('tracking generator')
        with patch.object(shared,'with_history_keys',forbidden):
            restored=await self.tracking('restore','link',p.transaction_id)
            before=await self.snapshot()
            self.assertEqual(await self.tracking('restore','link',p.transaction_id),restored)
            self.assertEqual(await self.snapshot(),before)
        self.assertEqual(await self.tx(p),t)
        self.assertEqual(len(before['transactions']),1)
        self.assertEqual(before['accounts'][0]['current_balance'],970)

    async def test_mark_no_money_or_history_then_expense(self):
        def forbidden(*a):self.fail('mark generator')
        with patch.object(shared,'with_history_keys',forbidden):await self.tracking('mark','mark')
        state=await self.snapshot()
        self.assertEqual(state['transactions'],[])
        self.assertEqual(state['accounts'][0]['current_balance'],1000)
        for rec in state['recurring_payment_records']:self.assertNotIn('_history_keys',rec)
        p=await self.pay('real')
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')

    async def test_rollback_after_all_writes(self):
        original=self.ctx.ns['recompute_account_balance']
        async def fail(*a,**kw):
            await original(*a,**kw)
            raise HTTPException(503,'Synthetic after writes')
        before=await self.snapshot()
        with patch.dict(self.ctx.ns,{'recompute_account_balance':fail}):
            with self.assertRaises(HTTPException):await self.pay('failure')
        self.assertEqual(await self.snapshot(),before)

    async def test_uncertain_commit_original_recovery(self):
        self.db.commit_then_error=True
        with self.assertRaises(HTTPException) as e:await self.pay('uncertain')
        self.assertEqual(e.exception.status_code,503)
        before=await self.snapshot()
        p=await self.pay('uncertain')
        self.assertFalse(p.created)
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')

    async def test_unverifiable_does_not_change_finance(self):
        with patch('backend.history_keys.parse_instant',side_effect=HTTPException(422,'Synthetic unverified derived date')):
            p=await self.pay('one')
            self.assertEqual(inspect_history_keys(await self.tx(p),1),'unverifiable')
        self.assertEqual((await self.snapshot())['accounts'][0]['current_balance'],970)

    async def test_public_adapter_passes_control_and_disabled_r4_blocks(self):
        settings=activation_settings('1')
        settings=SimpleNamespace(**{**vars(settings),'history_keys_write_enabled':True,'history_keys_generation':1})
        self.ctx.ns['settings']=settings
        payload=self.ctx.ns['BillPayIn'](amount=30,account_id='account',date='2026-10-01T00:00:00+00:00').model_dump()
        from unittest.mock import AsyncMock
        with patch.object(shared,'_hello',AsyncMock(return_value=dispatch.HELLO)):
            r=await self.ctx.request('POST','/bills/bill/payments',json=payload,headers={'Idempotency-Key':'public'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('_history',r.text)
        tx=await self.db.transactions.find_one({'id':r.json()['transaction_id']})
        self.assertEqual(inspect_history_keys(tx,1),'ready')
        self.ctx.ns['settings']=activation_settings('0')
        before=await self.snapshot()
        r=await self.ctx.request('POST','/bills/bill/payments',json=payload,headers={'Idempotency-Key':'other'})
        self.assertEqual(r.status_code,409,r.text)
        self.assertEqual(await self.snapshot(),before)
