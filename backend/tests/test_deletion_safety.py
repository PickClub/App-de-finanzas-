"""Deletion dependency regressions using the transactional in-memory DB only."""
import ast
import copy
from pathlib import Path
import unittest

from fastapi import APIRouter
from backend.tests import test_payment_consistency as fixtures


class DeletionSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = fixtures.PaymentTests()
        self.context.setUp()
        self.db = self.context.db
        source = Path(__file__).resolve().parents[1] / "server.py"
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "delete_category")
        router = APIRouter(prefix="/api")
        self.context.ns["api"] = router
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), self.context.ns)
        self.context.app.include_router(router)

    async def test_empty_account_can_be_deleted(self):
        response = await self.context.request("DELETE", "/accounts/a")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(a["id"] == "a" for a in self.db.data["accounts"]))

    async def test_ordinary_and_incoming_transfer_block_account(self):
        for field in ("account_id", "to_account_id"):
            with self.subTest(field=field):
                self.db.data["transactions"] = [{"id": "t", field: "a", "type": "transfer", "amount": 10}]
                before = copy.deepcopy(self.db.data)
                response = await self.context.request("DELETE", "/accounts/a")
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.db.data, before)

    async def test_debt_and_recurrence_block_account(self):
        for collection, field in (("debts", "account_id"), ("recurring_templates", "account_id"), ("recurring_templates", "to_account_id")):
            with self.subTest(collection=collection, field=field):
                self.setUp()
                self.db.data[collection].append({"id": "reference", field: "a"})
                before = copy.deepcopy(self.db.data)
                response = await self.context.request("DELETE", "/accounts/a")
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.db.data, before)

    async def test_empty_category_can_be_deleted(self):
        self.db.data["categories"] = [{"id": "category"}]
        response = await self.context.request("DELETE", "/categories/category")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.data["categories"], [])

    async def test_all_category_references_block_deletion(self):
        for collection in ("transactions", "budgets", "debts", "recurring_templates"):
            with self.subTest(collection=collection):
                self.setUp()
                self.db.data["categories"] = [{"id": "category"}]
                self.db.data[collection].append({"id": "reference", "category_id": "category"})
                before = copy.deepcopy(self.db.data)
                response = await self.context.request("DELETE", "/categories/category")
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.db.data, before)

    async def test_recurrence_source_blocks_payment_and_movement_deletion(self):
        payment = await self.context.created()
        self.db.data["recurring_templates"] = [{"id": "r", "source_transaction_id": payment["transaction_id"]}]
        before = copy.deepcopy(self.db.data)
        for path in ("/debt-payments/" + payment["id"], "/transactions/" + payment["transaction_id"]):
            response = await self.context.request("DELETE", path)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(self.db.data, before)


if __name__ == "__main__":
    unittest.main()
