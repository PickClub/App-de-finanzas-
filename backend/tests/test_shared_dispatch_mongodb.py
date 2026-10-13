"""Real public R4 integration on new synthetic databases, never existing data."""
import asyncio
import os
import unittest
from unittest.mock import patch
from pymongo.errors import OperationFailure
from backend import shared_obligations as shared
from backend.tests import test_shared_payments_mongodb as core
from backend.tests.test_shared_dispatch import DispatchCases


@unittest.skipUnless(os.environ.get("MONEYFLOW_R4_DISPATCH_REAL_TESTS")=="1","Explicit opt-in required")
class SharedDispatchMongoTests(DispatchCases,unittest.IsolatedAsyncioTestCase):
    asyncSetUp=core.SharedPaymentMongoTests.asyncSetUp
    asyncTearDown=core.SharedPaymentMongoTests.asyncTearDown

    async def test_reconciliation_snapshot_concurrent_with_annulment(self):
        first=await self.pay_ok("bill","snapshot-reconcile",60)
        started,proceed=asyncio.Event(),asyncio.Event()
        original=shared._read_event
        calls=0
        async def paused_read(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==1:
                started.set()
                await asyncio.wait_for(proceed.wait(),15)
            return await original(*args,**kwargs)
        data=dict(amount=60,account_id="account",date="2026-10-11T12:00:00+00:00")
        headers={"Idempotency-Key":"snapshot-reconcile","MoneyFlow-Environment-ID":self.ob["environment_id"],"MoneyFlow-User-ID":"default-user"}
        with patch.object(shared,"_read_event",paused_read):
            task=asyncio.create_task(self.ctx.request("POST","/bills/bill/payments/reconcile",json=data,headers=headers))
            try:
                await asyncio.wait_for(started.wait(),15)
                await self.remove_ok("bill",first["id"])
            finally:
                proceed.set()
            response=await asyncio.wait_for(task,15)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["status"],"matched")  # valid pre-annul snapshot
        response=await self.reconcile("bill","snapshot-reconcile",60)
        self.assertEqual(response.json()["status"],"cancelled")  # committed post-annul snapshot
        final=await self.snapshot()
        self.assertEqual(len(final["transactions"]),0)
        self.assertEqual(final["accounts"][0]["current_balance"],1000)

    async def run_concurrent(self, amounts, accounts, keys, origins=("bill","recurring")):
        barrier=asyncio.Barrier(2)
        original=shared._lock_payment_obligation
        attempts=0
        async def lock(*args,**kwargs):
            nonlocal attempts
            attempts+=1
            if attempts<=2:
                await asyncio.wait_for(barrier.wait(),15)
            return await original(*args,**kwargs)
        with patch.object(shared,"_lock_payment_obligation",lock):
            results=await asyncio.wait_for(asyncio.gather(self.post(origins[0],keys[0],amounts[0],accounts[0]),
                self.post(origins[1],keys[1],amounts[1],accounts[1])),30)
        self.assertIn(112,self.audit.failures)
        return results

    async def test_concurrent_overpay_distinct_accounts(self):
        results=await self.run_concurrent((70,70),("account","second"),("one","two"))
        self.assertEqual(sorted(r.status_code for r in results),[200,422])
        data=await self.snapshot()
        self.assertEqual((len(data["transactions"]),len(data["bill_payments"]),len(data["recurring_payment_records"])),(1,1,1))
        self.assertEqual(sum(a["current_balance"] for a in data["accounts"]),1930)
        self.assertEqual(len(data["bills"]),1)

    async def test_concurrent_exact_completion_same_and_distinct_accounts(self):
        results=await self.run_concurrent((60,40),("account","second"),("one","two"))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual((len(data["transactions"]),len(data["bill_payments"]),len(data["bills"])),(2,2,2))
        self.assertEqual(sum(a["current_balance"] for a in data["accounts"]),1900)

    async def test_concurrent_exact_completion_same_account(self):
        results=await self.run_concurrent((50,50),("account","account"),("one","two"))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual((len(data["transactions"]),len(data["bills"])),(2,2))
        self.assertEqual(data["accounts"][0]["current_balance"],900)

    async def test_concurrent_same_key_recovers_single_payment_and_next_bill(self):
        results=await self.run_concurrent((100,100),("account","account"),("same","same"),("bill","bill"))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual((len(data["transactions"]),len(data["bill_payments"]),len(data["bills"])),(1,1,2))
        self.assertEqual(data["accounts"][0]["current_balance"],900)

    async def test_concurrent_two_full_payments_create_only_one_next_period(self):
        results=await self.run_concurrent((100,100),("account","second"),("one","two"))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        data=await self.snapshot()
        self.assertEqual((len(data["transactions"]),len(data["bill_payments"]),len(data["bills"])),(1,1,2))
        self.assertEqual(sum(a["current_balance"] for a in data["accounts"]),1900)

    async def test_unknown_commit_recovers_payment_and_generation_without_writes(self):
        actual_client=self.ctx.ns["client"]
        class LostResponseSession:
            def __init__(inner,session): inner.session=session
            async def __aenter__(inner): return inner
            async def __aexit__(inner,*args): await inner.session.end_session()
            async def with_transaction(inner,callback,**kwargs):
                await inner.session.with_transaction(callback,**kwargs)
                raise OperationFailure("Lost commit response",details={"errorLabels":["UnknownTransactionCommitResult"]})
        class LostResponseClient:
            async def start_session(inner): return LostResponseSession(await actual_client.start_session())
        with patch.dict(self.ctx.ns,{"client":LostResponseClient()}):
            response=await self.post("bill","uncertain",100)
        self.assertEqual(response.status_code,503)
        before=await self.snapshot()
        self.assertEqual((len(before["transactions"]),len(before["bill_payments"]),len(before["bills"])),(1,1,2))
        self.assertEqual(before["accounts"][0]["current_balance"],900)
        await self.pay_ok("bill","uncertain",100)
        self.assertEqual(await self.snapshot(),before)

    async def concurrent_changes(self, actions):
        barrier=asyncio.Barrier(2)
        original=shared._lock_payment_obligation
        attempts=0
        async def lock(*args,**kwargs):
            nonlocal attempts
            attempts+=1
            if attempts<=2:
                await asyncio.wait_for(barrier.wait(),15)
            return await original(*args,**kwargs)
        with patch.object(shared,"_lock_payment_obligation",lock):
            results=await asyncio.wait_for(asyncio.gather(*(action() for action in actions)),30)
        self.assertIn(112,self.audit.failures)
        return results

    async def test_concurrent_annul_from_both_endpoints_one_refund(self):
        first=await self.pay_ok("recurring","concurrent-delete",60)
        payment=await self.db.bill_payments.find_one({"recurring_record_id":first["id"]})
        results=await self.concurrent_changes((lambda:self.remove("bill",payment["id"]),lambda:self.remove("recurring",first["id"])))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),0)
        self.assertEqual(data["accounts"][0]["current_balance"],1000)
        self.assertTrue(all(p["_shared_financial_state"]=="annulled" for p in data["bill_payments"]+data["recurring_payment_records"]))

    async def test_concurrent_withdraw_and_annul(self):
        first=await self.pay_ok("bill","withdraw-race",60)
        results=await self.concurrent_changes((lambda:self.remove("recurring",first["recurring_record_id"]),lambda:self.remove("bill",first["id"])))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),0)
        self.assertEqual(data["accounts"][0]["current_balance"],1000)
        self.assertTrue(all(p["deleted"] for p in data["bill_payments"]+data["recurring_payment_records"]))

    async def test_concurrent_withdraw_same_record_never_refunds(self):
        first=await self.pay_ok("bill","withdraw-twice",60)
        results=await self.concurrent_changes((lambda:self.remove("recurring",first["recurring_record_id"]),lambda:self.remove("recurring",first["recurring_record_id"])))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],940)
        before=await self.snapshot()
        response=await self.post("recurring","over-after-race",41,"second")
        self.assertEqual(response.status_code,422)
        self.assertEqual(await self.snapshot(),before)

    async def test_concurrent_annul_and_new_payment_serializable(self):
        first=await self.pay_ok("bill","old",60)
        results=await self.concurrent_changes((lambda:self.remove("bill",first["id"]),lambda:self.post("recurring","new",40,"second")))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual([a["current_balance"] for a in data["accounts"]],[1000,960])
        self.assertEqual(sum(p["amount"] for p in data["bill_payments"] if not p.get("deleted")),40)
        # If completion won first, its future bill is retained. Neither result
        # creates a duplicate: both valid serial orders may leave 1 or 2 bills.
        self.assertIn(len(data["bills"]),(1,2))

    async def test_delete_unknown_commit_recovers_without_refunding_twice(self):
        first=await self.pay_ok("bill","unknown-delete",100)
        actual_client=self.ctx.ns["client"]
        class LostResponseSession:
            def __init__(inner,session): inner.session=session
            async def __aenter__(inner): return inner
            async def __aexit__(inner,*args): await inner.session.end_session()
            async def with_transaction(inner,callback,**kwargs):
                await inner.session.with_transaction(callback,**kwargs)
                raise OperationFailure("Lost DELETE commit response",details={"errorLabels":["UnknownTransactionCommitResult"]})
        class LostResponseClient:
            async def start_session(inner): return LostResponseSession(await actual_client.start_session())
        with patch.dict(self.ctx.ns,{"client":LostResponseClient()}):
            response=await self.remove("bill",first["id"])
        self.assertEqual(response.status_code,503)
        before=await self.snapshot()
        self.assertEqual(len(before["transactions"]),0)
        self.assertEqual(before["accounts"][0]["current_balance"],1000)
        self.assertEqual(len(before["bills"]),2)
        await self.remove_ok("bill",first["id"])
        self.assertEqual(await self.snapshot(),before)

    async def test_template_creation_wins_annul_revalidates_and_rejects(self):
        first=await self.pay_ok("bill","template-race",60)
        ready,finished=asyncio.Event(),asyncio.Event()
        original=shared._payment_parents
        calls=0
        async def parents(*args,**kwargs):
            nonlocal calls
            result=await original(*args,**kwargs)
            calls+=1
            if calls==1:
                ready.set()
                await asyncio.wait_for(finished.wait(),15)
            return result
        with patch.object(shared,"_payment_parents",parents):
            task=asyncio.create_task(self.remove("bill",first["id"]))
            await asyncio.wait_for(ready.wait(),15)
            template=await self.ctx.request("POST","/recurring",json=dict(name="Synthetic template",amount=60,type="expense",
                source_transaction_id=first["transaction_id"]))
            finished.set()
            response=await asyncio.wait_for(task,30)
        self.assertEqual(template.status_code,200,template.text)
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn(112,self.audit.failures)
        data=await self.snapshot()
        self.assertEqual(len(data["recurring_templates"]),1)
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],940)
        self.assertTrue(all(not p.get("deleted") for p in data["bill_payments"]+data["recurring_payment_records"]))

    async def test_annul_wins_template_creation_revalidates_missing_movement(self):
        first=await self.pay_ok("bill","annul-race",60)
        ready,finished=asyncio.Event(),asyncio.Event()
        original=self.ctx.ns["coordinate"]
        calls=0
        async def coordinate(database,user,payload,session,*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==1:
                self.assertIsNotNone(await database.transactions.find_one({"id":first["transaction_id"]},session=session))
                ready.set()
                await asyncio.wait_for(finished.wait(),15)
            return await original(database,user,payload,session,*args,**kwargs)
        with patch.dict(self.ctx.ns,{"coordinate":coordinate}):
            task=asyncio.create_task(self.ctx.request("POST","/recurring",json=dict(name="Synthetic template",amount=60,type="expense",
                source_transaction_id=first["transaction_id"])))
            await asyncio.wait_for(ready.wait(),15)
            response=await self.remove("bill",first["id"])
            finished.set()
            template=await asyncio.wait_for(task,30)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(template.status_code,422,template.text)
        self.assertIn(112,self.audit.failures)
        data=await self.snapshot()
        self.assertEqual(len(data["recurring_templates"]),0)
        self.assertEqual(len(data["transactions"]),0)
        self.assertEqual(data["accounts"][0]["current_balance"],1000)
        self.assertTrue(all(p["_shared_financial_state"]=="annulled" for p in data["bill_payments"]+data["recurring_payment_records"]))

    async def test_concurrent_restore_same_intention_is_one_journal(self):
        first=await self.pay_ok("bill","restore-source",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        action=lambda:self.post("recurring","restore-key",60,mode="link",transaction_id=first["transaction_id"])
        results=await self.concurrent_changes((action,action))
        self.assertEqual([r.status_code for r in results],[200,200])
        self.assertEqual(results[0].json(),results[1].json())
        data=await self.snapshot()
        self.assertEqual((len(data["shared_tracking_intents"]),len(data["transactions"]),len(data["bill_payments"])),(1,1,1))
        self.assertEqual(data["accounts"][0]["current_balance"],940)

    async def test_concurrent_restore_distinct_intentions_only_one_accepted(self):
        first=await self.pay_ok("bill","restore-source",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        results=await self.concurrent_changes((lambda:self.post("recurring","restore-one",60,mode="link",transaction_id=first["transaction_id"]),
            lambda:self.post("recurring","restore-two",60,mode="link",transaction_id=first["transaction_id"])))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        data=await self.snapshot()
        self.assertEqual((len(data["shared_tracking_intents"]),len(data["transactions"])),(1,1))
        self.assertEqual(data["accounts"][0]["current_balance"],940)

    async def test_concurrent_mark_same_key_deduplicates_without_financial_effect(self):
        action=lambda:self.post("recurring","mark-race",80,mode="mark",settles=True)
        results=await self.concurrent_changes((action,action))
        self.assertEqual([r.status_code for r in results],[200,200])
        self.assertEqual(results[0].json(),results[1].json())
        data=await self.snapshot()
        self.assertEqual((len(data["shared_tracking_intents"]),len(data["recurring_payment_records"]),len(data["transactions"])),(1,1,0))
        self.assertEqual(data["accounts"][0]["current_balance"],1000)

    async def test_concurrent_mark_and_expense_keep_real_pending(self):
        results=await self.concurrent_changes((lambda:self.post("recurring","mark-concurrent",90,mode="mark",settles=True),
            lambda:self.post("bill","financial-concurrent",60)))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],940)
        response=await self.post("recurring","excess-concurrent",41)
        self.assertEqual(response.status_code,422)

    async def test_concurrent_restore_and_annul_cannot_resurrect_money(self):
        first=await self.pay_ok("bill","restore-annul-source",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        results=await self.concurrent_changes((lambda:self.post("recurring","restore-annul",60,mode="link",transaction_id=first["transaction_id"]),
            lambda:self.remove("bill",first["id"])))
        self.assertEqual(results[1].status_code,200)
        self.assertIn(results[0].status_code,(200,409))
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),0)
        self.assertEqual(data["accounts"][0]["current_balance"],1000)
        self.assertTrue(all(p["_shared_financial_state"]=="annulled" for p in data["bill_payments"]+data["recurring_payment_records"]))

    async def test_concurrent_parent_amount_reduction_and_payment_no_overpay(self):
        await self.once_identity()
        await self.pay_ok("bill","partial-race",60)
        results=await self.concurrent_changes((lambda:self.bill_edit(amount=80),lambda:self.post("recurring","additional-race",30)))
        self.assertIn([r.status_code for r in results],([200,422],[409,200]))
        data=await self.snapshot()
        actual=data["bills"][0]["amount"]
        paid=sum(t["amount"] for t in data["transactions"])
        self.assertLessEqual(paid,actual)
        self.assertEqual(data["accounts"][0]["current_balance"],1000-paid)
        self.assertEqual(sum(p["amount"] for p in data["bill_payments"]),paid)
        self.assertEqual(sum(r["amount"] for r in data["recurring_payment_records"]),paid)
        self.assertEqual(len(data["bills"]),1)

    async def test_concurrent_bill_defaults_and_completion_preserve_original_accounts(self):
        await self.pay_ok("bill","partial-defaults",60)
        results=await self.concurrent_changes((lambda:self.bill_edit(name="Changed",account_id="second"),
            lambda:self.post("recurring","finish-defaults",40,"second")))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual([a["current_balance"] for a in data["accounts"]],[940,960])
        self.assertEqual(len(data["transactions"]),2)
        self.assertEqual(len(data["bills"]),2)
        original=next(t for t in data["transactions"] if t["amount"]==60)
        self.assertEqual(original["account_id"],"account")

    async def test_concurrent_recurring_description_and_completion_revalidates_new_reservation(self):
        await self.pay_ok("bill","partial-rp-edit",60)
        results=await self.concurrent_changes((lambda:self.rp_edit(name="Changed recurring",account_id="second"),
            lambda:self.post("bill","finish-rp-edit",40,"second")))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual([a["current_balance"] for a in data["accounts"]],[940,960])
        self.assertEqual(len(data["bills"]),2)
        self.assertEqual(len(data["shared_obligations"]),2)
        self.assertEqual(len(data["transactions"]),2)

    async def test_concurrent_safe_pause_and_past_once_payment(self):
        await self.once_identity()
        results=await self.concurrent_changes((lambda:self.state_change("pause",today="2026-11-01"),
            lambda:self.post("bill","pay-past",100)))
        self.assertEqual([r.status_code for r in results],[200,200])
        data=await self.snapshot()
        self.assertEqual(len(data["bills"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],900)
        self.assertEqual(data["recurring_payments"][0]["state"],"paused")
