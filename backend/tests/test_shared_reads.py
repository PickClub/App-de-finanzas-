"""R4 2D.1 dormant readers; synthetic financial state, no server startup."""
import ast
import copy
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock

from fastapi import HTTPException
from pymongo.errors import OperationFailure
from backend import shared_obligations as shared
from backend.tests import test_shared_payments as core
from backend.tests.test_shared_obligations import ENVIRONMENT, USER, parents

TODAY = date(2026, 10, 10)


class ReadCases:
    snapshot = core.PaymentCases.snapshot
    transact = core.PaymentCases.transact
    intent = core.PaymentCases.intent
    pay = core.PaymentCases.pay
    change = core.PaymentCases.change

    async def seed(self, collection, doc):
        return await self.transact(lambda session: getattr(self.db, collection).insert_one(doc, session=session))

    async def update(self, collection, query, changes):
        return await self.transact(lambda session: getattr(self.db, collection).update_one(query, {"$set": changes}, session=session))

    async def view(self, **selector):
        return await self.transact(lambda session: shared.read_shared_view(self.db,
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            **(selector or {"bill_id": "bill"})))

    def bill(self, view):
        bill, _ = parents()
        bill.update(amount=float(self.ob["actual_amount"].to_decimal()), due_date="2026-10-20",
                    reminder_days=3, payments=[])
        # Use the existing actual serializer, never start a server/client.
        public = self.ctx.ns["_bill_public"](bill, 0, TODAY)
        public["payments"] = []
        return shared.shared_bill_public(public, view, TODAY)

    def period(self, view):
        legacy = self.ctx.ns["_rp_state"]({}, "2026-10-20", 100, list(view.records), TODAY)
        return shared.shared_recurring_public(legacy, view, TODAY)

    async def test_partial_and_complete_unique_movements(self):
        await self.pay("one", 60)
        before = await self.snapshot()
        view = await self.view()
        self.assertEqual((self.bill(view)["paid_amount"], self.period(view)["remaining"]), (60, 40))
        self.assertEqual(len(shared.shared_paid_events([view])), 1)
        self.assertEqual(await self.snapshot(), before)
        await self.pay("two", 40, "recurring")
        view = await self.view()
        self.assertEqual((self.bill(view)["status"], self.period(view)["paid"]), ("paid", 100))
        self.assertEqual(len(shared.shared_paid_events([view])), 2)

    async def test_retired_tracking_keeps_financial_paid(self):
        await self.pay("retire", 60)
        await self.change("retire", "bill", "retire_both")
        before = await self.snapshot()
        view = await self.view()
        self.assertEqual((self.bill(view)["paid_amount"], self.period(view)["remaining"]), (60, 40))
        self.assertEqual((self.bill(view)["payments"], self.period(view)["records"]), ([], []))
        self.assertEqual(len(shared.shared_paid_events([view])), 1)
        self.assertEqual(await self.snapshot(), before)

    async def test_annulled_money_is_not_paid(self):
        await self.pay("annul", 60)
        await self.change("annul", "bill", "annul")
        before = await self.snapshot()
        view = await self.view()
        self.assertEqual((self.bill(view)["paid_amount"], self.period(view)["remaining"]), (0, 100))
        self.assertEqual(shared.shared_paid_events([view]), [])
        self.assertEqual(await self.snapshot(), before)

    async def test_mark_and_settles_do_not_pay_money(self):
        await self.seed("recurring_payment_records", dict(_id="mark", id="mark", user_id=USER,
            recurring_id="rp", due_date="2026-10-20", mode="mark", amount=100, settles=True,
            transaction_id=None, created_at="2026-10-01"))
        before = await self.snapshot()
        view = await self.view()
        self.assertEqual((self.period(view)["paid"], self.period(view)["remaining"]), (0, 100))
        self.assertEqual(shared.shared_paid_events([view]), [])
        self.assertEqual(await self.snapshot(), before)

    async def test_variable_actual_amount_and_frozen_period(self):
        await self.update("shared_obligations", {"_id": self.ob["_id"]}, {
            "actual_amount": shared.Decimal128("50"), "variable_snapshot": True})
        await self.update("bills", {"id": "bill"}, {"amount": 50})
        self.ob = await self.db.shared_obligations.find_one({"_id": self.ob["_id"]})
        await self.pay("variable", 50)
        view = await self.view()
        self.assertEqual((self.period(view)["expected"], self.period(view)["paid"], self.period(view)["remaining"]), (50, 50, 0))
        await self.update("recurring_payments", {"id": "rp"}, {"versions": []})
        before = await self.snapshot()
        views = await self.transact(lambda session: shared.read_shared_periods(self.db, "rp",
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session))
        states = shared.shared_period_states([], views, TODAY)
        self.assertEqual(states[0]["due_date"], "2026-10-20")
        self.assertEqual(states[0]["remaining"], 0)
        self.assertEqual(await self.snapshot(), before)

    async def test_legacy_absence_and_corrupt_history_fail_closed(self):
        self.assertIsNone(await self.view(bill_id="unmanaged"))
        before = await self.snapshot()
        await self.seed("transactions", dict(_id="orphan", id="orphan", user_id=USER,
            recurring_payment_id="rp", type="expense", amount=20, account_id="account"))
        corrupt = await self.snapshot()
        with self.assertRaises(HTTPException) as exc:
            await self.view()
        self.assertEqual(exc.exception.status_code, 409)
        self.assertEqual(await self.snapshot(), corrupt)
        self.assertNotEqual(before, corrupt)

    async def test_lookup_error_is_not_absence(self):
        before = await self.snapshot()
        with patch.object(shared, "has_managed_obligation", AsyncMock(side_effect=OperationFailure("read unavailable"))):
            with self.assertRaises(HTTPException) as exc:
                await self.view(bill_id="unmanaged")
        self.assertEqual(exc.exception.status_code, 503)
        self.assertEqual(await self.snapshot(), before)

    async def test_original_period_not_amount_or_date_matching(self):
        await self.pay("one", 40)
        before = await self.snapshot()
        self.assertIsNone(await self.view(recurring_id="rp", original_due_date="2026-11-20"))
        october = await self.view(recurring_id="rp", original_due_date="2026-10-20")
        self.assertEqual(october.summary.paid, 40)
        self.assertEqual(await self.snapshot(), before)

    async def test_valid_other_period_is_not_counted(self):
        await self.pay("october", 30)
        bill, _ = parents()
        bill.update(_id="november", id="november", due_date="2026-11-20")
        await self.seed("bills", bill)
        ob = await self.transact(lambda session: shared.create_shared_obligation(self.db, "november",
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            occurrences=self.ctx.ns["_rp_occurrences"]))
        payload = self.ctx.ns["BillPayIn"](amount=70, account_id="second").model_dump()
        await self.transact(lambda session: shared.register_shared_payment(self.db, ob["_id"],
            origin="bill", receipt_id="november-payment", transaction_id="november-expense", payload=payload,
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            recompute_account_balance=self.ctx.ns["recompute_account_balance"]))
        before = await self.snapshot()
        october = await self.view()
        november = await self.view(bill_id="november")
        self.assertEqual((october.summary.paid, november.summary.paid), (30, 70))
        self.assertEqual(len(shared.shared_paid_events([october, november])), 2)
        self.assertEqual(await self.snapshot(), before)

    async def test_public_metadata_and_calendar_projection(self):
        await self.pay("one", 60)
        view = await self.view()
        event = dict(id="bill:bill", source="bill", ref_id="bill", date="2099-01-01", amount=100,
                     realized=False, counts_in_net=False, status="pending", partial=False)
        projected = shared.shared_calendar_due(event, view, TODAY)
        self.assertEqual((projected["date"], projected["amount"]), ("2026-10-20", 40))
        def keys(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    self.assertFalse(k.startswith("_shared_"))
                    self.assertNotIn(k, {"_id", "request_fingerprint", "_reference_revision", "_payment_revision"})
                    keys(v)
            elif isinstance(value, list):
                for v in value: keys(v)
        keys(self.bill(view)); keys(self.period(view)); keys(shared.shared_paid_events([view]))
        await self.pay("complete", 40)
        self.assertIsNone(shared.shared_calendar_due(event, await self.view(), TODAY))


class EndpointReadCases:
    async def get(self, path):
        from types import SimpleNamespace
        self.ctx.ns["settings"] = SimpleNamespace(expected_financial_environment_id=ENVIRONMENT)
        with patch.dict(self.ctx.ns, {"_rp_today": lambda *args: TODAY}):
            return await self.ctx.request("GET", path)

    async def good_get(self, path):
        response = await self.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_shared_", response.text)
        self.assertNotIn("request_fingerprint", response.text)
        self.assertNotIn("_reference_revision", response.text)
        self.assertNotIn("_payment_revision", response.text)
        return response.json()

    async def test_endpoints_partial_retired_and_complete(self):
        await self.pay("one", 60, date="2026-10-11T12:00:00+00:00")
        await self.change("one", "bill", "retire_both")
        before = await self.snapshot()
        bill = await self.good_get("/bills/bill")
        self.assertEqual((bill["paid_amount"], bill["remaining"], bill["payments"]), (60, 40, []))
        listed = await self.good_get("/bills")
        self.assertEqual(listed["items"][0]["remaining"], 40)
        summary = await self.good_get("/bills/summary?year=2026&month=10")
        self.assertEqual(summary["paid_month"], {"amount": 60, "count": 1})
        self.assertEqual(summary["pending"], {"amount": 40, "count": 1})
        detail = await self.good_get("/recurring-payments/rp")
        self.assertEqual((detail["paid_total"], detail["payments_count"]), (60, 1))
        occurrences = await self.good_get("/recurring-payments/rp/occurrences")
        state = next(s for s in occurrences["items"] if s["due_date"] == "2026-10-20")
        self.assertEqual((state["paid"], state["remaining"]), (60, 40))
        overview = await self.good_get("/recurring-payments/overview?year=2026&month=10")
        self.assertEqual(overview["totals"]["paid"], 60)
        self.assertEqual(overview["totals"]["pending"], 40)
        self.assertEqual(await self.snapshot(), before)
        # Fully paid identity with one retired tracking view still reads paid.
        await self.update("shared_obligations", {"_id": self.ob["_id"]}, {"lifecycle": "bound"})
        await self.pay("two", 40, "recurring", date="2026-10-12T12:00:00+00:00")
        bill = await self.good_get("/bills/bill")
        self.assertEqual((bill["status"], bill["remaining"]), ("paid", 0))
        summary = await self.good_get("/bills/summary?year=2026&month=10")
        self.assertEqual(summary["paid_month"], {"amount": 100, "count": 2})

    async def test_endpoints_marks_do_not_settle_and_annulment_is_read_correctly(self):
        await self.seed("recurring_payment_records", dict(_id="mark", id="mark", user_id=USER,
            recurring_id="rp", due_date="2026-10-20", mode="mark", amount=100, settles=True,
            transaction_id=None, created_at="2026-10-01"))
        overview = await self.good_get("/recurring-payments/overview?year=2026&month=10")
        self.assertEqual((overview["totals"]["paid"], overview["totals"]["pending"]), (0, 100))
        detail = await self.good_get("/recurring-payments/rp")
        self.assertEqual((detail["paid_total"], detail["payments_count"]), (0, 0))
        # Mark history is not silently adopted into money: prepare a separate
        # synthetic annulled event by removing only the test mark in a test txn.
        await self.transact(lambda session: self.db.recurring_payment_records.delete_one({"id": "mark"}, session=session))
        await self.pay("annul", 40)
        await self.change("annul", "bill", "annul")
        before = await self.snapshot()
        self.assertEqual((await self.good_get("/bills/bill"))["paid_amount"], 0)
        self.assertEqual((await self.good_get("/recurring-payments/rp"))["paid_total"], 0)
        self.assertEqual(await self.snapshot(), before)

    async def test_endpoints_calendar_one_pending_and_one_real_expense(self):
        await self.pay("one", 60, date="2026-10-11T12:00:00+00:00")
        await self.change("one", "bill", "retire_both")
        before = await self.snapshot()
        result = await self.good_get("/calendar/events?start=2026-10-01&end=2026-10-31")
        planned = [e for e in result["events"] if e["kind"] in ("bill", "recurring") and not e["realized"]]
        self.assertEqual([(e["date"], e["amount"]) for e in planned], [("2026-10-20", 40)])
        actual = [e for e in result["events"] if e["realized"] and e["counts_in_net"]]
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]["amount"], 60)
        upcoming = await self.good_get("/calendar/upcoming?days=30")
        self.assertEqual([(e["date"], e["amount"]) for e in upcoming["items"]], [("2026-10-20", 40)])
        summary = await self.good_get("/calendar/summary?year=2026&month=10")
        self.assertEqual(summary["bills"], {"amount": 100, "count": 1, "available": True})
        self.assertEqual(await self.snapshot(), before)

    async def test_endpoints_frozen_dates_and_variable_amount(self):
        await self.update("shared_obligations", {"_id": self.ob["_id"]}, {
            "actual_amount": shared.Decimal128("50"), "variable_snapshot": True})
        await self.update("bills", {"id": "bill"}, {"amount": 50, "due_date": "2026-11-03"})
        await self.update("recurring_payments", {"id": "rp"}, {"versions": []})
        self.ob = await self.db.shared_obligations.find_one({"_id": self.ob["_id"]})
        await self.pay("variable", 20, date="2026-10-11T12:00:00+00:00")
        before = await self.snapshot()
        bill = await self.good_get("/bills/bill")
        self.assertEqual((bill["due_date"], bill["remaining"]), ("2026-10-20", 30))
        overview = await self.good_get("/recurring-payments/overview?year=2026&month=10")
        self.assertEqual((overview["totals"]["expected"], overview["totals"]["pending"]), (50, 30))
        events = (await self.good_get("/calendar/events?start=2026-10-01&end=2026-10-31"))["events"]
        self.assertEqual([e["date"] for e in events if e["kind"] == "bill" and not e["realized"]], ["2026-10-20"])
        self.assertEqual(await self.snapshot(), before)

    async def test_endpoints_ambiguous_history_and_read_errors_fail_closed(self):
        await self.seed("transactions", dict(_id="orphan", id="orphan", user_id=USER,
            recurring_payment_id="rp", type="expense", amount=20, account_id="account"))
        before = await self.snapshot()
        for path in ("/bills", "/bills/bill", "/bills/summary", "/recurring-payments",
                     "/recurring-payments/overview", "/recurring-payments/rp/occurrences",
                     "/calendar/events?start=2026-10-01&end=2026-10-31"):
            response = await self.get(path)
            self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(await self.snapshot(), before)
        with patch.object(shared, "_probe_shared_history", AsyncMock(side_effect=OperationFailure("unavailable"))):
            response = await self.get("/bills")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(await self.snapshot(), before)

    async def test_endpoints_normal_history_unchanged_and_context_does_not_escape(self):
        # Remove only this synthetic test identity before exercising legacy GETs.
        await self.update("recurring_payments", {"id": "rp"}, {"created_at": "2026-10-01"})
        await self.transact(lambda session: self.db.shared_obligations.delete_one({"_id": self.ob["_id"]}, session=session))
        await self.seed("recurring_payment_records", dict(_id="mark", id="mark", user_id=USER,
            recurring_id="rp", due_date="2026-10-20", mode="mark", amount=100, settles=True,
            transaction_id=None, created_at="2026-10-01"))
        before = await self.snapshot()
        overview = await self.good_get("/recurring-payments/overview?year=2026&month=10")
        self.assertEqual(overview["totals"]["paid"], 100)  # unchanged legacy tracking semantics
        bill = await self.good_get("/bills/bill")
        self.assertEqual(bill["remaining"], 100)
        self.assertIsNone(shared.current_shared_view(bill_id="bill"))
        self.assertEqual(await self.snapshot(), before)

    async def test_endpoints_other_periods_and_constant_network_queries(self):
        class CountDatabase:
            def __init__(self, database):
                self.database, self.calls = database, 0

            def __getattr__(self, name):
                owner, col = self, getattr(self.database, name)
                class CountCollection:
                    def find(self, *args, **kwargs):
                        owner.calls += 1
                        return col.find(*args, **kwargs)
                    async def find_one(self, *args, **kwargs):
                        owner.calls += 1
                        return await col.find_one(*args, **kwargs)
                return CountCollection()
        await self.pay("october", 30, date="2026-10-11T12:00:00+00:00")
        counted = CountDatabase(self.db)
        with patch.dict(self.ctx.ns, {"db": counted}):
            await self.good_get("/bills")
        first_calls = counted.calls
        bill, _ = parents()
        bill.update(_id="november", id="november", due_date="2026-11-20")
        await self.seed("bills", bill)
        ob = await self.transact(lambda session: shared.create_shared_obligation(self.db, "november",
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            occurrences=self.ctx.ns["_rp_occurrences"]))
        payload = self.ctx.ns["BillPayIn"](amount=70, account_id="second", date="2026-11-11T12:00:00+00:00").model_dump()
        await self.transact(lambda session: shared.register_shared_payment(self.db, ob["_id"],
            origin="bill", receipt_id="november-payment", transaction_id="november-expense", payload=payload,
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            recompute_account_balance=self.ctx.ns["recompute_account_balance"]))
        before = await self.snapshot()
        counted.calls = 0
        with patch.dict(self.ctx.ns, {"db": counted}):
            listed = await self.good_get("/bills")
        self.assertEqual(counted.calls, first_calls)
        self.assertEqual(first_calls, 13)
        self.assertEqual({b["id"]: b["paid_amount"] for b in listed["items"]}, {"bill": 30, "november": 70})
        summary = await self.good_get("/bills/summary?year=2026&month=10")
        self.assertEqual(summary["paid_month"], {"amount": 30, "count": 1})
        self.assertEqual(await self.snapshot(), before)

    async def test_endpoints_crossed_provenance_and_invalid_movement_date_rejected(self):
        bill, _ = parents()
        bill.update(_id="crossed", id="crossed", _shared_obligation_id=self.ob["_id"])
        await self.seed("bills", bill)
        before = await self.snapshot()
        response = await self.get("/bills")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(await self.snapshot(), before)
        await self.transact(lambda session: self.db.bills.delete_one({"id": "crossed"}, session=session))
        result = await self.pay("bad-date", 30)
        await self.update("transactions", {"id": result.transaction_id}, {"date": "unverifiable"})
        before = await self.snapshot()
        response = await self.get("/calendar/events?start=2026-10-01&end=2026-10-31")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(await self.snapshot(), before)


class SharedReadTests(ReadCases, EndpointReadCases, unittest.IsolatedAsyncioTestCase):
    asyncSetUp = core.SharedPaymentTests.asyncSetUp

    def test_recursive_serializer_preserves_legacy_contract(self):
        doc = dict(id="p", amount=70, account_id=None, notes="", bill_id="bill",
                   request_fingerprint="secret", _reference_revision=2,
                   _shared_intent={"payload": "private"}, nested=[{"id": "tx", "_shared_obligation_id": "hidden"}])
        old = copy.deepcopy(doc)
        self.assertEqual(shared.public_financial_document(doc), dict(id="p", amount=70,
            account_id=None, notes="", bill_id="bill", nested=[{"id": "tx"}]))
        self.assertEqual(doc, old)

    def test_no_endpoint_calls_prepared_readers_or_core(self):
        tree = ast.parse(Path("backend/server.py").read_text())
        forbidden = {"_shared_bill_read", "_shared_recurring_read", "register_shared_payment", "change_shared_payment"}
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and node.decorator_list:
                called = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
                self.assertFalse(called & forbidden, node.name)
