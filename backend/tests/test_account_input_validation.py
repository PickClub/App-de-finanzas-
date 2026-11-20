"""Account request regressions using extracted routes and synthetic memory only."""
import ast
import copy
from pathlib import Path
import unittest

import httpx
from fastapi import FastAPI

from backend.tests.test_transaction_validation import TransactionValidationTests


class AccountInputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        TransactionValidationTests.setUp(self)
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
        nodes = [node for node in tree.body
                 if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
                 and node.name in {"Account", "create_account"}]
        self.assertEqual({node.name for node in nodes}, {"Account", "create_account"})
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<account routes>", "exec"), self.ns)
        self.app = FastAPI()
        self.app.include_router(self.ns["api"])

    async def request(self, method, path, **kwargs):
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://account-test.invalid") as client:
            return await client.request(method, "/api" + path, **kwargs)

    async def test_invalid_account_types_rejected_before_writes(self):
        for method, path in (("POST", "/accounts"), ("PUT", "/accounts/a")):
            for kind in ("invalid", "", "CASH", None, 123):
                with self.subTest(method=method, kind=kind):
                    before = copy.deepcopy(self.db.data)
                    writes = self.db.writes
                    response = await self.request(method, path, json={
                        "name": "Synthetic invalid account", "type": kind, "initial_balance": 1000,
                    })
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertIn(["body", "type"], [error["loc"] for error in response.json()["detail"]])
                    self.assertEqual(self.db.data, before)
                    self.assertEqual(self.db.writes, writes)

    async def test_supported_types_and_openings_preserve_balances(self):
        for kind in ("cash", "checking", "savings", "credit_card", "wallet", "other"):
            for opening in (0, 1000, -100):
                with self.subTest(kind=kind, opening=opening):
                    before = copy.deepcopy(self.db.data)
                    response = await self.request("POST", "/accounts", json={
                        "name": "Synthetic account", "type": kind, "initial_balance": opening,
                        "color": "#126046", "icon": "wallet-outline", "currency": "USD",
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    account = response.json()
                    self.assertEqual(account["type"], kind)
                    self.assertEqual(account["initial_balance"], opening)
                    self.assertEqual(account["current_balance"], opening)
                    self.assertEqual(account["user_id"], "default-user")
                    self.assertEqual(account["currency"], "USD")
                    self.assertEqual(account["color"], "#126046")
                    self.assertNotIn("_id", account)
                    self.assertEqual(self.db.data["accounts"][:-1], before["accounts"])
                    self.assertEqual(len(self.db.data["accounts"]), len(before["accounts"]) + 1)
                    for collection in before:
                        if collection != "accounts":
                            self.assertEqual(self.db.data[collection], before[collection])

    async def test_default_type_remains_cash(self):
        response = await self.request("POST", "/accounts", json={"name": "Synthetic default"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["type"], "cash")
        self.assertEqual(response.json()["current_balance"], 0)

    async def test_valid_edit_keeps_derived_balance_and_history(self):
        expense = await self.request("POST", "/transactions", json={
            "name": "Synthetic expense", "type": "expense", "amount": 25, "account_id": "a",
        })
        self.assertEqual(expense.status_code, 200, expense.text)
        movements = copy.deepcopy(self.db.data["transactions"])
        payments = copy.deepcopy(self.db.data["debt_payments"])
        for kind in ("cash", "checking", "savings", "credit_card", "wallet", "other"):
            response = await self.request("PUT", "/accounts/a", json={
                "name": "Synthetic edited account", "type": kind, "initial_balance": 1100,
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["current_balance"], 1075)
            self.assertEqual(response.json()["type"], kind)
            self.assertEqual(next(a for a in self.db.data["accounts"] if a["id"] == "b")["current_balance"], 500)
            self.assertEqual(self.db.data["transactions"], movements)
            self.assertEqual(self.db.data["debt_payments"], payments)
