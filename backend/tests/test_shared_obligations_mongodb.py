"""Opt-in R4 stage 1: exclusively new loopback databases, retained afterwards."""
import asyncio
import copy
import os
import unittest
import uuid
from unittest.mock import patch

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, OperationFailure

from backend import shared_obligations as shared
from backend.tests.test_reference_integrity import context
from backend.tests.test_reference_mongodb import ConflictAudit
from backend.tests.test_shared_obligations import SharedCases, ENVIRONMENT, OTHER_ENVIRONMENT, USER, metadata, parents, graph, provenance, activation_settings


@unittest.skipUnless(os.environ.get("MONEYFLOW_R4_REAL_TESTS") == "1", "R4 stage 1 real tests require explicit opt-in")
class SharedMongoDBTests(SharedCases, unittest.IsolatedAsyncioTestCase):
    real = True

    async def asyncSetUp(self):
        self.name = "test_r4_stage1_"+uuid.uuid4().hex
        self.audit = ConflictAudit()
        self.client = AsyncIOMotorClient(
            "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true",
            serverSelectionTimeoutMS=5000, event_listeners=[self.audit])
        hello = await self.client.admin.command("hello")
        self.assertEqual(self.client.address, ("127.0.0.1", 27018))
        self.assertEqual(hello["setName"], "app_finanzas_dev_rs")
        self.assertTrue(hello["isWritablePrimary"])
        self.assertIsNotNone(hello.get("logicalSessionTimeoutMinutes"))
        self.db = self.client[self.name]
        self.assertTrue(self.name.startswith("test_r4_stage1_"))
        self.assertEqual(await self.db.list_collection_names(), [])
        self.collections = ("accounts", "categories", "transactions", "debts", "debt_payments", "bills", "bill_payments",
            "recurring_payments", "recurring_payment_records", "recurring_templates", "saving_goals", "goal_contributions",
            "budgets", "users", "moneyflow_metadata", "shared_obligations")
        for col in self.collections:
            await self.db.create_collection(col)
        await shared.install_indexes(self.db)
        await shared.require_indexes(self.db)
        await self.db.moneyflow_metadata.insert_one(metadata())
        bill, rp = parents()
        await self.db.bills.insert_one(bill)
        await self.db.recurring_payments.insert_one(rp)
        await self.db.accounts.insert_one(dict(_id="account", id="account", user_id=USER, initial_balance=1000, current_balance=1000))
        self.ctx = context(self.db, self.client)
        self.occurrences = self.ctx.ns["_rp_occurrences"]
        self.scope = shared.Scope(ENVIRONMENT, USER)
        print("R4 STAGE 1 VERIFIED NEW DB:", self.name, self._testMethodName, flush=True)

    async def transaction(self, callback):
        # Use the existing payment runner / driver retry and commit semantics.
        # No new transaction runner is added to application code.
        return await self.ctx.ns["payment_transaction"](callback)

    async def asyncTearDown(self):
        try:
            for database, command, address in self.audit.events:
                self.assertIn(database, (self.name, "admin"))
                self.assertEqual(address, ("127.0.0.1", 27018))
                self.assertNotIn(command, ("drop", "dropDatabase"))
            print("R4 STAGE 1 RETAINED:", self.name, "commands:", len(self.audit.events), flush=True)
        finally:
            self.client.close()

    async def test_unique_indexes_reject_duplicate_period_and_bill(self):
        doc = await self.transaction(self.create)
        duplicate = copy.deepcopy(doc)
        duplicate.update(_id=str(uuid.uuid4()), bill_id="second-bill")
        with self.assertRaises(DuplicateKeyError):
            await self.db.shared_obligations.insert_one(duplicate)
        other_period = copy.deepcopy(doc)
        other_period.update(_id=str(uuid.uuid4()), original_due_date="2026-11-20")
        with self.assertRaises(DuplicateKeyError):
            await self.db.shared_obligations.insert_one(other_period)
        self.assertEqual(await self.db.shared_obligations.count_documents({}), 1)
        # An archived identity must not release its unique historical period.
        await self.db.shared_obligations.update_one({"_id":doc["_id"]}, {"$set":{"lifecycle":"archived"}})
        with self.assertRaises(DuplicateKeyError):
            await self.db.shared_obligations.insert_one(duplicate)

    async def test_real_activation_requirements_readonly_and_missing_index(self):
        before = await self.snapshot()
        collections = await self.db.list_collection_names()
        async def ready(session):
            return await shared.require_activation(self.db, activation_settings("1"), effective_user=USER, session=session)
        self.assertEqual(await self.transaction(ready), self.scope)
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(await self.db.list_collection_names(), collections)
        # Only remove an index created by this fixture in its brand-new DB.
        await self.db.shared_obligations.drop_index("shared_bill_unique")
        await self.rejected_async(ready, 503)
        self.assertNotIn("shared_bill_unique", await self.db.shared_obligations.index_information())
        self.assertEqual(await self.snapshot(), before)

    async def test_real_activation_incorrect_index_and_absent_context(self):
        before = await self.snapshot()
        await self.db.shared_obligations.drop_index("shared_bill_unique")
        await self.db.shared_obligations.create_index([("user_id", 1), ("bill_id", 1)], name="shared_bill_unique", unique=False)
        async def ready(session):
            return await shared.require_activation(self.db, activation_settings("1"), effective_user=USER, session=session)
        await self.rejected_async(ready, 503)
        self.assertFalse((await self.db.shared_obligations.index_information())["shared_bill_unique"].get("unique", False))
        self.assertEqual(await self.snapshot(), before)
        await self.db.moneyflow_metadata.delete_one({"_id": "financial-context"})
        before = await self.snapshot()
        await self.rejected_async(ready, 503)
        self.assertEqual(await self.snapshot(), before)

    async def test_concurrent_creation_retries_without_duplicate_identity(self):
        barrier = asyncio.Barrier(2)
        calls = 0
        original = shared.coordinate
        async def synchronized(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls <= 2:
                await asyncio.wait_for(barrier.wait(), 15)
            return await original(*args, **kwargs)
        before = await self.snapshot()
        with patch.object(shared, "coordinate", synchronized):
            one, two = await asyncio.wait_for(asyncio.gather(self.transaction(self.create), self.transaction(self.create)), 30)
        self.assertEqual(one, two)
        self.assertIn(112, self.audit.failures)
        self.assertEqual(await self.db.shared_obligations.count_documents({}), 1)
        for collection in ("accounts", "transactions", "bill_payments", "recurring_payment_records"):
            self.assertEqual((await self.snapshot())[collection], before[collection])
        self.assertEqual((await self.db.bills.find_one({"id":"bill"}))["_reference_revision"], 1)
        self.assertEqual((await self.db.recurring_payments.find_one({"id":"rp"}))["_reference_revision"], 1)

    async def test_index_requirements_are_not_installed_by_resolver(self):
        # Only remove an index created in THIS fresh isolated database.
        await self.db.shared_obligations.drop_index("shared_bill_unique")
        before = await self.snapshot()
        await self.rejected_async(self.create, 503)
        draft, persisted = await self.transaction(self.read)
        self.assertFalse(persisted)
        self.assertEqual(draft["bill_id"], "bill")
        self.assertEqual(await self.snapshot(), before)
        self.assertNotIn("shared_bill_unique", await self.db.shared_obligations.index_information())

    async def test_rollback_after_metadata_insert(self):
        before = await self.snapshot()
        async def abort(session):
            await self.create(session)
            raise RuntimeError("Synthetic abort after identity insert")
        with self.assertRaises(RuntimeError):
            await self.transaction(abort)
        self.assertEqual(await self.snapshot(), before)

    async def test_existing_identity_preserves_period_after_backend_restart(self):
        one = await self.transaction(self.create)
        await self.db.recurring_payments.update_one({"id":"rp"}, {"$set":{"versions":[dict(valid_from="2026-11-01", start_date="2026-11-01", frequency="monthly", due_day=1, amount=200)]}})
        before = await self.snapshot()
        self.ctx = context(self.db, self.client)
        self.occurrences = self.ctx.ns["_rp_occurrences"]
        two = await self.transaction(self.create)
        self.assertEqual(one, two)
        self.assertEqual(two["original_due_date"], "2026-10-20")
        self.assertEqual(await self.snapshot(), before)

    async def test_real_partial_payment_inspection_deduplicates_lookup_paths(self):
        doc = await self.transaction(self.create)
        for suffix in ("1", "2"):
            p, r, tx = graph(suffix, 30)
            provenance(doc, p, r, tx)
            for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
                await self.insert(col, value)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT, effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual(result.paid, 60)
        self.assertEqual(result.remaining, 40)
        self.assertEqual(result.transaction_ids, ("tx1", "tx2"))
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(await self.db.transactions.count_documents({}), 2)

    async def test_real_retirement_does_not_reopen_paid_obligation(self):
        doc = await self.transaction(self.create)
        p, r, tx = graph(amount=100)
        provenance(doc, p, r, tx)
        p["deleted"] = r["deleted"] = True
        for flag in ("bill_id", "bill_payment_id", "recurring_payment_id", "recurring_record_id"):
            tx.pop(flag)
        for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.insert(col, value)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT, effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual(result.paid, 100)
        self.assertEqual(result.remaining, 0)
        self.assertEqual(await self.snapshot(), before)

    async def test_reprovisioned_context_cannot_reassign_existing_identity(self):
        await self.transaction(self.create)
        await self.db.moneyflow_metadata.update_one({"_id":"financial-context"}, {"$set":{"environment_id":OTHER_ENVIRONMENT}})
        before = await self.snapshot()
        async def changed(session):
            return await shared.create_shared_obligation(self.db, "bill", expected_environment_id=OTHER_ENVIRONMENT,
                     effective_user=USER, session=session, occurrences=self.occurrences)
        await self.rejected_async(changed)
        self.assertEqual(await self.snapshot(), before)

    async def test_unknown_commit_recovery_keeps_one_identity(self):
        real_client = self.client
        class UncertainSession:
            def __init__(inner, session): inner.session = session
            async def __aenter__(inner): return inner
            async def __aexit__(inner, *args): await inner.session.end_session()
            async def with_transaction(inner, callback, **kwargs):
                await inner.session.with_transaction(callback, **kwargs)
                raise OperationFailure("Synthetic lost commit confirmation", details={"errorLabels":["UnknownTransactionCommitResult"]})
        class UncertainClient:
            async def start_session(inner): return UncertainSession(await real_client.start_session())
        self.ctx.ns["client"] = UncertainClient()
        try:
            await self.rejected_async(self.create, 503)
        finally:
            self.ctx.ns["client"] = real_client
        before = await self.snapshot()
        recovered = await self.transaction(self.create)
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(await self.db.shared_obligations.count_documents({}), 1)
        self.assertEqual(recovered["_id"], before["shared_obligations"][0]["_id"])

    async def test_inspection_snapshot_and_concurrent_identity_revision(self):
        doc = await self.transaction(self.create)
        reading, committed = asyncio.Event(), asyncio.Event()

        async def read_snapshot(session):
            await self.db.shared_obligations.find_one({"_id": doc["_id"]}, session=session)
            reading.set()
            await asyncio.wait_for(committed.wait(), 15)
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)

        async def writer():
            await asyncio.wait_for(reading.wait(), 15)
            async def update(session):
                await self.db.shared_obligations.update_one({"_id": doc["_id"]},
                    {"$set": {"actual_amount": shared.Decimal128("80"), "revision": 1}}, session=session)
                await self.db.bills.update_one({"id": "bill"}, {"$set": {"amount": 80}}, session=session)
            await self.transaction(update)
            committed.set()

        result, _ = await asyncio.wait_for(asyncio.gather(self.transaction(read_snapshot), writer()), 30)
        self.assertEqual(result.remaining, 100)  # both reads belong to the old snapshot
        before = await self.snapshot()
        async def stale(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        await self.rejected_async(stale)  # writer wins before this transaction
        current = await self.db.shared_obligations.find_one({"_id": doc["_id"]})
        async def fresh(session):
            return await shared.inspect_payments(self.db, current, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        self.assertEqual((await self.transaction(fresh)).remaining, 80)
        self.assertEqual(await self.snapshot(), before)

    async def test_legacy_foreign_period_partials_replay_and_readonly_exclusion(self):
        doc = await self.transaction(self.create)
        bill, rp = parents()
        bill.update(_id="legacy-nov", id="legacy-nov", due_date="2026-11-20")
        await self.insert("bills", bill)
        results = []
        for amount, key in ((70, "nov-seventy"), (30, "nov-thirty"), (70, "nov-seventy")):
            response = await self.ctx.request("POST", "/bills/legacy-nov/payments",
                json={"amount": amount, "account_id": "account"}, headers={"Idempotency-Key": key})
            self.assertEqual(response.status_code, 200, response.text)
            results.append(response.json())
        self.assertEqual(results[0]["id"], results[2]["id"])
        self.assertNotEqual(results[0]["id"], results[1]["id"])
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual((result.paid, result.remaining, result.transaction_ids), (0, 100, ()))
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(len(before["bill_payments"]), 2)
        self.assertEqual(len(before["recurring_payment_records"]), 2)
        self.assertEqual(len(before["transactions"]), 2)
        self.assertEqual(len(before["shared_obligations"]), 1)
        self.assertEqual(before["accounts"][0]["current_balance"], 900)
