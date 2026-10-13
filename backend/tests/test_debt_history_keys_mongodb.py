"""Opt-in debt key tests: one NEW retained DB, actual async route callbacks.

MONEYFLOW_C3_DEBT_KEYS_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_debt_history_keys_mongodb
"""
import asyncio
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from pymongo.uri_parser import parse_uri
from backend.history_keys import inspect_history_keys
from backend.tests import test_debt_history_keys as cases
from backend.tests import test_payment_consistency as memory
from backend.tests import test_ordinary_history_keys_mongodb as isolation

URI = "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true"
PREFIX = "test_c3_debt_keys_"


class ScopedDB:
    def __init__(self, database, name, prefix):
        self.database, self.name, self.prefix = database, name, prefix

    def __getattr__(self, collection):
        assert self.database.name == self.name and self.name.startswith(PREFIX)
        return self.database[self.prefix + collection]


@unittest.skipUnless(os.environ.get("MONEYFLOW_C3_DEBT_KEYS_REAL_TESTS") == "1", "Explicit isolated MongoDB opt-in required")
class DebtKeyMongoTests(cases.DebtKeyCases, unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        parsed = parse_uri(URI)
        assert parsed["nodelist"] == [("127.0.0.1", 27018)] and parsed["database"] is None
        assert parsed["options"]["replicaset"] == "app_finanzas_dev_rs" and parsed["options"]["directconnection"]
        cls.name = PREFIX + uuid.uuid4().hex
        cls.audit = isolation.Audit(cls.name)
        with MongoClient(URI, connect=False, serverSelectionTimeoutMS=3000, event_listeners=[cls.audit]) as client:
            hello = client.admin.command("hello")
            assert client.address == ("127.0.0.1", 27018) and hello["isWritablePrimary"]
            assert hello["setName"] == "app_finanzas_dev_rs" and hello.get("logicalSessionTimeoutMinutes") and hello["maxWireVersion"] >= 7
            assert not client.admin.command({"listDatabases": 1, "filter": {"name": cls.name}, "nameOnly": True})["databases"]
            client[cls.name].create_collection("experiment", check_exists=False)
            client[cls.name].experiment.insert_one({"_id": "synthetic-only", "retained": True, "purpose": "debt movement key maintenance"})
        print("NEW SYNTHETIC DATABASE RETAINED:", cls.name, flush=True)

    @classmethod
    def tearDownClass(cls):
        assert not cls.audit.violations, cls.audit.violations
        assert {db for db, _ in cls.audit.events} <= {"admin", cls.name}
        print("ISOLATION VERIFIED; NO DROP OR EXPLICIT INDEX:", cls.name, flush=True)

    async def asyncSetUp(self):
        memory.PaymentTests.setUp(self)
        initial = self.db.data
        self.client = AsyncIOMotorClient(URI, connect=False, serverSelectionTimeoutMS=3000, maxPoolSize=4, event_listeners=[self.audit])
        self.addCleanup(self.client.close)
        hello = await self.client.admin.command("hello")
        self.assertTrue(hello["isWritablePrimary"])
        self.assertEqual(self.client.address, ("127.0.0.1", 27018))
        physical = self.client[self.name]
        prefix = self._testMethodName + "_"
        self.db = ScopedDB(physical, self.name, prefix)
        for name in initial:
            await physical.create_collection(prefix + name, check_exists=False)
            if initial[name]:
                await getattr(self.db, name).insert_many(initial[name])
        self.ns.update(db=self.db, client=self.client, settings=SimpleNamespace(history_keys_write_enabled=True, history_keys_generation=1))

    async def test_real_edit_conflict_revalidates_keys_and_receipt(self):
        p = await self.pay()
        validate = self.ns["validate_payment"]
        arrived, release = asyncio.Event(), asyncio.Event()
        attempts = {}
        async def overlap(*args, **kwargs):
            task = asyncio.current_task()
            attempts[task] = attempts.get(task, 0) + 1
            if attempts[task] == 1:
                if not arrived.is_set():
                    arrived.set()
                    await asyncio.wait_for(release.wait(), 10)
                else:
                    release.set()
            return await validate(*args, **kwargs)
        with patch.dict(self.ns, {"validate_payment": overlap}):
            await asyncio.gather(self.edit(p, amount=80, date="2026-10-02"), self.edit(p, amount=90, date="2026-10-03"))
        tx, receipt = await self.stored(p), await self.receipt(p)
        self.assertGreaterEqual(sum(attempts.values()), 3)
        self.assertEqual(inspect_history_keys(tx, 1), "ready")
        self.assertEqual((tx["amount"], tx["date"]), (receipt["amount"], receipt["date"]))
        self.assertEqual(await self.balance(), 1000-tx["amount"])
        self.assertEqual((await self.debt())["remaining_amount"], 500-tx["amount"])
        print("REAL EDIT CONFLICT ATTEMPTS", sorted(attempts.values()), flush=True)

    async def test_real_create_confirmation_lost_and_original_retry(self):
        start = self.client.start_session
        async def lost_after_commit(*args, **kwargs):
            session = await start(*args, **kwargs)
            original = session.with_transaction
            async def uncertain(callback, **options):
                await original(callback, **options)
                raise OperationFailure("Synthetic lost application confirmation after real commit", details={"errorLabels": ["UnknownTransactionCommitResult"]})
            session.with_transaction = uncertain
            return session
        with patch.object(self.client, "start_session", side_effect=lost_after_commit):
            await self.pay(expected=503)
        before = await self.snapshot()
        p = await self.pay()
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(inspect_history_keys(await self.stored(p), 1), "ready")
        self.assertEqual(await self.balance(), 900)

    async def test_real_delete_confirmation_lost_no_second_refund(self):
        p = await self.pay()
        start = self.client.start_session
        async def lost_after_commit(*args, **kwargs):
            session = await start(*args, **kwargs)
            original = session.with_transaction
            async def uncertain(callback, **options):
                await original(callback, **options)
                raise OperationFailure("Synthetic lost delete confirmation", details={"errorLabels": ["UnknownTransactionCommitResult"]})
            session.with_transaction = uncertain
            return session
        with patch.object(self.client, "start_session", side_effect=lost_after_commit):
            response = await self.request("DELETE", "/debt-payments/" + p["id"])
            self.assertEqual(response.status_code, 503, response.text)
        before = await self.snapshot()
        response = await self.request("DELETE", "/debt-payments/" + p["id"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(await self.snapshot(), before)
        self.assertIsNone(await self.stored(p))
        self.assertEqual(await self.balance(), 1000)

    async def test_real_concurrent_deletes_refund_once(self):
        p = await self.pay()
        responses = await asyncio.gather(self.request("DELETE", "/debt-payments/" + p["id"]), self.request("DELETE", "/debt-payments/" + p["id"]))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual(await self.balance(), 1000)
        self.assertIsNone(await self.stored(p))
        self.assertTrue((await self.receipt(p))["deleted"])


if __name__ == "__main__":
    unittest.main()
