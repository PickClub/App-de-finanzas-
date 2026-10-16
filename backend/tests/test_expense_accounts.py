"""Expense account requirements against AST routes and synthetic transactions only."""
import copy
import unittest
from unittest.mock import patch
from pymongo.errors import OperationFailure

from backend.tests import test_transaction_validation as harness


class ExpenseAccountTests(unittest.IsolatedAsyncioTestCase):
    setUp = harness.TransactionValidationTests.setUp
    request = harness.TransactionValidationTests.request
    balance = harness.TransactionValidationTests.balance

    async def create(self, **changes):
        payload = dict(name="Synthetic expense", type="expense", amount=25)
        payload.update(changes)
        return await self.request("POST", "/transactions", json=payload)

    async def test_missing_null_empty_invalid_deleted_and_foreign_accounts_rejected(self):
        self.db.data["accounts"].extend([
            dict(id="foreign", user_id="other", initial_balance=100, current_balance=100),
            dict(id="deleted", user_id="default-user", deleted=True, initial_balance=100, current_balance=100),
        ])
        for fields in ({}, {"account_id": None}, {"account_id": ""}, {"account_id": " "},
                       {"account_id": "missing"}, {"account_id": "deleted"}, {"account_id": "foreign"}):
            with self.subTest(fields=fields):
                before = copy.deepcopy(self.db.data)
                writes = self.db.writes
                response = await self.create(**fields)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(self.db.data, before)
                self.assertEqual(self.db.writes, writes)

    async def test_valid_expense_balances_and_omitted_edit_reference(self):
        response = await self.create(account_id="a")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.balance(), 975)
        tid = response.json()["id"]
        response = await self.request("PUT", "/transactions/" + tid, json=dict(name="Renamed", type="expense", amount=25))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["account_id"], "a")
        self.assertEqual(self.balance(), 975)
        self.assertEqual(len(self.db.data["transactions"]), 1)
        response = await self.request("DELETE", "/accounts/a")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.balance(), 975)

    async def test_edit_cannot_clear_or_replace_with_invalid_account(self):
        tx = (await self.create(account_id="a")).json()
        for account in (None, "", "missing"):
            before = copy.deepcopy(self.db.data)
            response = await self.request("PUT", "/transactions/" + tx["id"], json=dict(name="Edit", type="expense", amount=25, account_id=account))
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.db.data, before)

    async def test_failed_transaction_rolls_back_all_writes(self):
        for fail_at in (1, 2):
            self.setUp()
            self.db.fail_at = fail_at
            before = copy.deepcopy(self.db.data)
            response = await self.create(account_id="a")
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(self.db.data, before)

    async def test_legacy_accountless_expense_untouched_by_new_writes(self):
        legacy = dict(id="legacy", user_id="default-user", type="expense", name="Historical", amount=10, account_id=None)
        self.db.data["transactions"].append(copy.deepcopy(legacy))
        response = await self.create(account_id="a")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.db.data["transactions"][0], legacy)
        self.assertEqual(self.balance(), 975)

    async def test_other_types_remain_optional_and_conversion_to_expense_is_guarded(self):
        for kind in ("income", "loan_given", "loan_received"):
            response = await self.create(type=kind)
            self.assertEqual(response.status_code, 200, response.text)
            before = copy.deepcopy(self.db.data)
            converted = await self.request("PUT", "/transactions/" + response.json()["id"], json=dict(name="Convert", type="expense", amount=25))
            self.assertEqual(converted.status_code, 422)
            self.assertEqual(self.db.data, before)

    async def test_aborted_callback_retry_has_one_financial_effect(self):
        original = harness.OrdinaryCollection.insert_one
        attempted_ids = []

        async def insert(collection, doc, *, session=None):
            if collection.name == "transactions":
                attempted_ids.append(doc["id"])
            await original(collection, doc, session=session)
            if collection.name == "transactions" and len(attempted_ids) == 1:
                raise OperationFailure("Aborted transient attempt", details={"errorLabels": ["TransientTransactionError"]})

        with patch.object(harness.OrdinaryCollection, "insert_one", insert):
            response = await self.create(account_id="a")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(attempted_ids), 2)
        self.assertEqual(attempted_ids[0], attempted_ids[1])
        self.assertEqual(len(self.db.data["transactions"]), 1)
        self.assertEqual(self.balance(), 975)

    async def test_uncertain_commit_is_not_automatically_repeated(self):
        self.db.commit_then_error = True
        response = await self.create(account_id="a")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(self.db.data["transactions"]), 1)
        self.assertEqual(self.balance(), 975)
