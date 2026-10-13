"""R4 stage 1 only: pure checks / memory transactions, never server startup."""
import ast
import copy
from decimal import Decimal, getcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bson.decimal128 import Decimal128
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError, OperationFailure

from backend import shared_obligations as shared
from backend.config import ConfigurationError, settings_from_mapping
from backend.tests import test_payment_consistency as memory
from backend.tests.test_reference_integrity import Collection, Database, context


ENVIRONMENT = "11111111-1111-4111-8111-111111111111"
OTHER_ENVIRONMENT = "22222222-2222-4222-8222-222222222222"
USER = "default-user"


def activation_settings(flag=None, expected=ENVIRONMENT):
    values = dict(APP_ENV="test", MONGO_URL="mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true",
                  DB_NAME="test_r4_activation_settings", CORS_ORIGINS="http://localhost:8081",
                  MONEYFLOW_EXPECTED_ENVIRONMENT_ID=expected or "")
    if flag is not None:
        values["MONEYFLOW_SHARED_OBLIGATIONS_ENABLED"] = flag
    return settings_from_mapping(values)


def metadata(environment=ENVIRONMENT):
    return dict(_id="financial-context", version=1, environment_id=environment, created_at="2026-01-01T00:00:00+00:00")


def parents():
    bill = dict(_id="bill", id="bill", user_id=USER, name="Synthetic bill", amount=100,
                due_date="2026-10-20", frequency="monthly", anchor_day=20, recurring_payment_id="rp",
                account_id=None, category_id=None, series_id="not-a-document", next_bill_id=None)
    rp = dict(_id="rp", id="rp", user_id=USER, name="Synthetic recurring", variable=False,
              account_id=None, category_id=None, pauses=[], end_date=None, state="active",
              versions=[dict(valid_from="2026-10-01", start_date="2026-10-20", frequency="monthly", due_day=20, amount=100)])
    return bill, rp


def graph(suffix="1", amount=70):
    tid, pid, rid = "tx"+suffix, "payment"+suffix, "record"+suffix
    tx = dict(_id=tid, id=tid, user_id=USER, amount=amount, type="expense", account_id="account",
              bill_id="bill", bill_payment_id=pid, recurring_payment_id="rp", recurring_record_id=rid)
    p = dict(_id=pid, id=pid, user_id=USER, bill_id="bill", transaction_id=tid,
             recurring_record_id=rid, amount=amount, account_id="account")
    r = dict(_id=rid, id=rid, user_id=USER, recurring_id="rp", due_date="2026-10-20", mode="link",
             bill_payment_id=pid, transaction_id=tid, amount=amount, account_id="account")
    return p, r, tx


def provenance(document, p, r, tx, state="active"):
    for value in (p, r, tx):
        value.update(_shared_obligation_id=document["_id"], _shared_origin_receipt_id=p["id"])
    p["_shared_financial_state"] = r["_shared_financial_state"] = state


class MemoryCollection(Collection):
    async def index_information(self):
        if self.name == "shared_tracking_intents":
            return {"_id_": {"key": [("_id", 1)]}}
        return copy.deepcopy(self.database.indexes)

    async def create_index(self, keys, *, name, unique):
        self.database.indexes[name] = dict(key=keys, unique=unique)

    async def insert_one(self, doc, *, session=None):
        if self.name == "shared_obligations":
            for spec in self.database.indexes.values():
                keys = [k for k, _ in spec["key"]]
                if any(all(d.get(k) == doc.get(k) for k in keys) for d in self.docs(session)):
                    raise DuplicateKeyError("Synthetic unique identity violation")
        return await super().insert_one(doc, session=session)


class MemoryDatabase(Database):
    def __init__(self):
        super().__init__()
        self.data["shared_obligations"] = []
        self.data["shared_tracking_intents"] = []
        self.indexes = {}

    def __getattr__(self, name):
        return MemoryCollection(self, name)


