"""Opt-in shared key financial tests: one NEW retained DB, actual async route callbacks.

MONEYFLOW_C3_SHARED_KEYS_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_shared_history_keys_mongodb
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
from backend import shared_obligations as shared
from fastapi import HTTPException
from backend.tests.test_shared_obligations import ENVIRONMENT, USER
from backend.tests import test_shared_payments as core
from backend.tests import test_shared_history_keys as cases
from backend.history_keys import inspect_history_keys
from backend.tests.test_shared_obligations import activation_settings
from backend.tests import test_payment_consistency as memory

from backend.tests import test_ordinary_history_keys_mongodb as isolation

URI = "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true"
PREFIX = "test_c3_shared_keys_"


class Audit(isolation.Audit):
    def started(self, event):
        if event.database_name == self.name and event.command_name in ('findAndModify','listIndexes','createIndexes'):
            if event.command_name == 'createIndexes':
                assert event.command['createIndexes'].endswith('_shared_obligations')
                expected = dict(shared.INDEXES)
                for index in event.command['indexes']:
                    assert index['name'] in expected and index.get('unique') is True
                    assert tuple(index['key'].items()) == expected[index['name']]
            self.events.append((event.database_name, event.command_name))
        else:
            super().started(event)


class ScopedDB:
    def __init__(self, database, name, prefix):
        self.database, self.name, self.prefix = database, name, prefix

    @property
    def client(self):
        return self.database.client

    def __getattr__(self, collection):
        assert self.database.name == self.name and self.name.startswith(PREFIX)
        return self.database[self.prefix + collection]


@unittest.skipUnless(os.environ.get("MONEYFLOW_C3_SHARED_KEYS_REAL_TESTS") == "1", "Explicit isolated MongoDB opt-in required")
class SharedKeyMongoPrerequisites(cases.SharedHistoryTests):
    snapshot = core.PaymentCases.snapshot
    transact = core.PaymentCases.transact
    intent = core.PaymentCases.intent
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
            client[cls.name].experiment.insert_one({"_id": "synthetic-only", "retained": True, "purpose": "shared history key financial validation"})
        print("NEW SYNTHETIC DATABASE RETAINED:", cls.name, flush=True)

    @classmethod
    def tearDownClass(cls):
        assert not cls.audit.violations, cls.audit.violations
        assert {db for db, _ in cls.audit.events} <= {"admin", cls.name}
        print("ISOLATION VERIFIED; ONLY AUTHORIZED R4 INDEXES; NO DROP:", cls.name, flush=True)

    async def asyncSetUp(self):
        await core.SharedPaymentTests.asyncSetUp(self)
        initial = self.db.data
        missing = self._testMethodName == "test_real_missing_indexes_block_creation_and_annulment_without_writes"
        if not missing:
            initial["shared_obligations"] = []
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
        self.ctx.ns.update(db=self.db, client=self.client)
        self.history_settings = SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)
        if not missing:
            await shared.install_indexes(self.db)
            await shared.require_indexes(self.db)
            self.ob = await self.transact(lambda session: shared.create_shared_obligation(self.db,"bill",
                expected_environment_id=ENVIRONMENT,effective_user=USER,session=session,
                occurrences=self.ctx.ns["_rp_occurrences"]))

    async def asyncTearDown(self):
        state = await self.snapshot()
        for collection,docs in state.items():
            if collection != 'transactions':
                for doc in docs:
                    self.assertNotIn('_history_keys',doc)
        indexes = await self.db.shared_obligations.index_information()
        expected = dict(shared.INDEXES)
        self.assertEqual(set(indexes)-{'_id_'}, set() if 'missing_indexes' in self._testMethodName else set(expected))
        print('REAL SCENARIO FINISHED:',self._testMethodName,flush=True)


    async def test_real_missing_indexes_block_creation_and_annulment_without_writes(self):
        before = await self.snapshot()
        start = len(self.audit.events)
        settings = SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)
        callbacks = [
            lambda session: shared.register_shared_payment(self.db,self.ob['_id'],
                **self.intent('new',30),expected_environment_id=ENVIRONMENT,effective_user=USER,
                session=session,recompute_account_balance=self.ctx.ns['recompute_account_balance'],history_settings=settings),
            lambda session: shared.change_shared_payment(self.db,self.ob['_id'],origin='bill',receipt_id='absent',action='annul',
                expected_environment_id=ENVIRONMENT,effective_user=USER,session=session,
                recompute_account_balance=self.ctx.ns['recompute_account_balance']),
        ]
        for callback in callbacks:
            with self.assertRaises(HTTPException) as e:await self.transact(callback)
            self.assertEqual(e.exception.status_code,503)
        self.assertEqual(await self.snapshot(),before)
        self.assertFalse(any(c in {'insert','update','delete','findAndModify','createIndexes'} for _,c in self.audit.events[start:]))

    def lose_confirmation(self):
        start=self.client.start_session
        async def lost(*args,**kwargs):
            session=await start(*args,**kwargs)
            original=session.with_transaction
            async def uncertain(callback,**options):
                await original(callback,**options)
                raise OperationFailure('Synthetic client confirmation lost after real commit',details={'errorLabels':['UnknownTransactionCommitResult']})
            session.with_transaction=uncertain
            return session
        return patch.object(self.client,'start_session',side_effect=lost)

    async def test_uncertain_commit_original_recovery(self):
        with self.lose_confirmation():
            with self.assertRaises(HTTPException) as e:await self.pay('uncertain')
            self.assertEqual(e.exception.status_code,503)
        before=await self.snapshot()
        p=await self.pay('uncertain')
        self.assertFalse(p.created)
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(inspect_history_keys(await self.tx(p),1),'ready')
        with self.lose_confirmation():
            with self.assertRaises(HTTPException) as e:await self.change('uncertain','bill','annul')
            self.assertEqual(e.exception.status_code,503)
        before=await self.snapshot()
        await self.change('uncertain','bill','annul')
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(before['accounts'][0]['current_balance'],1000)

    async def test_public_adapter_passes_control_and_disabled_r4_blocks(self):
        self.ctx.ns['settings']=SimpleNamespace(**{**vars(activation_settings('1')),'history_keys_write_enabled':True,'history_keys_generation':1})
        for origin,key in (('bill','public-bill'),('recurring','public-recurring')):
            payload=self.ctx.ns['BillPayIn'](amount=30,account_id='account',date='2026-10-01T00:00:00+00:00').model_dump()
            path='/bills/bill/payments'
            if origin=='recurring':
                path='/recurring-payments/rp/payments'
                payload.update(mode='expense',due_date=self.ob['original_due_date'])
            r=await self.ctx.request('POST',path,json=payload,headers={'Idempotency-Key':key})
            self.assertEqual(r.status_code,200,r.text)
            self.assertNotIn('_history',r.text)
            tx=await self.db.transactions.find_one({'id':r.json()['transaction_id']})
            self.assertEqual(inspect_history_keys(tx,1),'ready')
        self.ctx.ns['settings']=activation_settings('0')
        before=await self.snapshot()
        r=await self.ctx.request('POST','/bills/bill/payments',json=dict(amount=30,account_id='account'),headers={'Idempotency-Key':'blocked'})
        self.assertEqual(r.status_code,409,r.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_real_concurrent_overpayment_revalidates_snapshot(self):
        original=shared._lock_payment_obligation
        gate=asyncio.Barrier(2)
        attempts={}
        async def synchronized(*args,**kwargs):
            task=asyncio.current_task()
            attempts[task]=attempts.get(task,0)+1
            if attempts[task]==1:await asyncio.wait_for(gate.wait(),15)
            return await original(*args,**kwargs)
        async def outcome(fn):
            try:return await fn()
            except HTTPException as e:return e.status_code
        with patch.object(shared,'_lock_payment_obligation',synchronized):
            results=await asyncio.wait_for(asyncio.gather(outcome(lambda:self.pay('one',70)),outcome(lambda:self.pay('two',70,origin='recurring',account='second'))),30)
        self.assertEqual(sum(isinstance(r,shared.SharedPaymentResult) for r in results),1)
        self.assertIn(409,results)
        self.assertGreaterEqual(sum(attempts.values()),3)
        state=await self.snapshot()
        self.assertEqual(len(state['transactions']),1)
        self.assertEqual(sum(t['amount'] for t in state['transactions']),70)
        self.assertEqual(sum(a['current_balance'] for a in state['accounts']),1930)
        self.assertEqual(inspect_history_keys(state['transactions'][0],1),'ready')
        print('REAL SHARED LOCK ATTEMPTS',sorted(attempts.values()),flush=True)

    async def test_real_restore_rollback_preserves_journal_and_money(self):
        p=await self.pay('one')
        await self.change('one','bill','retire_recurring')
        before=await self.snapshot()
        original=shared.register_shared_tracking
        async def fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise HTTPException(503,'Synthetic after administrative journal write')
        with patch.object(shared,'register_shared_tracking',fail):
            with self.assertRaises(HTTPException):await self.tracking('restore','link',p.transaction_id)
        self.assertEqual(await self.snapshot(),before)
        await self.tracking('restore','link',p.transaction_id)
        self.assertEqual((await self.tx(p))['_history_keys'],before['transactions'][0]['_history_keys'])
        self.assertEqual((await self.snapshot())['accounts'][0]['current_balance'],970)


if __name__=='__main__':unittest.main()
