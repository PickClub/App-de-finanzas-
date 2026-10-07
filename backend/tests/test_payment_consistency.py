"""Isolated payment tests. Never imports server.py, Motor, .env, or a live DB.

Run: python -B backend/tests/test_payment_consistency.py
The database double models transaction commit/rollback, not MongoDB itself.
"""
import ast
import asyncio
import copy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import List, Literal, Optional
import unittest
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator
from pymongo import ReadPreference
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern


def matches(doc, query):
    for key, value in query.items():
        actual = doc.get(key)
        if isinstance(value, dict) and "$ne" in value:
            if actual == value["$ne"]:
                return False
        elif actual != value:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = copy.deepcopy(docs)

    def __aiter__(self):
        self.iterator = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration:
            raise StopAsyncIteration

    def sort(self, key, direction):
        self.docs.sort(key=lambda doc: doc[key], reverse=direction < 0)
        return self

    async def to_list(self, length):
        return self.docs[:length]


class Collection:
    def __init__(self, database, name):
        self.database, self.name = database, name

    def docs(self, session):
        return (session.data if session else self.database.data)[self.name]

    async def find_one(self, query, projection=None, *, session=None):
        return copy.deepcopy(next((d for d in self.docs(session) if matches(d, query)), None))

    def find(self, query, projection=None, *, session=None):
        return Cursor([d for d in self.docs(session) if matches(d, query)])

    def before_write(self, session):
        if session is None:
            raise AssertionError("Payment flow attempted a write outside a transaction")
        self.database.writes += 1
        if self.database.fail_at == self.database.writes:
            raise OperationFailure("Injected write failure")

    async def insert_one(self, doc, *, session=None):
        self.before_write(session)
        if any(d.get("_id") == doc.get("_id") for d in self.docs(session)):
            raise DuplicateKeyError("Duplicate _id")
        self.docs(session).append(copy.deepcopy(doc))

    async def update_one(self, query, update, *, session=None):
        self.before_write(session)
        for doc in self.docs(session):
            if matches(doc, query):
                doc.update(copy.deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def delete_one(self, query, *, session=None):
        self.before_write(session)
        docs = self.docs(session)
        for doc in docs:
            if matches(doc, query):
                docs.remove(doc)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class Database:
    def __init__(self):
        self.data = {name: [] for name in (
            "accounts", "debts", "debt_payments", "transactions", "users",
            "categories", "budgets", "saving_goals", "recurring_templates",
        )}
        self.writes = 0
        self.fail_at = None
        self.fail_commit = False
        self.commit_then_error = False
        self.lock = asyncio.Lock()

    def __getattr__(self, name):
        if name in self.data:
            return Collection(self, name)
        raise AttributeError(name)


class Session:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def with_transaction(self, callback, **options):
        async with self.database.lock:
            self.data = copy.deepcopy(self.database.data)
            result = await callback(self)
            if self.database.fail_commit:
                raise OperationFailure("Injected commit failure")
            self.database.data = self.data
            if self.database.commit_then_error:
                self.database.commit_then_error = False
                raise OperationFailure("Commit result unavailable")
            return result


class Client:
    def __init__(self, database):
        self.database, self.supported = database, True

    async def start_session(self):
        if not self.supported:
            raise OperationFailure("Transactions unsupported", code=20)
        return Session(self.database)


class PaymentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database()
        self.client = Client(self.db)
        self.db.data["accounts"] = [
            dict(id="a", user_id="default-user", initial_balance=1000, current_balance=1000),
            dict(id="b", user_id="default-user", initial_balance=500, current_balance=500),
        ]
        self.db.data["debts"] = [dict(
            id="d", user_id="default-user", name="Debt", direction="i_owe",
            original_amount=500, remaining_amount=500, total_paid=0, status="active",
            start_date="2026-01-01T00:00:00+00:00",
        )]
        tree = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text())
        nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name != "shutdown"]
        router = APIRouter(prefix="/api")
        self.ns = dict(globals(), api=router, db=self.db, client=self.client,
                       DEFAULT_USER_ID="default-user", PROJ={"_id": 0})
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<isolated backend>", "exec"), self.ns)
        self.app = FastAPI()
        self.app.include_router(router)

    async def request(self, method, path, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://payment-test.invalid") as client:
            return await client.request(method, "/api" + path, **kwargs)

    async def pay(self, amount=100, account="a", key=None):
        headers = {"Idempotency-Key": key} if key else {}
        return await self.request("POST", "/debt-payments", json={"debt_id": "d", "amount": amount, "account_id": account}, headers=headers)

    def balance(self, account="a"):
        return next(a["current_balance"] for a in self.db.data["accounts"] if a["id"] == account)

    def active_payments(self):
        return [p for p in self.db.data["debt_payments"] if not p.get("deleted")]

    async def created(self, **kwargs):
        response = await self.pay(**kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_create_links_both_records_and_balances(self):
        p = await self.created()
        tx = self.db.data["transactions"][0]
        self.assertEqual(p["transaction_id"], tx["id"])
        self.assertEqual(tx["debt_payment_id"], p["id"])
        self.assertEqual(self.balance(), 900)
        self.assertEqual(self.db.data["debts"][0]["remaining_amount"], 400)

    async def test_receivable_payment_increases_account(self):
        self.db.data["debts"][0]["direction"] = "they_owe"
        await self.created()
        self.assertEqual(self.balance(), 1100)
        self.assertEqual(self.db.data["transactions"][0]["type"], "income")

    async def test_no_account_remains_supported(self):
        await self.created(account=None)
        self.assertEqual(self.balance(), 1000)
        self.assertEqual(self.db.data["debts"][0]["remaining_amount"], 400)

    async def test_delete_from_either_endpoint_and_retry(self):
        for endpoint in ("debt-payments", "transactions"):
            with self.subTest(endpoint=endpoint):
                p = await self.created()
                identifier = p["id"] if endpoint == "debt-payments" else p["transaction_id"]
                for _ in range(2):
                    response = await self.request("DELETE", f"/{endpoint}/{identifier}")
                    self.assertEqual(response.status_code, 200)
                self.assertEqual(self.balance(), 1000)
                self.assertEqual(self.db.data["debts"][0]["remaining_amount"], 500)
                self.assertEqual(self.active_payments(), [])
                self.assertEqual(self.db.data["transactions"], [])

    async def test_edit_movement_updates_payment_and_both_accounts(self):
        p = await self.created()
        response = await self.request("PUT", f"/transactions/{p['transaction_id']}", json={
            "name": "Edited", "type": "debt_payment", "amount": 150,
            "account_id": "b", "notes": "Changed", "category_id": "category",
        })
        self.assertEqual(response.status_code, 200, response.text)
        payment = self.active_payments()[0]
        self.assertEqual(payment["amount"], 150)
        self.assertEqual(payment["account_id"], "b")
        self.assertEqual(payment["notes"], "Changed")
        self.assertEqual(response.json()["debt_id"], "d")
        self.assertEqual(self.balance(), 1000)
        self.assertEqual(self.balance("b"), 350)
        self.assertEqual(self.db.data["debts"][0]["remaining_amount"], 350)

    async def test_invalid_amounts_and_missing_references_do_not_write(self):
        before = copy.deepcopy(self.db.data)
        for amount in (0, -1):
            response = await self.pay(amount=amount)
            self.assertEqual(response.status_code, 422)
        for amount in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValidationError):
                self.ns["DebtPaymentCreate"](debt_id="d", amount=amount)
        self.assertEqual((await self.pay(account="missing")).status_code, 404)
        self.assertEqual((await self.pay(amount=501)).status_code, 422)
        self.assertEqual(self.db.data, before)

    async def test_nonfinite_json_amounts_return_422(self):
        before = copy.deepcopy(self.db.data)
        for value in ("NaN", "Infinity", "-Infinity", "1e999"):
            response = await self.request("POST", "/debt-payments", content='{"debt_id":"d","amount":' + value + '}', headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.data, before)

    async def test_each_create_write_and_commit_failure_rolls_back(self):
        before = copy.deepcopy(self.db.data)
        for step in range(1, 5):
            with self.subTest(step=step):
                self.db.writes, self.db.fail_at = 0, step
                self.assertEqual((await self.pay()).status_code, 503)
                self.assertEqual(self.db.data, before)
        self.db.fail_at, self.db.fail_commit = None, True
        self.assertEqual((await self.pay()).status_code, 503)
        self.assertEqual(self.db.data, before)

    async def test_delete_and_edit_failures_roll_back(self):
        p = await self.created()
        before = copy.deepcopy(self.db.data)
        for step in range(1, 5):
            self.db.writes, self.db.fail_at = 0, step
            self.assertEqual((await self.request("DELETE", f"/debt-payments/{p['id']}")).status_code, 503)
            self.assertEqual(self.db.data, before)
        for step in range(1, 6):
            self.db.writes, self.db.fail_at = 0, step
            response = await self.request("PUT", f"/transactions/{p['transaction_id']}", json={
                "name": "Edited", "type": "debt_payment", "amount": 150, "account_id": "b",
            })
            self.assertEqual(response.status_code, 503)
            self.assertEqual(self.db.data, before)

    async def test_same_key_is_idempotent_and_conflicting_payload_rejected(self):
        responses = await asyncio.gather(*[self.pay(key="operation-1") for _ in range(5)])
        self.assertEqual([r.status_code for r in responses], [200] * 5)
        self.assertEqual(len({r.json()["id"] for r in responses}), 1)
        self.assertEqual(len(self.active_payments()), 1)
        self.assertEqual(len(self.db.data["transactions"]), 1)
        self.assertEqual(self.balance(), 900)
        self.assertEqual((await self.pay(amount=101, key="operation-1")).status_code, 409)

    async def test_retry_after_uncertain_commit_does_not_duplicate(self):
        self.db.commit_then_error = True
        self.assertEqual((await self.pay(key="uncertain")).status_code, 503)
        await self.created(key="uncertain")
        self.assertEqual(len(self.active_payments()), 1)
        self.assertEqual(self.balance(), 900)

    async def test_retry_after_delete_does_not_resurrect_payment(self):
        p = await self.created(key="deleted")
        self.assertEqual((await self.request("DELETE", f"/debt-payments/{p['id']}")).status_code, 200)
        self.assertEqual((await self.pay(key="deleted")).status_code, 409)
        self.assertEqual(self.active_payments(), [])
        self.assertEqual(self.balance(), 1000)
        self.assertEqual((await self.request("GET", "/debts/d/payments")).json(), [])
        summary = await self.request("GET", "/summary")
        self.assertEqual(summary.json()["debts"]["paid_this_month"], 0)

    async def test_full_payment_and_reopening_by_edit(self):
        p = await self.created(amount=500)
        self.assertEqual(self.db.data["debts"][0]["status"], "paid")
        response = await self.request("PUT", f"/transactions/{p['transaction_id']}", json={
            "name": "Edited", "type": "debt_payment", "amount": 200, "account_id": None,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.data["debts"][0]["status"], "active")
        self.assertEqual(self.db.data["debts"][0]["remaining_amount"], 300)
        self.assertEqual(self.balance(), 1000)

    async def test_metadata_edit_preserves_payment_link(self):
        p = await self.created()
        tx = copy.deepcopy(self.db.data["transactions"][0])
        tx["category_id"] = "new-category"
        response = await self.request("PUT", f"/transactions/{p['transaction_id']}", json=tx)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["debt_payment_id"], p["id"])
        self.assertEqual(response.json()["category_id"], "new-category")
        self.assertEqual(self.balance(), 900)

    async def test_unlinked_payment_creation_is_rejected(self):
        before = copy.deepcopy(self.db.data)
        for changes in ({"type": "debt_payment"}, {"type": "income", "debt_id": "d"}):
            payload = dict(name="Unlinked", amount=100, account_id="a", **changes)
            response = await self.request("POST", "/transactions", json=payload)
            self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.data, before)

    async def test_corrupted_link_is_rejected_without_changes(self):
        p = await self.created()
        self.db.data["transactions"][0]["debt_payment_id"] = "wrong-payment"
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.request("DELETE", f"/debt-payments/{p['id']}")).status_code, 409)
        self.assertEqual((await self.request("DELETE", f"/transactions/{p['transaction_id']}")).status_code, 409)
        self.assertEqual(self.db.data, before)

    async def test_parents_can_be_deleted_after_payment_cancellation(self):
        p = await self.created(key="cancel-first")
        await self.request("DELETE", f"/debt-payments/{p['id']}")
        for path in ("/debts/d", "/accounts/a"):
            self.assertEqual((await self.request("DELETE", path)).status_code, 200)
        self.assertEqual(self.active_payments(), [])
        self.assertEqual(self.db.data["transactions"], [])

    async def test_equal_payments_without_key_are_distinct(self):
        p1, p2 = await self.created(), await self.created()
        self.assertNotEqual(p1["id"], p2["id"])
        self.assertEqual(self.balance(), 800)

    async def test_unsupported_database_rejects_before_any_write(self):
        self.client.supported = False
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.pay()).status_code, 503)
        self.assertEqual(self.db.data, before)
        self.assertEqual(self.db.writes, 0)

    async def test_legacy_records_are_not_guessed_or_partially_deleted(self):
        self.db.data["debt_payments"] = [dict(id="legacy", user_id="default-user", debt_id="d", amount=100, account_id="a")]
        self.db.data["transactions"] = [dict(id="legacy-tx", user_id="default-user", debt_id="d", type="debt_payment", amount=100, account_id="a")]
        before = copy.deepcopy(self.db.data)
        for path in ("/debt-payments/legacy", "/transactions/legacy-tx"):
            self.assertEqual((await self.request("DELETE", path)).status_code, 409)
        self.assertEqual(self.db.data, before)

    async def test_parent_deletion_and_direction_change_are_guarded(self):
        await self.created()
        before = copy.deepcopy(self.db.data)
        for path in ("/debts/d", "/accounts/a"):
            self.assertEqual((await self.request("DELETE", path)).status_code, 409)
        response = await self.request("PUT", "/debts/d", json={"name": "Debt", "direction": "they_owe", "original_amount": 500})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.data, before)

    async def test_linked_movement_cannot_change_type_or_debt(self):
        p = await self.created()
        before = copy.deepcopy(self.db.data)
        for changes in ({"type": "expense"}, {"debt_id": "other"}, {"amount": -1}, {"amount": 501}):
            payload = dict(name="Edited", type="debt_payment", amount=100, account_id="a")
            payload.update(changes)
            response = await self.request("PUT", f"/transactions/{p['transaction_id']}", json=payload)
            self.assertIn(response.status_code, (409, 422))
        self.assertEqual(self.db.data, before)


if __name__ == "__main__":
    unittest.main()
