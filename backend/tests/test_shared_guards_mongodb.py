"""R4 2B: brand-new synthetic databases, no explicit index creation or cleanup."""
import asyncio
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from backend import reference_integrity as references
from backend import shared_obligations as shared
from backend.tests.test_reference_integrity import context
from backend.tests.test_reference_mongodb import ConflictAudit
from backend.tests.test_shared_guards import GuardCases
from backend.tests.test_shared_obligations import parents, ENVIRONMENT, USER


@unittest.skipUnless(os.environ.get("MONEYFLOW_R4_GUARD_REAL_TESTS") == "1", "Explicit R4 guard opt-in required")
class SharedGuardMongoTests(GuardCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.name = "test_r4_guards_"+uuid.uuid4().hex
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
            "budgets", "users", "moneyflow_metadata", "shared_obligations")
        for col in self.collections:
            await self.db.create_collection(col)
        bill, rp = parents()
        await self.db.bills.insert_one(bill)
        await self.db.recurring_payments.insert_one(rp)
        await self.db.accounts.insert_one(dict(_id="account", id="account", user_id=USER, initial_balance=1000, current_balance=1000))
        self.ctx = context(self.db, self.client)
        print("NEW R4 GUARD DB VERIFIED:", self.name, self._testMethodName, flush=True)

    async def asyncTearDown(self):
        try:
            for database, command, address in self.audit.events:
                self.assertIn(database, (self.name, "admin"))
                self.assertEqual(address, ("127.0.0.1", 27018))
                self.assertNotIn(command, ("drop", "dropDatabase", "createIndexes", "dropIndexes"))
            print("R4 GUARD DB RETAINED:", self.name, flush=True)
        finally:
            self.client.close()

    async def test_state_update_error_and_unsupported_transaction_roll_back(self):
        original = self.ctx.ns["_rp_get"]
        calls = 0
        async def failed_after_write(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OperationFailure("Synthetic error after state update")
            return await original(*args, **kwargs)
        self.ctx.ns["_rp_get"] = failed_after_write
        try:
            await self.assert_blocked("POST", "/recurring-payments/rp/pause", code=503)
        finally:
            self.ctx.ns["_rp_get"] = original
        real_client = self.ctx.ns["client"]
        class UnsupportedSession:
            async def __aenter__(inner): return inner
            async def __aexit__(inner, *args): pass
            async def with_transaction(inner, callback, **kwargs):
                raise OperationFailure("Transaction numbers require a replica set")
        class UnsupportedClient:
            async def start_session(inner): return UnsupportedSession()
        self.ctx.ns["client"] = UnsupportedClient()
        try:
            await self.assert_blocked("POST", "/recurring-payments/rp/pause", code=503)
        finally:
            self.ctx.ns["client"] = real_client

    async def test_unmanaged_bill_concurrent_payments_keep_r2_guarantee(self):
        await self.db.accounts.insert_one(dict(_id="second", id="second", user_id=USER, initial_balance=1000, current_balance=1000))
        async def pay(account):
            return await self.ctx.request("POST", "/bills/bill/payments", json={"amount": 70, "account_id": account},
                headers={"Idempotency-Key": "concurrent-"+account})
        responses = await asyncio.gather(pay("account"), pay("second"))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 422])
        pays = await self.db.bill_payments.find({}).to_list(None)
        txs = await self.db.transactions.find({}).to_list(None)
        accounts = await self.db.accounts.find({}).to_list(None)
        self.assertEqual(len(pays), 1)
        self.assertEqual(len(txs), 1)
        self.assertEqual((pays[0]["amount"], txs[0]["amount"]), (70, 70))
        self.assertEqual(sum(a["current_balance"] for a in accounts), 1930)
        self.assertEqual(await self.db.shared_obligations.count_documents({}), 0)

    async def test_state_uncertain_commit_is_not_reported_as_confirmation(self):
        real_client = self.ctx.ns["client"]
        class UncertainSession:
            def __init__(inner, session): inner.session = session
            async def __aenter__(inner): return inner
            async def __aexit__(inner, *args): await inner.session.end_session()
            async def with_transaction(inner, callback, **kwargs):
                await inner.session.with_transaction(callback, **kwargs)
                raise OperationFailure("Lost commit confirmation", details={"errorLabels": ["UnknownTransactionCommitResult"]})
        class UncertainClient:
            async def start_session(inner): return UncertainSession(await real_client.start_session())
        before = await self.snapshot()
        self.ctx.ns["client"] = UncertainClient()
        try:
            response = await self.ctx.request("POST", "/recurring-payments/rp/pause")
            self.assertEqual(response.status_code, 503, response.text)
        finally:
            self.ctx.ns["client"] = real_client
        after = await self.snapshot()
        self.assertEqual(after["recurring_payments"][0]["state"], "paused")
        for collection in self.collections:
            if collection != "recurring_payments":
                self.assertEqual(after[collection], before[collection])
        await self.assert_blocked("POST", "/recurring-payments/rp/pause")

    async def test_reservation_wins_pause_retries_and_blocks(self):
        checked, committed = asyncio.Event(), asyncio.Event()
        original = references.guard_legacy_recurring
        attempts = 0
        async def delayed(*args, **kwargs):
            nonlocal attempts
            await original(*args, **kwargs)
            attempts += 1
            if attempts == 1:
                checked.set()
                await asyncio.wait_for(committed.wait(), 15)
        async def binding():
            await asyncio.wait_for(checked.wait(), 15)
            async def callback(session):
                bill = await self.db.bills.find_one({"id": "bill"}, session=session)
                rp = await self.db.recurring_payments.find_one({"id": "rp"}, session=session)
                doc = shared.resolve_documents(bill, rp, shared.Scope(ENVIRONMENT, USER), occurrences=self.ctx.ns["_rp_occurrences"])
                await references.coordinate(self.db, USER, {"bill_id": "bill", "recurring_id": "rp"}, session)
                await self.db.shared_obligations.insert_one(doc, session=session)
            await self.ctx.ns["payment_transaction"](callback)
            committed.set()
        with patch.dict(self.ctx.ns, guard_legacy_recurring=delayed):
            response, _ = await asyncio.wait_for(asyncio.gather(
                self.ctx.request("POST", "/recurring-payments/rp/pause"), binding()), 30)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn(112, self.audit.failures)
        self.assertEqual((await self.db.recurring_payments.find_one({"id": "rp"}))["state"], "active")
        self.assertEqual(await self.db.shared_obligations.count_documents({}), 1)
        self.assertEqual(await self.db.transactions.count_documents({}), 0)
        self.assertEqual((await self.db.accounts.find_one({"id": "account"}))["current_balance"], 1000)

    async def test_pause_wins_binding_revalidates_updated_schedule(self):
        read, paused = asyncio.Event(), asyncio.Event()
        attempts = 0
        async def binding(session):
            nonlocal attempts
            attempts += 1
            bill = await self.db.bills.find_one({"id": "bill"}, session=session)
            rp = await self.db.recurring_payments.find_one({"id": "rp"}, session=session)
            doc = shared.resolve_documents(bill, rp, shared.Scope(ENVIRONMENT, USER), occurrences=self.ctx.ns["_rp_occurrences"])
            if attempts == 1:
                read.set()
                await asyncio.wait_for(paused.wait(), 15)
            await references.coordinate(self.db, USER, {"bill_id": "bill", "recurring_id": "rp"}, session)
            await self.db.shared_obligations.insert_one(doc, session=session)
        async def pause():
            await asyncio.wait_for(read.wait(), 15)
            # A fixed historical day ensures the tested due falls inside the pause.
            self.ctx.ns["_rp_today"] = lambda: __import__("datetime").date(2026, 10, 12)
            response = await self.ctx.request("POST", "/recurring-payments/rp/pause")
            self.assertEqual(response.status_code, 200, response.text)
            paused.set()
        async def rejected_binding():
            with self.assertRaises(HTTPException) as exc:
                await self.ctx.ns["payment_transaction"](binding)
            self.assertEqual(exc.exception.status_code, 409)
        await asyncio.wait_for(asyncio.gather(rejected_binding(), pause()), 30)
        self.assertIn(112, self.audit.failures)
        self.assertGreater(attempts, 1)
        self.assertEqual((await self.db.recurring_payments.find_one({"id": "rp"}))["state"], "paused")
        self.assertEqual(await self.db.shared_obligations.count_documents({}), 0)
        self.assertEqual(await self.db.transactions.count_documents({}), 0)
