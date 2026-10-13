"""Internal R4 2C: original route IDs/payloads, no public payment integration."""
import asyncio
import copy
import unittest
import uuid

from fastapi import HTTPException
from backend import shared_obligations as shared
from backend.tests import test_payment_consistency as memory
from backend.tests.test_reference_integrity import context
from backend.tests.test_shared_obligations import MemoryDatabase, parents, metadata, ENVIRONMENT, USER


class PaymentCases:
    async def snapshot(self):
        return {c: await getattr(self.db, c).find({}).to_list(None) for c in self.collections}

    async def transact(self, callback):
        return await self.ctx.ns["payment_transaction"](callback)

    def intent(self, key, amount=60, origin="bill", account="account", **changes):
        if origin == "bill":
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{USER}:bill-payment:bill:{key}"))
            tid = str(uuid.uuid5(uuid.NAMESPACE_URL, "bill-payment-movement:"+pid))
            payload = self.ctx.ns["BillPayIn"](amount=amount, account_id=account).model_dump()
        else:
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{USER}:recurring-record:rp:{key}"))
            tid = str(uuid.uuid5(uuid.NAMESPACE_URL, "recurring-record-movement:"+pid))
            payload = self.ctx.ns["RecurringPayRecordCreate"](amount=amount, account_id=account,
                due_date=self.ob["original_due_date"], mode="expense", settles=False).model_dump()
        payload.update(changes)
        return dict(origin=origin, receipt_id=pid, transaction_id=tid, payload=payload)

    async def pay(self, key, amount=60, origin="bill", account="account", **changes):
        intent = self.intent(key, amount, origin, account, **changes)
        return await self.transact(lambda session: shared.register_shared_payment(self.db, self.ob["_id"],
            **intent, expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            recompute_account_balance=self.ctx.ns["recompute_account_balance"]))

    async def change(self, key, origin, action):
        intent = self.intent(key, origin=origin)
        return await self.transact(lambda session: shared.change_shared_payment(self.db, self.ob["_id"],
            origin=origin, receipt_id=intent["receipt_id"], action=action,
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
            recompute_account_balance=self.ctx.ns["recompute_account_balance"]))

    async def rejected(self, operation, code=409):
        before = await self.snapshot()
        with self.assertRaises(HTTPException) as exc:
            await operation()
        self.assertEqual(exc.exception.status_code, code)
        self.assertEqual(await self.snapshot(), before)

    async def test_interleaved_sixty_forty_one_movement_per_intention(self):
        first = await self.pay("first", 60)
        second = await self.pay("second", 40, "recurring")
        self.assertTrue(first.created and second.created)
        self.assertEqual((second.summary.paid, second.summary.remaining), (100, 0))
        data = await self.snapshot()
        self.assertEqual((len(data["transactions"]), len(data["bill_payments"]), len(data["recurring_payment_records"])), (2, 2, 2))
        self.assertEqual(data["accounts"][0]["current_balance"], 900)
        self.assertEqual(first.transaction_id, self.intent("first", 60)["transaction_id"])
        self.assertEqual(second.recurring_record["id"], self.intent("second", 40, "recurring")["receipt_id"])
        await self.rejected(lambda: self.pay("third", 1))

    async def test_same_origin_id_replays_exactly_different_payload_rejected(self):
        original = await self.pay("retry", 30)
        before = await self.snapshot()
        replay = await self.pay("retry", 30)
        self.assertFalse(replay.created)
        self.assertEqual(replay.transaction_id, original.transaction_id)
        self.assertEqual(await self.snapshot(), before)
        await self.rejected(lambda: self.pay("retry", 31))
        await self.rejected(lambda: self.pay("retry", 30, notes="different"))
        other = await self.pay("legitimate", 30)
        self.assertTrue(other.created)
        self.assertEqual((other.summary.paid, other.summary.remaining), (60, 40))
        self.assertNotEqual(other.transaction_id, original.transaction_id)

    async def test_seventy_seventy_and_cross_account_partials(self):
        await self.pay("one", 70, account="account")
        await self.rejected(lambda: self.pay("two", 70, "recurring", "second"))
        completed = await self.pay("three", 30, "recurring", "second")
        self.assertEqual((completed.summary.paid, completed.summary.remaining), (100, 0))
        accounts = (await self.snapshot())["accounts"]
        self.assertEqual([a["current_balance"] for a in accounts], [930, 970])

    async def test_retirement_never_refunds_and_original_intention_recovers(self):
        await self.pay("retire", 60)
        for action in ("retire_recurring", "retire_bill"):
            result = await self.change("retire", "bill", action)
            self.assertEqual((result.summary.paid, result.summary.remaining), (60, 40))
            self.assertEqual((await self.snapshot())["accounts"][0]["current_balance"], 940)
            before = await self.snapshot()
            replay = await self.pay("retire", 60)
            self.assertFalse(replay.created)
            self.assertEqual(await self.snapshot(), before)
        await self.rejected(lambda: self.pay("replacement", 40))
        self.assertEqual((await self.db.shared_obligations.find_one({"_id": self.ob["_id"]}))["lifecycle"], "tracking_detached")

    async def test_annulment_refunds_once_and_tombstones_prevent_resurrection(self):
        original = await self.pay("annul", 60, "recurring")
        result = await self.change("annul", "recurring", "annul")
        self.assertEqual((result.financial_state, result.summary.paid, result.summary.remaining), ("annulled", 0, 100))
        data = await self.snapshot()
        self.assertEqual(data["accounts"][0]["current_balance"], 1000)
        self.assertEqual(len(data["transactions"]), 0)
        self.assertEqual((len(data["bill_payments"]), len(data["recurring_payment_records"])), (1, 1))
        self.assertEqual(result.transaction_id, original.transaction_id)
        again = await self.change("annul", "recurring", "annul")
        self.assertEqual(again.financial_state, "annulled")
        self.assertEqual(await self.snapshot(), data)
        await self.rejected(lambda: self.pay("annul", 60, "recurring"))
        legitimate = await self.pay("after-refund", 60)
        self.assertEqual(legitimate.summary.paid, 60)
        self.assertEqual((await self.snapshot())["accounts"][0]["current_balance"], 940)

    async def test_history_corruption_is_rejected_without_partial_writes(self):
        event = await self.pay("history", 30)
        async def corrupt(session):
            await self.db.recurring_payment_records.update_one({"id": event.recurring_record["id"]},
                {"$set": {"account_id": "second"}}, session=session)
        await self.transact(corrupt)
        await self.rejected(lambda: self.pay("new", 10))
        await self.rejected(lambda: self.change("history", "bill", "annul"))

    async def test_historical_schedule_changes_do_not_move_period(self):
        async def reschedule(session):
            await self.db.bills.update_one({"id": "bill"}, {"$set": {"due_date": "2026-12-01", "frequency": "once"}}, session=session)
            await self.db.recurring_payments.update_one({"id": "rp"}, {"$set": {"versions": [
                dict(valid_from="2026-11-01", start_date="2026-11-01", frequency="daily", amount=200)]}}, session=session)
        await self.transact(reschedule)
        event = await self.pay("original-period", 30, "recurring")
        self.assertEqual(event.recurring_record["due_date"], "2026-10-20")
        await self.rejected(lambda: self.pay("wrong-period", 30, "recurring", due_date="2026-11-20"))

    async def test_other_verified_period_does_not_enter_common_total(self):
        bill, rp = parents()
        bill.update(_id="nov", id="nov", due_date="2026-11-20")
        async def setup(session):
            await self.db.bills.insert_one(bill, session=session)
        await self.transact(setup)
        response = await self.ctx.request("POST", "/bills/nov/payments", json={"amount": 20, "account_id": "account"})
        self.assertEqual(response.status_code, 200, response.text)
        event = await self.pay("oct", 30)
        self.assertEqual((event.summary.paid, event.summary.remaining), (30, 70))
        self.assertEqual((await self.snapshot())["accounts"][0]["current_balance"], 950)

    async def test_no_foreign_context_or_unrepresentable_amount(self):
        await self.rejected(lambda: self.pay("bad", -1))
        await self.rejected(lambda: self.pay("zero", 0))
        intent = self.intent("context", 10)
        await self.rejected(lambda: self.transact(lambda session: shared.register_shared_payment(
            self.db, self.ob["_id"], **intent, expected_environment_id="22222222-2222-4222-8222-222222222222",
            effective_user=USER, session=session, recompute_account_balance=self.ctx.ns["recompute_account_balance"])), 503)
        for value in (float("inf"), float("nan"), "12345678901234567890.12345"):
            malformed = copy.deepcopy(intent)
            malformed["payload"]["amount"] = value
            await self.rejected(lambda: self.transact(lambda session: shared.register_shared_payment(
                self.db, self.ob["_id"], **malformed, expected_environment_id=ENVIRONMENT,
                effective_user=USER, session=session, recompute_account_balance=self.ctx.ns["recompute_account_balance"])))

    async def test_annulled_orphan_receipt_is_not_silently_adopted(self):
        event = await self.pay("orphan", 30, "recurring")
        await self.change("orphan", "recurring", "annul")
        async def corrupt(session):
            await self.db.bill_payments.delete_one({"id": event.bill_payment["id"]}, session=session)
            await self.db.recurring_payment_records.update_one({"id": event.recurring_record["id"]},
                {"$set": {"bill_payment_id": None}}, session=session)
        await self.transact(corrupt)
        await self.rejected(lambda: self.pay("fresh", 10))

    async def test_normalized_effective_date_preserves_original_payload_and_fingerprint(self):
        intent = self.intent("date", 30, date="2026-10-20")
        async def callback(session, date):
            return await shared.register_shared_payment(self.db, self.ob["_id"], **intent,
                expected_environment_id=ENVIRONMENT, effective_user=USER, session=session,
                recompute_account_balance=self.ctx.ns["recompute_account_balance"], effective_date=date)
        await self.rejected(lambda: self.transact(lambda session: callback(session, "2026-10-21T00:00:00+00:00")))
        result = await self.transact(lambda session: callback(session, "2026-10-20T00:00:00+00:00"))
        self.assertEqual(result.bill_payment["date"], "2026-10-20T00:00:00+00:00")
        self.assertEqual(result.bill_payment["_shared_intent"]["payload"]["date"], "2026-10-20")


