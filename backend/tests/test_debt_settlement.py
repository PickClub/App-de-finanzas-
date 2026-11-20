"""Account/external settlement certification against a new isolated replica."""
import asyncio
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from backend.tests import settlement_store as isolated

from backend.tests import test_r3_replica as regression
from backend import debt_operations

@unittest.skipUnless(
    os.getenv("PW_SETTLEMENT_TEST_TARGET") == isolated.TARGET,
    "Explicit disposable settlement replica required",
)
class SettlementTests(regression.ReplicaTests):
    # The inherited suite has a different opt-in. This class uses only its own
    # exact target and restores every temporary fixture patch after completion.
    __unittest_skip__ = False

    @classmethod
    def setUpClass(cls):
        environment = patch.dict(os.environ, {"R3_SECURITY_TEST_TARGET": isolated.TARGET})
        environment.start()
        cls.addClassCleanup(environment.stop)
        fixtures = patch.multiple(regression, **{
            name: getattr(isolated, name)
            for name in ("connect", "async_client", "DATABASE", "TARGET", "Store", "Fence", "retry_auth")
        })
        fixtures.start()
        cls.addClassCleanup(fixtures.stop)
        super().setUpClass()

    async def call(self, method, path, actor="a", key=None, **kwargs):
        # Existing regressions represent explicit registered-account/external choices.
        if not self._testMethodName.startswith("test_source_") and method == "POST" and path in (
            "/debt-payments", "/debt-payments/reconcile"
        ):
            payload = kwargs.get("json")
            if payload is not None and "settlement_source" not in payload:
                kwargs["json"] = {**payload, "settlement_source":
                                  "account" if payload.get("account_id") else "external"}
        return await super().call(method, path, actor, key, **kwargs)

    async def partial_debt_fixture(self, amount):
        return {**await super().partial_debt_fixture(amount), "settlement_source": "account"}

    async def fixture(self, source="account", direction="i_owe", amount=180):
        debt = await self.ok("POST", "/debts", json={
            "name": "Isolated settlement", "direction": direction, "original_amount": 4000,
        })
        return {
            "debt_id": debt["id"], "amount": amount, "notes": None, "date": None,
            "settlement_source": source,
            "account_id": self.accounts["a"][0] if source == "account" else None,
        }

    def assert_state(self, payload, paid, source, direction="i_owe"):
        owner = self.owner["a"]
        debt = self.db.debts.find_one({"id": payload["debt_id"], "user_id": owner})
        self.assertEqual(Decimal(str(debt["remaining_amount"])), Decimal("4000") - Decimal(str(paid)))
        self.assertEqual(Decimal(str(debt["total_paid"])), Decimal(str(paid)))
        rows = list(self.db.transactions.find({"user_id": owner, "debt_id": payload["debt_id"]}))
        payments = list(self.db.debt_payments.find({
            "user_id": owner, "debt_id": payload["debt_id"], "deleted": {"$ne": True},
        }))
        self.assertEqual(len(rows), int(paid > 0))
        self.assertEqual(len(payments), int(paid > 0))
        if paid:
            tx, payment = rows[0], payments[0]
            for field in ("settlement_source", "account_id", "amount", "debt_id"):
                self.assertEqual(tx.get(field), payment.get(field))
            self.assertEqual(payment["transaction_id"], tx["id"])
            self.assertEqual(tx["debt_payment_id"], payment["id"])
            self.assertEqual(tx.get("settlement_source"), source)
            self.assertEqual(tx["type"], "income" if direction == "they_owe" else "debt_payment")
        self.assert_reconciled("a")

    async def test_source_account_external_and_reports(self):
        for source in ("account", "external"):
            payload = await self.fixture(source)
            before = self.balances("a")
            summary_before = await self.ok("GET", "/summary")
            await self.ok("POST", "/debt-payments", key=source, json=payload)
            self.assert_state(payload, 180, source)
            self.assertEqual(self.balances("a"), [before[0] - (180 if source == "account" else 0), before[1]])
            summary = await self.ok("GET", "/summary")
            self.assertEqual(Decimal(str(summary["month_expense"])) -
                             Decimal(str(summary_before["month_expense"])), Decimal("180"))

    async def test_source_missing_invalid_and_owner(self):
        payload = await self.fixture()
        before_a, before_b = self.financial_snapshot("a"), self.financial_snapshot("b")
        invalid = [
            {k: v for k, v in payload.items() if k != "settlement_source"},
            {**payload, "settlement_source": None},
            {**payload, "settlement_source": "historical"},
            {**payload, "account_id": None},
            {**payload, "account_id": "missing"},
            {**payload, "account_id": self.accounts["b"][0]},
            {**payload, "settlement_source": "external"},
        ]
        for index, body in enumerate(invalid):
            response = await self.call("POST", "/debt-payments", key=f"invalid-{index}", json=body)
            self.assertIn(response.status_code, (422, 404))
            self.assertEqual(self.financial_snapshot("a"), before_a)
            self.assertEqual(self.financial_snapshot("b"), before_b)
        response = await self.call("POST", "/debt-payments", "b", key="foreign-debt", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_source_edit_switch_and_reverse(self):
        payload = await self.fixture()
        receipt = await self.ok("POST", "/debt-payments", key="original", json=payload)
        path = "/transactions/" + receipt["transaction_id"]
        before_b = self.financial_snapshot("b")
        for index, (amount, source, account, balances) in enumerate([
            (200, "account", self.accounts["a"][0], [-100, 0]),
            (200, "account", self.accounts["a"][1], [100, -200]),
            (200, "external", None, [100, 0]),
            (200, "account", self.accounts["a"][0], [-100, 0]),
        ]):
            await self.ok("PUT", path, key=f"edit-{index}", json={
                "name": "Edited settlement", "type": "debt_payment", "amount": amount,
                "settlement_source": source, "account_id": account,
            })
            self.assert_state(payload, amount, source)
            self.assertEqual(self.balances("a"), balances)
        # Original retry returns the same receipt after edits and creates no second effect.
        replay = await self.ok("POST", "/debt-payments", key="original", json=payload)
        self.assertEqual(replay["id"], receipt["id"])
        self.assert_state(payload, 200, "account")
        response = await self.call("PUT", path, "b", json={
            "name": "Forbidden", "type": "debt_payment", "amount": 1,
        })
        self.assertEqual(response.status_code, 404)
        await self.ok("DELETE", "/debt-payments/" + receipt["id"], key="reverse")
        self.assert_state(payload, 0, None)
        self.assertEqual(self.balances("a"), [100, 0])
        await self.ok("DELETE", "/debt-payments/" + receipt["id"], key="reverse")
        response = await self.call("POST", "/debt-payments", key="original", json=payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_source_receipts(self):
        for source in ("account", "external"):
            payload = await self.fixture(source, "they_owe")
            balances = self.balances("a")
            before = await self.ok("GET", "/summary")
            receipt = await self.ok("POST", "/debt-payments", key="receipt-" + source, json=payload)
            self.assert_state(payload, 180, source, "they_owe")
            self.assertEqual(self.balances("a"), [balances[0] + (180 if source == "account" else 0), balances[1]])
            after = await self.ok("GET", "/summary")
            self.assertEqual(after["month_income"] - before["month_income"], 180)
            self.assertEqual(after["month_expense"], before["month_expense"])
            await self.ok("DELETE", "/debt-payments/" + receipt["id"], key="reverse-" + source)
            self.assert_state(payload, 0, None, "they_owe")
            self.assertEqual(self.balances("a"), balances)

    async def test_source_legacy_omission_is_preserved(self):
        payload = await self.fixture("external")
        receipt = await self.ok("POST", "/debt-payments", key="legacy", json=payload)
        old_request = {k: v for k, v in payload.items() if k != "settlement_source"}
        self.db.debt_payments.update_one({"id": receipt["id"]}, {
            "$unset": {"settlement_source": ""},
            "$set": {"request_fingerprint": debt_operations.payment_fingerprint(
                debt_operations.DebtPaymentCreate(**old_request))},
        })
        self.db.transactions.update_one({"id": receipt["transaction_id"]}, {"$unset": {"settlement_source": ""}})
        replay = await self.ok("POST", "/debt-payments", key="legacy", json=old_request)
        self.assertEqual(replay["id"], receipt["id"])
        await self.ok("PUT", "/transactions/" + receipt["transaction_id"], json={
            "name": "Historical edit", "type": "debt_payment", "amount": 200,
        })
        self.assert_state(payload, 200, None)
        for collection, identifier in (("transactions", receipt["transaction_id"]), ("debt_payments", receipt["id"])):
            self.assertNotIn("settlement_source", self.db[collection].find_one({"id": identifier}))
        response = await self.call("PUT", "/transactions/" + receipt["transaction_id"], json={
            "name": "Implicit account switch", "type": "debt_payment", "amount": 200,
            "account_id": self.accounts["a"][0],
        })
        self.assertEqual(response.status_code, 422)
        reconciled = await self.ok("POST", "/debt-payments/reconcile", key="legacy", json=old_request)
        self.assertEqual(reconciled["status"], "matched")
        await self.ok("DELETE", "/debt-payments/" + receipt["id"], key="legacy-reverse")
        self.assert_state(payload, 0, None)

    async def test_source_concurrent_retries_and_overpay(self):
        payload = await self.fixture(amount=2500)
        before_b = self.financial_snapshot("b")
        responses = await asyncio.gather(*[
            self.call("POST", "/debt-payments", key=key, json=payload) for key in ("one", "two")
        ])
        for index, response in enumerate(responses):
            if response.status_code == 503:
                responses[index] = await self.call("POST", "/debt-payments", key=("one", "two")[index], json=payload)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 422])
        self.assert_state(payload, 2500, "account")
        winning_key = ("one", "two")[next(i for i, r in enumerate(responses) if r.status_code == 200)]
        replays = await asyncio.gather(*[
            self.call("POST", "/debt-payments", key=winning_key, json=payload) for _ in range(2)
        ])
        self.assertTrue(all(r.status_code in (200, 503) for r in replays))
        self.assert_state(payload, 2500, "account")
        changed = await self.call("POST", "/debt-payments", key=winning_key,
                                  json={**payload, "settlement_source": "external", "account_id": None})
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(self.financial_snapshot("b"), before_b)


if __name__ == "__main__":
    unittest.main()