class SharedCases:
    def pure_document(self, bill=None, rp=None, **kwargs):
        b, r = parents()
        return shared.resolve_documents(bill or b, rp or r, self.scope, occurrences=self.occurrences, **kwargs)

    def rejected(self, fn, code=409):
        with self.assertRaises(HTTPException) as exc:
            fn()
        self.assertEqual(exc.exception.status_code, code)

    async def rejected_async(self, fn, code=409):
        with self.assertRaises(HTTPException) as exc:
            await self.transaction(fn)
        self.assertEqual(exc.exception.status_code, code)

    async def snapshot(self):
        return {col: await self.db[col].find({}).to_list(None) for col in self.collections} if self.real else copy.deepcopy(self.db.data)

    async def insert(self, col, doc):
        await getattr(self.db, col).insert_one(copy.deepcopy(doc))

    async def create(self, session):
        return await shared.create_shared_obligation(self.db, "bill", expected_environment_id=ENVIRONMENT,
                                                    effective_user=USER, session=session, occurrences=self.occurrences)

    async def read(self, session):
        return await shared.resolve_shared_obligation(self.db, "bill", expected_environment_id=ENVIRONMENT,
                                                     effective_user=USER, session=session, occurrences=self.occurrences)

    async def test_stable_identity_context_and_restart(self):
        doc = await self.transaction(self.create)
        before = await self.snapshot()
        again = await self.transaction(self.create)
        self.assertEqual(doc, again)
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(doc["_id"], shared.identity(self.scope, "rp", "2026-10-20"))
        self.assertNotEqual(doc["_id"], shared.identity(shared.Scope(OTHER_ENVIRONMENT, USER), "rp", "2026-10-20"))
        self.assertNotEqual(doc["_id"], shared.identity(shared.Scope(ENVIRONMENT, "other-effective-user"), "rp", "2026-10-20"))
        self.assertNotEqual(doc["_id"], shared.identity(self.scope, "rp", "2026-11-20"))

    async def test_resolver_missing_identity_is_read_only(self):
        before = await self.snapshot()
        draft, persisted = await self.transaction(self.read)
        self.assertFalse(persisted)
        self.assertEqual(draft["original_due_date"], "2026-10-20")
        self.assertEqual(await self.snapshot(), before)

    async def test_identity_creation_writes_only_metadata_and_coordination(self):
        before = await self.snapshot()
        doc = await self.transaction(self.create)
        after = await self.snapshot()
        self.assertEqual(after["shared_obligations"], [doc])
        for collection in self.collections:
            if collection in ("shared_obligations", "bills", "recurring_payments"):
                continue
            self.assertEqual(after[collection], before[collection])
        for collection in ("bills", "recurring_payments"):
            expected = dict(before[collection][0], _reference_revision=1)
            self.assertEqual(after[collection], [expected])

    async def test_one_bill_per_period_and_no_series_foreign_key(self):
        self.assertEqual(self.pure_document()["bill_id"], "bill")
        second, rp = parents()
        second.update(id="second", _id="second")
        self.rejected(lambda: self.pure_document(candidates=[second]))
        await self.insert("bills", second)
        before = await self.snapshot()
        await self.rejected_async(self.create)
        self.assertEqual(await self.snapshot(), before)

    async def test_frequency_date_and_fixed_amount_compatibility(self):
        for field, value in (("frequency", "weekly"), ("due_date", "2026-10-21"), ("amount", 120)):
            bill, rp = parents()
            bill[field] = value
            self.rejected(lambda: self.pure_document(bill, rp))
        bill, rp = parents()
        bill["frequency"] = "once"
        self.assertEqual(self.pure_document(bill, rp)["original_due_date"], bill["due_date"])

    async def test_variable_real_amount_separate_from_estimate(self):
        bill, rp = parents()
        bill["amount"], rp["variable"] = 50, True
        doc = self.pure_document(bill, rp)
        self.assertEqual(doc["actual_amount"].to_decimal(), Decimal(50))
        self.assertEqual(doc["estimated_amount"].to_decimal(), Decimal(100))
        p, r, tx = graph(amount=50)
        result = shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx])
        self.assertEqual((result.paid, result.remaining, result.financial_status), (Decimal(50), Decimal(0), "paid"))

    async def test_original_period_not_remapped_by_date_or_schedule_edit(self):
        doc = self.pure_document()
        bill, rp = parents()
        bill.update(due_date="2026-11-01", frequency="once")
        rp["versions"] = [dict(valid_from="2026-11-01", start_date="2026-11-01", frequency="daily", amount=200)]
        before = copy.deepcopy((doc, bill, rp))
        resolved = self.pure_document(bill, rp, existing=doc)
        self.assertEqual(resolved, doc)
        self.assertEqual((doc, bill, rp), before)

    async def test_amount_reassignment_and_invalid_snapshot_rejected(self):
        doc = self.pure_document()
        bill, rp = parents()
        bill["amount"] = 120
        self.rejected(lambda: self.pure_document(bill, rp, existing=doc))
        bad = copy.deepcopy(doc)
        bad["schedule_snapshot"]["due_day"] = 21
        self.rejected(lambda: self.pure_document(existing=bad))

    async def test_duplicate_calendar_versions_are_ambiguous(self):
        bill, rp = parents()
        rp["versions"].append(copy.deepcopy(rp["versions"][0]))
        self.rejected(lambda: self.pure_document(bill, rp))

    async def test_same_movement_two_receipts_counted_once(self):
        p, r, tx = graph()
        p["amount"], r["amount"] = "70.00", Decimal128("70.0")
        before = copy.deepcopy((p, r, tx))
        result = shared.verify_payments(self.pure_document(), self.scope, payments=[p], records=[r], movements=[tx])
        self.assertEqual((result.paid, result.remaining, result.transaction_ids), (Decimal(70), Decimal(30), ("tx1",)))
        self.assertEqual((p, r, tx), before)

    async def test_two_equal_partial_payments_are_distinct_real_events(self):
        p, r, tx = graph("1", 30)
        p2, r2, tx2 = graph("2", 30)
        result = shared.verify_payments(self.pure_document(), self.scope, payments=[p, p2], records=[r, r2], movements=[tx, tx2])
        self.assertEqual(result.paid, Decimal(60))
        self.assertEqual(result.remaining, Decimal(40))
        self.assertEqual(result.transaction_ids, ("tx1", "tx2"))

    async def test_inconsistent_legacy_graph_rejected_without_repair(self):
        for collection, field, value in (("payment", "amount", 80), ("record", "account_id", "other"),
                ("record", "due_date", "2026-11-20"), ("payment", "bill_id", "other"),
                ("transaction", "bill_payment_id", None), ("transaction", "type", "income")):
            p, r, tx = graph()
            {"payment": p, "record": r, "transaction": tx}[collection][field] = value
            before = copy.deepcopy((p, r, tx))
            self.rejected(lambda: shared.verify_payments(self.pure_document(), self.scope, payments=[p], records=[r], movements=[tx]))
            self.assertEqual((p, r, tx), before)

    async def test_unshared_recurring_expense_not_adopted_by_amount_or_date(self):
        p, r, tx = graph(amount=100)
        r.pop("bill_payment_id")
        tx.pop("bill_payment_id")
        tx.pop("bill_id")
        self.rejected(lambda: shared.verify_payments(self.pure_document(), self.scope, records=[r], movements=[tx]))

    async def test_retired_legacy_receipt_is_not_assumed_refunded(self):
        p, r, tx = graph()
        p["deleted"] = r["deleted"] = True
        self.rejected(lambda: shared.verify_payments(self.pure_document(), self.scope, payments=[p], records=[r], movements=[tx]))
        self.rejected(lambda: shared.verify_payments(self.pure_document(), self.scope, payments=[p], records=[r]))

    async def test_retired_tracking_with_provenance_preserves_paid_money(self):
        doc = self.pure_document()
        p, r, tx = graph(amount=100)
        provenance(doc, p, r, tx)
        p["deleted"] = r["deleted"] = True
        for field in ("bill_id", "bill_payment_id", "recurring_payment_id", "recurring_record_id"):
            tx.pop(field)
        result = shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx])
        self.assertEqual((result.paid, result.remaining, result.retained_transaction_ids), (Decimal(100), Decimal(0), ("tx1",)))

    async def test_explicit_financial_annulment_requires_missing_movement(self):
        doc = self.pure_document()
        p, r, tx = graph()
        provenance(doc, p, r, tx, "annulled")
        p["deleted"] = r["deleted"] = True
        result = shared.verify_payments(doc, self.scope, payments=[p], records=[r])
        self.assertEqual((result.paid, result.remaining, result.annulled_transaction_ids), (Decimal(0), Decimal(100), ("tx1",)))
        self.rejected(lambda: shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx]))

    async def test_tracking_marks_are_not_real_payments(self):
        r = dict(id="mark", user_id=USER, recurring_id="rp", due_date="2026-10-20", mode="mark", amount=100, transaction_id=None)
        result = shared.verify_payments(self.pure_document(), self.scope, records=[r])
        self.assertEqual(result.paid, Decimal(0))
        self.assertTrue(result.requires_reconciliation)

    async def test_overpaid_and_extra_movements_rejected(self):
        p, r, tx = graph("1", 70)
        p2, r2, tx2 = graph("2", 70)
        self.rejected(lambda: shared.verify_payments(self.pure_document(), self.scope, payments=[p, p2], records=[r, r2], movements=[tx, tx2]))
        self.rejected(lambda: shared.verify_payments(self.pure_document(), self.scope, payments=[p], records=[r], movements=[tx, tx2]))

    async def test_existing_history_never_migrated_on_creation(self):
        for collection in ("bill_payments", "recurring_payment_records", "transactions"):
            p, r, tx = graph()
            value = {"bill_payments": p, "recurring_payment_records": r, "transactions": tx}[collection]
            await self.insert(collection, value)
            before = await self.snapshot()
            await self.rejected_async(self.create)
            self.assertEqual(await self.snapshot(), before)

    async def test_inspection_reads_graph_and_detects_extra_inverse_links(self):
        doc = await self.transaction(self.create)
        p, r, tx = graph()
        for collection, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.insert(collection, value)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT, effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual(result.paid, Decimal(70))
        self.assertEqual(await self.snapshot(), before)
        extra = dict(tx, _id="extra", id="extra")
        await self.insert("transactions", extra)
        before = await self.snapshot()
        await self.rejected_async(inspect)
        self.assertEqual(await self.snapshot(), before)

    async def test_context_missing_or_different_never_writes(self):
        for expected in (None, OTHER_ENVIRONMENT):
            before = await self.snapshot()
            async def wrong(session):
                return await shared.create_shared_obligation(self.db, "bill", expected_environment_id=expected,
                     effective_user=USER, session=session, occurrences=self.occurrences)
            await self.rejected_async(wrong, 503)
            self.assertEqual(await self.snapshot(), before)

    async def test_internal_serialization_deep_and_dormant_routes(self):
        value = {"id": "tx", "amount": 70, "_shared_obligation_id": "internal", "payments": [{"id": "payment", "_shared_financial_state": "active"}]}
        before = copy.deepcopy(value)
        self.assertEqual(shared.without_shared_metadata(value), {"id": "tx", "amount": 70, "payments": [{"id": "payment"}]})
        self.assertEqual(value, before)
        source = Path(__file__).resolve().parents[1].joinpath("server.py").read_text()
        # 2D.1 may import read-only serializers. Imports do not activate money.
        tree = ast.parse(source)
        financial_calls = {"register_shared_payment", "change_shared_payment"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
                self.assertNotIn(name, financial_calls)
        # Unmanaged legacy writes remain unchanged; no shared payments are active.
        for amount, path, key in ((100, "/recurring-payments/rp/payments", "rp-intent"), (100, "/bills/bill/payments", "bill-intent")):
            data = dict(amount=amount, account_id="account")
            if "recurring-payments" in path:
                data.update(mode="expense", due_date="2026-10-20")
            response = await self.ctx.request("POST", path, json=data, headers={"Idempotency-Key":key})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("_shared_", response.text)
            self.assertNotIn("_reference_revision", response.text)
        self.assertEqual((await self.db.accounts.find_one({"id":"account"}))["current_balance"], 800)
        await self.insert("shared_obligations", self.pure_document())
        before = await self.snapshot()
        response = await self.ctx.request("POST", "/bills/bill/payments",
            json={"amount": 1, "account_id": "account"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(await self.snapshot(), before)

    async def test_document_revision_lifecycle_and_context_validation(self):
        doc = self.pure_document()
        for field, value in (("version", True), ("revision", -1), ("lifecycle", "paid"), ("environment_id", OTHER_ENVIRONMENT), ("_id", "wrong")):
            invalid = dict(doc, **{field:value})
            self.rejected(lambda: shared.validate_document(invalid, self.scope))
        retired = dict(doc, lifecycle="tracking_detached")
        self.assertEqual(shared.validate_document(retired, self.scope)["lifecycle"], "tracking_detached")
        self.rejected(lambda: self.pure_document(existing=retired))

    async def test_wrong_movement_scope_and_unknown_retirement_origin_rejected(self):
        doc = self.pure_document()
        p, r, tx = graph()
        tx["_shared_obligation_id"] = "other-obligation"
        self.rejected(lambda: shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx]))
        p, r, tx = graph()
        provenance(doc, p, r, tx)
        for value in (p, r, tx):
            value["_shared_origin_receipt_id"] = "unverifiable-source"
        p["deleted"] = r["deleted"] = True
        self.rejected(lambda: shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx]))

    async def test_annulled_corrupt_receipt_not_treated_as_zero_money(self):
        doc = self.pure_document()
        p, r, tx = graph()
        provenance(doc, p, r, tx, "annulled")
        p["deleted"] = r["deleted"] = True
        p["amount"] = "NaN"
        self.rejected(lambda: shared.verify_payments(doc, self.scope, payments=[p], records=[r]))

    async def test_recurring_origin_needs_explicit_provenance_not_legacy_mode_guess(self):
        doc = self.pure_document()
        p, r, tx = graph()
        r["mode"] = "expense"
        self.rejected(lambda: shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx]))
        provenance(doc, p, r, tx)
        for value in (p, r, tx):
            value["_shared_origin_receipt_id"] = r["id"]
        result = shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx])
        self.assertEqual(result.paid, Decimal(70))

    async def test_malformed_calendar_and_declared_missing_identity_fail_closed(self):
        for bad in ("unknown", None):
            bill, rp = parents()
            rp["versions"][0]["frequency"] = bad
            self.rejected(lambda: self.pure_document(bill, rp))
        await self.transaction(lambda s: self.db.bills.update_one({"id":"bill"}, {"$set":{"_shared_obligation_id":"missing"}}, session=s))
        before = await self.snapshot()
        await self.rejected_async(self.create)
        self.assertEqual(await self.snapshot(), before)

    async def test_creation_rejects_orphan_recurring_movement(self):
        p, r, tx = graph()
        tx.pop("bill_id")
        tx.pop("bill_payment_id")
        await self.insert("transactions", tx)
        before = await self.snapshot()
        await self.rejected_async(self.create)
        self.assertEqual(await self.snapshot(), before)

    async def test_category_consistency_preserves_legacy_absence_representation(self):
        doc = self.pure_document()
        p, r, tx = graph()
        tx["category_id"], r["category_id"] = "", None
        before = copy.deepcopy((p, r, tx))
        self.assertEqual(shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx]).paid, 70)
        self.assertEqual((p, r, tx), before)
        r["category_id"] = "other-category"
        self.rejected(lambda: shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx]))

    async def test_incompatible_managed_links_on_shared_expense_rejected(self):
        p, r, tx = graph()
        tx["debt_payment_id"] = "other-payment"
        self.rejected(lambda: shared.verify_payments(self.pure_document(), self.scope, payments=[p], records=[r], movements=[tx]))

    async def test_inspection_detects_foreign_inverse_receipt_for_same_movement(self):
        doc = await self.transaction(self.create)
        p, r, tx = graph()
        for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.insert(col, value)
        await self.insert("bill_payments", dict(p, _id="foreign", id="foreign", bill_id="other-bill"))
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT, effective_user=USER, session=session)
        await self.rejected_async(inspect)
        self.assertEqual(await self.snapshot(), before)

    async def test_exact_decimal_calculation_does_not_change_global_precision(self):
        bill, rp = parents()
        bill["amount"], rp["variable"] = Decimal128("2E34"), True
        doc = self.pure_document(bill, rp)
        p, r, tx = graph("1", Decimal128("1E34"))
        p2, r2, tx2 = graph("2", Decimal128("0.01"))
        precision = getcontext().prec
        result = shared.verify_payments(doc, self.scope, payments=[p, p2], records=[r, r2], movements=[tx, tx2])
        self.assertEqual(result.paid, Decimal("10000000000000000000000000000000000.01"))
        self.assertEqual(result.remaining, Decimal("9999999999999999999999999999999999.99"))
        self.assertEqual(getcontext().prec, precision)

    async def test_unrepresentable_metadata_money_rejected_not_rounded(self):
        bill, rp = parents()
        bill["amount"], rp["variable"] = "123456789012345678901234567890123456789", True
        self.rejected(lambda: self.pure_document(bill, rp))

    async def test_one_view_retired_keeps_shared_financial_payment(self):
        for retired in ("bill", "recurring"):
            doc = self.pure_document()
            p, r, tx = graph(amount=100)
            provenance(doc, p, r, tx)
            if retired == "recurring":
                r["deleted"] = True
                p["recurring_record_id"] = None
                tx.pop("recurring_payment_id")
                tx.pop("recurring_record_id")
            else:
                p["deleted"] = True
                r.pop("bill_payment_id")
                tx.pop("bill_id")
                tx.pop("bill_payment_id")
            result = shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx])
            self.assertEqual(result.paid, 100)
            self.assertEqual(result.remaining, 0)

    async def test_retired_contradictory_links_rejected_without_writes(self):
        doc = await self.transaction(self.create)
        for owner, field in (("tx", "bill_id"), ("tx", "bill_payment_id"),
                ("tx", "recurring_payment_id"), ("tx", "recurring_record_id"),
                ("payment", "recurring_record_id"), ("record", "bill_payment_id")):
            with self.subTest(owner=owner, field=field):
                p, r, tx = graph(amount=100)
                provenance(doc, p, r, tx)
                p["deleted"] = r["deleted"] = True
                {"tx": tx, "payment": p, "record": r}[owner][field] = "foreign-reference"
                # Invoke the database reader too, not just the pure verifier.
                for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
                    await self.transaction(lambda session, c=col: getattr(self.db, c).delete_many({}, session=session))
                    await self.insert(col, value)
                before = await self.snapshot()
                async def inspect(session):
                    return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                        effective_user=USER, session=session)
                await self.rejected_async(inspect)
                self.assertEqual(await self.snapshot(), before)

    async def test_retired_absent_links_allowed_but_reciprocal_conflict_rejected(self):
        doc = self.pure_document()
        p, r, tx = graph(amount=100)
        provenance(doc, p, r, tx)
        p["deleted"] = r["deleted"] = True
        for field in ("bill_id", "bill_payment_id", "recurring_payment_id", "recurring_record_id"):
            tx[field] = "" if "payment" in field else None
        p["recurring_record_id"], r["bill_payment_id"] = None, ""
        before = copy.deepcopy((p, r, tx))
        self.assertEqual(shared.verify_payments(doc, self.scope, payments=[p], records=[r], movements=[tx]).paid, 100)
        self.assertEqual((p, r, tx), before)
        p2 = dict(p, _id="other-payment", id="other-payment", recurring_record_id=r["id"])
        p["recurring_record_id"], r["bill_payment_id"] = r["id"], p2["id"]
        before = copy.deepcopy((p, p2, r, tx))
        self.rejected(lambda: shared.verify_payments(doc, self.scope, payments=[p, p2], records=[r], movements=[tx]))
        self.assertEqual((p, p2, r, tx), before)

    async def test_stale_persisted_identity_rejected_without_writes(self):
        doc = await self.transaction(self.create)
        p, r, tx = graph(amount=70)
        for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.insert(col, value)
        await self.transaction(lambda session: self.db.shared_obligations.update_one(
            {"_id": doc["_id"]}, {"$set": {"actual_amount": Decimal128("50"), "revision": 1}}, session=session))
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        await self.rejected_async(inspect)
        current = await self.db.shared_obligations.find_one({"_id": doc["_id"]})
        async def inspect_current(session):
            return await shared.inspect_payments(self.db, current, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        await self.rejected_async(inspect_current)  # canonical 70 > 50
        self.assertEqual(await self.snapshot(), before)

    async def test_recurring_orphan_not_invisible(self):
        doc = await self.transaction(self.create)
        p, r, tx = graph(amount=100)
        for key in ("bill_id", "bill_payment_id"):
            tx.pop(key)
        await self.insert("transactions", tx)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        await self.rejected_async(inspect)
        self.assertEqual(await self.snapshot(), before)

    async def test_explicit_draft_cannot_override_persisted_identity(self):
        doc = self.pure_document()
        before = await self.snapshot()
        async def inspect(session, value=doc, draft=False):
            return await shared.inspect_payments(self.db, value, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session, draft=draft)
        await self.rejected_async(inspect)
        result = await self.transaction(lambda session: inspect(session, draft=True))
        self.assertEqual((result.paid, result.remaining), (0, 100))
        self.assertEqual(await self.snapshot(), before)
        canonical = await self.transaction(self.create)
        before = await self.snapshot()
        await self.rejected_async(lambda session: inspect(session, draft=True))
        spoofed = dict(canonical, actual_amount=Decimal128("200"))
        result = await self.transaction(lambda session: inspect(session, value=spoofed))
        self.assertEqual(result.remaining, 100)  # canonical wins even same revision
        wrong_bill = dict(canonical, bill_id="different-bill")
        await self.rejected_async(lambda session: inspect(session, value=wrong_bill, draft=True))
        self.assertEqual(await self.snapshot(), before)

    async def test_valid_other_period_does_not_block_inspection(self):
        doc = await self.transaction(self.create)
        p, r, tx = graph(amount=30)
        for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.insert(col, value)
        p2, r2, tx2 = graph("other", 100)
        r2.update(due_date="2026-11-20", mode="expense")
        r2.pop("bill_payment_id")
        tx2.pop("bill_id")
        tx2.pop("bill_payment_id")
        await self.insert("recurring_payment_records", r2)
        await self.insert("transactions", tx2)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual((result.paid, result.remaining, result.transaction_ids), (30, 70, ("tx1",)))
        self.assertEqual(await self.snapshot(), before)
        await self.transaction(lambda session: self.db.recurring_payment_records.update_one(
            {"id": r2["id"]}, {"$set": {"account_id": "contradiction"}}, session=session))
        before = await self.snapshot()
        await self.rejected_async(inspect)
        self.assertEqual(await self.snapshot(), before)

    async def test_other_shared_period_verified_without_cross_association(self):
        doc = await self.transaction(self.create)
        bill, rp = parents()
        bill.update(_id="other-bill", id="other-bill", due_date="2026-11-20")
        other = shared.resolve_documents(bill, rp, self.scope, occurrences=self.occurrences)
        await self.insert("bills", bill)
        await self.insert("shared_obligations", other)
        p, r, tx = graph("other", 50)
        p["bill_id"] = tx["bill_id"] = "other-bill"
        r["due_date"] = "2026-11-20"
        provenance(other, p, r, tx)
        for col, value in (("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.insert(col, value)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual((result.paid, result.remaining), (0, 100))
        self.assertEqual(await self.snapshot(), before)
        await self.transaction(lambda session: self.db.transactions.update_one(
            {"id": tx["id"]}, {"$set": {"bill_payment_id": "foreign-payment"}}, session=session))
        before = await self.snapshot()
        await self.rejected_async(inspect)
        self.assertEqual(await self.snapshot(), before)

    async def test_other_legacy_bill_payment_from_current_route_is_excluded(self):
        doc = await self.transaction(self.create)
        bill, rp = parents()
        bill.update(_id="bill-nov", id="bill-nov", due_date="2026-11-20")
        await self.insert("bills", bill)
        response = await self.ctx.request("POST", "/bills/bill-nov/payments",
            json={"amount": 70, "account_id": "account"}, headers={"Idempotency-Key": "nov-real-route"})
        self.assertEqual(response.status_code, 200, response.text)
        payment = response.json()
        record = await self.db.recurring_payment_records.find_one({"id": payment["recurring_record_id"]})
        tx = await self.db.transactions.find_one({"id": payment["transaction_id"]})
        self.assertEqual(record["due_date"], "2026-11-20")
        self.assertEqual((record["bill_payment_id"], tx["bill_payment_id"]), (payment["id"], payment["id"]))
        self.assertNotIn("_shared_obligation_id", tx)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual((result.paid, result.remaining, result.transaction_ids), (0, 100, ()))
        self.assertEqual(await self.snapshot(), before)
        self.assertEqual(len(before["shared_obligations"]), 1)
        self.assertEqual(len(before["bill_payments"]), 1)
        self.assertEqual(len(before["transactions"]), 1)
        self.assertEqual(before["accounts"][0]["current_balance"], 930)

    async def test_activation_flag_defaults_and_no_effect_when_disabled(self):
        before = await self.snapshot()
        for flag in (None, "0"):
            settings = activation_settings(flag, expected=None)
            self.assertFalse(settings.shared_obligations_enabled)
            with patch.object(shared, "_hello", side_effect=AssertionError("No topology read when disabled")):
                await self.rejected_async(lambda session: shared.require_activation(
                    self.db, settings, effective_user=USER, session=session))
        for flag in ("", "true", "false", "yes", "2"):
            with self.assertRaises(ConfigurationError):
                activation_settings(flag)
        self.assertEqual(await self.snapshot(), before)

    async def test_activation_context_and_indices_fail_closed(self):
        hello = dict(setName="synthetic_rs", isWritablePrimary=True, maxWireVersion=17, logicalSessionTimeoutMinutes=30)
        before = await self.snapshot()
        with patch.object(shared, "_hello", AsyncMock(return_value=hello)):
            async def ready(session):
                return await shared.require_activation(self.db, activation_settings("1"), effective_user=USER, session=session)
            self.assertEqual(await self.transaction(ready), self.scope)
            for expected in (None, "invalid", OTHER_ENVIRONMENT):
                await self.rejected_async(lambda session: shared.require_activation(self.db,
                    activation_settings("1", expected), effective_user=USER, session=session), 503)
            with patch.object(shared, "require_indexes", AsyncMock(side_effect=HTTPException(503, "Missing indices"))):
                await self.rejected_async(ready, 503)
        self.assertEqual(await self.snapshot(), before)

    async def test_activation_rejects_transaction_incapable_topologies(self):
        good = dict(setName="synthetic_rs", isWritablePrimary=True, maxWireVersion=17, logicalSessionTimeoutMinutes=30)
        bad = ({k:v for k,v in good.items() if k != "setName"}, dict(good, logicalSessionTimeoutMinutes=None),
               dict(good, isWritablePrimary=False), dict(good, maxWireVersion=6),
               dict(good, msg="isdbgrid", maxWireVersion=7))
        before = await self.snapshot()
        for topology in bad:
            with patch.object(shared, "_hello", AsyncMock(return_value=topology)):
                await self.rejected_async(lambda session: shared.require_activation(self.db,
                    activation_settings("1"), effective_user=USER, session=session), 503)
        self.assertEqual(await self.snapshot(), before)

    async def test_disabled_managed_obligation_detector_and_legacy_guard(self):
        self.assertFalse(activation_settings().shared_obligations_enabled)
        async def detected(session, **changes):
            return await shared.has_managed_obligation(self.db, effective_user=USER,
                session=session, **(dict(bill_id="bill") | changes))
        before = await self.snapshot()
        self.assertFalse(await self.transaction(detected))
        self.assertEqual(await self.snapshot(), before)
        await self.transaction(self.create)
        before = await self.snapshot()
        self.assertTrue(await self.transaction(detected))
        async def guard(session):
            return await shared.require_legacy_allowed(self.db, effective_user=USER, session=session, bill_id="bill")
        await self.rejected_async(guard)
        self.assertFalse(await self.transaction(lambda session: detected(session, bill_id="another-bill")))
        self.assertTrue(await self.transaction(lambda session: shared.has_managed_obligation(
            self.db, effective_user=USER, session=session, recurring_id="rp", original_due_date="2026-10-20")))
        self.assertEqual(await self.snapshot(), before)

    async def test_detector_preserves_corrupt_and_retired_markers(self):
        await self.insert("bill_payments", dict(id="tombstone", user_id=USER, bill_id="bill", transaction_id="old-tx",
            deleted=True, _shared_obligation_id="missing-or-corrupt"))
        before = await self.snapshot()
        for lookup in (dict(bill_id="bill"), dict(transaction_id="old-tx")):
            self.assertTrue(await self.transaction(lambda session: shared.has_managed_obligation(
                self.db, effective_user=USER, session=session, **lookup)))
        await self.rejected_async(lambda session: shared.has_managed_obligation(
            self.db, effective_user=USER, session=session, recurring_id="rp"))
        self.assertEqual(await self.snapshot(), before)

    async def test_activation_and_detector_database_errors_never_allow_fallback(self):
        before = await self.snapshot()
        class UnavailableDatabase:
            def __getattr__(inner, name):
                raise OperationFailure("Synthetic read failure")
        await self.rejected_async(lambda session: shared.has_managed_obligation(
            UnavailableDatabase(), effective_user=USER, session=session, bill_id="bill"), 503)
        with patch.object(shared, "_hello", AsyncMock(side_effect=OperationFailure("Synthetic hello failure"))):
            await self.rejected_async(lambda session: shared.require_activation(self.db,
                activation_settings("1"), effective_user=USER, session=session), 503)
        topology = dict(setName="synthetic_rs", isWritablePrimary=True, maxWireVersion=17, logicalSessionTimeoutMinutes=30)
        with patch.object(shared, "_hello", AsyncMock(return_value=topology)), patch.object(
                shared, "_scope", AsyncMock(side_effect=OperationFailure("Transactions not supported"))):
            await self.rejected_async(lambda session: shared.require_activation(self.db,
                activation_settings("1"), effective_user=USER, session=session), 503)
        self.assertEqual(await self.snapshot(), before)

    async def test_legacy_other_period_incompatible_graphs_still_conflict(self):
        doc = await self.transaction(self.create)
        bill, rp = parents()
        bill.update(_id="legacy-nov", id="legacy-nov", due_date="2026-11-20")
        p, r, tx = graph("legacy", 70)
        p["bill_id"] = tx["bill_id"] = bill["id"]
        r["due_date"] = "2026-11-20"
        originals = {"bills": bill, "bill_payments": p, "recurring_payment_records": r, "transactions": tx}
        for col, value in originals.items():
            await self.insert(col, value)
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        cases = (("bill_payments", "transaction_id", "foreign"),
            ("bill_payments", "recurring_record_id", "foreign"),
            ("bill_payments", "bill_id", "bill"),
            ("bill_payments", "account_id", "foreign"),
            ("bill_payments", "amount", "70.0000000000000001"),
            ("recurring_payment_records", "bill_payment_id", "foreign"),
            ("recurring_payment_records", "recurring_id", "foreign"),
            ("recurring_payment_records", "account_id", "foreign"),
            ("recurring_payment_records", "amount", "70.0000000000000001"),
            ("recurring_payment_records", "due_date", "2026-10-20"),
            ("recurring_payment_records", "due_date", "not-a-period"),
            ("transactions", "bill_payment_id", "foreign"),
            ("transactions", "recurring_record_id", "foreign"),
            ("transactions", "account_id", "foreign"),
            ("transactions", "amount", "70.0000000000000001"),
            ("bills", "recurring_payment_id", "foreign"),
            ("bills", "user_id", "other-user"),
            ("bill_payments", "deleted", True),
            ("recurring_payment_records", "deleted", True))
        for col, field, value in cases:
            with self.subTest(collection=col, field=field, value=value):
                original = originals[col]
                await self.transaction(lambda session: getattr(self.db, col).update_one(
                    {"_id": original["_id"]}, {"$set": {field: value}}, session=session))
                before = await self.snapshot()
                await self.rejected_async(inspect)
                self.assertEqual(await self.snapshot(), before)
                update = {"$set": {field: original[field]}} if field in original else {"$unset": {field: ""}}
                await self.transaction(lambda session: getattr(self.db, col).update_one(
                    {"_id": original["_id"]}, update, session=session))
        # A second receipt on the same movement with another due is ambiguous.
        extra = dict(r, _id="ambiguous", id="ambiguous", due_date="2026-12-20")
        await self.insert("recurring_payment_records", extra)
        before = await self.snapshot()
        await self.rejected_async(inspect)
        self.assertEqual(await self.snapshot(), before)

    async def test_legacy_other_period_uses_historical_record_not_current_bill_date(self):
        doc = await self.transaction(self.create)
        bill, rp = parents()
        bill.update(_id="historical-nov", id="historical-nov", due_date="2027-01-01")
        p, r, tx = graph("historic", 70)
        p["bill_id"] = tx["bill_id"] = bill["id"]
        r.update(due_date="2026-11-20", amount=Decimal128("70.000"))
        p["amount"] = "70.00"
        for col, value in (("bills", bill), ("bill_payments", p), ("recurring_payment_records", r), ("transactions", tx)):
            await self.insert(col, value)
        before = await self.snapshot()
        async def inspect(session):
            return await shared.inspect_payments(self.db, doc, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session)
        result = await self.transaction(inspect)
        self.assertEqual((result.paid, result.remaining), (0, 100))
        self.assertEqual(await self.snapshot(), before)


class SharedObligationTests(SharedCases, unittest.IsolatedAsyncioTestCase):
    real = False

    async def asyncSetUp(self):
        self.db = MemoryDatabase()
        self.collections = tuple(self.db.data)
        self.client = memory.Client(self.db)
        self.ctx = context(self.db, self.client)
        self.occurrences = self.ctx.ns["_rp_occurrences"]
        self.scope = shared.Scope(ENVIRONMENT, USER)
        await shared.install_indexes(self.db)
        self.db.data["moneyflow_metadata"] = [metadata()]
        bill, rp = parents()
        self.db.data["bills"], self.db.data["recurring_payments"] = [bill], [rp]
        self.db.data["accounts"] = [dict(_id="account", id="account", user_id=USER, initial_balance=1000, current_balance=1000)]

    async def transaction(self, callback):
        async with await self.client.start_session() as session:
            async def call(s):
                s.in_transaction = True
                return await callback(s)
            return await session.with_transaction(call)

    async def insert(self, col, doc):
        # Synthetic fixture setup, not an application write or relaxed guard.
        self.db.data[col].append(copy.deepcopy(doc))

    async def test_missing_or_partial_indexes_block_before_any_write(self):
        self.db.indexes = {}
        before = await self.snapshot()
        await self.rejected_async(self.create, 503)
        self.assertEqual(await self.snapshot(), before)
        await shared.install_indexes(self.db)
        self.db.indexes["shared_bill_unique"]["partialFilterExpression"] = {"lifecycle":"bound"}
        await self.rejected_async(self.create, 503)
        self.assertEqual(await self.snapshot(), before)

    async def test_active_transaction_required(self):
        for session in (None, SimpleNamespace(in_transaction=False)):
            with self.assertRaises(RuntimeError):
                await self.create(session)

    async def test_rollback_metadata_creation_does_not_change_financial_data(self):
        before = await self.snapshot()
        self.db.fail_at = 3  # two parent coordination writes, then identity insert
        with self.assertRaises(Exception):
            await self.transaction(self.create)
        self.assertEqual(await self.snapshot(), before)
