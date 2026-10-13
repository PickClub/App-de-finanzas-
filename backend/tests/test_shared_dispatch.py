"""R4 2D.3 public POST adapters, isolated AST routes and synthetic memory."""
import copy
from contextlib import nullcontext
import unittest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from pymongo.errors import OperationFailure
from backend import shared_obligations as shared
from backend.tests import test_shared_payments as core
from backend.tests.test_shared_obligations import activation_settings, ENVIRONMENT, USER

HELLO = dict(isWritablePrimary=True, setName="synthetic", logicalSessionTimeoutMinutes=30, maxWireVersion=17)


class DispatchCases:
    snapshot = core.PaymentCases.snapshot
    transact = core.PaymentCases.transact

    async def reconcile(self, origin, key, amount=60, account="account", **extra):
        data=dict(amount=amount,account_id=account,date="2026-10-11T12:00:00+00:00")
        path="/bills/bill/payments/reconcile"
        if origin=="recurring":
            path="/recurring-payments/rp/payments/reconcile"
            data.update(mode="expense",due_date="2026-10-20")
        data.update(extra)
        before=await self.snapshot()
        write_count = self.db.writes if isinstance(getattr(self.db,"data",None),dict) else None
        commands = len(self.audit.events) if hasattr(self,"audit") else None
        response=await self.ctx.request("POST",path,json=data,headers={"Idempotency-Key":key,
            "MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":USER})
        self.assertEqual(await self.snapshot(),before)
        if write_count is not None:
            self.assertEqual(self.db.writes,write_count)
        if commands is not None:
            self.assertFalse(any(command in {"insert","update","delete","findAndModify","create","createIndexes"} for _,command,_ in self.audit.events[commands:]))
        self.assertNotIn("_shared_",response.text)
        self.assertNotIn("fingerprint",response.text)
        return response

    async def test_reconcile_confirmed_from_both_origins_and_disabled_r4(self):
        await self.pay_ok("bill","confirmed-bill",60)
        await self.pay_ok("recurring","confirmed-rp",40)
        self.ctx.ns["settings"]=activation_settings("0")
        for origin,key,amount in (("bill","confirmed-bill",60),("recurring","confirmed-rp",40)):
            response=await self.reconcile(origin,key,amount)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()["status"],"matched")
            self.assertTrue(response.json()["original_request_matches"])
            self.assertEqual(response.json()["financial_state"],"active")

    async def test_reconcile_annulled_both_origins_does_not_refund(self):
        for origin,key in (("bill","annulled-bill"),("recurring","annulled-rp")):
            receipt=await self.pay_ok(origin,key,30)
            await self.remove_ok(origin,receipt["id"])
            response=await self.reconcile(origin,key,30)
            self.assertEqual(response.json()["status"],"cancelled",response.text)
            self.assertEqual(response.json()["financial_state"],"annulled")
        self.assertEqual((await self.snapshot())["accounts"][0]["current_balance"],1000)

    async def test_reconcile_restoration_intent_removed_and_later_annulled(self):
        first=await self.pay_ok("bill","restore-source",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        restored=await self.pay_ok("recurring","restore-key",None,mode="link",transaction_id=first["transaction_id"])
        kwargs=dict(mode="link",transaction_id=first["transaction_id"])
        response=await self.reconcile("recurring","restore-key",None,**kwargs)
        self.assertEqual(response.json()["status"],"matched",response.text)
        self.assertEqual(response.json()["receipt"]["id"],restored["id"])
        await self.remove_ok("recurring",restored["id"])
        response=await self.reconcile("recurring","restore-key",None,**kwargs)
        self.assertEqual(response.json()["status"],"tracking_removed",response.text)
        self.assertEqual(response.json()["financial_state"],"active")
        await self.remove_ok("bill",first["id"])
        response=await self.reconcile("recurring","restore-key",None,**kwargs)
        self.assertEqual(response.json()["status"],"cancelled",response.text)

    async def test_reconcile_mark_removed_keeps_no_financial_effect(self):
        mark=await self.pay_ok("recurring","mark-key",20,mode="mark",settles=True)
        response=await self.reconcile("recurring","mark-key",20,mode="mark",settles=True)
        self.assertEqual(response.json()["status"],"matched",response.text)
        self.assertEqual(response.json()["financial_state"],"none")
        await self.remove_ok("recurring",mark["id"])
        response=await self.reconcile("recurring","mark-key",20,mode="mark",settles=True)
        self.assertEqual(response.json()["status"],"tracking_removed",response.text)
        self.assertEqual(len((await self.snapshot())["transactions"]),0)

    async def test_reconcile_absent_and_different_payload_never_claim_failure(self):
        self.ctx.ns["settings"]=activation_settings("0")
        for origin in ("bill","recurring"):
            response=await self.reconcile(origin,"absent")
            self.assertEqual(response.json()["status"],"not_found",response.text)
            self.assertIsNone(response.json()["original_request_matches"])
            self.assertEqual(response.json()["financial_state"],"unknown")
        await self.pay_ok("bill","original",60)
        response=await self.reconcile("bill","original",61)
        self.assertEqual(response.json()["status"],"discrepancy",response.text)
        self.assertIsNone(response.json()["receipt"])

    async def test_reconcile_context_headers_mandatory_and_never_expose_foreign_data(self):
        await self.pay_ok("bill","context-reconcile",60)
        before=await self.snapshot()
        for path,data in (("/bills/bill/payments/reconcile",dict(amount=60,account_id="account")),
                          ("/recurring-payments/rp/payments/reconcile",dict(amount=60,account_id="account",mode="expense",due_date="2026-10-20"))):
            for headers,code in (({},422),({"Idempotency-Key":"context-reconcile"},422),
                ({"Idempotency-Key":"context-reconcile","MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":"other"},409),
                ({"Idempotency-Key":"context-reconcile","MoneyFlow-Environment-ID":"22222222-2222-4222-8222-222222222222","MoneyFlow-User-ID":USER},409)):
                response=await self.ctx.request("POST",path,json=data,headers=headers)
                self.assertEqual(response.status_code,code,response.text)
                self.assertEqual(await self.snapshot(),before)
                self.assertNotIn("receipt",response.text)

    async def test_reconcile_incomplete_history_and_lost_response(self):
        first=await self.pay_ok("bill","lost-response",60)
        response=await self.reconcile("bill","lost-response",60)
        self.assertEqual(response.json()["status"],"matched",response.text)
        await self.transact(lambda session:self.db.recurring_payment_records.delete_one({"id":first["recurring_record_id"]},session=session))
        response=await self.reconcile("bill","lost-response",60)
        self.assertEqual(response.json()["status"],"unverifiable",response.text)
        self.assertIsNone(response.json()["receipt"])

    async def test_reconcile_legacy_active_and_ambiguous_tombstone(self):
        await self.context_cases(False)
        response=await self.reconcile("bill","valid-protected",10)
        self.assertEqual(response.json()["status"],"matched",response.text)
        response=await self.reconcile("recurring","valid-protected",10)
        self.assertEqual(response.json()["status"],"matched",response.text)
        pid=response.json()["receipt"]["id"]
        await self.remove_ok("recurring",pid)
        response=await self.reconcile("recurring","valid-protected",10)
        self.assertEqual(response.json()["status"],"unverifiable",response.text)

    async def test_reconcile_changed_period_dates_and_missing_journal_are_not_confirmation(self):
        await self.pay_ok("recurring","period-proof",30)
        response=await self.reconcile("recurring","period-proof",30,due_date="2026-11-20")
        self.assertEqual(response.json()["status"],"discrepancy",response.text)
        first=await self.pay_ok("bill","date-proof",30)
        await self.update("bill_payments",{"id":first["id"]},{"date":"2026-10-12T12:00:00+00:00"})
        response=await self.reconcile("bill","date-proof",30)
        self.assertEqual(response.json()["status"],"unverifiable",response.text)
        # Repair only this synthetic fixture for the independent journal case.
        await self.update("bill_payments",{"id":first["id"]},{"date":"2026-10-11T12:00:00+00:00"})
        mark=await self.pay_ok("recurring","missing-journal",20,mode="mark")
        await self.transact(lambda session:self.db.shared_tracking_intents.delete_one({"target_id":mark["id"]},session=session))
        response=await self.reconcile("recurring","missing-journal",20,mode="mark")
        self.assertEqual(response.json()["status"],"unverifiable",response.text)

    async def test_reconcile_partial_event_is_not_absent(self):
        first=await self.pay_ok("bill","partial-event",30)
        await self.transact(lambda session:self.db.bill_payments.delete_one({"id":first["id"]},session=session))
        response=await self.reconcile("bill","partial-event",30)
        self.assertEqual(response.json()["status"],"unverifiable",response.text)

    async def test_reconcile_corrupt_administrative_capsule_never_returns_confirmation(self):
        mark=await self.pay_ok("recurring","bad-journal",20,mode="mark")
        await self.update("shared_tracking_intents",{"target_id":mark["id"]},{"capsule":None})
        response=await self.reconcile("recurring","bad-journal",20,mode="mark")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["status"],"unverifiable")
        self.assertIsNone(response.json()["receipt"])

    async def post(self, origin, key, amount=60, account="account", **extra):
        self.ctx.ns["settings"] = activation_settings("1")
        data = dict(amount=amount, account_id=account, date="2026-10-11T12:00:00+00:00")
        path = "/bills/bill/payments"
        if origin == "recurring":
            path = "/recurring-payments/rp/payments"
            data.update(mode="expense", due_date="2026-10-20")
        data.update(extra)
        if isinstance(getattr(self.db, "data", None), dict):
            with patch.object(shared, "_hello", AsyncMock(return_value=HELLO)):
                return await self.ctx.request("POST", path, json=data, headers={"Idempotency-Key":key})
        return await self.ctx.request("POST", path, json=data, headers={"Idempotency-Key":key})

    async def pay_ok(self, origin, key, amount=60, account="account", **extra):
        response = await self.post(origin, key, amount, account, **extra)
        self.assertEqual(response.status_code, 200, response.text)
        for field in ("_shared_", "request_fingerprint", "_reference_revision", "_bill_generation_origin"):
            self.assertNotIn(field, response.text)
        return response.json()

    async def update(self, collection, query, changes):
        return await self.transact(lambda session: getattr(self.db, collection).update_one(query, {"$set": changes}, session=session))

    async def test_bill_then_recurring_and_reverse_sixty_forty(self):
        first = await self.pay_ok("bill", "one", 60)
        self.assertIsNone(first["next_bill_id"])
        second = await self.pay_ok("recurring", "two", 40, "second", settles=True, allow_overpay=True)
        self.assertFalse(second["settles"])
        data = await self.snapshot()
        self.assertEqual((len(data["transactions"]),len(data["bill_payments"]),len(data["recurring_payment_records"])), (2,2,2))
        self.assertEqual([a["current_balance"] for a in data["accounts"]], [940,960])
        next_bill = next(b for b in data["bills"] if b["id"] != "bill")
        self.assertEqual((next_bill["due_date"],next_bill["frequency"]), ("2026-11-20","monthly"))
        self.assertEqual(len(data["bills"]),2)
        before = await self.snapshot()
        replay = await self.pay_ok("recurring", "two", 40, "second", settles=True, allow_overpay=True)
        self.assertEqual(replay,second)
        self.assertEqual(await self.snapshot(),before)
        response = await self.post("bill","over",1)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_recurring_then_bill_same_account_equal_legitimate_partials(self):
        await self.pay_ok("recurring","one",50)
        final = await self.pay_ok("bill","two",50)
        self.assertIsNotNone(final["next_bill_id"])
        data = await self.snapshot()
        self.assertEqual(data["accounts"][0]["current_balance"],900)
        self.assertEqual(len(data["transactions"]),2)
        self.assertEqual(len(data["bills"]),2)
        before = await self.snapshot()
        response = await self.post("bill","two",49)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_full_monthly_from_either_origin(self):
        result = await self.pay_ok("bill","full",100)
        before = await self.snapshot()
        await self.pay_ok("bill","full",100)
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(len(before["bills"]),2)
        self.assertEqual(before["accounts"][0]["current_balance"],900)
        self.assertEqual(len(before["transactions"]),1)
        self.assertIsNotNone(result["next_bill_id"])

    async def test_once_linked_to_monthly_never_generates(self):
        await self.update("bills",{"id":"bill"},{"frequency":"once"})
        await self.transact(lambda session: self.db.shared_obligations.delete_one({"_id":self.ob["_id"]}, session=session))
        result = await self.pay_ok("recurring","once",100)
        data = await self.snapshot()
        self.assertEqual(len(data["bills"]),1)
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual(data["shared_obligations"][0]["bill_schedule_snapshot"]["frequency"],"once")

    async def test_frozen_bill_schedule_after_partial_payment(self):
        await self.pay_ok("recurring","partial",60)
        await self.update("bills",{"id":"bill"},{"due_date":"2026-11-03","frequency":"once","anchor_day":3})
        await self.pay_ok("bill","finish",40)
        data = await self.snapshot()
        next_bill = next(b for b in data["bills"] if b["id"] != "bill")
        self.assertEqual((next_bill["due_date"],next_bill["frequency"],next_bill["anchor_day"]), ("2026-11-20","monthly",20))
        self.assertEqual(data["recurring_payment_records"][0]["due_date"],"2026-10-20")
        before = await self.snapshot()
        await self.pay_ok("bill","finish",40)
        self.assertEqual(await self.snapshot(),before)

    async def test_old_missing_schedule_and_prior_history_are_not_adopted(self):
        await self.transact(lambda session: self.db.shared_obligations.update_one({"_id":self.ob["_id"]},
            {"$unset":{"bill_schedule_snapshot":""}},session=session))
        before = await self.snapshot()
        response = await self.post("bill","old",100)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        await self.transact(lambda session: self.db.shared_obligations.delete_one({"_id":self.ob["_id"]},session=session))
        await self.transact(lambda session: self.db.bill_payments.insert_one(dict(_id="old",id="old",bill_id="bill",user_id=USER,
            amount=10,account_id="account",transaction_id="absent"),session=session))
        before = await self.snapshot()
        response = await self.post("recurring","history",60)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_disabled_managed_blocks_and_plain_legacy_continues(self):
        await self.pay_ok("bill","partial",60)
        self.ctx.ns["settings"] = activation_settings("0")
        before = await self.snapshot()
        response = await self.ctx.request("POST","/bills/bill/payments",json=dict(amount=40,account_id="account"),headers={"Idempotency-Key":"disabled"})
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        # A different unlinked invoice has no managed history and keeps legacy flow.
        await self.transact(lambda session:self.db.bills.insert_one(dict(_id="plain",id="plain",user_id=USER,name="Plain",amount=100,
            frequency="once",due_date="2026-10-20",anchor_day=20,series_id="plain",recurring_payment_id=None),session=session))
        response = await self.ctx.request("POST","/bills/plain/payments",json=dict(amount=30,account_id="second"),headers={"Idempotency-Key":"plain"})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((await self.db.accounts.find_one({"id":"second"}))["current_balance"],970)

    async def test_shared_mark_link_rejected_and_payload_due_preserved(self):
        before = await self.snapshot()
        for mode in ("link",):
            response = await self.post("recurring",mode,10,mode=mode)
            self.assertEqual(response.status_code,409)
            self.assertEqual(await self.snapshot(),before)
        raw_due = "2026-10-20T12:00:00Z"
        result = await self.pay_ok("recurring","normalized",30,due_date=raw_due)
        self.assertEqual(result["due_date"],"2026-10-20")
        record = await self.db.recurring_payment_records.find_one({"id":result["id"]})
        self.assertEqual(record["_shared_intent"]["payload"]["due_date"],raw_due)
        before = await self.snapshot()
        await self.pay_ok("recurring","normalized",30,due_date=raw_due)
        self.assertEqual(await self.snapshot(),before)
        response = await self.post("recurring","normalized",30,due_date="2026-10-20")
        self.assertEqual(response.status_code,409)

    async def test_generation_failure_rolls_back_all_financial_writes(self):
        before = await self.snapshot()
        original = shared.generate_next_shared_bill
        async def failed(*args,**kwargs):
            await original(*args,**kwargs)
            raise OperationFailure("Injected generation failure")
        with patch.object(shared,"generate_next_shared_bill",failed):
            response = await self.post("recurring","failing",100)
        self.assertEqual(response.status_code,503)
        self.assertEqual(await self.snapshot(),before)

    async def test_generation_proof_survives_future_bill_edit_or_deletion(self):
        result=await self.pay_ok("bill","full",100)
        next_id=result["next_bill_id"]
        await self.update("bills",{"id":next_id},{"due_date":"2026-12-03","frequency":"once","anchor_day":3})
        before=await self.snapshot()
        await self.pay_ok("bill","full",100)
        self.assertEqual(await self.snapshot(),before)
        # Synthetic removed-child state: never repair/recreate it on recovery.
        # Current public guards block deleting the reserved future bill.
        await self.transact(lambda session:self.db.bills.delete_one({"id":next_id},session=session))
        await self.update("bills",{"id":"bill"},{"next_bill_id":None})
        before=await self.snapshot()
        await self.pay_ok("bill","full",100)
        self.assertEqual(await self.snapshot(),before)
        self.assertEqual(len(before["transactions"]),1)

    async def test_invalid_public_input_and_activation_rejected_without_writes(self):
        before=await self.snapshot()
        for amount,account,code in ((0,"account",422),(-1,"account",422),(10,None,422),(10,"absent",422),(101,"account",422)):
            response=await self.post("recurring","invalid",amount,account,settles=True,allow_overpay=True)
            self.assertEqual(response.status_code,code,response.text)
            self.assertEqual(await self.snapshot(),before)
        with patch.object(shared,"require_activation",AsyncMock(side_effect=HTTPException(503,"wrong context"))):
            response=await self.post("bill","no-context",30)
        self.assertEqual(response.status_code,503)
        self.assertEqual(await self.snapshot(),before)

    async def test_compact_due_and_new_period_preserve_original_intent(self):
        await self.pay_ok("recurring","compact",60,due_date="20261020")
        await self.pay_ok("bill","finish",40)
        source=await self.db.bills.find_one({"id":"bill"})
        next_id=source["next_bill_id"]
        topology = patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
        with topology:
            response=await self.ctx.request("POST","/bills/"+next_id+"/payments",
                json=dict(amount=30,account_id="account",date="2026-11-11T12:00:00+00:00"),
                headers={"Idempotency-Key":"next-period"})
        self.assertEqual(response.status_code,200,response.text)
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),3)
        self.assertEqual(len(data["bills"]),2)
        self.assertEqual(data["accounts"][0]["current_balance"],870)
        current=next(ob for ob in data["shared_obligations"] if ob["bill_id"]==next_id)
        self.assertEqual(current["original_due_date"],"2026-11-20")

    async def test_generated_future_period_remains_reserved_when_disabled(self):
        first=await self.pay_ok("bill","full",100)
        next_id=first["next_bill_id"]
        self.ctx.ns["settings"]=activation_settings("0")
        before=await self.snapshot()
        response=await self.ctx.request("POST","/bills/"+next_id+"/payments",
            json=dict(amount=30,account_id="account"),headers={"Idempotency-Key":"disabled-next"})
        self.assertEqual(response.status_code,409)
        response=await self.ctx.request("POST","/recurring-payments/rp/payments",
            json=dict(amount=30,account_id="account",mode="expense",due_date="2026-11-20"),
            headers={"Idempotency-Key":"disabled-next-rp"})
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_incompatible_future_recurrence_rolls_back_completion(self):
        recurring=await self.db.recurring_payments.find_one({"id":"rp"})
        versions=copy.deepcopy(recurring["versions"])
        versions.append(dict(valid_from="2026-11-01",start_date="2026-11-25",frequency="monthly",due_day=25,amount=100))
        await self.update("recurring_payments",{"id":"rp"},{"versions":versions})
        before=await self.snapshot()
        response=await self.post("bill","incompatible-next",100)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def remove(self, origin, receipt_id):
        path = "/bills/payments/" if origin == "bill" else "/recurring-payments/payments/"
        topology = patch.object(shared, "_hello", AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
        with topology:
            return await self.ctx.request("DELETE", path+receipt_id)

    async def remove_ok(self, origin, receipt_id):
        response = await self.remove(origin,receipt_id)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),{"ok":True})

    async def test_annul_bill_and_recurring_refund_once(self):
        first = await self.pay_ok("bill","bill-annul",30)
        second = await self.pay_ok("recurring","rp-annul",40,"second")
        await self.remove_ok("bill",first["id"])
        await self.remove_ok("recurring",second["id"])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),0)
        self.assertEqual([a["current_balance"] for a in data["accounts"]],[1000,1000])
        for col in ("bill_payments","recurring_payment_records"):
            self.assertEqual(len(data[col]),2)
            self.assertTrue(all(r["deleted"] and r["_shared_financial_state"]=="annulled" for r in data[col]))
        before=await self.snapshot()
        for rec in data["bill_payments"]:
            await self.remove_ok("bill",rec["id"])
        for rec in data["recurring_payment_records"]:
            await self.remove_ok("recurring",rec["id"])
        self.assertEqual(await self.snapshot(),before)
        response=await self.post("bill","bill-annul",30)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_withdraw_link_keeps_money_then_annul(self):
        first=await self.pay_ok("bill","withdraw",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],940)
        self.assertEqual(data["bill_payments"][0]["recurring_record_id"],None)
        before=await self.snapshot()
        await self.remove_ok("recurring",first["recurring_record_id"])
        self.assertEqual(await self.snapshot(),before)
        # Withdrawal did not reopen pending: 41 cannot be paid after 60.
        response=await self.post("recurring","over-after-withdraw",41)
        self.assertEqual(response.status_code,422)
        self.assertEqual(await self.snapshot(),before)
        await self.remove_ok("bill",first["id"])
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),0)
        self.assertEqual(data["accounts"][0]["current_balance"],1000)

    async def test_annul_preserves_future_bill_and_repayment_does_not_regenerate(self):
        first=await self.pay_ok("bill","complete",100)
        next_id=first["next_bill_id"]
        next_bill=await self.db.bills.find_one({"id":next_id})
        source=await self.db.shared_obligations.find_one({"_id":self.ob["_id"]})
        reserved=await self.db.shared_obligations.find_one({"bill_id":next_id})
        await self.remove_ok("bill",first["id"])
        self.assertEqual(await self.db.bills.find_one({"id":next_id}),next_bill)
        self.assertEqual(await self.db.shared_obligations.find_one({"bill_id":next_id}),reserved)
        self.assertEqual((await self.db.shared_obligations.find_one({"_id":self.ob["_id"]}))["next_bill_generation"],source["next_bill_generation"])
        second=await self.pay_ok("recurring","repay",100)
        data=await self.snapshot()
        self.assertEqual(len(data["bills"]),2)
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],900)

    async def test_delete_disabled_invalid_context_and_corruption_no_writes(self):
        first=await self.pay_ok("bill","protected",60)
        self.ctx.ns["settings"]=activation_settings("0")
        before=await self.snapshot()
        for origin,pid in (("bill",first["id"]),("recurring",first["recurring_record_id"])):
            response=await self.remove(origin,pid)
            self.assertEqual(response.status_code,409)
            self.assertEqual(await self.snapshot(),before)
        self.ctx.ns["settings"]=activation_settings("1")
        with patch.object(shared,"require_activation",AsyncMock(side_effect=HTTPException(503,"context unavailable"))):
            response=await self.remove("bill",first["id"])
        self.assertEqual(response.status_code,503)
        self.assertEqual(await self.snapshot(),before)
        await self.update("recurring_payment_records",{"id":first["recurring_record_id"]},{"mode":"expense"})
        before=await self.snapshot()
        response=await self.remove("recurring",first["recurring_record_id"])
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_annul_template_source_rejected_with_tracking_untouched(self):
        first=await self.pay_ok("bill","template",60)
        await self.transact(lambda session:self.db.recurring_templates.insert_one(
            dict(_id="template",id="template",user_id=USER,source_transaction_id=first["transaction_id"]),session=session))
        before=await self.snapshot()
        response=await self.remove("bill",first["id"])
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        await self.remove_ok("recurring",first["recurring_record_id"])
        self.assertEqual((await self.db.accounts.find_one({"id":"account"}))["current_balance"],940)
        before=await self.snapshot()
        response=await self.remove("bill",first["id"])
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_delete_failures_roll_back_and_generic_routes_stay_blocked(self):
        first=await self.pay_ok("bill","rollback",60)
        before=await self.snapshot()
        original=shared.change_shared_payment
        async def failed(*args,**kwargs):
            await original(*args,**kwargs)
            raise OperationFailure("Injected after DELETE writes")
        for origin,pid in (("bill",first["id"]),("recurring",first["recurring_record_id"])):
            with patch.object(shared,"change_shared_payment",failed):
                response=await self.remove(origin,pid)
            self.assertEqual(response.status_code,503)
            self.assertEqual(await self.snapshot(),before)
        for method,body in (("PUT",dict(name="blocked",amount=60,type="expense",account_id="account")),("DELETE",None)):
            response=await self.ctx.request(method,"/transactions/"+first["transaction_id"],**({"json":body} if body else {}))
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(await self.snapshot(),before)

    async def test_legacy_delete_without_managed_history_unchanged(self):
        self.ctx.ns["settings"]=activation_settings("0")
        await self.transact(lambda session:self.db.bills.insert_one(dict(_id="plain",id="plain",user_id=USER,name="Plain",amount=100,
            frequency="once",due_date="2026-10-20",anchor_day=20,series_id="plain",recurring_payment_id=None),session=session))
        response=await self.ctx.request("POST","/bills/plain/payments",json=dict(amount=30,account_id="account"),headers={"Idempotency-Key":"plain-delete"})
        self.assertEqual(response.status_code,200,response.text)
        await self.remove_ok("bill",response.json()["id"])
        self.assertEqual((await self.db.accounts.find_one({"id":"account"}))["current_balance"],1000)
        before=await self.snapshot()
        await self.remove_ok("bill",response.json()["id"])
        self.assertEqual(await self.snapshot(),before)

    async def test_annul_failure_before_balance_rolls_back(self):
        first=await self.pay_ok("recurring","balance-fail",60)
        before=await self.snapshot()
        with patch.dict(self.ctx.ns,{"recompute_account_balance":AsyncMock(side_effect=OperationFailure("Injected balance failure"))}):
            response=await self.remove("recurring",first["id"])
        self.assertEqual(response.status_code,503)
        self.assertEqual(await self.snapshot(),before)

    async def test_mark_then_expense_and_retirement_never_changes_money(self):
        result=await self.pay_ok("recurring","mark-one",80,mode="mark",settles=True)
        self.assertFalse(result["settles"])
        before=await self.snapshot()
        self.assertEqual(len(before["transactions"]),0)
        self.assertEqual(len(before["bill_payments"]),0)
        self.assertEqual(before["accounts"][0]["current_balance"],1000)
        replay=await self.pay_ok("recurring","mark-one",80,mode="mark",settles=True)
        self.assertEqual(replay,result)
        self.assertEqual(await self.snapshot(),before)
        await self.pay_ok("bill","actual",60)
        self.assertEqual((await self.db.accounts.find_one({"id":"account"}))["current_balance"],940)
        response=await self.post("recurring","excess",41)
        self.assertEqual(response.status_code,422)
        financial_before=(await self.snapshot())["transactions"]
        await self.remove_ok("recurring",result["id"])
        data=await self.snapshot()
        self.assertEqual(data["transactions"],financial_before)
        self.assertEqual(data["accounts"][0]["current_balance"],940)
        before=await self.snapshot()
        await self.remove_ok("recurring",result["id"])
        self.assertEqual(await self.snapshot(),before)
        response=await self.post("recurring","mark-one",80,mode="mark",settles=True)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_restore_original_tracking_preserves_financial_ids_and_replays(self):
        first=await self.pay_ok("bill","original",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        before=await self.snapshot()
        transaction=before["transactions"][0]
        original=await self.db.recurring_payment_records.find_one({"id":first["recurring_record_id"]})
        result=await self.pay_ok("recurring","restore",60,mode="link",transaction_id=first["transaction_id"])
        self.assertEqual(result["id"],first["recurring_record_id"])
        after=await self.snapshot()
        self.assertEqual((len(after["transactions"]),len(after["bill_payments"]),len(after["recurring_payment_records"])),(1,1,1))
        self.assertEqual(after["accounts"],before["accounts"])
        self.assertEqual(after["transactions"][0]["_shared_intent"],transaction["_shared_intent"])
        self.assertEqual(after["recurring_payment_records"][0]["_shared_intent"],original["_shared_intent"])
        self.assertEqual(len(after["shared_tracking_intents"]),1)
        replay=await self.pay_ok("recurring","restore",60,mode="link",transaction_id=first["transaction_id"])
        self.assertEqual(replay,result)
        self.assertEqual(await self.snapshot(),after)
        response=await self.post("recurring","restore",59,mode="link",transaction_id=first["transaction_id"])
        self.assertEqual(response.status_code,409)
        response=await self.post("recurring","another-restore",60,mode="link",transaction_id=first["transaction_id"])
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),after)
        await self.remove_ok("recurring",result["id"])
        self.assertEqual((await self.db.accounts.find_one({"id":"account"}))["current_balance"],940)
        response=await self.post("recurring","restore",60,mode="link",transaction_id=first["transaction_id"])
        self.assertEqual(response.status_code,409)
        await self.remove_ok("bill",first["id"])
        self.assertEqual((await self.db.accounts.find_one({"id":"account"}))["current_balance"],1000)

    async def test_restore_rejects_account_period_legacy_and_annulled(self):
        first=await self.pay_ok("bill","full-link",100)
        before=await self.snapshot()
        response=await self.post("recurring","active",100,mode="link",transaction_id=first["transaction_id"])
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        await self.remove_ok("recurring",first["recurring_record_id"])
        before=await self.snapshot()
        for changes in (dict(account_id="second"),dict(amount=99),dict(due_date="2026-11-20")):
            payload=dict(amount=100,account_id="account",mode="link",transaction_id=first["transaction_id"])
            payload.update(changes)
            response=await self.post("recurring","wrong",**payload)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(await self.snapshot(),before)
        await self.transact(lambda session:self.db.transactions.insert_one(dict(_id="legacy",id="legacy",user_id=USER,
            name="Unassigned",type="expense",amount=10,account_id="account",date="2026-10-20"),session=session))
        before=await self.snapshot()
        response=await self.post("recurring","legacy-link",10,mode="link",transaction_id="legacy")
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        await self.remove_ok("bill",first["id"])
        before=await self.snapshot()
        response=await self.post("recurring","cancelled-link",100,mode="link",transaction_id=first["transaction_id"])
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_tracking_disabled_and_rollback_leave_no_partial_writes(self):
        first=await self.pay_ok("bill","to-restore",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        before=await self.snapshot()
        original=shared.register_shared_tracking
        async def fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise OperationFailure("Injected after administrative writes")
        for mode in ("mark","link"):
            extra=dict(mode=mode)
            if mode=="link":extra["transaction_id"]=first["transaction_id"]
            with patch.object(shared,"register_shared_tracking",fail):
                response=await self.post("recurring","fail-"+mode,60,**extra)
            self.assertEqual(response.status_code,503)
            self.assertEqual(await self.snapshot(),before)
        self.ctx.ns["settings"]=activation_settings("0")
        for mode in ("mark","link"):
            response=await self.ctx.request("POST","/recurring-payments/rp/payments",json=dict(mode=mode,amount=60,
                account_id="account",due_date="2026-10-20",transaction_id=first["transaction_id"] if mode=="link" else None),
                headers={"Idempotency-Key":"disabled-admin"})
            self.assertEqual(response.status_code,409)
            self.assertEqual(await self.snapshot(),before)

    async def test_tracking_lost_response_replays_both_modes_without_writes(self):
        first=await self.pay_ok("bill","loss-source",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        for mode in ("mark","link"):
            extra=dict(mode=mode)
            if mode=="link":extra["transaction_id"]=first["transaction_id"]
            if isinstance(getattr(self.db,"data",None),dict):
                self.db.commit_then_error=True
                response=await self.post("recurring","lost-"+mode,60,**extra)
            else:
                actual_client=self.ctx.ns["client"]
                class LostSession:
                    def __init__(inner,session):inner.session=session
                    async def __aenter__(inner):return inner
                    async def __aexit__(inner,*args):await inner.session.end_session()
                    async def with_transaction(inner,callback,**kwargs):
                        await inner.session.with_transaction(callback,**kwargs)
                        raise OperationFailure("Lost administrative commit response",details={"errorLabels":["UnknownTransactionCommitResult"]})
                class LostClient:
                    async def start_session(inner):return LostSession(await actual_client.start_session())
                with patch.dict(self.ctx.ns,{"client":LostClient()}):
                    response=await self.post("recurring","lost-"+mode,60,**extra)
            self.assertEqual(response.status_code,503)
            before=await self.snapshot()
            self.assertEqual(len(before["transactions"]),1)
            self.assertEqual(before["accounts"][0]["current_balance"],940)
            await self.pay_ok("recurring","lost-"+mode,60,**extra)
            self.assertEqual(await self.snapshot(),before)

    async def test_tracking_reads_context_and_foreign_movement_fail_closed(self):
        mark=await self.pay_ok("recurring","read-mark",100,mode="mark",settles=True)
        response=await self.ctx.request("GET","/bills/bill")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((response.json()["paid_amount"],response.json()["remaining"]),(0,100))
        self.assertNotIn("_shared_",response.text)
        first=await self.pay_ok("bill","read-finance",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        await self.transact(lambda session:self.db.transactions.insert_one(dict(_id="foreign",id="foreign",user_id="another-user",
            amount=60,type="expense",account_id="account",_shared_obligation_id=self.ob["_id"]),session=session))
        before=await self.snapshot()
        response=await self.post("recurring","foreign-link",60,mode="link",transaction_id="foreign")
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        for mode in ("mark","link"):
            with patch.object(shared,"require_activation",AsyncMock(side_effect=HTTPException(503,"Unverifiable context"))):
                response=await self.post("recurring","context-"+mode,60,mode=mode,transaction_id=first["transaction_id"] if mode=="link" else None)
            self.assertEqual(response.status_code,503)
            self.assertEqual(await self.snapshot(),before)
        response=await self.ctx.request("GET","/bills/bill")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((response.json()["paid_amount"],response.json()["remaining"]),(60,40))

    async def test_missing_or_unreadable_journal_blocks_before_writes(self):
        database=self.db
        class Proxy:
            def __init__(inner,error):inner.error=error
            def __getattr__(inner,name):
                if name=="shared_tracking_intents":
                    class Journal:
                        async def index_information(obj):
                            if inner.error:raise OperationFailure("Injected journal lookup error")
                            return {}
                    return Journal()
                return getattr(database,name)
        before=await self.snapshot()
        for error in (False,True):
            with patch.dict(self.ctx.ns,{"db":Proxy(error)}):
                response=await self.post("recurring","missing-journal",30,mode="mark")
            self.assertEqual(response.status_code,503,response.text)
            self.assertEqual(await self.snapshot(),before)

    async def bill_edit(self, **changes):
        self.ctx.ns["settings"]=activation_settings("1")
        bill=await self.db.bills.find_one({"id":"bill"})
        data={key:bill.get(key) for key in ("name","amount","due_date","frequency","account_id","category_id","recurring_payment_id")}
        data.update(changes)
        topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
        with topology:return await self.ctx.request("PUT","/bills/bill",json=data)

    async def rp_edit(self, **changes):
        self.ctx.ns["settings"]=activation_settings("1")
        rp=await self.db.recurring_payments.find_one({"id":"rp"})
        version=rp["versions"][-1]
        data={key:rp.get(key) for key in ("name","variable","account_id","category_id","end_date")}
        data.update({key:version.get(key) for key in ("amount","frequency","start_date","due_day")})
        data.update(changes)
        topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
        with topology:return await self.ctx.request("PUT","/recurring-payments/rp",json=data)

    async def state_change(self, action, today="2026-10-12"):
        from datetime import date
        self.ctx.ns["settings"]=activation_settings("1")
        topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
        with topology,patch.dict(self.ctx.ns,{"_rp_today":lambda *args:date.fromisoformat(today)}):
            return await self.ctx.request("POST","/recurring-payments/rp/"+action)

    async def once_identity(self):
        await self.update("bills",{"id":"bill"},{"frequency":"once"})
        await self.transact(lambda session:self.db.shared_obligations.delete_one({"_id":self.ob["_id"]},session=session))
        self.ob=await self.transact(lambda session:shared.create_shared_obligation(self.db,"bill",expected_environment_id=ENVIRONMENT,
            effective_user=USER,session=session,occurrences=self.ctx.ns["_rp_occurrences"]))

    async def test_parent_partial_sixty_amount_and_descriptive_edit_pays_afterwards(self):
        first=await self.pay_ok("bill","partial-parent",60)
        before=await self.snapshot()
        for changes in (dict(amount=59),dict(amount=80),dict(due_date="2026-10-21"),dict(frequency="once"),dict(recurring_payment_id=None)):
            response=await self.bill_edit(**changes)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(await self.snapshot(),before)
        response=await self.bill_edit(name="Renamed",description="Safe description",account_id="second")
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn("_shared_",response.text)
        after=await self.snapshot()
        self.assertEqual(after["transactions"],before["transactions"])
        self.assertEqual(after["bill_payments"],before["bill_payments"])
        self.assertEqual(shared.public_financial_document(after["accounts"]),shared.public_financial_document(before["accounts"]))
        await self.pay_ok("bill","finish-parent",40,"second")
        data=await self.snapshot()
        self.assertEqual([a["current_balance"] for a in data["accounts"]],[940,960])
        child=next(b for b in data["bills"] if b["id"]!="bill")
        self.assertEqual(child["account_id"],"second")
        self.assertEqual(child["frequency"],"monthly")

    async def test_once_amount_edit_preserves_schedule_and_payments(self):
        await self.once_identity()
        response=await self.bill_edit(amount=80)
        self.assertEqual(response.status_code,200,response.text)
        first=await self.pay_ok("bill","once-partial",60)
        before=await self.snapshot()
        response=await self.bill_edit(amount=59)
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        response=await self.bill_edit(amount=90)
        self.assertEqual(response.status_code,200,response.text)
        await self.pay_ok("recurring","once-finish",30)
        data=await self.snapshot()
        self.assertEqual(len(data["bills"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],910)
        ob=next(o for o in data["shared_obligations"] if o["bill_id"]=="bill")
        self.assertEqual(ob["original_due_date"],"2026-10-20")
        self.assertEqual(ob["bill_schedule_snapshot"]["frequency"],"once")
        self.assertEqual(before["bill_payments"][0],data["bill_payments"][0])

    async def test_parent_edit_existing_future_reservation_unchanged(self):
        first=await self.pay_ok("bill","full-parent",100)
        child=await self.db.bills.find_one({"id":first["next_bill_id"]})
        reserved=await self.db.shared_obligations.find_one({"bill_id":child["id"]})
        response=await self.bill_edit(amount=120,name="More actual",account_id="second")
        self.assertEqual(response.status_code,200,response.text)
        await self.pay_ok("recurring","additional",20,"second")
        self.assertEqual(await self.db.bills.find_one({"id":child["id"]}),child)
        self.assertEqual(await self.db.shared_obligations.find_one({"bill_id":child["id"]}),reserved)
        before=await self.snapshot()
        for path in ("/bills/"+child["id"],"/bills/bill","/recurring-payments/rp"):
            response=await self.ctx.request("DELETE",path)
            self.assertEqual(response.status_code,409)
            self.assertEqual(await self.snapshot(),before)
        response=await self.rp_edit(frequency="weekly",start_date="2026-12-01")
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_recurring_description_defaults_allowed_programming_states_blocked(self):
        await self.pay_ok("bill","rp-partial",60)
        before=await self.snapshot()
        for changes in (dict(amount=80),dict(frequency="weekly",start_date="2026-12-01"),dict(end_date="2026-12-31")):
            response=await self.rp_edit(**changes)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(await self.snapshot(),before)
        for action in ("pause","resume","end"):
            response=await self.state_change(action)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(await self.snapshot(),before)
        response=await self.rp_edit(name="RP renamed",notes="Administrative description",account_id="second")
        self.assertEqual(response.status_code,200,response.text)
        after=await self.snapshot()
        self.assertEqual(after["transactions"],before["transactions"])
        self.assertEqual(after["bill_payments"],before["bill_payments"])
        self.assertEqual(after["recurring_payments"][0]["versions"],before["recurring_payments"][0]["versions"])
        await self.pay_ok("recurring","rp-finish",40,"second")
        self.assertEqual(len((await self.snapshot())["bills"]),2)

    async def test_once_future_program_and_past_state_changes_do_not_block_payment(self):
        await self.once_identity()
        before=await self.snapshot()
        response=await self.state_change("pause")
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        # Only once reservations: a new version strictly AFTER their dates is safe.
        response=await self.rp_edit(frequency="weekly",start_date="2026-12-01",due_day=None,amount=80)
        self.assertEqual(response.status_code,200,response.text)
        rp=await self.db.recurring_payments.find_one({"id":"rp"})
        self.assertEqual(rp["versions"][0],before["recurring_payments"][0]["versions"][0])
        for action in ("pause","resume","end"):
            response=await self.state_change(action,today="2026-11-01")
            self.assertEqual(response.status_code,200,response.text)
        # Past original once obligation remains payable after future-only changes.
        await self.pay_ok("recurring","past-once",100)
        data=await self.snapshot()
        self.assertEqual(len(data["bills"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],900)

    async def test_parent_reserved_delete_disabled_and_rollback_no_writes(self):
        before=await self.snapshot()
        for path in ("/bills/bill","/recurring-payments/rp"):
            response=await self.ctx.request("DELETE",path)
            self.assertEqual(response.status_code,409)
            self.assertEqual(await self.snapshot(),before)
        original=shared.edit_shared_bill
        async def fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise OperationFailure("Injected after shared parent edit")
        with patch.dict(self.ctx.ns,{"edit_shared_bill":fail}):
            response=await self.bill_edit(name="Rollback")
        self.assertEqual(response.status_code,503)
        self.assertEqual(await self.snapshot(),before)
        self.ctx.ns["settings"]=activation_settings("0")
        response=await self.ctx.request("PUT","/bills/bill",json=dict(name="Blocked",amount=100,due_date="2026-10-20",frequency="monthly"))
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_parent_unknown_commit_and_history_corruption(self):
        await self.once_identity()
        await self.pay_ok("bill","parent-before-loss",60)
        if isinstance(getattr(self.db,"data",None),dict):
            self.db.commit_then_error=True
            response=await self.bill_edit(amount=90)
        else:
            actual_client=self.ctx.ns["client"]
            class LostSession:
                def __init__(inner,session):inner.session=session
                async def __aenter__(inner):return inner
                async def __aexit__(inner,*args):await inner.session.end_session()
                async def with_transaction(inner,callback,**kwargs):
                    await inner.session.with_transaction(callback,**kwargs)
                    raise OperationFailure("Lost parent edit commit response",details={"errorLabels":["UnknownTransactionCommitResult"]})
            class LostClient:
                async def start_session(inner):return LostSession(await actual_client.start_session())
            with patch.dict(self.ctx.ns,{"client":LostClient()}):response=await self.bill_edit(amount=90)
        self.assertEqual(response.status_code,503)
        data=await self.snapshot()
        self.assertEqual(data["bills"][0]["amount"],90)
        self.assertEqual(len(data["transactions"]),1)
        self.assertEqual(data["accounts"][0]["current_balance"],940)
        response=await self.ctx.request("GET","/bills/bill")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((response.json()["paid_amount"],response.json()["remaining"]),(60,30))
        await self.update("recurring_payment_records",{"id":data["recurring_payment_records"][0]["id"]},{"amount":61})
        before=await self.snapshot()
        response=await self.bill_edit(name="Blocked corrupt graph")
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_paused_periodic_resume_and_invalid_future_reference_blocked(self):
        await self.update("recurring_payments",{"id":"rp"},{"state":"paused","pauses":[dict(start="2026-10-12",end=None)]})
        before=await self.snapshot()
        response=await self.state_change("resume")
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)
        await self.update("recurring_payments",{"id":"rp"},{"state":"active","pauses":[]})
        await self.update("bills",{"id":"bill"},{"account_id":"missing-historical-default"})
        before=await self.snapshot()
        response=await self.bill_edit(name="Cannot hide future failure")
        self.assertEqual(response.status_code,409)
        self.assertEqual(await self.snapshot(),before)

    async def test_variable_actual_edit_keeps_estimate_and_future_payment_compatible(self):
        await self.update("recurring_payments",{"id":"rp"},{"variable":True})
        await self.transact(lambda session:self.db.shared_obligations.delete_one({"_id":self.ob["_id"]},session=session))
        self.ob=await self.transact(lambda session:shared.create_shared_obligation(self.db,"bill",expected_environment_id=ENVIRONMENT,
            effective_user=USER,session=session,occurrences=self.ctx.ns["_rp_occurrences"]))
        response=await self.bill_edit(amount=80)
        self.assertEqual(response.status_code,200,response.text)
        await self.pay_ok("bill","var-partial",60)
        response=await self.bill_edit(amount=90)
        self.assertEqual(response.status_code,200,response.text)
        await self.pay_ok("recurring","var-complete",30)
        data=await self.snapshot()
        self.assertEqual(data["accounts"][0]["current_balance"],910)
        child=next(b for b in data["bills"] if b["id"]!="bill")
        self.assertEqual(child["amount"],90)
        original=next(ob for ob in data["shared_obligations"] if ob["bill_id"]=="bill")
        self.assertEqual(shared.money(original["estimated_amount"]),100)
        self.assertEqual(shared.money(original["actual_amount"]),90)
        self.assertEqual(original["schedule_snapshot"]["amount"],100)

    async def context_cases(self, enabled):
        if not enabled:
            await self.transact(lambda session:self.db.shared_obligations.delete_one({"_id":self.ob["_id"]},session=session))
        self.ctx.ns["settings"]=activation_settings("1" if enabled else "0")
        for path,data in (("/bills/bill/payments",dict(amount=10,account_id="account",date="2026-10-11T12:00:00+00:00")),
            ("/recurring-payments/rp/payments",dict(amount=10,account_id="account",mode="expense",due_date="2026-10-20",date="2026-10-11T12:00:00+00:00"))):
            before=await self.snapshot()
            for env,user,code in ((ENVIRONMENT,"another-user",409),("22222222-2222-4222-8222-222222222222",USER,409),
                (ENVIRONMENT,None,422),(None,USER,422),("malformed",USER,409),(ENVIRONMENT,"",422)):
                headers={"Idempotency-Key":"wrong-context"}
                if env is not None:headers["MoneyFlow-Environment-ID"]=env
                if user is not None:headers["MoneyFlow-User-ID"]=user
                topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
                with topology:response=await self.ctx.request("POST",path,json=data,headers=headers)
                self.assertEqual(response.status_code,code,response.text)
                self.assertEqual(await self.snapshot(),before)
            for key,protected in (("valid-protected",True),("old-no-headers",False)):
                headers={"Idempotency-Key":key}
                if protected:headers.update({"MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":USER})
                topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
                with topology:response=await self.ctx.request("POST",path,json=data,headers=headers)
                self.assertEqual(response.status_code,200,response.text)
        result=await self.snapshot()
        self.assertEqual(len(result["transactions"]),4)
        self.assertEqual(result["accounts"][0]["current_balance"],960)
        context=await shared.get_financial_context(self.db,ENVIRONMENT,USER)
        self.assertTrue(context["capabilities"]["bill_payment_context_headers"])
        self.assertTrue(context["capabilities"]["recurring_payment_context_headers"])
        self.assertEqual(context["mode"],"single_user")

    async def test_context_headers_shared_no_writes_on_mismatch(self):
        await self.context_cases(True)

    async def test_delete_context_headers_reject_before_refund_or_retirement(self):
        first = await self.pay_ok("bill", "protected-delete", 60)
        second = await self.pay_ok("recurring", "protected-delete-rp", 20)
        before = await self.snapshot()
        for path in ("/bills/payments/"+first["id"], "/recurring-payments/payments/"+second["id"],
                     "/recurring-payments/payments/"+first["recurring_record_id"]):
            for headers, code in (({"MoneyFlow-Environment-ID":"22222222-2222-4222-8222-222222222222","MoneyFlow-User-ID":USER},409),
                                  ({"MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":"other"},409),
                                  ({"MoneyFlow-Environment-ID":ENVIRONMENT},422),
                                  ({"MoneyFlow-User-ID":USER},422),
                                  ({"MoneyFlow-Environment-ID":"malformed","MoneyFlow-User-ID":USER},409),
                                  ({"MoneyFlow-Environment-ID":"","MoneyFlow-User-ID":USER},422)):
                topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
                with topology:
                    response = await self.ctx.request("DELETE", path, headers=headers)
                self.assertEqual(response.status_code,code,response.text)
                self.assertEqual(await self.snapshot(),before)
                self.assertNotIn("_shared_",response.text)
        topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
        with topology:
            for path in ("/bills/payments/"+first["id"],"/recurring-payments/payments/"+second["id"]):
                response=await self.ctx.request("DELETE",path,headers={"MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":USER})
                self.assertEqual(response.status_code,200,response.text)
        data=await self.snapshot()
        self.assertEqual(len(data["transactions"]),0)
        self.assertEqual(data["accounts"][0]["current_balance"],1000)

    async def test_candidates_offer_only_verified_retired_link_without_writes(self):
        first=await self.pay_ok("bill","candidate",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        before=await self.snapshot()
        response=await self.ctx.request("GET","/recurring-payments/rp/link-candidates?due_date=2026-10-20")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual([t["id"] for t in response.json()],[first["transaction_id"]])
        self.assertNotIn("_shared_",response.text)
        self.assertNotIn("request_fingerprint",response.text)
        self.assertEqual(await self.snapshot(),before)
        await self.pay_ok("recurring","restore-candidate",60,mode="link",transaction_id=first["transaction_id"])
        after=await self.snapshot()
        response=await self.ctx.request("GET","/recurring-payments/rp/link-candidates?due_date=2026-10-20")
        self.assertEqual(response.json(),[])
        self.assertEqual(after["accounts"],before["accounts"])
        self.assertEqual(len(after["transactions"]),1)
        self.assertEqual(await self.snapshot(),after)

    async def test_candidates_corrupt_provenance_rejected_without_metadata_or_writes(self):
        first=await self.pay_ok("bill","bad-candidate",60)
        await self.remove_ok("recurring",first["recurring_record_id"])
        await self.update("transactions",{"id":first["transaction_id"]},{"bill_payment_id":"contradictory"})
        before=await self.snapshot()
        response=await self.ctx.request("GET","/recurring-payments/rp/link-candidates?due_date=2026-10-20")
        self.assertEqual(response.status_code,409,response.text)
        self.assertNotIn("_shared_",response.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_candidates_legacy_only_for_unmanaged_period_and_no_orphan_leak(self):
        await self.transact(lambda session:self.db.shared_obligations.delete_one({"_id":self.ob["_id"]},session=session))
        self.ctx.ns["settings"]=activation_settings("0")
        tx=dict(_id="legacy",id="legacy",user_id=USER,type="expense",amount=25,account_id="account",date="2026-10-11T12:00:00+00:00")
        await self.transact(lambda session:self.db.transactions.insert_one(tx,session=session))
        before=await self.snapshot()
        response=await self.ctx.request("GET","/recurring-payments/rp/link-candidates?due_date=2026-10-20")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual([t["id"] for t in response.json()],["legacy"])
        self.assertEqual(await self.snapshot(),before)
        await self.update("transactions",{"id":"legacy"},{"_shared_obligation_id":"missing","_shared_intent":{"secret_internal_payload":"synthetic"}})
        before=await self.snapshot()
        response=await self.ctx.request("GET","/recurring-payments/rp/link-candidates?due_date=2026-10-20")
        self.assertEqual(response.status_code,409,response.text)
        self.assertNotIn("secret_internal_payload",response.text)
        self.assertNotIn("_shared_",response.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_candidates_do_not_offer_other_period_annulled_or_active_events(self):
        first=await self.pay_ok("bill","full-candidate",100)
        await self.remove_ok("recurring",first["recurring_record_id"])
        before=await self.snapshot()
        response=await self.ctx.request("GET","/recurring-payments/rp/link-candidates?due_date=2026-11-20")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),[])
        self.assertEqual(await self.snapshot(),before)
        await self.remove_ok("bill",first["id"])
        before=await self.snapshot()
        response=await self.ctx.request("GET","/recurring-payments/rp/link-candidates?due_date=2026-10-20")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),[])
        self.assertEqual(await self.snapshot(),before)

    async def test_delete_context_legacy_compatibility(self):
        await self.context_cases(False)
        before=await self.snapshot()
        payments=before["bill_payments"]
        for endpoint,pid in (("/bills/payments/",payments[0]["id"]),
                             ("/recurring-payments/payments/",before["recurring_payment_records"][0]["id"])):
            response=await self.ctx.request("DELETE",endpoint+pid,headers={"MoneyFlow-Environment-ID":"22222222-2222-4222-8222-222222222222","MoneyFlow-User-ID":USER})
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(await self.snapshot(),before)
        headers={"MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":USER}
        response=await self.ctx.request("DELETE","/bills/payments/"+payments[0]["id"],headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        response=await self.ctx.request("DELETE","/bills/payments/"+payments[1]["id"])
        self.assertEqual(response.status_code,200,response.text)
        data=await self.snapshot()
        self.assertEqual(data["accounts"][0]["current_balance"],980)

    async def test_protected_delete_rollback_after_financial_change(self):
        first=await self.pay_ok("bill","delete-rollback",60)
        before=await self.snapshot()
        original=shared.change_shared_payment
        async def fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise OperationFailure("Synthetic failure after refund")
        topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
        with topology,patch.object(shared,"change_shared_payment",fail):
            response=await self.ctx.request("DELETE","/bills/payments/"+first["id"],headers={"MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":USER})
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_context_headers_legacy_without_r4(self):
        await self.context_cases(False)

    async def test_protected_context_rollback_and_uncertain_commit_recovery(self):
        self.ctx.ns["settings"]=activation_settings("1")
        headers={"Idempotency-Key":"protected-rollback","MoneyFlow-Environment-ID":ENVIRONMENT,"MoneyFlow-User-ID":USER}
        data=dict(amount=60,account_id="account",date="2026-10-11T12:00:00+00:00")
        async def post():
            topology=patch.object(shared,"_hello",AsyncMock(return_value=HELLO)) if isinstance(getattr(self.db,"data",None),dict) else nullcontext()
            with topology:return await self.ctx.request("POST","/bills/bill/payments",json=data,headers=headers)
        before=await self.snapshot()
        original=shared.register_shared_payment
        async def fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise OperationFailure("Injected protected financial failure")
        with patch.object(shared,"register_shared_payment",fail):response=await post()
        self.assertEqual(response.status_code,503)
        self.assertEqual(await self.snapshot(),before)
        if isinstance(getattr(self.db,"data",None),dict):
            self.db.commit_then_error=True
            response=await post()
        else:
            actual=self.ctx.ns["client"]
            class LostSession:
                def __init__(inner,session):inner.session=session
                async def __aenter__(inner):return inner
                async def __aexit__(inner,*args):await inner.session.end_session()
                async def with_transaction(inner,callback,**kwargs):
                    await inner.session.with_transaction(callback,**kwargs)
                    raise OperationFailure("Lost protected commit",details={"errorLabels":["UnknownTransactionCommitResult"]})
            class LostClient:
                async def start_session(inner):return LostSession(await actual.start_session())
            with patch.dict(self.ctx.ns,{"client":LostClient()}):response=await post()
        self.assertEqual(response.status_code,503)
        saved=await self.snapshot()
        self.assertEqual(len(saved["transactions"]),1)
        self.assertEqual(saved["accounts"][0]["current_balance"],940)
        response=await post()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(await self.snapshot(),saved)


class SharedDispatchTests(DispatchCases,unittest.IsolatedAsyncioTestCase):
    asyncSetUp = core.SharedPaymentTests.asyncSetUp

    async def test_unknown_commit_recovers_same_intention_and_generation(self):
        self.db.commit_then_error=True
        response = await self.post("bill","uncertain",100)
        self.assertEqual(response.status_code,503)
        before = await self.snapshot()
        self.assertEqual((len(before["transactions"]),len(before["bills"])),(1,2))
        await self.pay_ok("bill","uncertain",100)
        self.assertEqual(await self.snapshot(),before)

    async def test_delete_unknown_commit_recovers_without_second_refund(self):
        first=await self.pay_ok("bill","uncertain-delete",60)
        self.db.commit_then_error=True
        response=await self.remove("bill",first["id"])
        self.assertEqual(response.status_code,503)
        before=await self.snapshot()
        self.assertEqual(len(before["transactions"]),0)
        self.assertEqual(before["accounts"][0]["current_balance"],1000)
        await self.remove_ok("bill",first["id"])
        self.assertEqual(await self.snapshot(),before)

    async def test_delete_without_transactions_rejected_without_writes(self):
        first=await self.pay_ok("bill","unsupported-delete",60)
        before=await self.snapshot()
        self.client.supported=False
        response=await self.remove("bill",first["id"])
        self.assertEqual(response.status_code,503)
        self.assertEqual(await self.snapshot(),before)

    async def test_tracking_unknown_commit_recovers_exact_result(self):
        self.db.commit_then_error=True
        response=await self.post("recurring","uncertain-mark",30,mode="mark",settles=True)
        self.assertEqual(response.status_code,503)
        before=await self.snapshot()
        self.assertEqual(len(before["shared_tracking_intents"]),1)
        self.assertEqual(len(before["transactions"]),0)
        await self.pay_ok("recurring","uncertain-mark",30,mode="mark",settles=True)
        self.assertEqual(await self.snapshot(),before)
