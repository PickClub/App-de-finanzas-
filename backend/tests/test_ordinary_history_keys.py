"""Actual ordinary route AST, synthetic memory; key writes enabled only in fixture."""
import asyncio
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pymongo.errors import OperationFailure
from backend.config import settings_from_mapping, ConfigurationError
from backend.history_keys import inspect_history_keys
from backend.tests import test_payment_consistency as memory


class ConfigTests(unittest.TestCase):
    def values(self, **extra):
        return {"APP_ENV": "test", "MONGO_URL": "mongodb://127.0.0.1:27018/", "DB_NAME": "test_synthetic",
                "CORS_ORIGINS": "http://synthetic.invalid", **extra}

    def test_defaults_off_and_no_implicit_generation(self):
        settings = settings_from_mapping(self.values())
        self.assertFalse(settings.history_keys_write_enabled)
        self.assertIsNone(settings.history_keys_generation)
        self.assertFalse(settings.shared_obligations_enabled)

    def test_explicit_flag_and_generation(self):
        settings = settings_from_mapping(self.values(MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED="1", MONEYFLOW_HISTORY_KEYS_GENERATION="1"))
        self.assertTrue(settings.history_keys_write_enabled)
        self.assertEqual(settings.history_keys_generation, 1)
        self.assertFalse(settings.shared_obligations_enabled)

    def test_bad_flags_and_missing_or_invalid_generation(self):
        for extra in ({"MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED": "true"},
                      {"MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED": "1"},
                      *({"MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED": "1", "MONEYFLOW_HISTORY_KEYS_GENERATION": v}
                        for v in ("0", "-1", "01", "1.0", "2147483648", "secret-value"))):
            with self.assertRaises(ConfigurationError):
                settings_from_mapping(self.values(**extra))


