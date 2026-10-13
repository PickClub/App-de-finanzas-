"""Debt route key maintenance in synthetic memory; no startup or real DB."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pymongo.errors import OperationFailure
from backend.history_keys import inspect_history_keys
from backend.tests import test_payment_consistency as memory


class DebtKeyCases:
    request = memory.PaymentTests.request

    async def pay(self, key="original", amount=100, account="a", date="20261001T120000.123456+010203", expected=200, **extra):
        response = await self.request("POST", "/debt-payments", json={"debt_id": "d", "amount": amount,
            "account_id": account, "date": date, **extra}, headers={"Idempotency-Key": key} if key else {})
        self.assertEqual(response.status_code, expected, response.text)
        self.assertNotIn("_history", response.text)
        return response.json()

    async def edit(self, payment, amount=100, date="20261001T120000.123456+010203", expected=200, **extra):
        tx = await self.stored(payment)
        response = await self.request("PUT", "/transactions/" + payment["transaction_id"],
            json={"name": "Synthetic debt movement", "amount": amount, "type": tx["type"], "account_id": "a", "date": date, **extra})
        self.assertEqual(response.status_code, expected, response.text)
        self.assertNotIn("_history", response.text)
        return response.json()

    async def stored(self, payment):
        return await self.db.transactions.find_one({"id": payment["transaction_id"]})

    async def receipt(self, payment):
        return await self.db.debt_payments.find_one({"id": payment["id"]})

    async def balance(self, aid="a"):
        return (await self.db.accounts.find_one({"id": aid}))["current_balance"]

    async def debt(self):
        return await self.db.debts.find_one({"id": "d"})

    async def snapshot(self):
        return {name: await getattr(self.db, name).find({}).sort("id", 1).to_list(None)
                for name in ("transactions", "accounts", "debts", "debt_payments", "recurring_templates", "categories")}

    async def test_create_payment_sources_receipt_balance_and_ready(self):
        p = await self.pay()
        tx = await self.stored(p)
        self.assertEqual(inspect_history_keys(tx, 1), "ready")
        self.assertEqual(tx["date"], "20261001T120000.123456+010203")
        self.assertEqual((tx["debt_payment_id"], tx["debt_id"], tx["amount"]), (p["id"], "d", 100))
        self.assertNotIn("_history_keys", await self.receipt(p))
        self.assertEqual(await self.balance(), 900)
        self.assertEqual(((await self.debt())["total_paid"], (await self.debt())["remaining_amount"]), (100, 400))

    async def test_collection_they_owe_creates_income_keys(self):
        await self.ns["payment_transaction"](lambda session: self.db.debts.update_one({"id": "d"}, {"$set": {"direction": "they_owe"}}, session=session))
        p = await self.pay()
        tx = await self.stored(p)
        self.assertEqual(tx["type"], "income")
        self.assertEqual(inspect_history_keys(tx, 1), "ready")
        self.assertEqual(await self.balance(), 1100)
        self.assertEqual((await self.debt())["remaining_amount"], 400)

    async def test_edit_amount_date_from_final_preserves_original_fingerprint(self):
        p = await self.pay()
        original = await self.receipt(p)
        before = (await self.stored(p))["_history_keys"]
        await self.edit(p, amount=80, date="2026-W40-5T12:00:00.999999Z")
        tx, receipt = await self.stored(p), await self.receipt(p)
        self.assertEqual(inspect_history_keys(tx, 1), "ready")
        self.assertNotEqual(before, tx["_history_keys"])
        self.assertEqual((tx["date"], receipt["date"]), ("2026-W40-5T12:00:00.999999Z",)*2)
        self.assertEqual(receipt["request_fingerprint"], original["request_fingerprint"])
        self.assertEqual((receipt["id"], tx["id"]), (p["id"], p["transaction_id"]))
        self.assertEqual(await self.balance(), 920)
        self.assertEqual((await self.debt())["remaining_amount"], 420)
        before = await self.snapshot()
        await self.pay()  # Original creation payload, not edited current fields.
        self.assertEqual(await self.snapshot(), before)

    async def test_admin_edit_notes_account_omitted_and_null(self):
        p = await self.pay(notes="original")
        original = (await self.stored(p))["_history_keys"]
        response = await self.request("PUT", "/transactions/" + p["transaction_id"], json={"name": "Rename", "amount": 100, "type": "debt_payment"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.stored(p))["notes"], "original")
        self.assertEqual((await self.stored(p))["_history_keys"], original)
        await self.edit(p, date=None, account_id="b", notes=None)
        tx = await self.stored(p)
        self.assertEqual(tx["date"], p["date"])
        self.assertIsNone(tx["notes"])
        self.assertEqual(tx["_history_keys"], original)
        self.assertEqual((await self.balance(), await self.balance("b")), (1000, 400))

    async def test_original_retry_and_payload_conflict_no_writes(self):
        p = await self.pay(date=None)
        before = await self.snapshot()
        retry = await self.pay(date=None)
        self.assertEqual(retry, p)
        await self.pay(amount=101, date=None, expected=409)
        self.assertEqual(await self.snapshot(), before)

    async def test_two_independent_equal_payments(self):
        first, second = await asyncio.gather(self.pay(key="one"), self.pay(key="two"))
        self.assertNotEqual(first["transaction_id"], second["transaction_id"])
        self.assertEqual(await self.balance(), 800)
        self.assertEqual((await self.debt())["remaining_amount"], 300)
        for p in (first, second):
            self.assertEqual(inspect_history_keys(await self.stored(p), 1), "ready")

    async def test_same_intent_concurrent_one_movement(self):
        first, second = await asyncio.gather(self.pay(), self.pay())
        self.assertEqual(first, second)
        self.assertEqual(await self.balance(), 900)
        self.assertEqual(len((await self.snapshot())["transactions"]), 1)
        self.assertEqual(inspect_history_keys(await self.stored(first), 1), "ready")

    async def test_unverifiable_dates_accepted_and_transition_to_ready(self):
        p = await self.pay(date="2026-1001T120000Z")
        self.assertEqual(inspect_history_keys(await self.stored(p), 1), "unverifiable")
        await self.edit(p, date="2026-10-01")
        self.assertEqual(inspect_history_keys(await self.stored(p), 1), "ready")
        await self.edit(p, date="invalid-date")
        self.assertEqual(inspect_history_keys(await self.stored(p), 1), "unverifiable")
        self.assertEqual(await self.balance(), 900)

    async def test_disabled_and_legacy_admin_edit_no_backfill(self):
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=False)
        p = await self.pay()
        await self.edit(p, amount=80)
        self.assertNotIn("_history_keys", await self.stored(p))
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=True, history_keys_generation=1)
        await self.edit(p, amount=80, notes="administrative")
        self.assertNotIn("_history_keys", await self.stored(p))
        await self.edit(p, amount=70)
        self.assertEqual(inspect_history_keys(await self.stored(p), 1), "ready")
        self.assertEqual(await self.balance(), 930)

    async def test_create_edit_delete_rollback_after_partial_writes(self):
        recompute = self.ns["recompute_debt"]
        async def fail(*args, **kwargs):
            await recompute(*args, **kwargs)
            raise OperationFailure("Synthetic after-write failure")
        before = await self.snapshot()
        with patch.dict(self.ns, {"recompute_debt": fail}):
            await self.pay(expected=503)
        self.assertEqual(await self.snapshot(), before)
        p = await self.pay()
        for action in ("edit", "delete"):
            before = await self.snapshot()
            with patch.dict(self.ns, {"recompute_debt": fail}):
                if action == "edit":
                    await self.edit(p, amount=80, expected=503)
                else:
                    response = await self.request("DELETE", "/debt-payments/" + p["id"])
                    self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(await self.snapshot(), before)

    async def test_delete_exactly_once_tombstone_and_late_retry(self):
        p = await self.pay()
        for _ in range(2):
            response = await self.request("DELETE", "/debt-payments/" + p["id"])
            self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(await self.stored(p))
        receipt = await self.receipt(p)
        self.assertTrue(receipt["deleted"])
        self.assertNotIn("_history_keys", receipt)
        self.assertEqual(await self.balance(), 1000)
        self.assertEqual((await self.debt())["remaining_amount"], 500)
        before = await self.snapshot()
        await self.pay(expected=409)
        self.assertEqual(await self.snapshot(), before)

    async def test_generic_delete_and_r3_source_protection(self):
        p = await self.pay()
        await self.ns["payment_transaction"](lambda session: self.db.recurring_templates.insert_one({"id": "template", "source_transaction_id": p["transaction_id"]}, session=session))
        before = await self.snapshot()
        response = await self.request("DELETE", "/transactions/" + p["transaction_id"])
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(await self.snapshot(), before)
        await self.ns["payment_transaction"](lambda session: self.db.recurring_templates.delete_one({"id": "template"}, session=session))
        response = await self.request("DELETE", "/transactions/" + p["transaction_id"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(await self.stored(p))
        self.assertTrue((await self.receipt(p))["deleted"])
        self.assertEqual(await self.balance(), 1000)

    async def test_repeated_put_preserves_keys_and_financial_result(self):
        p = await self.pay()
        await self.edit(p, amount=80)
        before = await self.snapshot()
        await self.edit(p, amount=80)
        self.assertEqual(await self.snapshot(), before)


class DebtKeyMemoryTests(DebtKeyCases, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        memory.PaymentTests.setUp(self)
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=True, history_keys_generation=1)

    async def test_unknown_commit_recovers_same_original_intent(self):
        self.db.commit_then_error = True
        await self.pay(expected=503)
        before = await self.snapshot()
        p = await self.pay()
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(inspect_history_keys(await self.stored(p), 1), "ready")
        self.assertEqual(await self.balance(), 900)

    async def test_transient_edit_retries_with_updated_session(self):
        p = await self.pay()
        original = self.ns["recompute_debt"]
        calls = []
        async def once(*args, **kwargs):
            await original(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                raise OperationFailure("Synthetic transient", details={"errorLabels": ["TransientTransactionError"]})
        # Memory with_transaction deliberately has no driver retry; supply its
        # synthetic equivalent without changing the production handler.
        original_start = self.client.start_session
        async def start_with_driver_retry():
            session = await original_start()
            original_with_transaction = session.with_transaction
            async def with_transaction(operation, **options):
                for attempt in range(2):
                    try:
                        return await original_with_transaction(operation, **options)
                    except OperationFailure as error:
                        if attempt or not error.has_error_label("TransientTransactionError"):
                            raise
            session.with_transaction = with_transaction
            return session
        with patch.dict(self.ns, {"recompute_debt": once}), patch.object(self.client, "start_session", side_effect=start_with_driver_retry):
            await self.edit(p, amount=80)
        self.assertEqual(len(calls), 2)
        self.assertEqual(inspect_history_keys(await self.stored(p), 1), "ready")
        self.assertEqual(await self.balance(), 920)


if __name__ == "__main__":
    unittest.main()
