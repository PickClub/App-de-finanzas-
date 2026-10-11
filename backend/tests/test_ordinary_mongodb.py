"""Opt-in R1 tests on a unique disposable DB at the fixed local replica set.

MONEYFLOW_R1_REAL_TESTS=1 python -B -m unittest backend.tests.test_ordinary_mongodb
Never imports the server, loads .env, or uses the financial development DB.
"""
import asyncio
import os
import unittest
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import monitoring
from fastapi import HTTPException
from backend.tests import test_payment_consistency as harness


class CommandAudit(monitoring.CommandListener):
    def __init__(self):
        self.events = []

    def started(self, event):
        self.events.append((event.database_name, event.command_name, event.connection_id))

    def succeeded(self, event):
        pass

    def failed(self, event):
        pass


class IsolatedDatabase:
    def __init__(self, database, client, name):
        self.database, self.client, self.name = database, client, name

    def __getattr__(self, collection):
        assert self.database.name == self.name
        assert self.client.address == ("127.0.0.1", 27018)
        return self.database[collection]


@unittest.skipUnless(os.environ.get("MONEYFLOW_R1_REAL_TESTS") == "1", "Real MongoDB tests are opt-in")
class OrdinaryMongoDBTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.name = "moneyflow_r1_temp_" + uuid.uuid4().hex
        self.audit = CommandAudit()
        self.client = AsyncIOMotorClient(
            f"mongodb://127.0.0.1:27018/{self.name}?replicaSet=app_finanzas_dev_rs&directConnection=true",
            serverSelectionTimeoutMS=5000, event_listeners=[self.audit],
        )
        self.db = self.client.get_default_database()
        self.initialized = False
        self.addAsyncCleanup(self.cleanup)
        hello = await self.client.admin.command("hello")
        self.assertEqual(self.client.address, ("127.0.0.1", 27018))
        self.assertEqual(hello.get("setName"), "app_finanzas_dev_rs")
        self.assertTrue(hello.get("isWritablePrimary"))
        self.assertIsNotNone(hello.get("logicalSessionTimeoutMinutes"))
        self.assertEqual(self.db.name, self.name)
        self.assertNotEqual(self.name, "development_local_finanzas")
        self.assertEqual(await self.db.list_collection_names(), [])
        self.context = harness.PaymentTests()
        self.context.setUp()
        self.context.ns.update(db=IsolatedDatabase(self.db, self.client, self.name), client=self.client)
        self.assertEqual(self.context.ns["db"].accounts.database.name, self.name)
        self.initialized = True
        for name in ("accounts", "categories", "debts", "transactions", "debt_payments", "recurring_templates"):
            await self.db.create_collection(name)
        await self.db.accounts.insert_many([
            dict(id="a", user_id="default-user", initial_balance=1000, current_balance=1000),
            dict(id="b", user_id="default-user", initial_balance=500, current_balance=500),
        ])
        await self.db.debts.insert_one(dict(
            id="d", user_id="default-user", name="Synthetic", direction="i_owe",
            original_amount=500, remaining_amount=500, total_paid=0, status="active", start_date="2026-01-01",
        ))

    async def cleanup(self):
        try:
            if self.initialized:
                self.assertTrue(self.name.startswith("moneyflow_r1_temp_"))
                self.assertNotEqual(self.name, "development_local_finanzas")
                self.assertEqual(self.db.name, self.name)
                self.assertEqual(self.client.address, ("127.0.0.1", 27018))
                await self.client.drop_database(self.name)
                self.assertEqual(await self.db.list_collection_names(), [])
                for database, command, address in self.audit.events:
                    self.assertIn(database, (self.name, "admin"))
                    self.assertEqual(address, ("127.0.0.1", 27018))
                print("TEMP DB ISOLATION/CLEANUP VERIFIED:", self.name)
        finally:
            self.client.close()

    async def request(self, method, path, payload=None, expected=200):
        response = await self.context.request(method, path, **({"json": payload} if payload is not None else {}))
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def payload(self, **updates):
        data = dict(name="Synthetic", amount=100, type="expense", account_id="a")
        data.update(updates)
        return data

    async def add(self, **updates):
        return await self.request("POST", "/transactions", self.payload(**updates))

    async def balance(self, account="a"):
        return (await self.db.accounts.find_one({"id": account}))["current_balance"]

    async def snapshot(self):
        return {name: await self.db[name].find({}).sort("_id", 1).to_list(None)
                for name in sorted(await self.db.list_collection_names())}

    async def test_real_conflict_two_expenses_end_at_800(self):
        original = self.context.ns["recompute_account_balance"]
        ready = asyncio.Event()
        calls = 0
        async def overlap(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                ready.set()
            if calls <= 2:
                await asyncio.wait_for(ready.wait(), 5)
            return await original(*args, **kwargs)
        self.context.ns["recompute_account_balance"] = overlap
        await asyncio.wait_for(asyncio.gather(self.add(), self.add()), 15)
        self.assertEqual(await self.balance(), 800)
        self.assertEqual(await self.db.transactions.count_documents({}), 2)
        self.assertGreaterEqual(calls, 3, "A real write conflict must re-execute an aborted transaction")

    async def account_overlap(self, movement_operation, expected_balance):
        original = self.context.ns["recompute_account_balance"]
        ready, release = asyncio.Event(), asyncio.Event()
        calls = 0
        async def pause_first(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                ready.set()
                await asyncio.wait_for(release.wait(), 5)
            return await original(*args, **kwargs)
        self.context.ns["recompute_account_balance"] = pause_first
        task = asyncio.create_task(movement_operation())
        try:
            await asyncio.wait_for(ready.wait(), 5)
            await self.request("PUT", "/accounts/a", {"name": "Changed", "initial_balance": 2000})
        finally:
            release.set()
        await asyncio.wait_for(task, 15)
        self.assertEqual(await self.balance(), expected_balance)
        self.assertGreaterEqual(calls, 3)

    async def test_account_change_and_creation_are_serializable(self):
        await self.account_overlap(self.add, 1900)
        self.assertEqual(await self.db.transactions.count_documents({}), 1)

    async def test_account_change_and_edit_are_serializable(self):
        tx = await self.add()
        async def edit():
            return await self.request("PUT", "/transactions/" + tx["id"], self.payload(amount=200))
        await self.account_overlap(edit, 1800)

    async def test_account_change_and_delete_are_serializable(self):
        tx = await self.add()
        async def delete():
            return await self.request("DELETE", "/transactions/" + tx["id"])
        await self.account_overlap(delete, 2000)
        self.assertEqual(await self.db.transactions.count_documents({}), 0)

    async def test_account_change_and_debt_payment_are_serializable(self):
        async def pay():
            return await self.request("POST", "/debt-payments", dict(debt_id="d", amount=100, account_id="a"))
        await self.account_overlap(pay, 1900)
        self.assertEqual(await self.db.transactions.count_documents({}), 1)
        self.assertEqual(await self.db.debt_payments.count_documents({}), 1)
        self.assertEqual((await self.db.debts.find_one({"id": "d"}))["remaining_amount"], 400)

    async def test_real_rollback_create_edit_delete_and_account(self):
        tx = await self.add()
        original = self.context.ns["recompute_account_balance"]
        async def fail_after_write(*args, **kwargs):
            self.assertTrue(kwargs["session"].in_transaction)
            raise HTTPException(422, "Isolated injected failure after financial write")
        self.context.ns["recompute_account_balance"] = fail_after_write
        for method, path, payload in (
            ("POST", "/transactions", self.payload()),
            ("PUT", "/transactions/" + tx["id"], self.payload(amount=200)),
            ("DELETE", "/transactions/" + tx["id"], None),
            ("PUT", "/accounts/a", dict(name="Changed", initial_balance=2000)),
        ):
            before = await self.snapshot()
            await self.request(method, path, payload, 422)
            self.assertEqual(await self.snapshot(), before)
        self.context.ns["recompute_account_balance"] = original
        self.assertGreaterEqual(sum(command == "abortTransaction" for _, command, _ in self.audit.events), 4)

    async def test_transfer_lifecycle_and_second_balance_rollback(self):
        tx = await self.add(type="transfer", to_account_id="b")
        self.assertEqual((await self.balance(), await self.balance("b")), (900, 600))
        original = self.context.ns["recompute_account_balance"]
        calls = 0
        async def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise HTTPException(422, "Isolated failure between account updates")
            return await original(*args, **kwargs)
        for method in ("POST", "PUT", "DELETE"):
            calls = 0
            self.context.ns["recompute_account_balance"] = fail_second
            before = await self.snapshot()
            path = "/transactions" if method == "POST" else "/transactions/" + tx["id"]
            data = self.payload(type="transfer", to_account_id="b", amount=200) if method != "DELETE" else None
            await self.request(method, path, data, 422)
            self.assertEqual(await self.snapshot(), before)
        self.context.ns["recompute_account_balance"] = original
        await self.request("PUT", "/transactions/" + tx["id"], self.payload(type="transfer", to_account_id="b", amount=200))
        self.assertEqual((await self.balance(), await self.balance("b")), (800, 700))
        await self.request("DELETE", "/transactions/" + tx["id"])
        self.assertEqual((await self.balance(), await self.balance("b")), (1000, 500))
        tx = await self.add()
        await self.request("PUT", "/transactions/" + tx["id"], self.payload(account_id="b"))
        self.assertEqual((await self.balance(), await self.balance("b")), (1000, 400))