class OrdinaryKeyCases:
    request = memory.PaymentTests.request

    def payload(self, **changes):
        return {"name": "Synthetic ordinary", "amount": 100, "type": "expense", "account_id": "a",
                "date": "20261001T120000.123456+010203", **changes}

    async def add(self, **changes):
        response = await self.request("POST", "/transactions", json=self.payload(**changes))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_history", response.text)
        return response.json()

    async def edit(self, tid, **changes):
        response = await self.request("PUT", "/transactions/" + tid, json=self.payload(**changes))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_history", response.text)
        return response.json()

    async def stored(self, tid):
        return await self.db.transactions.find_one({"id": tid})

    async def balance(self, aid="a"):
        return (await self.db.accounts.find_one({"id": aid}))["current_balance"]

    async def snapshot(self):
        return {collection: await getattr(self.db, collection).find({}).sort("id", 1).to_list(None)
                for collection in ("transactions", "accounts", "categories", "debts", "debt_payments", "recurring_templates")}

    async def test_create_expense_income_transfer_exact_sources_and_balances(self):
        for kind, extra, a, b in (("expense", {}, 900, 500), ("income", {}, 1000, 500),
                                  ("transfer", {"to_account_id": "b"}, 900, 600)):
            tx = await self.add(type=kind, **extra)
            stored = await self.stored(tx["id"])
            self.assertEqual(inspect_history_keys(stored, 1), "ready")
            self.assertEqual(stored["date"], self.payload()["date"])
            self.assertEqual(stored["amount"], 100)
            self.assertEqual((await self.balance(), await self.balance("b")), (a, b))

    async def test_edit_amount_date_final_document(self):
        tx = await self.add()
        before = await self.stored(tx["id"])
        await self.edit(tx["id"], amount=200, date="2026-W40-5T23:59:59.999999Z")
        final = await self.stored(tx["id"])
        self.assertEqual(inspect_history_keys(final, 1), "ready")
        self.assertNotEqual(before["_history_keys"], final["_history_keys"])
        self.assertEqual(final["date"], "2026-W40-5T23:59:59.999999Z")
        self.assertEqual(final["id"], tx["id"])
        self.assertEqual(await self.balance(), 800)

    async def test_descriptive_and_account_edits_keep_keys(self):
        tx = await self.add()
        before = (await self.stored(tx["id"]))["_history_keys"]
        await self.edit(tx["id"], name="Renamed", notes="Original text", account_id="b")
        self.assertEqual((await self.stored(tx["id"]))["_history_keys"], before)
        self.assertEqual((await self.balance(), await self.balance("b")), (1000, 400))

    async def test_omitted_and_explicit_null_follow_existing_semantics(self):
        tx = await self.add(notes="Keep")
        response = await self.request("PUT", "/transactions/" + tx["id"], json={"name": "Edited", "amount": 100, "type": "expense"})
        self.assertEqual(response.status_code, 200, response.text)
        stored = await self.stored(tx["id"])
        self.assertEqual((stored["date"], stored["account_id"], stored["notes"]), (tx["date"], "a", "Keep"))
        self.assertEqual(inspect_history_keys(stored, 1), "ready")
        await self.edit(tx["id"], date=None, account_id=None, notes=None)
        stored = await self.stored(tx["id"])
        self.assertEqual(stored["date"], tx["date"])
        self.assertIsNone(stored["account_id"])
        self.assertIsNone(stored["notes"])
        self.assertEqual(inspect_history_keys(stored, 1), "ready")
        self.assertEqual(await self.balance(), 1000)

    async def test_unverifiable_dates_do_not_add_financial_rejections(self):
        tx = await self.add(date="2026-1001T120000Z")
        stored = await self.stored(tx["id"])
        self.assertEqual(inspect_history_keys(stored, 1), "unverifiable")
        self.assertEqual(stored["date"], "2026-1001T120000Z")
        self.assertEqual(await self.balance(), 900)
        await self.edit(tx["id"], date="2026-10-01")
        self.assertEqual(inspect_history_keys(await self.stored(tx["id"]), 1), "ready")
        await self.edit(tx["id"], date="invalid-again")
        self.assertEqual(inspect_history_keys(await self.stored(tx["id"]), 1), "unverifiable")
        self.assertEqual(await self.balance(), 900)

    async def test_disabled_no_keys_and_no_repair_of_previous_keys(self):
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=False, history_keys_generation=None)
        tx = await self.add()
        await self.edit(tx["id"], amount=120)
        self.assertNotIn("_history_keys", await self.stored(tx["id"]))
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=True, history_keys_generation=1)
        managed = await self.add()
        original = (await self.stored(managed["id"]))["_history_keys"]
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=False, history_keys_generation=None)
        await self.edit(managed["id"], amount=80)
        self.assertEqual((await self.stored(managed["id"]))["_history_keys"], original)
        self.assertEqual(await self.balance(), 800)

    async def test_legacy_admin_edit_does_not_backfill_but_source_edit_does(self):
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=False)
        tx = await self.add()
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=True, history_keys_generation=1)
        await self.edit(tx["id"], notes="Administrative")
        self.assertNotIn("_history_keys", await self.stored(tx["id"]))
        await self.edit(tx["id"], amount=90)
        self.assertEqual(inspect_history_keys(await self.stored(tx["id"]), 1), "ready")
        self.assertEqual(await self.balance(), 910)

    async def test_two_equal_independent_posts_remain_two_legitimate_movements(self):
        first, second = await asyncio.gather(self.add(), self.add())
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(await self.balance(), 800)
        for tx in (first, second):
            self.assertEqual(inspect_history_keys(await self.stored(tx["id"]), 1), "ready")

    async def test_loan_types_receive_keys_without_financial_changes(self):
        for kind in ("loan_given", "loan_received"):
            tx = await self.add(type=kind)
            self.assertEqual(inspect_history_keys(await self.stored(tx["id"]), 1), "ready")
            await self.edit(tx["id"], type=kind, amount=80)
            self.assertEqual(inspect_history_keys(await self.stored(tx["id"]), 1), "ready")
        self.assertEqual(await self.balance(), 1000)

    async def test_repeated_put_does_not_duplicate_or_double_discount(self):
        tx = await self.add()
        await self.edit(tx["id"], amount=200)
        before = await self.snapshot()
        await self.edit(tx["id"], amount=200)
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(await self.balance(), 800)

    async def test_rollback_when_recomputation_fails_after_write(self):
        original = self.ns["recompute_account_balance"]
        async def fail(*args, **kwargs):
            await original(*args, **kwargs)
            raise OperationFailure("Synthetic after-write failure")
        before = await self.snapshot()
        with patch.dict(self.ns, {"recompute_account_balance": fail}):
            response = await self.request("POST", "/transactions", json=self.payload())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(await self.snapshot(), before)
        tx = await self.add()
        before = await self.snapshot()
        with patch.dict(self.ns, {"recompute_account_balance": fail}):
            response = await self.request("PUT", "/transactions/" + tx["id"], json=self.payload(amount=200))
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(await self.snapshot(), before)

    async def test_internal_transient_retry_keeps_id_and_date(self):
        original = self.ns["recompute_account_balance"]
        calls, seen = [], []
        async def conflict_once(aid, session):
            tx = await self.db.transactions.find_one({}, session=session)
            seen.append((tx["id"], tx["date"], tx["_history_keys"]))
            calls.append(1)
            await original(aid, session=session)
            if len(calls) == 1:
                raise OperationFailure("Synthetic transient", details={"errorLabels": ["TransientTransactionError"]})
        with patch.dict(self.ns, {"recompute_account_balance": conflict_once}):
            tx = await self.add(date=None)
        self.assertEqual(len(calls), 2)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(tx["id"], seen[0][0])
        self.assertEqual(await self.balance(), 900)

    async def test_debt_payment_and_linked_edit_keep_idempotent_original_receipt(self):
        response = await self.request("POST", "/debt-payments", json={"debt_id": "d", "amount": 100, "account_id": "a"}, headers={"Idempotency-Key": "original"})
        self.assertEqual(response.status_code, 200, response.text)
        payment = response.json()
        self.assertEqual(inspect_history_keys(await self.stored(payment["transaction_id"]), 1), "ready")
        response = await self.request("PUT", "/transactions/" + payment["transaction_id"], json={"name": "Edited debt", "amount": 80, "type": "debt_payment", "account_id": "a"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(inspect_history_keys(await self.stored(payment["transaction_id"]), 1), "ready")
        before = await self.snapshot()
        response = await self.request("POST", "/debt-payments", json={"debt_id": "d", "amount": 100, "account_id": "a"}, headers={"Idempotency-Key": "original"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(await self.snapshot(), before)


class OrdinaryKeyMemoryTests(OrdinaryKeyCases, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        memory.PaymentTests.setUp(self)
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=True, history_keys_generation=1)

    async def test_unknown_commit_is_uncertain_and_already_stored_atomically(self):
        self.db.commit_then_error = True
        response = await self.request("POST", "/transactions", json=self.payload())
        self.assertEqual(response.status_code, 503, response.text)
        stored = self.db.data["transactions"][0]
        self.assertEqual(inspect_history_keys(stored, 1), "ready")
        self.assertEqual(await self.balance(), 900)
        response = await self.request("PUT", "/transactions/" + stored["id"], json=self.payload(amount=100))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.db.data["transactions"]), 1)

    async def test_disabled_generator_is_never_called(self):
        self.ns["settings"] = SimpleNamespace(history_keys_write_enabled=False)
        def forbidden(*args, **kwargs):
            raise AssertionError("Generator disabled")
        with patch.dict(self.ns, {"with_history_keys": forbidden, "history_update_fields": forbidden}):
            tx = await self.add()
            await self.edit(tx["id"], amount=90)


if __name__ == "__main__":
    unittest.main()
