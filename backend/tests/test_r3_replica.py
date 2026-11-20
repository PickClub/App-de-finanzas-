"""Explicit opt-in certification against the dedicated disposable R3 replica."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from pymongo.errors import OperationFailure

from backend.auth_core import AuthService, InvalidCredentials, StorageUnavailable
from backend.authenticated_api import create_authenticated_app
from backend.tests.r3_replica_support import DATABASE, TARGET, Fence, Store, async_client, connect, retry_auth
from backend.tests.test_auth_core import Delivery, PASSWORD


class DestinationTests(unittest.TestCase):
    def test_invalid_targets_are_rejected_before_network(self):
        with patch("backend.r3_local_store.MongoClient") as client:
            for target in (None, TARGET.replace("27118", "27018"),
                           TARGET.replace("127.0.0.1", "example.com"),
                           TARGET.replace(DATABASE, "development_local_finanzas"),
                           TARGET.replace("r3_security_test_rs", "wrong")):
                with self.assertRaises(ValueError):
                    connect(target)
            client.assert_not_called()


@unittest.skipUnless(os.getenv("R3_SECURITY_TEST_TARGET"), "Explicit isolated replica required")
class ReplicaTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = os.environ["R3_SECURITY_TEST_TARGET"]
        cls.sync = connect(cls.target)
        cls.addClassCleanup(cls.sync.close)
        cls.db = cls.sync[DATABASE]
        for name, key in (("auth_users", "email"), ("auth_sessions", "access_digest"), ("users", "id")):
            cls.db[name].create_index(key, unique=True)
        cls.environment = str(uuid4())
        cls.db.moneyflow_metadata.update_one(
            {"_id": "financial-context"},
            {"$setOnInsert": {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                              "environment_id": cls.environment}}, upsert=True,
        )
        cls.environment = cls.db.moneyflow_metadata.find_one({"_id": "financial-context"})["environment_id"]

    async def asyncSetUp(self):
        self.motor = async_client(self.target)
        self.addCleanup(self.motor.close)
        self.store = Store(self.db)
        self.delivery = Delivery()
        self.operator = object()
        self.now = datetime.now(timezone.utc)
        self.auth = AuthService(self.store, self.delivery, lambda actor: actor is self.operator,
                                lambda: self.now)
        self.fence = Fence(self.motor[DATABASE])
        self.app = create_authenticated_app(self.auth, self.motor[DATABASE],
                                       expected_environment_id=self.environment, write_fence=self.fence)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://r3-isolated.invalid")
        self.addAsyncCleanup(self.http.aclose)
        self.email, self.tokens, self.owner, self.accounts = {}, {}, {}, {}
        for actor in ("a", "b"):
            email = self.email[actor] = f"{actor}-{uuid4().hex}@example.com"
            self.auth.invite(self.operator, email)
            self.auth.accept_invitation(self.delivery.messages[-1][2], PASSWORD)
            self.tokens[actor] = self.auth.login(email, PASSWORD)
            self.owner[actor] = self.auth.authenticate(self.tokens[actor].access).user_id
            self.accounts[actor] = [
                (await self.ok("POST", "/accounts", actor,
                               json={"name": name, "initial_balance": amount}))["id"]
                for name, amount in (("Source", 100), ("Target", 0))
            ]

    async def call(self, method, path, actor="a", key=None, **kwargs):
        headers = {"Authorization": f"Bearer {self.tokens[actor].access}"} if actor else {}
        if key:
            headers["Idempotency-Key"] = key
        return await self.http.request(method, "/api" + path, headers=headers, **kwargs)

    async def ok(self, method, path, actor="a", **kwargs):
        response = await self.call(method, path, actor, **kwargs)
        self.assertIn(response.status_code, (200, 201, 204), response.text)
        return response.json() if response.content else None

    def transfer(self, actor, amount=10):
        source, target = self.accounts[actor]
        return {"name": "Transfer", "type": "transfer", "amount": amount,
                "account_id": source, "to_account_id": target}

    def balances(self, actor):
        return [self.db.accounts.find_one({"id": aid, "user_id": self.owner[actor]})["current_balance"]
                for aid in self.accounts[actor]]

    def assert_reconciled(self, actor):
        rows = list(self.db.transactions.find({"user_id": self.owner[actor]}))
        for aid in self.accounts[actor]:
            account = self.db.accounts.find_one({"id": aid, "user_id": self.owner[actor]})
            delta = sum(
                row["amount"] * (1 if row["type"] == "income" else -1)
                for row in rows if row.get("account_id") == aid
            )
            delta += sum(row["amount"] for row in rows
                         if row["type"] == "transfer" and row.get("to_account_id") == aid)
            self.assertEqual(account["current_balance"], account["initial_balance"] + delta)

    async def test_ab_profiles_notes_categories_history_and_legacy(self):
        legacy = {"id": str(uuid4()), "user_id": "default-user", "name": "Legacy synthetic"}
        self.db.accounts.insert_one(legacy.copy())
        foreign = self.accounts["b"][0]
        before = list(self.db.accounts.find({"user_id": self.owner["b"]}))
        denied = await self.call("PUT", f"/accounts/{foreign}", json={"name": "Attempt"})
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(list(self.db.accounts.find({"user_id": self.owner["b"]})), before)
        for actor in ("a", "b"):
            self.assertEqual((await self.ok("GET", "/user", actor))["id"], self.owner[actor])
            self.assertEqual(len(await self.ok("GET", "/accounts", actor)), 2)
            await self.ok("POST", "/categories/init-defaults", actor)
            self.assertTrue(all(row["user_id"] == self.owner[actor]
                                for row in await self.ok("GET", "/categories", actor)))
        note = await self.ok("POST", "/notes", json={"title": "A", "content": "Synthetic", "color": "#123456"})
        self.assertEqual((await self.call("GET", f"/notes/{note['id']}", "b")).status_code, 404)
        self.assertEqual(await self.ok("GET", "/notes", "b"), [])
        self.assertEqual(self.db.notes.count_documents({"id": note["id"], "user_id": self.owner["a"]}), 1)
        await self.ok("POST", "/transactions", json=self.transfer("a"))
        self.assertEqual((await self.ok("GET", "/transactions/page", "b"))["total"], 0)
        self.assertEqual((await self.ok("GET", "/summary", "b"))["total_balance"], 100)
        self.assertEqual(self.db.accounts.count_documents(legacy), 1)
        self.assertEqual((await self.call("POST", "/seed")).status_code, 404)

    async def test_concurrent_transfer_idempotency_and_lost_response(self):
        payload = self.transfer("a")
        self.tokens["other"] = self.auth.login(self.email["a"], PASSWORD)
        responses = await asyncio.gather(*[
            self.call("POST", "/transactions", actor, key="shared-key", json=payload)
            for actor in ("a", "other")
        ])
        self.assertTrue(all(response.status_code in (200, 503) for response in responses))
        self.assertIn(200, [response.status_code for response in responses])
        # Deliberately disregard the first response; recover through the original key.
        a = await self.ok("POST", "/transactions", key="shared-key", json=payload)
        b = await self.ok("POST", "/transactions", "b", key="shared-key", json=self.transfer("b"))
        self.assertNotEqual(a["id"], b["id"])
        responses = await asyncio.gather(*[
            self.call("POST", "/transactions", actor, key=key, json=payload)
            for actor, key in (("a", "different-1"), ("other", "different-2"))
        ])
        self.assertTrue(all(response.status_code in (200, 503) for response in responses))
        for key in ("different-1", "different-2"):
            await self.ok("POST", "/transactions", key=key, json=payload)
        for actor, count in (("a", 3), ("b", 1)):
            self.assertEqual(self.db.transactions.count_documents({"user_id": self.owner[actor]}), count)
            self.assertEqual(self.db.movement_receipts.count_documents({"user_id": self.owner[actor]}), count)
            self.assertEqual(self.balances(actor), [100 - 10 * count, 10 * count])
            self.assert_reconciled(actor)

    async def test_rollback_after_ledger_and_receipt_writes(self):
        async def fail(_):
            raise OperationFailure("Synthetic pre-commit failure")

        self.fence.after = fail
        result = await self.call("POST", "/transactions", key="rollback", json=self.transfer("a"))
        self.assertEqual(result.status_code, 503)
        self.assertEqual(self.balances("a"), [100, 0])
        for name in ("transactions", "movement_receipts"):
            self.assertEqual(self.db[name].count_documents({"user_id": self.owner["a"]}), 0)
        self.assert_reconciled("a")

    async def test_revocation_wins_before_transfer_and_payment_fences(self):
        debt = await self.ok("POST", "/debts", json={"name": "Loan", "direction": "i_owe", "original_amount": 30})
        cases = [("/transactions", self.transfer("a")),
                 ("/debt-payments", {"debt_id": debt["id"], "amount": 10, "account_id": self.accounts["a"][0]})]
        for path, payload in cases:
            entered, resume = asyncio.Event(), asyncio.Event()

            async def pause(_):
                entered.set()
                await resume.wait()

            self.fence.before = pause
            request = asyncio.create_task(self.call("POST", path, json=payload, key="revoked"))
            await asyncio.wait_for(entered.wait(), 5)
            await asyncio.to_thread(self.auth.logout, self.tokens["a"].access)
            resume.set()
            self.assertEqual((await request).status_code, 401)
            self.tokens["a"] = self.auth.login(self.email["a"], PASSWORD)
        self.assertEqual(self.balances("a"), [100, 0])
        self.assertEqual(self.db.transactions.count_documents({"user_id": self.owner["a"]}), 0)
        self.assertEqual(self.db.debt_payments.count_documents({"user_id": self.owner["a"]}), 0)
        self.assertEqual(self.db.debts.find_one({"id": debt["id"]})["remaining_amount"], 30)

    async def test_concurrent_refresh_recovery_expiry_and_auth_outage(self):
        old = self.tokens["a"]

        def rotate():
            try:
                return retry_auth(self.auth.rotate, old.refresh)
            except InvalidCredentials:
                return None

        results = await asyncio.gather(asyncio.to_thread(rotate), asyncio.to_thread(rotate))
        winners = [value for value in results if value]
        self.assertEqual(len(winners), 1)
        with self.assertRaises(InvalidCredentials):
            self.auth.authenticate(winners[0].access)
        self.assertTrue(self.db.auth_sessions.find_one({"user_id": self.owner["a"]})["revoked"])
        self.assertEqual(self.db.auth_refresh.count_documents({
            "family_id": self.db.auth_sessions.find_one({"user_id": self.owner["a"]})["_id"]
        }), 2)
        principal = self.auth.authenticate(self.tokens["b"].access)
        self.assertEqual(principal.user_id, self.owner["b"])
        self.auth.recover(self.operator, self.email["b"])
        self.auth.reset_password(self.delivery.messages[-1][2], "New synthetic password")
        self.assertTrue(self.db.auth_sessions.find_one({"_id": principal.family_id})["revoked"])
        self.tokens["a"] = self.auth.login(self.email["a"], PASSWORD)
        unavailable = connect(self.target)
        self.auth.store = Store(unavailable[DATABASE])
        unavailable.close()
        try:
            self.assertEqual((await self.call("POST", "/transactions", json=self.transfer("a"))).status_code, 503)
        finally:
            self.auth.store = self.store
        self.now += timedelta(minutes=11)
        self.assertEqual((await self.call("GET", "/accounts")).status_code, 401)
        self.assertEqual(self.db.transactions.count_documents({"user_id": self.owner["a"]}), 0)

    async def test_debt_bill_recurring_and_goal_ledger(self):
        source, target = self.accounts["a"]
        scope = {"user_id": self.owner["a"]}
        debt = await self.ok("POST", "/debts", json={
            "name": "Synthetic debt", "direction": "i_owe", "original_amount": 25,
        })
        payment = {"debt_id": debt["id"], "amount": 10, "account_id": source}
        receipt = await self.ok("POST", "/debt-payments", key="debt", json=payment)
        self.assertEqual(await self.ok("POST", "/debt-payments", key="debt", json=payment), receipt)
        self.assertEqual(self.db.debts.find_one({"id": debt["id"], **scope})["remaining_amount"], 15)
        await self.ok("DELETE", f"/debt-payments/{receipt['id']}")
        self.assertEqual((await self.call("POST", "/debt-payments", key="debt", json=payment)).status_code, 409)
        self.assertEqual(self.db.debts.find_one({"id": debt["id"], **scope})["remaining_amount"], 25)
        self.assertEqual(self.balances("a"), [100, 0])

        schedule = await self.ok("POST", "/recurring-payments", json={
            "name": "Synthetic subscription", "amount": 20, "start_date": "2026-11-04",
            "frequency": "monthly", "account_id": source,
        })
        bill = await self.ok("POST", "/bills", json={
            "name": "Synthetic bill", "amount": 20, "due_date": "2026-11-04",
            "frequency": "monthly", "account_id": source, "recurring_payment_id": schedule["id"],
        })
        path = f"/bills/{bill['id']}/payments"
        bill_payment = {"account_id": source, "amount": 20}
        self.tokens["other"] = self.auth.login(self.email["a"], PASSWORD)
        outcomes = await asyncio.gather(*[
            self.call("POST", path, actor, key="bill", json=bill_payment)
            for actor in ("a", "other")
        ])
        self.assertTrue(all(result.status_code in (200, 503) for result in outcomes))
        paid = await self.ok("POST", path, key="bill", json=bill_payment)
        self.assertEqual(self.db.bills.count_documents({"series_id": bill["id"], **scope}), 2)
        self.assertEqual(self.db.bill_payments.count_documents(scope), 1)
        linked = self.db.recurring_payment_records.find_one(scope)
        self.assertEqual(linked["transaction_id"], paid["transaction_id"])
        self.assertEqual(self.db.transactions.count_documents(scope), 1)
        duplicate = await self.call("POST", f"/recurring-payments/{schedule['id']}/payments", json={
            "due_date": "2026-11-04", "mode": "expense", "amount": 20, "account_id": source,
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.balances("a"), [80, 0])

        goal = await self.ok("POST", "/goals", json={
            "name": "Synthetic goal", "target_amount": 20, "account_id": target,
        })
        contributions = f"/goals/{goal['id']}/contributions"
        deposit = {"kind": "deposit", "amount": 20, "account_id": source, "real_movement": True}
        foreign = await self.call("POST", contributions,
                                  json={**deposit, "account_id": self.accounts["b"][0]})
        self.assertEqual(foreign.status_code, 404)
        await self.ok("POST", contributions, key="deposit", json=deposit)
        await self.ok("POST", contributions, key="deposit", json=deposit)
        await self.ok("POST", contributions, key="withdrawal",
                      json={**deposit, "kind": "withdrawal", "amount": 5})
        self.assertEqual(self.db.goal_contributions.count_documents(scope), 2)
        self.assertEqual(self.db.saving_goals.find_one({"id": goal["id"], **scope})["current_amount"], 15)
        self.assertEqual(self.balances("a"), [65, 15])
        self.assertEqual(self.balances("b"), [100, 0])
        self.assert_reconciled("a")
        self.assert_reconciled("b")

    async def test_catalog_account_reference_and_profile_races(self):
        owner = self.owner["a"]
        other_session = self.auth.login(self.email["a"], PASSWORD)
        self.tokens["other"] = other_session
        replies = await asyncio.gather(
            self.call("POST", "/categories/init-defaults"),
            self.call("POST", "/categories/init-defaults", "other"),
        )
        self.assertTrue(all(reply.status_code in (200, 503) for reply in replies))
        stable = await self.ok("POST", "/categories/init-defaults")
        self.assertEqual(stable["created"] + stable["groups_created"] + stable["links"], 0)
        categories = list(self.db.categories.find({"user_id": owner}))
        self.assertEqual(len(categories), stable["total"])
        self.assertEqual(len({(r["type"], r["name"], r["is_group"]) for r in categories}), len(categories))

        account = self.accounts["a"][1]
        delete, reference = await asyncio.gather(
            self.call("DELETE", f"/accounts/{account}"),
            self.call("POST", "/transactions", "other", json=self.transfer("a")),
        )
        self.assertTrue(delete.status_code == 200 or reference.status_code == 200)
        self.assertFalse(delete.status_code == reference.status_code == 200)
        stored = self.db.accounts.find_one({"id": account, "user_id": owner})
        movement = self.db.transactions.find_one({"to_account_id": account, "user_id": owner})
        self.assertTrue(stored is not None or movement is None)
        if movement:
            self.assert_reconciled("a")

        email = f"race-{uuid4().hex}@example.com"
        self.auth.invite(self.operator, email)
        invitation = self.delivery.messages[-1][2]

        def accept():
            try:
                self.auth.accept_invitation(invitation, PASSWORD)
                return True
            except (InvalidCredentials, StorageUnavailable):
                return False

        results = await asyncio.gather(asyncio.to_thread(accept), asyncio.to_thread(accept))
        self.assertEqual(results.count(True), 1)
        identity = self.db.auth_users.find_one({"email": email})
        self.assertEqual(identity["status"], "active")
        self.assertEqual(self.db.users.count_documents({"id": identity["id"]}), 1)

    async def test_response_dropped_after_commit_replays_original_receipt(self):
        async def drop_response(scope, receive, send):
            async def drop(message):
                if message["type"] == "http.response.start":
                    self.assertEqual(message["status"], 200)
                    self.assertEqual(self.balances("a"), [90, 10])
                    raise httpx.ReadError("Synthetic response loss after commit")
                await send(message)
            await self.app(scope, receive, drop)

        payload = self.transfer("a")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=drop_response),
                                     base_url="http://r3-isolated.invalid") as client:
            with self.assertRaises(httpx.ReadError):
                await client.post("/api/transactions", json=payload, headers={
                    "Authorization": f"Bearer {self.tokens['a'].access}",
                    "Idempotency-Key": "lost-response",
                })
        stored = self.db.transactions.find_one({"user_id": self.owner["a"]})
        response = await self.ok("POST", "/transactions", key="lost-response", json=payload)
        self.assertEqual(response["id"], stored["id"])
        self.assertEqual(self.db.transactions.count_documents({"user_id": self.owner["a"]}), 1)
        self.assertEqual(self.db.movement_receipts.count_documents({"user_id": self.owner["a"]}), 1)
        self.assert_reconciled("a")

    def financial_snapshot(self, actor):
        scope = {"user_id": self.owner[actor]}
        return {
            name: list(self.db[name].find(scope).sort("_id", 1))
            for name in ("accounts", "debts", "debt_payments", "transactions",
                         "categories", "movement_receipts")
        }

    async def partial_debt_fixture(self, amount):
        self.assertEqual(self.balances("a"), [100, 0])
        debt = await self.ok("POST", "/debts", json={
            "name": "Synthetic debt", "direction": "i_owe", "original_amount": 25,
        })
        self.assertEqual(debt["remaining_amount"], 25)
        return {"debt_id": debt["id"], "account_id": self.accounts["a"][0],
                "amount": amount, "date": "2026-10-01"}

    def assert_debt_payment_state(self, payload, paid):
        scope = {"user_id": self.owner["a"]}
        debt = self.db.debts.find_one(dict(scope, id=payload["debt_id"]))
        self.assertEqual(debt["remaining_amount"], 25 - paid)
        self.assertEqual(debt["total_paid"], paid)
        self.assertEqual(self.balances("a"), [100 - paid, 0])
        payments = list(self.db.debt_payments.find(dict(
            scope, debt_id=payload["debt_id"], deleted={"$ne": True})))
        movements = list(self.db.transactions.find(dict(scope, debt_id=payload["debt_id"])))
        self.assertEqual(len(payments), int(bool(paid)))
        self.assertEqual(len(movements), int(bool(paid)))
        self.assert_reconciled("a")
        if paid:
            payment, movement = payments[0], movements[0]
            self.assertEqual(payment["transaction_id"], movement["id"])
            self.assertEqual(movement["debt_payment_id"], payment["id"])
            for field in ("amount", "account_id", "debt_id", "date", "user_id"):
                self.assertEqual(payment[field], movement[field], field)
            self.assertEqual(payment["amount"], paid)
            self.assertTrue(payment["request_fingerprint"])
            return payment

    async def test_debt_payment_response_loss_after_commit(self):
        payload = await self.partial_debt_fixture(10)
        before_b = self.financial_snapshot("b")
        key = "debt-lost-response"

        async def drop_response(scope, receive, send):
            async def drop(message):
                if message["type"] == "http.response.start":
                    self.assertEqual(message["status"], 200)
                    self.assert_debt_payment_state(payload, 10)
                    raise httpx.ReadError("Synthetic debt response loss after commit")
                await send(message)
            await self.app(scope, receive, drop)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=drop_response),
                                     base_url="http://r3-isolated.invalid") as client:
            with self.assertRaises(httpx.ReadError):
                await client.post("/api/debt-payments", json=payload, headers={
                    "Authorization": f"Bearer {self.tokens['a'].access}",
                    "Idempotency-Key": key,
                })
        stored = self.assert_debt_payment_state(payload, 10)
        replay = await self.ok("POST", "/debt-payments", key=key, json=payload)
        for field in ("id", "transaction_id", "amount", "date"):
            self.assertEqual(replay[field], stored[field], field)
        before_a = self.financial_snapshot("a")
        mismatch = await self.call("POST", "/debt-payments", key=key,
                                   json={**payload, "amount": 11})
        self.assertEqual(mismatch.status_code, 409)
        foreign = await self.call("POST", "/debt-payments", "b", key=key,
                                  json={**payload, "account_id": self.accounts["b"][0]})
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(self.financial_snapshot("a"), before_a)
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_distinct_concurrent_debt_payments_cannot_overpay(self):
        payload = await self.partial_debt_fixture(15)
        before_b = self.financial_snapshot("b")
        self.tokens["other"] = self.auth.login(self.email["a"], PASSWORD)
        ready = asyncio.Event()
        arrivals = 0

        async def rendezvous(_):
            nonlocal arrivals
            arrivals += 1
            if arrivals >= 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=5)

        actors_and_keys = (("a", "payment-one"), ("other", "payment-two"))
        self.fence.before = rendezvous
        try:
            responses = await asyncio.gather(*(
                self.call("POST", "/debt-payments", actor, key=key, json=payload)
                for actor, key in actors_and_keys
            ))
        finally:
            self.fence.before = None
        self.assertGreaterEqual(arrivals, 2)
        for (actor, key), response in zip(actors_and_keys, responses, strict=True):
            if response.status_code == 503:
                response = await self.call("POST", "/debt-payments", actor, key=key, json=payload)
            self.assertIn(response.status_code, (200, 422), response.text)
            if response.status_code == 200:
                self.assertEqual(response.json()["id"], self.assert_debt_payment_state(payload, 15)["id"])
            else:
                self.assertIn("saldo pendiente", response.json()["detail"])
        self.assert_debt_payment_state(payload, 15)
        before_a = self.financial_snapshot("a")
        foreign = await self.call("POST", "/debt-payments", key="foreign-account",
                                  json={**payload, "amount": 5, "account_id": self.accounts["b"][0]})
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(self.financial_snapshot("a"), before_a)
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_historical_edit_and_unchanged_save_preserve_fields(self):
        before_b = self.financial_snapshot("b")
        category = await self.ok("POST", "/categories", json={
            "name": "Synthetic historical category", "type": "expense",
        })
        for change_name, account_id in zip((True, False), self.accounts["a"], strict=True):
            with self.subTest(change_name=change_name):
                initial = Decimal(str(self.db.accounts.find_one({"id": account_id})["current_balance"]))
                payload = {"name": "Original historical expense", "amount": 12.34, "type": "expense",
                           "date": "2020-02-29T17:25:36.123+05:30", "account_id": account_id,
                           "category_id": category["id"], "notes": "Keep historical notes"}
                created = await self.ok("POST", "/transactions", json=payload)
                path = f"/transactions/{created['id']}"
                selector = {"id": created["id"], "user_id": self.owner["a"]}
                stored = self.db.transactions.find_one(selector)
                edit = {field: stored[field] for field in ("name", "amount", "type")}
                if change_name:
                    edit["name"] = "Only description changed"
                expected = {**stored, "name": edit["name"], "revision": 1}
                before_history = await self.ok("GET", "/transactions/page")
                before_a = self.financial_snapshot("a")
                for method in ("GET", "PUT"):
                    options = {"json": edit} if method == "PUT" else {}
                    self.assertEqual((await self.call(method, path, "b", **options)).status_code, 404)
                self.assertEqual(self.financial_snapshot("a"), before_a)
                await self.ok("PUT", path, json={**edit, "expected_revision": 0})
                self.assertEqual(self.db.transactions.find_one(selector), expected)
                after_history = await self.ok("GET", "/transactions/page")
                self.assertEqual(after_history["total"], before_history["total"])
                self.assertEqual([row["id"] for row in after_history["items"]],
                                 [row["id"] for row in before_history["items"]])
                detail = await self.ok("GET", path)
                history_row = next(row for row in after_history["items"] if row["id"] == created["id"])
                for field in payload:
                    for view in (detail, history_row):
                        if field == "amount":
                            self.assertEqual(Decimal(str(view[field])), Decimal("12.34"))
                        else:
                            self.assertEqual(view[field], expected[field], field)
                self.assertEqual(stored["date"], payload["date"])
                self.assertEqual(self.db.transactions.count_documents(selector), 1)
                balance = self.db.accounts.find_one({"id": account_id})["current_balance"]
                self.assertEqual(Decimal(str(balance)), initial - Decimal("12.34"))
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_partial_debt_payment_reversal_preserves_tombstone(self):
        payload = await self.partial_debt_fixture(10)
        before_b = self.financial_snapshot("b")
        receipt = await self.ok("POST", "/debt-payments", key="partial-payment", json=payload)
        payment = self.assert_debt_payment_state(payload, 10)
        path = f"/debt-payments/{receipt['id']}"
        self.assertEqual(receipt["transaction_id"], payment["transaction_id"])
        history = await self.ok("GET", "/transactions/page")
        self.assertEqual([row["id"] for row in history["items"]], [payment["transaction_id"]])
        before_a = self.financial_snapshot("a")
        self.assertEqual((await self.call("DELETE", path, "b", key="reverse")).status_code, 404)
        self.assertEqual(self.financial_snapshot("a"), before_a)
        await self.ok("DELETE", path, key="reverse")
        self.assert_debt_payment_state(payload, 0)
        history = await self.ok("GET", "/transactions/page")
        self.assertEqual(history["total"], 0)
        self.assertEqual(history["items"], [])
        state = self.financial_snapshot("a")
        self.assertEqual(state["debt_payments"], [{**payment, "deleted": True}])
        self.assertEqual(len(state["movement_receipts"]), 1)
        await self.ok("DELETE", path, key="reverse")
        replay = await self.call("POST", "/debt-payments", key="partial-payment", json=payload)
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(self.financial_snapshot("a"), state)
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def assert_unknown_transaction_date_preserved(self, missing):
        before_b = self.financial_snapshot("b")
        account = self.accounts["a"][0]
        self.assertEqual(self.balances("a"), [100, 0])
        created = await self.ok("POST", "/transactions", json={
            "name": "Synthetic historical expense", "amount": 10, "type": "expense",
            "account_id": account, "date": "2020-01-02T12:00:00Z",
        })
        selector = {"id": created["id"], "user_id": self.owner["a"]}
        path = f"/transactions/{created['id']}"
        change = {"$unset": {"date": ""}} if missing else {"$set": {"date": None}}
        self.assertEqual(self.db.transactions.update_one(selector, change).matched_count, 1)
        before = self.db.transactions.find_one(selector)
        self.assertEqual("date" in before, not missing)
        self.assertIsNone(before.get("date"))
        self.assertEqual(self.balances("a"), [90, 0])
        detail_before = await self.ok("GET", path)
        self.assertEqual("date" in detail_before, not missing)
        self.assertIsNone(detail_before.get("date"))
        history_before = await self.call("GET", "/transactions/page")
        self.assertEqual(history_before.status_code, 409)
        result = await self.ok("PUT", path, json={
            "name": "Description only", "amount": 10, "type": "expense", "expected_revision": 0,
        })
        after = self.db.transactions.find_one(selector)
        self.assertEqual(after, dict(before, name="Description only", revision=1))
        self.assertEqual(self.balances("a"), [90, 0])
        detail = await self.ok("GET", path)
        for response in (result, detail):
            self.assertEqual("date" in response, not missing)
            self.assertIsNone(response.get("date"))
            self.assertEqual(response["name"], "Description only")
        history = await self.call("GET", "/transactions/page")
        self.assertEqual(history.status_code, 409)
        self.assertEqual(history.json(), history_before.json())
        self.assertEqual(self.financial_snapshot("b"), before_b)
        self.assert_reconciled("a")

    async def test_missing_date_preserved_on_edit(self):
        await self.assert_unknown_transaction_date_preserved(missing=True)

    async def test_null_date_preserved_on_edit(self):
        await self.assert_unknown_transaction_date_preserved(missing=False)

    async def stale_transaction_fixture(self):
        source, target = self.accounts["a"]
        self.assertEqual(self.balances("a"), [100, 0])
        created = await self.ok("POST", "/transactions", json={
            "name": "Synthetic expense", "type": "expense", "amount": 10,
            "date": "2020-01-02T12:00:00Z", "account_id": source,
        })
        self.tokens["other"] = self.auth.login(self.email["a"], PASSWORD)
        path = f"/transactions/{created['id']}"
        a = await self.ok("GET", path)
        stale = await self.ok("GET", path, "other")
        self.assertEqual(a, stale)
        self.assertEqual(self.balances("a"), [90, 0])
        return path, stale

    async def assert_characterized_edit(self, path, result, amount, account_id, balances):
        detail = await self.ok("GET", path)
        history = await self.ok("GET", "/transactions/page")
        stored = self.db.transactions.find_one({"id": detail["id"], "user_id": self.owner["a"]})
        self.assertEqual(history["total"], 1)
        self.assertEqual(len(history["items"]), 1)
        for record in (result, detail, stored, history["items"][0]):
            self.assertEqual(record["id"], detail["id"])
            self.assertEqual(record["amount"], amount)
            self.assertEqual(record["account_id"], account_id)
            self.assertEqual(record["name"], result["name"])
            self.assertEqual(record["date"], "2020-01-02T12:00:00Z")
        self.assertEqual(self.balances("a"), balances)
        self.assert_reconciled("a")

    async def assert_stale_edit_rejected(self, change_account):
        before_b = self.financial_snapshot("b")
        path, stale = await self.stale_transaction_fixture()
        source, target = self.accounts["a"]
        original = {"name": stale["name"], "type": "expense", "amount": 10}
        self.assertEqual((await self.call("PUT", path, json=original, key="old-client")).status_code, 422)
        self.assertEqual(self.balances("a"), [90, 0])
        result = await self.ok("PUT", path, json={
            **original, "expected_revision": stale["revision"],
            **({"account_id": target} if change_account else {"amount": 20}),
        })
        account = target if change_account else source
        amount = 10 if change_account else 20
        balances = [100, -10] if change_account else [80, 0]
        await self.assert_characterized_edit(path, result, amount, account, balances)
        before_a = self.financial_snapshot("a")
        edit = {**original, "name": "Stale description", "expected_revision": stale["revision"]}
        if change_account:
            edit["account_id"] = source
        self.assertEqual((await self.call("PUT", path, "other", key="stale", json=edit)).status_code, 409)
        self.assertEqual((await self.call("PUT", path, "b", json=edit)).status_code, 404)
        self.assertEqual(self.financial_snapshot("a"), before_a)
        self.assertEqual(self.financial_snapshot("b"), before_b)
        await self.assert_characterized_edit(path, result, amount, account, balances)

    async def test_stale_edit_cannot_overwrite_amount(self):
        await self.assert_stale_edit_rejected(change_account=False)

    async def test_stale_edit_cannot_overwrite_account(self):
        await self.assert_stale_edit_rejected(change_account=True)

    async def test_concurrent_edits_advance_legacy_revision_once(self):
        path, source = await self.stale_transaction_fixture()
        self.db.transactions.update_one({"id": source["id"], "user_id": self.owner["a"]},
                                        {"$unset": {"revision": ""}})
        self.assertEqual((await self.ok("GET", path))["revision"], 0)
        body = {"name": source["name"], "type": "expense", "amount": 20, "expected_revision": 0}
        pairs = (("a", "edit-a"), ("other", "edit-other"))
        responses = await asyncio.gather(*(self.call("PUT", path, actor, key=key, json=body)
                                          for actor, key in pairs))
        outcomes = []
        for (actor, key), response in zip(pairs, responses, strict=True):
            if response.status_code == 503:
                response = await self.call("PUT", path, actor, key=key, json=body)
            outcomes.append(response.status_code)
            if response.status_code == 200:
                self.assertEqual(await self.ok("PUT", path, actor, key=key, json=body), response.json())
        self.assertEqual(sorted(outcomes), [200, 409])
        self.assertEqual((await self.ok("GET", path))["revision"], 1)
        self.assertEqual(self.balances("a"), [80, 0])
        self.assertEqual(len(self.financial_snapshot("a")["movement_receipts"]), 1)

    async def test_recurring_links_invalidate_ordinary_draft(self):
        path, source = await self.stale_transaction_fixture()
        original = {"name": source["name"], "type": "expense", "amount": 10, "expected_revision": 0}
        before_b = self.financial_snapshot("b")
        for remove_schedule, start_revision in ((False, 0), (True, 2)):
            schedule = await self.ok("POST", "/recurring-payments", json={
                "name": "Synthetic tracking", "amount": 10, "start_date": "2020-01-02",
                "frequency": "monthly", "account_id": self.accounts["a"][0],
            })
            schedule_path = f"/recurring-payments/{schedule['id']}"
            payment_path = f"{schedule_path}/payments"
            payload = {"due_date": "2020-01-02", "mode": "link", "transaction_id": source["id"]}
            receipt = await self.ok("POST", payment_path, key="link", json=payload)
            self.assertEqual(await self.ok("POST", payment_path, key="link", json=payload), receipt)
            self.assertEqual((await self.ok("GET", path))["revision"], start_revision + 1)
            delete_path = schedule_path if remove_schedule else f"/recurring-payments/payments/{receipt['id']}"
            await self.ok("DELETE", delete_path)
            again = await self.call("DELETE", delete_path)
            self.assertIn(again.status_code, (200, 404))
            record = await self.ok("GET", path)
            self.assertEqual(record["revision"], start_revision + 2)
            self.assertNotIn("recurring_record_id", record)
            self.assertEqual((await self.call("PUT", path, json=original)).status_code, 409)
            await self.assert_characterized_edit(path, record, 10, source["account_id"], [90, 0])
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_bill_and_goal_unlinks_advance_once_without_financial_effect(self):
        before_b = self.financial_snapshot("b")
        source, target = self.accounts["a"]
        schedule = await self.ok("POST", "/recurring-payments", json={
            "name": "Synthetic recurring bill", "amount": 20, "start_date": "2026-11-04",
            "frequency": "monthly", "account_id": source,
        })
        bill = await self.ok("POST", "/bills", json={
            "name": "Synthetic bill", "amount": 20, "due_date": "2026-11-04",
            "frequency": "monthly", "account_id": source, "recurring_payment_id": schedule["id"],
        })
        payment = await self.ok("POST", f"/bills/{bill['id']}/payments", key="bill", json={
            "account_id": source, "amount": 20,
        })
        goal = await self.ok("POST", "/goals", json={
            "name": "Synthetic goal", "target_amount": 20, "account_id": target,
        })
        contribution = await self.ok("POST", f"/goals/{goal['id']}/contributions", key="deposit", json={
            "kind": "deposit", "amount": 20, "account_id": source, "real_movement": True,
        })
        self.assertEqual(self.balances("a"), [60, 20])
        for path, movement_id, removed in (
            (f"/bills/{bill['id']}", payment["transaction_id"], ("bill_id", "bill_payment_id")),
            (f"/goals/{goal['id']}", contribution["contribution"]["transaction_id"], ("goal_id", "goal_contribution_id")),
        ):
            movement_path = f"/transactions/{movement_id}"
            original = await self.ok("GET", movement_path)
            self.assertTrue(all(original.get(field) for field in removed))
            await self.ok("DELETE", path)
            repeat = await self.call("DELETE", path)
            self.assertIn(repeat.status_code, (200, 404))
            expected = {k: v for k, v in original.items() if k not in removed}
            expected["revision"] += 1
            self.assertEqual(await self.ok("GET", movement_path), expected)
            self.assertEqual(self.balances("a"), [60, 20])
        self.assert_reconciled("a")
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_linked_debt_payment_edit_keeps_existing_contract(self):
        before_b = self.financial_snapshot("b")
        payload = await self.partial_debt_fixture(10)
        payment = await self.ok("POST", "/debt-payments", key="linked-edit", json=payload)
        path = f"/transactions/{payment['transaction_id']}"
        await self.ok("PUT", path, json={
            "name": "Updated linked payment", "type": "debt_payment", "amount": 12,
        })
        self.assert_debt_payment_state(payload, 12)
        self.assertEqual(self.financial_snapshot("b"), before_b)

    async def test_commit_before_revocation_keeps_one_transfer_and_blocks_next_write(self):
        entered, resume = asyncio.Event(), asyncio.Event()

        async def pause(_):
            entered.set()
            await resume.wait()

        self.fence.after = pause
        request = asyncio.create_task(self.call(
            "POST", "/transactions", key="already-fenced", json=self.transfer("a")
        ))
        await asyncio.wait_for(entered.wait(), 5)
        revoking = asyncio.create_task(asyncio.to_thread(
            retry_auth, self.auth.logout, self.tokens["a"].access
        ))
        try:
            await asyncio.sleep(0.015)
        finally:
            resume.set()
        self.assertEqual((await asyncio.wait_for(request, 5)).status_code, 200)
        await asyncio.wait_for(revoking, 5)
        self.fence.after = None
        self.assertEqual((await self.call("POST", "/transactions", json=self.transfer("a"))).status_code, 401)
        scope = {"user_id": self.owner["a"]}
        self.assertTrue(self.db.auth_sessions.find_one(scope)["revoked"])
        self.assertEqual(self.db.transactions.count_documents(scope), 1)
        self.assertEqual(self.db.movement_receipts.count_documents(scope), 1)
        self.assert_reconciled("a")
