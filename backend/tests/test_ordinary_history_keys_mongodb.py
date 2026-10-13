"""Opt-in real ordinary routes, ONE new retained synthetic database per run.

MONEYFLOW_C3_ORDINARY_KEYS_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_ordinary_history_keys_mongodb
No imports of server startup, dotenv, existing databases, index creation or cleanup.
"""
import asyncio
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient, monitoring
from pymongo.errors import OperationFailure
from pymongo.uri_parser import parse_uri
from backend.history_keys import inspect_history_keys
from backend.tests import test_payment_consistency as memory
from backend.tests import test_ordinary_history_keys as cases

URI = "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true"
PREFIX = "test_c3_ordinary_keys_"


class Audit(monitoring.CommandListener):
    def __init__(self, name):
        self.name, self.violations, self.events = name, [], []

    def started(self, event):
        self.events.append((event.database_name, event.command_name))
        allowed = {"create", "find", "insert", "update", "delete", "aggregate", "getMore", "killCursors"}
        admin = {"hello", "commitTransaction", "abortTransaction", "endSessions", "listDatabases"}
        valid = (event.database_name == self.name and event.command_name in allowed) or (event.database_name == "admin" and event.command_name in admin)
        if event.command_name == "listDatabases":
            valid = valid and event.command.get("filter") == {"name": self.name} and event.command.get("nameOnly") is True
        if not valid:
            self.violations.append((event.database_name, event.command_name))

    def succeeded(self, event):
        pass

    def failed(self, event):
        pass


class ScopedDB:
    def __init__(self, database, name, prefix):
        self.database, self.name, self.prefix = database, name, prefix

    def __getattr__(self, collection):
        if self.database.name != self.name or not self.name.startswith(PREFIX):
            raise AssertionError("Synthetic database mismatch")
        return self.database[self.prefix + collection]


@unittest.skipUnless(os.environ.get("MONEYFLOW_C3_ORDINARY_KEYS_REAL_TESTS") == "1", "Explicit isolated MongoDB opt-in required")
class OrdinaryKeyMongoTests(cases.OrdinaryKeyCases, unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        parsed = parse_uri(URI)
        assert parsed["nodelist"] == [("127.0.0.1", 27018)] and parsed["database"] is None
        assert parsed["options"]["replicaset"] == "app_finanzas_dev_rs" and parsed["options"]["directconnection"]
        cls.name = PREFIX + uuid.uuid4().hex
        cls.audit = Audit(cls.name)
        with MongoClient(URI, connect=False, serverSelectionTimeoutMS=3000, event_listeners=[cls.audit]) as client:
            hello = client.admin.command("hello")
            assert client.address == ("127.0.0.1", 27018) and hello["isWritablePrimary"]
            assert hello["setName"] == "app_finanzas_dev_rs" and hello.get("logicalSessionTimeoutMinutes") and hello["maxWireVersion"] >= 7
            assert not client.admin.command({"listDatabases": 1, "filter": {"name": cls.name}, "nameOnly": True})["databases"]
            client[cls.name].create_collection("experiment", check_exists=False)
            client[cls.name].experiment.insert_one({"_id": "synthetic-only", "retained": True, "purpose": "actual ordinary route key maintenance"})
        print("NEW SYNTHETIC DATABASE RETAINED:", cls.name, flush=True)

    @classmethod
    def tearDownClass(cls):
        assert not cls.audit.violations, cls.audit.violations
        assert {db for db, _ in cls.audit.events} <= {"admin", cls.name}
        print("ISOLATION VERIFIED; NO DROP OR EXPLICIT INDEX:", cls.name, flush=True)

    async def asyncSetUp(self):
        memory.PaymentTests.setUp(self)
        initial = self.db.data
        # One reused client per isolated async test; enough pool for two concurrent requests.
        self.client = AsyncIOMotorClient(URI, connect=False, serverSelectionTimeoutMS=3000,
                                        maxPoolSize=4, event_listeners=[self.audit])
        self.addCleanup(self.client.close)
        hello = await self.client.admin.command("hello")
        self.assertTrue(hello["isWritablePrimary"])
        self.assertEqual(self.client.address, ("127.0.0.1", 27018))
        prefix = self._testMethodName + "_"
        physical = self.client[self.name]
        self.db = ScopedDB(physical, self.name, prefix)
        for collection in initial:
            await physical.create_collection(prefix + collection, check_exists=False)
            if initial[collection]:
                await getattr(self.db, collection).insert_many(initial[collection])
        self.ns.update(db=self.db, client=self.client,
                       settings=SimpleNamespace(history_keys_write_enabled=True, history_keys_generation=1))

    async def test_real_concurrent_edits_retry_and_rederive_fresh_document(self):
        tx = await self.add()
        read_keys = self.ns["history_update_fields"]
        validate = self.ns["validate_transaction"]
        arrived, release = asyncio.Event(), asyncio.Event()
        attempts = {}
        derived = []
        def record_keys(current, final, generation):
            derived.append((final["amount"], final["date"]))
            return read_keys(current, final, generation)
        async def overlap(payload, current=None, session=None):
            task = asyncio.current_task()
            attempts[task] = attempts.get(task, 0) + 1
            if attempts[task] == 1:
                if not arrived.is_set():
                    arrived.set()
                    await asyncio.wait_for(release.wait(), 10)
                else:
                    release.set()
            return await validate(payload, current, session=session)
        with patch.dict(self.ns, {"validate_transaction": overlap, "history_update_fields": record_keys}):
            await asyncio.gather(self.edit(tx["id"], amount=120, date="2026-10-02"),
                                 self.edit(tx["id"], amount=130, date="2026-10-03"))
        self.assertGreaterEqual(sum(attempts.values()), 3)
        stored = await self.stored(tx["id"])
        self.assertEqual(inspect_history_keys(stored, 1), "ready")
        self.assertIn((stored["amount"], stored["date"]), {(120, "2026-10-02"), (130, "2026-10-03")})
        self.assertEqual(await self.balance(), 1000 - stored["amount"])
        self.assertIn((stored["amount"], stored["date"]), derived)
        print("REAL CONFLICT RETRIES", sorted(attempts.values()), flush=True)

    async def test_real_commit_confirmation_lost_no_automatic_post_replay(self):
        original_start = self.client.start_session
        callbacks = []
        async def start_session(*args, **kwargs):
            session = await original_start(*args, **kwargs)
            commit = session.commit_transaction
            async def commit_then_uncertain():
                await commit()
                callbacks.append(1)
                raise OperationFailure("Synthetic lost confirmation after real commit", details={"errorLabels": ["UnknownTransactionCommitResult"]})
            session.commit_transaction = commit_then_uncertain
            return session
        with patch.object(self.client, "start_session", side_effect=start_session):
            response = await self.request("POST", "/transactions", json=self.payload())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(len(callbacks), 1)
        stored = await self.db.transactions.find_one({})
        self.assertEqual(inspect_history_keys(stored, 1), "ready")
        self.assertEqual(await self.balance(), 900)
        self.assertEqual(await self.db.transactions.count_documents({}), 1)


if __name__ == "__main__":
    unittest.main()
