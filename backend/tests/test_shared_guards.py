"""R4 2B route guards: synthetic memory data, no activation or indexes."""
import ast
import copy
from datetime import date
from pathlib import Path
import subprocess
import unittest
import uuid
from unittest.mock import patch, AsyncMock

from pymongo.errors import OperationFailure
from backend import shared_obligations as shared
from backend.tests import test_payment_consistency as memory
from backend.tests.test_reference_integrity import context
from backend.tests.test_shared_obligations import MemoryDatabase, parents, ENVIRONMENT, USER, graph, provenance, metadata


class GuardCases:
    async def fixture_write(self, collection, method, *args):
        async def operation(session):
            return await getattr(getattr(self.db, collection), method)(*args, session=session)
        return await self.ctx.ns["payment_transaction"](operation)

    async def snapshot(self):
        return {c: await getattr(self.db, c).find({}).to_list(None) for c in self.collections}

    async def reserve(self):
        bill = await self.db.bills.find_one({"id": "bill"})
        rp = await self.db.recurring_payments.find_one({"id": "rp"})
        doc = shared.resolve_documents(bill, rp, shared.Scope(ENVIRONMENT, USER), occurrences=self.ctx.ns["_rp_occurrences"])
        # Explicit synthetic fixture, not adoption performed by application code.
        await self.fixture_write("shared_obligations", "insert_one", doc)
        return doc

    async def pay(self):
        response = await self.ctx.request("POST", "/bills/bill/payments", json={"amount": 70, "account_id": "account"},
            headers={"Idempotency-Key": "legacy-seventy"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def assert_blocked(self, method, path, payload=None, code=409):
        before = await self.snapshot()
        response = await self.ctx.request(method, path, **({"json": payload} if payload is not None else {}))
        self.assertEqual(response.status_code, code, response.text)
        self.assertEqual(await self.snapshot(), before)
        return response

    async def test_managed_write_route_matrix_has_zero_changes(self):
        payment = await self.pay()
        await self.reserve()
        matrix = (("POST", "/bills/bill/payments", {"amount": 10, "account_id": "account"}),
            ("PUT", "/bills/bill", {"name": "Synthetic", "amount": 100, "due_date": "2026-10-20"}),
            ("DELETE", "/bills/bill", None),
            ("DELETE", "/bills/payments/"+payment["id"], None),
            ("POST", "/recurring-payments/rp/payments", {"amount": 10, "account_id": "account", "mode": "expense", "due_date": "2026-10-20"}),
            ("POST", "/recurring-payments/rp/payments", {"amount": 10, "mode": "mark", "due_date": "2026-10-20"}),
            ("PUT", "/recurring-payments/rp", {"name": "Synthetic", "amount": 100, "frequency": "monthly", "start_date": "2026-10-20", "due_day": 20}),
            ("DELETE", "/recurring-payments/rp", None),
            ("DELETE", "/recurring-payments/payments/"+payment["recurring_record_id"], None),
            *(("POST", "/recurring-payments/rp/"+action, None) for action in ("pause", "resume", "end")))
        for method, path, payload in matrix:
            with self.subTest(method=method, path=path):
                response = await self.assert_blocked(method, path, payload)
                self.assertIn("R4", response.text)

    async def test_retired_shared_movement_and_inverse_identity_are_protected(self):
        payment = await self.pay()
        await self.fixture_write("transactions", "update_one", {"id": payment["transaction_id"]}, {"$set": {
            "bill_id": None, "bill_payment_id": None, "recurring_payment_id": None, "recurring_record_id": None}})
        await self.fixture_write("bill_payments", "update_one", {"id": payment["id"]}, {"$set": {"deleted": True}})
        await self.fixture_write("recurring_payment_records", "update_one", {"id": payment["recurring_record_id"]}, {"$set": {"deleted": True}})
        await self.reserve()
        for method in ("PUT", "DELETE"):
            await self.assert_blocked(method, "/transactions/"+payment["transaction_id"],
                {"name": "New name", "amount": 70, "type": "expense"} if method == "PUT" else None)
        await self.fixture_write("shared_obligations", "delete_many", {})  # only this test's synthetic reservation
        await self.fixture_write("transactions", "update_one", {"id": payment["transaction_id"]}, {"$set": {"_shared_obligation_id": "corrupt-marker"}})
        await self.assert_blocked("DELETE", "/transactions/"+payment["transaction_id"])

    async def test_unmanaged_period_and_legacy_replay_keep_finances(self):
        payment = await self.pay()
        replay = await self.ctx.request("POST", "/bills/bill/payments", json={"amount": 70, "account_id": "account"},
            headers={"Idempotency-Key": "legacy-seventy"})
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["id"], payment["id"])
        await self.reserve()
        bill, rp = parents()
        bill.update(_id="nov", id="nov", due_date="2026-11-20")
        await self.fixture_write("bills", "insert_one", bill)
        response = await self.ctx.request("POST", "/bills/nov/payments", json={"amount": 10, "account_id": "account"})
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = await self.snapshot()
        self.assertEqual(snapshot["accounts"][0]["current_balance"], 920)
        self.assertEqual(len(snapshot["bill_payments"]), 2)
        self.assertEqual(len(snapshot["transactions"]), 2)

    async def test_state_machine_matches_original_rules_fields_and_responses(self):
        source = subprocess.check_output(["git", "show", "7339615cd7ee5fddce733d4f2591561892a74fe0:backend/server.py"], text=True)
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_rp_set_state")
        node.args.args.append(ast.arg(arg="session"))
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and ((isinstance(call.func, ast.Attribute) and call.func.attr == "update_one")
                    or (isinstance(call.func, ast.Name) and call.func.id == "_rp_get")):
                call.keywords.append(ast.keyword(arg="session", value=ast.Name(id="session", ctx=ast.Load())))
        ast.fix_missing_locations(node)
        namespace = dict(self.ctx.ns)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "original state machine", "exec"), namespace)
        fixed = "2026-10-12T00:00:00+00:00"
        namespace["now_iso"] = self.ctx.ns["now_iso"] = lambda: fixed
        namespace["_rp_today"] = self.ctx.ns["_rp_today"] = lambda: date(2026, 10, 12)
        for action in ("pause", "resume", "end"):
            before = await self.snapshot()
            expected = await self.ctx.ns["payment_transaction"](lambda session: namespace["_rp_set_state"]("rp", action, session))
            changed = await self.db.recurring_payments.find_one({"id": "rp"})
            await self.fixture_write("recurring_payments", "update_one", {"id": "rp"}, {"$set": before["recurring_payments"][0]})
            # Remove any field introduced by the original call but absent before.
            extra = {key: "" for key in changed if key not in before["recurring_payments"][0]}
            if extra:
                await self.fixture_write("recurring_payments", "update_one", {"id": "rp"}, {"$unset": extra})
            response = await self.ctx.request("POST", "/recurring-payments/rp/"+action)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), expected)
        await self.assert_blocked("POST", "/recurring-payments/rp/end")

    async def test_lookup_failure_blocks_payments_and_state_without_changes(self):
        with patch.object(shared, "has_managed_obligation", AsyncMock(side_effect=OperationFailure("Synthetic query failure"))):
            await self.assert_blocked("POST", "/bills/bill/payments", {"amount": 10, "account_id": "account"}, 503)
            await self.assert_blocked("POST", "/recurring-payments/rp/pause", code=503)

    async def test_orphan_managed_expense_cannot_hide_from_period_guard(self):
        tx = dict(_id="orphan-r4", id="orphan-r4", user_id=USER, type="expense", amount=10,
                  account_id="account", recurring_payment_id="rp", recurring_record_id="missing",
                  _shared_obligation_id="missing-metadata")
        await self.fixture_write("transactions", "insert_one", tx)
        await self.assert_blocked("POST", "/recurring-payments/rp/payments",
            {"amount": 10, "account_id": "account", "mode": "expense", "due_date": "2026-10-20"})

    async def test_verified_managed_other_period_does_not_block_new_legacy_due(self):
        doc = await self.reserve()
        await self.fixture_write("moneyflow_metadata", "insert_one", metadata())
        p, r, tx = graph(amount=70)
        provenance(doc, p, r, tx)
        for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.fixture_write(col, "insert_one", value)
        await self.fixture_write("accounts", "update_one", {"id": "account"}, {"$set": {"current_balance": 930}})
        response = await self.ctx.request("POST", "/recurring-payments/rp/payments", json={
            "amount": 10, "account_id": "account", "mode": "expense", "due_date": "2026-11-20"})
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = await self.snapshot()
        self.assertEqual(snapshot["accounts"][0]["current_balance"], 920)
        self.assertEqual(len(snapshot["transactions"]), 2)
        self.assertEqual(len(snapshot["shared_obligations"]), 1)

    async def test_creation_and_linking_cannot_reclaim_managed_references(self):
        await self.reserve()
        await self.assert_blocked("POST", "/bills", {"name": "Duplicate", "amount": 100,
            "due_date": "2026-10-20", "recurring_payment_id": "rp"})
        key = "reserved-recurring-root"
        rid = str(uuid.uuid5(uuid.NAMESPACE_URL, USER+":recurring-payment:"+key))
        await self.fixture_write("shared_obligations", "insert_one",
            dict(_id="unknown-reserved-version", user_id=USER, recurring_id=rid, original_due_date="2026-10-20"))
        before = await self.snapshot()
        response = await self.ctx.request("POST", "/recurring-payments", json={"name": "Root", "amount": 100,
            "frequency": "monthly", "start_date": "2026-10-20"}, headers={"Idempotency-Key": key})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(await self.snapshot(), before)
        await self.fixture_write("transactions", "insert_one", dict(_id="managed-source", id="managed-source",
            user_id=USER, type="expense", amount=10, account_id="account", _shared_obligation_id="lost"))
        await self.assert_blocked("POST", "/recurring-payments/rp/payments", {"amount": 10,
            "mode": "link", "transaction_id": "managed-source", "due_date": "2026-11-20"})


class SharedGuardTests(GuardCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = MemoryDatabase()
        self.collections = tuple(self.db.data)
        self.client = memory.Client(self.db)
        self.ctx = context(self.db, self.client)
        bill, rp = parents()
        self.db.data["bills"], self.db.data["recurring_payments"] = [bill], [rp]
        self.db.data["accounts"] = [dict(_id="account", id="account", user_id=USER, initial_balance=1000, current_balance=1000)]

    async def test_state_write_and_commit_failure_roll_back(self):
        self.db.fail_at = 1
        await self.assert_blocked("POST", "/recurring-payments/rp/pause", code=503)
        self.db.fail_at = None
        self.db.fail_commit = True
        await self.assert_blocked("POST", "/recurring-payments/rp/pause", code=503)
