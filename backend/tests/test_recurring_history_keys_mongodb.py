"""Opt-in recurring key tests: one NEW retained DB, actual async route callbacks.

MONEYFLOW_C3_RECURRING_KEYS_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_recurring_history_keys_mongodb
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
from backend.tests import test_recurring_history_keys as cases
from backend.tests import test_payment_consistency as memory

from backend.tests import test_ordinary_history_keys_mongodb as isolation

URI = "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true"
PREFIX = "test_c3_recurring_keys_"


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


@unittest.skipUnless(os.environ.get("MONEYFLOW_C3_RECURRING_KEYS_REAL_TESTS") == "1", "Explicit isolated MongoDB opt-in required")
class RecurringKeyMongoTests(cases.RecurringKeyCases, unittest.IsolatedAsyncioTestCase):
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
            client[cls.name].experiment.insert_one({"_id": "synthetic-only", "retained": True, "purpose": "recurring expense key maintenance"})
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

    async def test_real_expense_conflict_revalidates_period(self):
        original=self.ns['coordinate']
        arrived,release=asyncio.Event(),asyncio.Event()
        attempts={}
        async def overlap(db,user,refs,session,**kwargs):
            if refs.get('recurring_id')=='rp':
                task=asyncio.current_task()
                attempts[task]=attempts.get(task,0)+1
                if attempts[task]==1:
                    await self.db.recurring_payments.find_one({'id':'rp'},session=session)
                    if not arrived.is_set():
                        arrived.set();await asyncio.wait_for(release.wait(),10)
                    else:release.set()
            return await original(db,user,refs,session,**kwargs)
        async def pay(key,account):
            return await self.request('POST','/recurring-payments/rp/payments',dict(mode='expense',amount=70,account_id=account,due_date='2026-10-20',date='2026-10-01'),key)
        with patch.dict(self.ns,{'coordinate':overlap}):
            responses=await asyncio.gather(pay('one','a'),pay('two','b'))
        self.assertEqual(sorted(r.status_code for r in responses),[200,422])
        self.assertGreaterEqual(sum(attempts.values()),3)
        state=await self.snapshot()
        self.assertEqual(len(state['transactions']),1)
        self.assertEqual(sum(p['amount'] for p in state['recurring_payment_records']),70)
        self.assertEqual(sum(a['current_balance'] for a in state['accounts']),1930)
        self.assertEqual(inspect_history_keys(state['transactions'][0],1),'ready')
        print('REAL RECURRING COORDINATION ATTEMPTS',sorted(attempts.values()),flush=True)

    def lose_confirmation(self):
        start=self.client.start_session
        async def lost(*args,**kwargs):
            session=await start(*args,**kwargs)
            original=session.with_transaction
            async def uncertain(callback,**options):
                await original(callback,**options)
                raise OperationFailure('Synthetic confirmation lost after real commit',details={'errorLabels':['UnknownTransactionCommitResult']})
            session.with_transaction=uncertain
            return session
        return patch.object(self.client,'start_session',side_effect=lost)

    async def test_real_confirmation_lost_and_original_retry(self):
        with self.lose_confirmation():await self.pay(status=503)
        before=await self.snapshot()
        p=await self.pay()
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')
        self.assertEqual(await self.balance(),970)

    async def test_real_delete_confirmation_lost_refund_once(self):
        p=await self.pay()
        with self.lose_confirmation():await self.remove(p,status=503)
        before=await self.snapshot()
        await self.remove(p)
        self.assertEqual(await self.snapshot(),before)
        self.assertIsNone(await self.tx(p))
        self.assertEqual(await self.balance(),1000)

    async def test_real_concurrent_delete_refunds_once(self):
        p=await self.pay()
        await asyncio.gather(self.remove(p),self.remove(p))
        self.assertIsNone(await self.tx(p))
        self.assertEqual(await self.balance(),1000)
        self.assertTrue((await self.db.recurring_payment_records.find_one({'id':p['id']}))['deleted'])


if __name__=='__main__':unittest.main()
