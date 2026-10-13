"""Goal history keys: actual route AST, synthetic memory, no startup."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from pymongo.errors import OperationFailure
from backend.history_keys import inspect_history_keys
from backend.tests import test_reference_integrity as reference
from backend.tests import test_payment_consistency as memory


def setup_memory(test):
    test.db = reference.Database()
    test.db.data['accounts'] = [dict(_id=a,id=a,user_id='default-user',name='Synthetic',initial_balance=1000,current_balance=1000) for a in ('source','goal-account','other')]
    test.db.data['saving_goals'] = [dict(_id='goal',id='goal',user_id='default-user',name='Synthetic goal',target_amount=500,initial_amount=0,current_amount=0,account_id='goal-account',priority='medium',target_date=None,created_at='2026-10-01')]
    test.client = memory.Client(test.db)
    test.ctx = reference.context(test.db,test.client)
    test.ns,test.app = test.ctx.ns,test.ctx.app
    test.ns['settings'] = SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)


class GoalKeyCases:
    async def request(self,method,path,payload=None,key=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app,raise_app_exceptions=False),base_url='http://synthetic.invalid') as client:
            r = await client.request(method,'/api'+path,**({'json':payload} if payload is not None else {}),headers={'Idempotency-Key':key} if key else {})
        self.assertNotIn('_history',r.text)
        return r

    async def contribute(self,key='original',amount=50,real=True,kind='deposit',account='source',when='2026-10-01T12:00:00.123456+01:02:03',status=200):
        r = await self.request('POST','/goals/goal/contributions',dict(amount=amount,kind=kind,real_movement=real,account_id=account,date=when,notes='Synthetic'),key)
        self.assertEqual(r.status_code,status,r.text)
        return r.json()

    async def snapshot(self):
        return {n:await getattr(self.db,n).find({}).sort('id',1).to_list(None) for n in ('accounts','transactions','saving_goals','goal_contributions')}

    async def transfer(self,result):
        return await self.db.transactions.find_one({'id':result['contribution']['transaction_id']})

    async def balances(self):
        return [(await self.db.accounts.find_one({'id':a}))['current_balance'] for a in ('source','goal-account','other')]

    async def test_real_deposit_sources_balance_and_receipt(self):
        p = await self.contribute()
        t = await self.transfer(p)
        self.assertEqual(inspect_history_keys(t,1),'ready')
        self.assertEqual((t['type'],t['account_id'],t['to_account_id'],t['amount']),('transfer','source','goal-account',50))
        self.assertEqual((t['goal_id'],t['goal_contribution_id']),('goal',p['contribution']['id']))
        self.assertEqual(await self.balances(),[950,1050,1000])
        self.assertEqual(p['goal']['current_amount'],50)
        receipt = await self.db.goal_contributions.find_one({'id':p['contribution']['id']})
        self.assertNotIn('_history_keys',receipt)

    async def test_real_withdrawal_correct_direction(self):
        await self.contribute()
        p = await self.contribute(key='withdrawal',kind='withdrawal',amount=20)
        t = await self.transfer(p)
        self.assertEqual((t['account_id'],t['to_account_id']),('goal-account','source'))
        self.assertEqual(inspect_history_keys(t,1),'ready')
        self.assertEqual(await self.balances(),[970,1030,1000])
        self.assertEqual(p['goal']['current_amount'],30)

    async def test_admin_contribution_never_calls_generator(self):
        def fail(*a):self.fail('administrative generator call')
        with patch.dict(self.ns,{'with_history_keys':fail}):p=await self.contribute(real=False)
        state=await self.snapshot()
        self.assertEqual(state['transactions'],[])
        self.assertIsNone(p['contribution']['transaction_id'])
        self.assertFalse(p['contribution']['real_movement'])
        self.assertEqual(await self.balances(),[1000,1000,1000])
        self.assertEqual(p['goal']['current_amount'],50)
        for d in state['goal_contributions']:self.assertNotIn('_history_keys',d)

    async def test_disabled_no_keys_no_generator(self):
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=False)
        def fail(*a):self.fail('disabled generator call')
        with patch.dict(self.ns,{'with_history_keys':fail}):p=await self.contribute()
        self.assertNotIn('_history_keys',await self.transfer(p))
        self.assertEqual(await self.balances(),[950,1050,1000])

    async def test_retry_original_null_date_and_payload_conflict(self):
        p=await self.contribute(when=None)
        before=await self.snapshot()
        q=await self.contribute(when=None)
        self.assertEqual(q['contribution'],p['contribution'])
        await self.contribute(amount=51,when=None,status=409)
        self.assertEqual(await self.snapshot(),before)

    async def test_equal_independent_contributions(self):
        a,b=await asyncio.gather(self.contribute(key='one'),self.contribute(key='two'))
        self.assertNotEqual(a['contribution']['transaction_id'],b['contribution']['transaction_id'])
        self.assertEqual(await self.balances(),[900,1100,1000])
        for p in (a,b):self.assertEqual(inspect_history_keys(await self.transfer(p),1),'ready')
        self.assertEqual((await self.db.saving_goals.find_one({'id':'goal'}))['current_amount'],100)

    async def test_concurrent_same_intention_one_transfer(self):
        a,b=await asyncio.gather(self.contribute(),self.contribute())
        self.assertEqual(a['contribution'],b['contribution'])
        self.assertEqual(len((await self.snapshot())['transactions']),1)
        self.assertEqual(await self.balances(),[950,1050,1000])

    async def test_rollback_after_first_balance_write(self):
        original=self.ns['recompute_account_balance']
        async def fail(*a,**kw):
            await original(*a,**kw)
            raise OperationFailure('Synthetic after source balance')
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_account_balance':fail}):await self.contribute(status=503)
        self.assertEqual(await self.snapshot(),before)

    async def test_rollback_after_receipt_and_goal_write(self):
        original=self.ns['recompute_goal']
        calls=0
        async def fail(*a,**kw):
            nonlocal calls
            result=await original(*a,**kw);calls+=1
            if calls==2:raise OperationFailure('Synthetic after receipt and goal')
            return result
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_goal':fail}):await self.contribute(status=503)
        self.assertEqual(await self.snapshot(),before)

    async def test_unverifiable_derivation_does_not_change_finance(self):
        # Route dates are normalized. Inject only the derived parser failure.
        with patch('backend.history_keys.parse_instant',side_effect=HTTPException(422,'Synthetic unverified date')):
            p=await self.contribute()
            self.assertEqual(inspect_history_keys(await self.transfer(p),1),'unverifiable')
        self.assertEqual(await self.balances(),[950,1050,1000])
        self.assertEqual((await self.transfer(p))['date'],'2026-10-01T12:00:00.123456+01:02:03')

    async def test_delete_goal_preserves_transfer_keys_and_balances(self):
        p=await self.contribute()
        t=await self.transfer(p)
        balances=await self.balances()
        for _ in range(2):
            r=await self.request('DELETE','/goals/goal');self.assertEqual(r.status_code,200,r.text)
        remaining=await self.transfer(p)
        self.assertEqual(remaining,{k:v for k,v in t.items() if k not in ('goal_id','goal_contribution_id')})
        self.assertEqual(inspect_history_keys(remaining,1),'ready')
        self.assertEqual(await self.balances(),balances)
        receipt=await self.db.goal_contributions.find_one({'id':p['contribution']['id']})
        self.assertTrue(receipt['deleted'])
        self.assertNotIn('_history_keys',receipt)
        before=await self.snapshot()
        await self.contribute(status=409)
        self.assertEqual(await self.snapshot(),before)

    async def test_invalid_accounts_and_withdrawal_leave_no_changes(self):
        before=await self.snapshot()
        for kw in (dict(account='missing'),dict(account='goal-account'),dict(kind='withdrawal')):
            await self.contribute(status=422,**kw)
            self.assertEqual(await self.snapshot(),before)


class GoalKeyMemoryTests(GoalKeyCases,unittest.IsolatedAsyncioTestCase):
    def setUp(self):setup_memory(self)

    async def test_uncertain_commit_recovers_original(self):
        self.db.commit_then_error=True
        await self.contribute(status=503)
        before=await self.snapshot()
        p=await self.contribute()
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(inspect_history_keys(await self.transfer(p),1),'ready')
