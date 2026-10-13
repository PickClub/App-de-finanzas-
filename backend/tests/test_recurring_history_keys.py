"""Recurring expense history metadata; exact AST routes, no application startup."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from pymongo.errors import OperationFailure
from backend.history_keys import inspect_history_keys, with_history_keys
from backend.tests import test_reference_integrity as reference
from backend.tests import test_payment_consistency as memory


def setup_memory(test):
    test.db=reference.Database()
    test.db.data['accounts']=[dict(_id=a,id=a,user_id='default-user',name='Synthetic',initial_balance=1000,current_balance=1000) for a in ('a','b')]
    test.db.data['recurring_payments']=[dict(_id='rp',id='rp',user_id='default-user',name='Synthetic recurring',account_id=None,category_id=None,variable=False,pauses=[],end_date=None,state='active',
        versions=[dict(valid_from='2026-10-01',start_date='2026-10-20',frequency='monthly',due_day=20,amount=100)])]
    test.client=memory.Client(test.db)
    test.ctx=reference.context(test.db,test.client)
    test.ns,test.app=test.ctx.ns,test.ctx.app
    test.ns['settings']=SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)


class RecurringKeyCases:
    async def request(self,method,path,payload=None,key=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app,raise_app_exceptions=False),base_url='http://synthetic.invalid') as client:
            r=await client.request(method,'/api'+path,**({'json':payload} if payload is not None else {}),headers={'Idempotency-Key':key} if key else {})
        self.assertNotIn('_history',r.text)
        return r

    async def pay(self,key='original',amount=30,mode='expense',account='a',due='2026-10-20',when='2026-10-01T12:00:00.123456+01:02:03',status=200,**extra):
        r=await self.request('POST','/recurring-payments/rp/payments',dict(amount=amount,mode=mode,account_id=account,due_date=due,date=when,notes='Synthetic',**extra),key)
        self.assertEqual(r.status_code,status,r.text)
        return r.json()

    async def snapshot(self):
        return {n:await getattr(self.db,n).find({}).sort('id',1).to_list(None) for n in ('accounts','transactions','recurring_payment_records','recurring_payments','recurring_templates')}

    async def tx(self,p):return await self.db.transactions.find_one({'id':p['transaction_id']})

    async def balance(self,a='a'):return (await self.db.accounts.find_one({'id':a}))['current_balance']

    async def remove(self,p,status=200):
        r=await self.request('DELETE','/recurring-payments/payments/'+p['id'])
        self.assertEqual(r.status_code,status,r.text)
        return r.json()

    async def test_expense_final_sources_ready_balance_receipt(self):
        p=await self.pay()
        t=await self.tx(p)
        self.assertEqual(inspect_history_keys(t,1),'ready')
        self.assertEqual((t['type'],t['amount'],t['account_id']),('expense',30,'a'))
        self.assertEqual((t['recurring_payment_id'],t['recurring_record_id']),('rp',p['id']))
        self.assertEqual(await self.balance(),970)
        self.assertNotIn('_history_keys',await self.db.recurring_payment_records.find_one({'id':p['id']}))
        self.assertEqual(p['due_date'],'2026-10-20')

    async def test_disabled_never_calls_generator(self):
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=False)
        def forbidden(*args):self.fail('disabled generation')
        with patch.dict(self.ns,{'with_history_keys':forbidden}):p=await self.pay()
        self.assertNotIn('_history_keys',await self.tx(p))
        self.assertEqual(await self.balance(),970)

    async def test_mark_never_generates_money_or_keys(self):
        def forbidden(*args):self.fail('mark generation')
        with patch.dict(self.ns,{'with_history_keys':forbidden}):p=await self.pay(mode='mark')
        self.assertIsNone(p['transaction_id'])
        self.assertEqual((await self.snapshot())['transactions'],[])
        self.assertEqual(await self.balance(),1000)
        self.assertNotIn('_history_keys',await self.db.recurring_payment_records.find_one({'id':p['id']}))
        await self.remove(p)
        self.assertEqual(await self.balance(),1000)

    async def synthetic_expense(self,keys=True):
        t=dict(_id='existing',id='existing',user_id='default-user',type='expense',name='Synthetic existing',amount=30,date='2026-10-02T12:00:00.123456Z',account_id='a',category_id=None)
        if keys:t=with_history_keys(t,1)
        async def operation(session):
            await self.db.transactions.insert_one(t,session=session)
            await self.ns['recompute_account_balance']('a',session=session)
        await self.ns['payment_transaction'](operation)
        return await self.db.transactions.find_one({'id':'existing'})

    async def test_link_preserves_existing_keys_and_retire_preserves_money(self):
        t=await self.synthetic_expense()
        def forbidden(*args):self.fail('link generation')
        with patch.dict(self.ns,{'with_history_keys':forbidden}):p=await self.pay(mode='link',transaction_id='existing')
        linked=await self.tx(p)
        self.assertEqual(linked,{**t,'recurring_payment_id':'rp','recurring_record_id':p['id']})
        self.assertEqual(inspect_history_keys(linked,1),'ready')
        self.assertEqual(await self.balance(),970)
        await self.remove(p)
        self.assertEqual(await self.tx(p),t)
        self.assertEqual(await self.balance(),970)
        before=await self.snapshot()
        await self.remove(p)
        await self.pay(mode='link',transaction_id='existing',status=409)
        self.assertEqual(await self.snapshot(),before)

    async def test_link_does_not_backfill_historical_missing_keys(self):
        t=await self.synthetic_expense(keys=False)
        def forbidden(*args):self.fail('legacy link backfill')
        with patch.dict(self.ns,{'with_history_keys':forbidden}):p=await self.pay(mode='link',transaction_id='existing')
        self.assertNotIn('_history_keys',await self.tx(p))
        await self.remove(p)
        self.assertEqual(await self.tx(p),t)

    async def test_original_retry_null_date_and_payload_conflict(self):
        p=await self.pay(when=None)
        before=await self.snapshot()
        self.assertEqual(await self.pay(when=None),p)
        await self.pay(amount=31,when=None,status=409)
        self.assertEqual(await self.snapshot(),before)

    async def test_two_equal_legitimate_and_other_period(self):
        a,b=await asyncio.gather(self.pay(key='one'),self.pay(key='two',account='b'))
        self.assertNotEqual(a['transaction_id'],b['transaction_id'])
        c=await self.pay(key='november',due='2026-11-20')
        self.assertEqual(c['due_date'],'2026-11-20')
        self.assertEqual((await self.balance(),await self.balance('b')),(940,970))
        for p in (a,b,c):self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')

    async def test_same_key_concurrent_one_movement(self):
        a,b=await asyncio.gather(self.pay(),self.pay())
        self.assertEqual(a,b)
        self.assertEqual(len((await self.snapshot())['transactions']),1)
        self.assertEqual(await self.balance(),970)

    async def test_delete_refund_once_tombstone_late_retry(self):
        p=await self.pay()
        await self.remove(p);await self.remove(p)
        self.assertIsNone(await self.tx(p))
        self.assertEqual(await self.balance(),1000)
        receipt=await self.db.recurring_payment_records.find_one({'id':p['id']})
        self.assertTrue(receipt['deleted'])
        self.assertNotIn('_history_keys',receipt)
        before=await self.snapshot()
        await self.pay(status=409)
        self.assertEqual(await self.snapshot(),before)

    async def test_partial_write_rollback_create_and_delete(self):
        original=self.ns['recompute_account_balance']
        async def fail(*a,**kw):
            await original(*a,**kw);raise OperationFailure('Synthetic after balance')
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_account_balance':fail}):await self.pay(status=503)
        self.assertEqual(await self.snapshot(),before)
        p=await self.pay()
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_account_balance':fail}):await self.remove(p,status=503)
        self.assertEqual(await self.snapshot(),before)

    async def test_template_protection_preserved(self):
        p=await self.pay()
        await self.ns['payment_transaction'](lambda s:self.db.recurring_templates.insert_one(dict(id='template',source_transaction_id=p['transaction_id']),session=s))
        before=await self.snapshot()
        await self.remove(p,status=409)
        self.assertEqual(await self.snapshot(),before)

    async def test_ready_unverifiable_without_financial_change(self):
        with patch('backend.history_keys.parse_instant',side_effect=HTTPException(422,'Synthetic derived parse failure')):
            p=await self.pay()
            self.assertEqual(inspect_history_keys(await self.tx(p),1),'unverifiable')
        self.assertEqual(await self.balance(),970)
        self.assertEqual((await self.tx(p))['date'],'2026-10-01T12:00:00.123456+01:02:03')


class RecurringKeyMemoryTests(RecurringKeyCases,unittest.IsolatedAsyncioTestCase):
    def setUp(self):setup_memory(self)

    async def test_uncertain_commit_recovery_creation_and_refund(self):
        self.db.commit_then_error=True
        await self.pay(status=503)
        before=await self.snapshot()
        p=await self.pay()
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')
        self.db.commit_then_error=True
        await self.remove(p,status=503)
        before=await self.snapshot()
        await self.remove(p)
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(await self.balance(),1000)