class SharedPaymentTests(PaymentCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = MemoryDatabase()
        self.collections = tuple(self.db.data)
        self.client = memory.Client(self.db)
        self.ctx = context(self.db, self.client)
        bill, rp = parents()
        self.db.data["bills"], self.db.data["recurring_payments"] = [bill], [rp]
        self.db.data["moneyflow_metadata"] = [metadata()]
        self.db.data["accounts"] = [dict(_id=aid, id=aid, user_id=USER, initial_balance=1000, current_balance=1000)
            for aid in ("account", "second")]
        await shared.install_indexes(self.db)
        self.ob = await self.transact(lambda session: shared.create_shared_obligation(self.db, "bill",
            expected_environment_id=ENVIRONMENT, effective_user=USER, session=session, occurrences=self.ctx.ns["_rp_occurrences"]))

    async def test_each_payment_write_failure_rolls_back_whole_event(self):
        before = await self.snapshot()
        for offset in range(1, 9):
            self.db.fail_at = self.db.writes+offset
            await self.rejected(lambda: self.pay("failing", 30), 503)
            self.assertEqual(await self.snapshot(), before)
            self.db.fail_at = None

    async def test_failed_annulment_rolls_back_money_and_both_receipts(self):
        await self.pay("annul-failure", 30)
        before = await self.snapshot()
        for offset in range(1, 9):
            self.db.fail_at = self.db.writes+offset
            await self.rejected(lambda: self.change("annul-failure", "bill", "annul"), 503)
            self.assertEqual(await self.snapshot(), before)
            self.db.fail_at = None

    async def test_failed_tracking_retirement_restores_all_links_and_money(self):
        await self.pay("retire-failure", 30)
        before = await self.snapshot()
        for offset in range(1, 12):
            self.db.fail_at = self.db.writes+offset
            await self.rejected(lambda: self.change("retire-failure", "bill", "retire_both"), 503)
            self.assertEqual(await self.snapshot(), before)
            self.db.fail_at = None
