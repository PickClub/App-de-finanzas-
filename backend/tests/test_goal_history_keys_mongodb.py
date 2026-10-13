"""Opt-in goal key tests: one NEW retained DB, actual async route callbacks.

MONEYFLOW_C3_GOAL_KEYS_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_goal_history_keys_mongodb
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
from backend.tests import test_goal_history_keys as cases
from backend.tests import test_payment_consistency as memory

from backend.tests import test_ordinary_history_keys_mongodb as isolation

URI = "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true"
PREFIX = "test_c3_goal_keys_"


class Audit(isolation.Audit):
    def started(self, event):
        if event.database_name == self.name and event.command_name == 'findAndModify':
            self.events.append((event.database_name, event.command_name))
        else:
            super().started(event)


class ScopedDB:
    def __init__(self, database, name, prefix):
        self.database, self.name, self.prefix = database, name, prefix

    def __getattr__(self, collection):
        assert self.database.name == self.name and self.name.startswith(PREFIX)
        return self.database[self.prefix + collection]


@unittest.skipUnless(os.environ.get("MONEYFLOW_C3_GOAL_KEYS_REAL_TESTS") == "1", "Explicit isolated MongoDB opt-in required")
class GoalKeyMongoTests(cases.GoalKeyCases, unittest.IsolatedAsyncioTestCase):
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
            client[cls.name].experiment.insert_one({"_id": "synthetic-only", "retained": True, "purpose": "goal transfer key maintenance"})
        print("NEW SYNTHETIC DATABASE RETAINED:", cls.name, flush=True)

    @classmethod
    def tearDownClass(cls):
        assert not cls.audit.violations, cls.audit.violations
        assert {db for db, _ in cls.audit.events} <= {"admin", cls.name}
        print("ISOLATION VERIFIED; NO DROP OR EXPLICIT INDEX:", cls.name, flush=True)

    async def asyncSetUp(self):
        cases.setup_memory(self)
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

    async def test_real_withdrawals_conflict_and_revalidate(self):
        await self.contribute(amount=100)
        original=self.ns['recompute_goal']
        arrived,release=asyncio.Event(),asyncio.Event()
        calls={}
        async def overlap(gid,session=None):
            task=asyncio.current_task()
            calls[task]=calls.get(task,0)+1
            if calls[task]==1:
                # Establish both transaction snapshots before either writes.
                await self.db.saving_goals.find_one({'id':gid},session=session)
                if not arrived.is_set():
                    arrived.set();await asyncio.wait_for(release.wait(),10)
                else:release.set()
            return await original(gid,session=session)
        async def withdraw(key):
            return await self.request('POST','/goals/goal/contributions',dict(amount=70,kind='withdrawal',real_movement=True,account_id='source',date='2026-10-01'),key)
        with patch.dict(self.ns,{'recompute_goal':overlap}):
            responses=await asyncio.gather(withdraw('one'),withdraw('two'))
        self.assertEqual(sorted(r.status_code for r in responses),[200,422])
        self.assertGreaterEqual(sum(calls.values()),4)
        self.assertEqual((await self.db.saving_goals.find_one({'id':'goal'}))['current_amount'],30)
        self.assertEqual(await self.balances(),[970,1030,1000])
        state=await self.snapshot()
        self.assertEqual(len(state['transactions']),2)
        for t in state['transactions']:self.assertEqual(inspect_history_keys(t,1),'ready')
        print('REAL WITHDRAWAL REVALIDATION CALLS',sorted(calls.values()),flush=True)

    async def test_real_confirmation_lost_and_original_retry(self):
        start=self.client.start_session
        async def lost(*args,**kwargs):
            session=await start(*args,**kwargs)
            original=session.with_transaction
            async def uncertain(callback,**options):
                await original(callback,**options)
                raise OperationFailure('Synthetic confirmation lost after real commit',details={'errorLabels':['UnknownTransactionCommitResult']})
            session.with_transaction=uncertain
            return session
        with patch.object(self.client,'start_session',side_effect=lost):await self.contribute(status=503)
        before=await self.snapshot()
        p=await self.contribute()
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(inspect_history_keys(await self.transfer(p),1),'ready')
        self.assertEqual(await self.balances(),[950,1050,1000])


if __name__=='__main__':unittest.main()
