"""R4 2C real transactions on exclusively new synthetic databases."""
import asyncio
import os
import unittest
import uuid
from unittest.mock import patch

from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException
from pymongo.errors import OperationFailure
from backend import shared_obligations as shared
from backend.tests.test_reference_integrity import context
from backend.tests.test_reference_mongodb import ConflictAudit
from backend.tests.test_shared_obligations import parents, metadata, ENVIRONMENT, USER
from backend.tests.test_shared_payments import PaymentCases


@unittest.skipUnless(os.environ.get("MONEYFLOW_R4_CORE_REAL_TESTS") == "1", "Explicit R4 core opt-in required")
class SharedPaymentMongoTests(PaymentCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.name = "test_r4_core_"+uuid.uuid4().hex
        self.audit = ConflictAudit()
        self.client = AsyncIOMotorClient("mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true",
            serverSelectionTimeoutMS=5000, event_listeners=[self.audit])
        hello = await self.client.admin.command("hello")
        self.assertEqual(self.client.address, ("127.0.0.1", 27018))
        self.assertEqual(hello["setName"], "app_finanzas_dev_rs")
        self.assertTrue(hello["isWritablePrimary"])
        self.assertIsNotNone(hello.get("logicalSessionTimeoutMinutes"))
        self.db = self.client[self.name]
        self.assertEqual(await self.db.list_collection_names(), [])
        self.collections = ("accounts", "categories", "transactions", "debts", "debt_payments", "bills", "bill_payments",
            "recurring_payments", "recurring_payment_records", "recurring_templates", "saving_goals", "goal_contributions",
            "budgets", "users", "moneyflow_metadata", "shared_obligations", "shared_tracking_intents")
        for col in self.collections:
            await self.db.create_collection(col)
        # Administrative test setup ONLY, before exercising the core.
        await shared.install_indexes(self.db)
        await self.db.moneyflow_metadata.insert_one(metadata())
        bill, rp = parents()
        await self.db.bills.insert_one(bill)
        await self.db.recurring_payments.insert_one(rp)
        await self.db.accounts.insert_many([dict(_id=aid, id=aid, user_id=USER, initial_balance=1000, current_balance=1000)
            for aid in ("account", "second")])
        self.ctx = context(self.db, self.client)
        self.ob = await self.transact(lambda session: shared.create_shared_obligation(self.db, "bill",
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session, occurrences=self.ctx.ns["_rp_occurrences"]))
        print("R4 CORE VERIFIED NEW DB:", self.name, self._testMethodName, flush=True)

    async def asyncTearDown(self):
        try:
            for database, command, address in self.audit.events:
                self.assertIn(database, (self.name, "admin"))
                self.assertEqual(address, ("127.0.0.1", 27018))
                self.assertNotIn(command, ("drop", "dropDatabase", "dropIndexes"))
            print("R4 CORE DB RETAINED:", self.name, flush=True)
        finally:
            self.client.close()

    async def concurrent(self, requests):
        original = shared._lock_payment_obligation
        barrier = asyncio.Barrier(len(requests))
        calls = 0
        async def synchronized(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls <= len(requests):
                await asyncio.wait_for(barrier.wait(), 15)
            return await original(*args, **kwargs)
        async def outcome(fn):
            try:
                return await fn()
            except HTTPException as error:
                return error.status_code
        with patch.object(shared, "_lock_payment_obligation", synchronized):
            results = await asyncio.wait_for(asyncio.gather(*(outcome(fn) for fn in requests)), 30)
        self.assertIn(112, self.audit.failures)
        return results

    async def test_concurrent_seventy_seventy_distinct_accounts_revalidates(self):
        results = await self.concurrent([lambda: self.pay("one", 70, "bill", "account"),
            lambda: self.pay("two", 70, "recurring", "second")])
        self.assertEqual(sum(isinstance(r, shared.SharedPaymentResult) for r in results), 1)
        self.assertIn(409, results)
        data = await self.snapshot()
        self.assertEqual((len(data["transactions"]), len(data["bill_payments"]), len(data["recurring_payment_records"])), (1, 1, 1))
        self.assertEqual(sum(a["current_balance"] for a in data["accounts"]), 1930)
        self.assertEqual(data["shared_obligations"][0]["revision"], 1)

    async def test_concurrent_equal_partials_and_original_id_replay(self):
        results = await self.concurrent([lambda: self.pay("one", 30, "bill", "account"),
            lambda: self.pay("two", 30, "recurring", "second")])
        self.assertTrue(all(isinstance(r, shared.SharedPaymentResult) for r in results))
        data = await self.snapshot()
        self.assertEqual((len(data["transactions"]), len(data["bill_payments"])), (2, 2))
        self.assertEqual(sum(a["current_balance"] for a in data["accounts"]), 1940)
        self.assertEqual(data["shared_obligations"][0]["revision"], 2)
        before = await self.snapshot()
        self.assertFalse((await self.pay("one", 30)).created)
        self.assertEqual(await self.snapshot(), before)

    async def test_concurrent_same_ids_creates_one_event(self):
        results = await self.concurrent([lambda: self.pay("same", 30), lambda: self.pay("same", 30)])
        self.assertEqual(sorted(r.created for r in results), [False, True])
        data = await self.snapshot()
        self.assertEqual((len(data["transactions"]), len(data["bill_payments"]), len(data["recurring_payment_records"])), (1, 1, 1))
        self.assertEqual(data["accounts"][0]["current_balance"], 970)
        self.assertEqual(data["shared_obligations"][0]["revision"], 1)

    async def test_real_failure_after_all_inserts_rolls_back_everything(self):
        before = await self.snapshot()
        original = self.ctx.ns["recompute_account_balance"]
        async def failed(*args, **kwargs):
            await original(*args, **kwargs)
            raise OperationFailure("Synthetic failure after balance update")
        self.ctx.ns["recompute_account_balance"] = failed
        try:
            await self.rejected(lambda: self.pay("abort", 30), 503)
        finally:
            self.ctx.ns["recompute_account_balance"] = original
        self.assertEqual(await self.snapshot(), before)

    async def test_unknown_commit_recovers_original_event_without_more_money(self):
        real_client = self.ctx.ns["client"]
        class UncertainSession:
            def __init__(inner, session): inner.session = session
            async def __aenter__(inner): return inner
            async def __aexit__(inner, *args): await inner.session.end_session()
            async def with_transaction(inner, callback, **kwargs):
                await inner.session.with_transaction(callback, **kwargs)
                raise OperationFailure("Synthetic lost commit response", details={"errorLabels": ["UnknownTransactionCommitResult"]})
        class UncertainClient:
            async def start_session(inner): return UncertainSession(await real_client.start_session())
        self.ctx.ns["client"] = UncertainClient()
        try:
            with self.assertRaises(HTTPException) as exc:
                await self.pay("uncertain", 30)
            self.assertEqual(exc.exception.status_code, 503)
        finally:
            self.ctx.ns["client"] = real_client
        before = await self.snapshot()
        self.assertEqual(before["accounts"][0]["current_balance"], 970)
        replay = await self.pay("uncertain", 30)
        self.assertFalse(replay.created)
        self.assertEqual(await self.snapshot(), before)

    async def test_variable_obligation_fifty_keeps_estimate_one_hundred(self):
        # New independent fixture within this same exclusively synthetic DB.
        bill, rp = parents()
        bill.update(_id="variable", id="variable", amount=50, recurring_payment_id="variable-rp")
        rp.update(_id="variable-rp", id="variable-rp", variable=True)
        await self.db.bills.insert_one(bill)
        await self.db.recurring_payments.insert_one(rp)
        ob = await self.transact(lambda session: shared.create_shared_obligation(self.db, "variable",
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session, occurrences=self.ctx.ns["_rp_occurrences"]))
        payload = self.ctx.ns["BillPayIn"](amount=50, account_id="account").model_dump()
        event = await self.transact(lambda session: shared.register_shared_payment(self.db, ob["_id"], origin="bill",
            receipt_id="variable-original", transaction_id="variable-movement", payload=payload,
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            recompute_account_balance=self.ctx.ns["recompute_account_balance"]))
        self.assertEqual((event.summary.paid, event.summary.remaining), (50, 0))
        self.assertEqual(ob["estimated_amount"].to_decimal(), 100)
        self.assertEqual((await self.db.accounts.find_one({"id": "account"}))["current_balance"], 950)

    async def test_distinct_obligations_same_account_preserve_r1_balance(self):
        bill, rp = parents()
        bill.update(_id="other", id="other", recurring_payment_id="other-rp")
        rp.update(_id="other-rp", id="other-rp")
        await self.db.bills.insert_one(bill)
        await self.db.recurring_payments.insert_one(rp)
        other = await self.transact(lambda session: shared.create_shared_obligation(self.db, "other",
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session, occurrences=self.ctx.ns["_rp_occurrences"]))
        payload = self.ctx.ns["BillPayIn"](amount=100, account_id="account").model_dump()
        async def other_payment():
            return await self.transact(lambda session: shared.register_shared_payment(self.db, other["_id"],
                origin="bill", receipt_id="other-original", transaction_id="other-movement", payload=payload,
                expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
                recompute_account_balance=self.ctx.ns["recompute_account_balance"]))
        results = await self.concurrent([lambda: self.pay("own", 100), other_payment])
        self.assertTrue(all(isinstance(r, shared.SharedPaymentResult) for r in results))
        self.assertEqual((await self.db.accounts.find_one({"id": "account"}))["current_balance"], 800)
        self.assertEqual(await self.db.transactions.count_documents({}), 2)
