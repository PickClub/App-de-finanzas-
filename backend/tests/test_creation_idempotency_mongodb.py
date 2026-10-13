"""Opt-in R5: new synthetic databases only; no existing DB access or cleanup."""
import asyncio
import os
import unittest
import uuid
from unittest.mock import patch

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from backend.tests.test_reference_integrity import context
from backend.tests.test_reference_mongodb import ConflictAudit
from backend.tests.test_creation_idempotency import CreationCases


@unittest.skipUnless(os.environ.get("MONEYFLOW_R5_REAL_TESTS") == "1", "Explicit R5 real opt-in required")
class CreationMongoTests(CreationCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.name = "test_r5_creation_" + uuid.uuid4().hex
        self.audit = ConflictAudit()
        self.client = AsyncIOMotorClient("mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true",
            serverSelectionTimeoutMS=5000, event_listeners=[self.audit])
        self.addCleanup(self.client.close)
        hello = await self.client.admin.command("hello")
        self.assertEqual(self.client.address, ("127.0.0.1",27018))
        self.assertEqual(hello.get("setName"), "app_finanzas_dev_rs")
        self.assertTrue(hello.get("isWritablePrimary"))
        self.assertIsNotNone(hello.get("logicalSessionTimeoutMinutes"))
        self.db = self.client[self.name]
        self.assertTrue(self.name.startswith("test_r5_creation_"))
        self.assertEqual(await self.db.list_collection_names(), [])
        self.collections = ("accounts","categories","transactions","debts","debt_payments","bills","bill_payments",
            "recurring_payments","recurring_payment_records","recurring_templates","saving_goals","goal_contributions",
            "budgets","users","moneyflow_metadata","shared_obligations","shared_tracking_intents")
        for col in self.collections:
            await self.db.create_collection(col)
        self.ctx = context(self.db, self.client)
        print("R5 VERIFIED NEW DB:", self.name, self._testMethodName, flush=True)

    async def asyncTearDown(self):
        for database, command, address in self.audit.events:
            self.assertIn(database, (self.name,"admin"))
            self.assertEqual(address, ("127.0.0.1",27018))
            self.assertNotIn(command, ("drop","dropDatabase","dropIndexes","createIndexes"))
        print("R5 DB RETAINED:", self.name, flush=True)

    async def insert(self, collection, doc):
        await self.db[collection].insert_one(dict(doc, _id=doc["id"]))

    async def race(self, kind, first, second, key="race"):
        hook = "_validate_budget" if kind == "budget" else "_bill_validate"
        original = self.ctx.ns[hook]
        barrier = asyncio.Barrier(2)
        calls = 0
        async def synchronized(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls <= 2:
                await asyncio.wait_for(barrier.wait(), 10)
            return await original(*args, **kwargs)
        with patch.dict(self.ctx.ns, {hook:synchronized}):
            responses = await asyncio.wait_for(asyncio.gather(self.create(kind,first,key),self.create(kind,second,key)), 30)
        self.assertTrue(any(code in (112,11000) for code in self.audit.failures))
        return responses

    async def test_concurrent_identical_requests_create_one(self):
        f = await self.prepare()
        for kind in ("budget","bill"):
            p = self.payload(kind,f)
            responses = await self.race(kind,p,p)
            self.assertEqual([r.status_code for r in responses], [200,200])
            self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])
            self.assertEqual(await self.db["budgets" if kind=="budget" else "bills"].count_documents({"name":"R5 synthetic"}),1)
        self.assertEqual(await self.db.transactions.count_documents({}),0)
        self.assertTrue(all(a["current_balance"]==1000 for a in await self.db.accounts.find({}).to_list(None)))

    async def test_concurrent_different_requests_reject_one(self):
        f = await self.prepare()
        await self.insert("categories",dict(id="other",user_id="default-user",name="Other",type="expense",is_group=False))
        for kind in ("budget","bill"):
            p = dict(self.payload(kind,f),category_id=f["category"])
            other = dict(self.payload(kind,f,250),category_id="other")
            responses = await self.race(kind,p,other)
            self.assertEqual(sorted(r.status_code for r in responses), [200,409])
            winner = next(r.json() for r in responses if r.status_code==200)
            field = "amount_limit" if kind=="budget" else "amount"
            docs = await self.db["budgets" if kind=="budget" else "bills"].find({"name":"R5 synthetic"}).to_list(None)
            self.assertEqual(len(docs),1)
            self.assertEqual(docs[0][field],winner[field])
        self.assertEqual(await self.db.transactions.count_documents({}),0)

    async def test_failure_after_insert_rolls_back_all_writes(self):
        f = await self.prepare()
        for kind in ("budget","bill"):
            before = await self.snapshot()
            original = self.ctx.ns["payment_transaction"]
            async def fail_transaction(callback):
                async def fail_after(session):
                    await callback(session)
                    raise OperationFailure("Synthetic failure after insert")
                return await original(fail_after)
            with patch.dict(self.ctx.ns,{"payment_transaction":fail_transaction}):
                self.assertEqual((await self.create(kind,self.payload(kind,f))).status_code,503)
            self.assertEqual(await self.snapshot(),before)

    async def test_lost_commit_response_recovers_without_second_creation(self):
        f = await self.prepare()
        real = self.client
        class Session:
            def __init__(self,session): self.session=session
            async def __aenter__(self): return self
            async def __aexit__(self,*args): await self.session.end_session()
            async def with_transaction(self,callback,**kwargs):
                await self.session.with_transaction(callback,**kwargs)
                raise OperationFailure("Synthetic lost commit response",details={"errorLabels":["UnknownTransactionCommitResult"]})
        class Client:
            async def start_session(self): return Session(await real.start_session())
        for kind in ("budget","bill"):
            p=self.payload(kind,f)
            with patch.dict(self.ctx.ns,{"client":Client()}):
                self.assertEqual((await self.create(kind,p)).status_code,503)
            before=await self.snapshot()
            self.assertEqual((await self.create(kind,p)).status_code,200)
            self.assertEqual(await self.snapshot(),before)
