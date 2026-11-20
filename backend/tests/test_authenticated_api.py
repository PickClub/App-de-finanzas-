"""ASGI boundary tests with synthetic credentials and records only."""
import ast
from contextlib import asynccontextmanager
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import re
from bson.decimal128 import Decimal128
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

import httpx

from backend.auth_core import AuthService, InvalidCredentials
from backend.authenticated_api import create_authenticated_app
from backend.tests.test_auth_core import Delivery, MemoryStore, PASSWORD
from backend.tests.test_payment_consistency import matches


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def matching(self, filters):
        return [row for row in self.rows if matches(row, filters)]

    def find(self, filters, projection=None, *, session=None):
        return Cursor(deepcopy(self.matching(filters)))

    def aggregate(self, pipeline, **options):
        rows = self.matching(pipeline[0]["$match"])
        if pipeline[1]["$group"]["_id"] == "$kind":
            totals = {}
            for row in rows:
                kind = row["kind"]
                totals[kind] = totals.get(kind, Decimal(0)) + Decimal(str(row["amount"]))
            return Cursor([{"_id": kind, "s": Decimal128(amount)}
                           for kind, amount in totals.items()])
        ids = [row["id"] for row in rows]
        return Cursor([{"duplicate": True}] if len(ids) != len(set(ids)) else [])

    async def count_documents(self, filters, *, session=None):
        return len(self.matching(filters))

    async def update_one(self, filters, changes, *, session):
        record = await self.find_one(filters)
        if record is not None:
            record.update(changes.get("$set", {}))
            for field, value in changes.get("$inc", {}).items():
                record[field] = record.get(field, 0) + value
            for field in changes.get("$unset", {}):
                record.pop(field, None)
        return SimpleNamespace(matched_count=int(record is not None))

    async def find_one(self, filters, projection=None, *, session=None):
        return next(iter(self.matching(filters)), None)

    async def insert_one(self, row, *, session):
        self.rows.append(deepcopy(row))

    async def find_one_and_update(self, filters, changes, *, return_document, session, projection=None):
        await self.update_one(filters, changes, session=session)
        return await self.find_one(filters, projection, session=session)

    async def update_many(self, filters, changes, *, session):
        for row in self.matching(filters):
            row.update(changes.get("$set", {}))
            for field in changes.get("$unset", {}):
                row.pop(field, None)

    async def delete_one(self, filters, *, session):
        rows = self.matching(filters)
        for row in rows:
            self.rows.remove(row)
        return SimpleNamespace(deleted_count=len(rows))


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, sort, direction=None):
        if direction is not None:
            sort = [(sort, direction)]
        for field, direction in reversed(sort):
            self.rows.sort(key=lambda row: row[field], reverse=direction < 0)
        return self

    def skip(self, offset):
        self.rows = self.rows[offset:]
        return self

    def limit(self, size):
        self.rows = self.rows[:size]
        return self

    def max_time_ms(self, milliseconds):
        return self

    def batch_size(self, size):
        return self

    async def close(self):
        pass

    async def __aiter__(self):
        for row in self.rows:
            yield row

    async def to_list(self, limit):
        return self.rows[:limit]


class AuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemoryStore()
        self.now = datetime.now(timezone.utc)
        self.fence_rejects = False
        delivery = Delivery()
        operator = object()
        self.auth = AuthService(self.store, delivery, lambda actor: actor is operator,
                                lambda: self.now)
        self.tokens = {}
        self.owners = {}
        for name in ("a", "b"):
            email = f"{name}@example.com"
            self.auth.invite(operator, email)
            self.auth.accept_invitation(delivery.messages[-1][2], PASSWORD)
            tokens = self.auth.login(email, PASSWORD)
            self.tokens[name] = tokens.access
            self.owners[name] = self.auth.authenticate(tokens.access).user_id

        rows = [
            {"id": name, "user_id": owner, "balance": 100, "date": "2026-11-04"}
            for name, owner in {**self.owners, "legacy": "default-user"}.items()
        ]
        self.database = SimpleNamespace(
            accounts=Collection(deepcopy(rows)), transactions=Collection(deepcopy(rows)),
            categories=Collection(), debts=Collection(), notes=Collection(),
            moneyflow_metadata=Collection([{
                "_id": "financial-context", "version": 1,
                "environment_id": self.owners["a"], "created_at": self.now.isoformat(),
            }]),
        )
        for name in ("movement_receipts", "recurring_templates", "bill_payments",
                     "recurring_payment_records", "goal_contributions", "debt_payments",
                     "bills", "recurring_payments", "shared_obligations", "budgets", "saving_goals", "users"):
            setattr(self.database, name, Collection())
        self.app = create_authenticated_app(
            self.auth, self.database, expected_environment_id=self.owners["a"],
            write_fence=self.write_fence,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://offline.invalid"
        )
        self.addAsyncCleanup(self.client.aclose)

    @asynccontextmanager
    async def write_fence(self, principal):
        if self.fence_rejects:
            raise InvalidCredentials("Invalid credentials")
        snapshots = {name: deepcopy(collection.rows)
                     for name, collection in vars(self.database).items()}
        try:
            yield SimpleNamespace(in_transaction=True)
        except BaseException:
            for name, rows in snapshots.items():
                getattr(self.database, name).rows = rows
            raise

    async def call(self, method, path, actor="a", **kwargs):
        headers = {"X-User-Id": self.owners["b"], **kwargs.pop("headers", {})}
        if actor:
            headers["Authorization"] = f"Bearer {self.tokens[actor]}"
        return await self.client.request(method, "/api" + path, headers=headers, **kwargs)

    async def test_scoped_reads_context_and_legacy(self):
        for own, other in (("a", "b"), ("b", "a")):
            for path in ("/accounts", "/transactions"):
                response = await self.call("GET", path, own)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.json()], [own])
            for foreign in (other, "legacy"):
                response = await self.call("GET", f"/transactions/{foreign}", own)
                self.assertEqual(response.status_code, 404)
            context = (await self.call("GET", "/financial-context", own)).json()
            self.assertEqual(context["mode"], "authenticated_user")
            self.assertEqual(context["user_id"], self.owners[own])
            self.assertFalse(any(context["capabilities"].values()))

    async def test_financial_mutations_and_aggregates_fail_closed(self):
        before = deepcopy(self.database.accounts.rows + self.database.transactions.rows)
        for method, path in (
            ("POST", "/seed"),
            ("GET", "/export"),
        ):
            response = await self.call(method, path, json={
                "type": "transfer", "account_id": "a", "destination_account_id": "b",
            })
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.database.accounts.rows + self.database.transactions.rows, before)

    async def test_notes_crud_and_owner_injection(self):
        data = {"title": "A", "content": "[x] first\n[ ] second", "color": "#126046",
                "listMode": "check", "palette": "green"}
        response = await self.call("POST", "/notes", json=data)
        self.assertEqual(response.status_code, 201)
        note = response.json()
        self.assertEqual(note["content"], data["content"])
        self.assertNotIn("user_id", note)
        path = f"/notes/{note['id']}"
        for method in ("GET", "PUT", "DELETE"):
            self.assertEqual((await self.call(method, path, "b", json=data)).status_code, 404)
        self.assertEqual((await self.call("GET", "/notes", "b")).json(), [])
        self.assertEqual((await self.call("PUT", path, json={
            **data, "user_id": self.owners["b"],
        })).status_code, 422)
        self.assertEqual((await self.call("GET", path)).json(), note)
        update = await self.call("PUT", path, json={**data, "pinned": True})
        self.assertTrue(update.json()["pinned"])
        self.assertEqual((await self.call("DELETE", path)).status_code, 204)
        self.assertEqual((await self.call("GET", path)).status_code, 404)

    async def test_expiry_revocation_and_storage_failure(self):
        for path in ("/accounts", "/notes", "/summary"):
            response = await self.call("GET", path, None)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.auth.logout(self.tokens["a"])
        self.assertEqual((await self.call("GET", "/accounts")).status_code, 401)
        self.store.fail_commit = True
        self.assertEqual((await self.call("GET", "/accounts", "b")).status_code, 503)
        self.store.fail_commit = False
        self.now += timedelta(minutes=10)
        self.assertEqual((await self.call("GET", "/accounts", "b")).status_code, 401)

    async def test_rejected_write_fence_produces_no_note(self):
        self.fence_rejects = True
        response = await self.call("POST", "/notes", json={
            "title": "A", "content": "Draft", "color": "#126046",
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.database.notes.rows, [])

    async def test_account_writes_and_balances_are_owner_scoped(self):
        for name in ("debt_payments", "recurring_templates", "bills", "recurring_payments",
                     "saving_goals", "goal_contributions", "bill_payments", "recurring_payment_records"):
            setattr(self.database, name, Collection())
        data = {"name": "New account", "initial_balance": 20}
        before = deepcopy(self.database.accounts.rows)
        for actor, target in (("a", "b"), ("b", "a"), ("a", "legacy")):
            for method in ("PUT", "DELETE"):
                result = await self.call(method, f"/accounts/{target}", actor, json=data)
                self.assertEqual(result.status_code, 404)
        self.assertEqual(self.database.accounts.rows, before)
        result = await self.call("POST", "/accounts", json=data)
        self.assertEqual(result.status_code, 200)
        account_id = result.json()["id"]
        self.assertEqual(result.json()["user_id"], self.owners["a"])
        self.database.transactions.rows.extend([
            {"id": "income-a", "type": "income", "amount": 10,
             "account_id": account_id, "user_id": self.owners["a"]},
            {"id": "income-b", "type": "income", "amount": 1000,
             "account_id": account_id, "user_id": self.owners["b"]},
        ])
        for row in self.database.transactions.rows[:3]:
            row.update(type="income", amount=1)
        result = await self.call("PUT", f"/accounts/{account_id}", json=data)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["current_balance"], 30)
        self.assertEqual((await self.call("DELETE", f"/accounts/{account_id}")).status_code, 409)
        self.database.transactions.rows = self.database.transactions.rows[:3]
        self.assertEqual((await self.call("DELETE", f"/accounts/{account_id}")).status_code, 200)

    async def test_history_cursor_and_totals_do_not_cross_users(self):
        self.database.transactions.rows.append({
            "id": "second-a", "user_id": self.owners["a"], "date": "2026-11-05",
        })
        result = await self.call("GET", "/transactions/page?limit=1")
        self.assertEqual(result.status_code, 200)
        page = result.json()
        self.assertEqual(page["total"], 2)
        self.assertEqual([item["id"] for item in page["items"]], ["second-a"])
        cursor = page["next_cursor"]
        result = await self.call("GET", "/transactions/page", params={"cursor": cursor})
        self.assertEqual([item["id"] for item in result.json()["items"]], ["a"])
        self.assertEqual((await self.call(
            "GET", "/transactions/page", "b", params={"cursor": cursor}
        )).status_code, 422)
        self.assertEqual((await self.call(
            "GET", "/transactions/page", params={"account_id": "b"}
        )).status_code, 404)

    async def test_transfer_requires_two_owned_accounts(self):
        data = {"name": "Transfer", "amount": 10, "type": "transfer",
                "account_id": "a", "to_account_id": "b"}
        before = deepcopy(self.database.accounts.rows + self.database.transactions.rows)
        for actor in ("a", "b"):
            response = await self.call("POST", "/transactions", actor, json=data)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.database.accounts.rows + self.database.transactions.rows, before)
        for row in self.database.transactions.rows:
            row.update(type="income", amount=0)
        for row in self.database.accounts.rows:
            row["initial_balance"] = 100
        self.database.accounts.rows.append({
            "id": "destination-a", "initial_balance": 50, "user_id": self.owners["a"],
        })
        response = await self.call("POST", "/transactions", json={
            **data, "to_account_id": "a",
        })
        self.assertEqual(response.status_code, 422)
        response = await self.call("POST", "/transactions", json={
            **data, "to_account_id": "destination-a",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], self.owners["a"])
        self.assertEqual(self.database.accounts.rows[0]["current_balance"], 90)
        self.assertEqual(self.database.accounts.rows[-1]["current_balance"], 60)
        self.assertEqual(self.database.accounts.rows[1]["balance"], 100)

    async def test_movement_lifecycle_and_owner_receipts(self):
        for row in self.database.accounts.rows:
            row.update(initial_balance=100, current_balance=100)
        self.database.transactions.rows.clear()
        create_key = {"Idempotency-Key": "same-create"}
        edit_key = {"Idempotency-Key": "same-edit"}
        delete_key = {"Idempotency-Key": "same-delete"}
        ids = {}
        for actor in ("a", "b"):
            payload = {"name": "Expense", "type": "expense", "amount": 10, "account_id": actor}
            created = await self.call("POST", "/transactions", actor, json=payload, headers=create_key)
            self.assertEqual(created.status_code, 200, created.text)
            ids[actor] = created.json()["id"]
            replay = await self.call("POST", "/transactions", actor, json=payload, headers=create_key)
            self.assertEqual(replay.json(), created.json())
            conflict = await self.call("POST", "/transactions", actor,
                                       json={**payload, "amount": 99}, headers=create_key)
            self.assertEqual(conflict.status_code, 409)
            path = f"/transactions/{ids[actor]}"
            self.assertEqual((await self.call("PUT", path, actor, json=payload,
                                              headers=create_key)).status_code, 409)
            edited = await self.call("PUT", path, actor, json={**payload, "amount": 25, "expected_revision": 0},
                                     headers=edit_key)
            self.assertEqual(edited.status_code, 200, edited.text)
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"], 75)
        self.assertNotEqual(ids["a"], ids["b"])
        before = deepcopy(self.database.transactions.rows)
        for actor, other in (("a", "b"), ("b", "a")):
            path = f"/transactions/{ids[other]}"
            data = {"name": "Expense", "type": "expense", "amount": 50, "account_id": actor}
            self.assertEqual((await self.call("PUT", path, actor, json=data)).status_code, 404)
            self.assertEqual((await self.call("DELETE", path, actor)).status_code, 404)
        self.assertEqual(self.database.transactions.rows, before)
        for actor in ("a", "b"):
            path = f"/transactions/{ids[actor]}"
            for _ in range(2):
                self.assertEqual((await self.call("DELETE", path, actor,
                                                  headers=delete_key)).status_code, 200)
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"], 100)
        self.assertEqual(len(self.database.movement_receipts.rows), 6)
        self.auth.logout(self.tokens["a"])
        self.assertEqual((await self.call("DELETE", f"/transactions/{ids['a']}",
                                          headers=delete_key)).status_code, 401)

    async def test_transfer_edit_and_delete_reverse_both_sides(self):
        for row in self.database.accounts.rows:
            row.update(initial_balance=100, current_balance=100)
        self.database.accounts.rows.append({
            "id": "target", "user_id": self.owners["a"], "initial_balance": 50, "current_balance": 50,
        })
        self.database.transactions.rows.clear()
        payload = {"name": "Transfer", "type": "transfer", "amount": 10,
                   "account_id": "a", "to_account_id": "target"}
        result = await self.call("POST", "/transactions", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        path = f"/transactions/{result.json()['id']}"
        references = await self.call("GET", path + "/references")
        self.assertEqual(references.json()["to_account_id"]["id"], "target")
        self.assertEqual((await self.call("GET", path + "/references", "b")).status_code, 404)
        before = deepcopy(self.database.accounts.rows)
        self.assertEqual((await self.call("PUT", path, json={
            **payload, "to_account_id": "b", "expected_revision": 0,
        })).status_code, 404)
        self.assertEqual(self.database.accounts.rows, before)
        edited = await self.call("PUT", path, json={**payload, "amount": 30, "expected_revision": 0})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual([row["current_balance"] for row in self.database.accounts.rows],
                         [70, 100, 100, 80])
        self.assertEqual((await self.call("DELETE", path)).status_code, 200)
        self.assertEqual([row["current_balance"] for row in self.database.accounts.rows],
                         [100, 100, 100, 50])

    async def test_debt_payment_lifecycle_is_scoped_and_reversible(self):
        for row in self.database.accounts.rows:
            row.update(initial_balance=100, current_balance=100)
        self.database.transactions.rows.clear()
        self.database.debts.rows.append({"id": "legacy", "user_id": "default-user"})
        obligations = {}
        for actor, direction in (("a", "i_owe"), ("b", "they_owe")):
            result = await self.call("POST", "/debts", actor, json={
                "name": "Synthetic loan", "direction": direction, "original_amount": 40,
                "account_id": actor, "due_date": "2027-02-01", "minimum_payment": 5,
            })
            self.assertEqual(result.status_code, 200, result.text)
            obligations[actor] = result.json()["id"]
        for actor, direction in (("a", "i_owe"), ("b", "they_owe")):
            summary = await self.call("GET", "/summary", actor)
            self.assertEqual(summary.status_code, 200, summary.text)
            totals = summary.json()["debts"]
            self.assertEqual(totals[direction], 40)
            self.assertEqual(totals["they_owe" if actor == "a" else "i_owe"], 0)
            if actor == "a":
                self.assertEqual(totals["next_payment"]["amount"], 5)
            else:
                self.assertIsNone(totals["next_payment"])
        receipts = {}
        header = {"Idempotency-Key": "same-payment"}
        for actor, other in (("a", "b"), ("b", "a")):
            did = obligations[actor]
            path = f"/debts/{did}"
            self.assertEqual((await self.call("GET", path, other)).status_code, 404)
            self.assertEqual((await self.call("GET", path + "/payments", other)).status_code, 404)
            self.assertEqual((await self.call("DELETE", path, other)).status_code, 404)
            self.assertEqual((await self.call("GET", "/debts/legacy", actor)).status_code, 404)
            edited = await self.call("PUT", path, actor, json={
                "name": "Updated", "direction": "i_owe" if actor == "a" else "they_owe",
                "original_amount": 40,
            })
            self.assertEqual(edited.status_code, 200, edited.text)
            payload = {"debt_id": did, "account_id": actor, "amount": 10, "settlement_source": "account"}
            before = deepcopy(self.database.accounts.rows)
            for invalid in ({**payload, "account_id": other}, {**payload, "debt_id": obligations[other]}):
                result = await self.call("POST", "/debt-payments", actor, json=invalid, headers=header)
                self.assertEqual(result.status_code, 404, result.text)
            self.assertEqual(self.database.accounts.rows, before)
            result = await self.call("POST", "/debt-payments", actor, json=payload, headers=header)
            self.assertEqual(result.status_code, 200, result.text)
            payment = receipts[actor] = result.json()
            replay = await self.call("POST", "/debt-payments", actor, json=payload, headers=header)
            self.assertEqual(replay.json(), payment)
            conflict = await self.call("POST", "/debt-payments", actor,
                                       json={**payload, "amount": 11}, headers=header)
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual((await self.call("GET", path, actor)).json()["remaining_amount"], 30)
            self.assertEqual((await self.call("DELETE", path, actor)).status_code, 409)
            movement_path = f"/transactions/{payment['transaction_id']}"
            result = await self.call("PUT", movement_path, actor, json={
                "name": "Settlement", "type": "debt_payment" if actor == "a" else "income",
                "amount": 40,
            })
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual((await self.call("GET", path, actor)).json()["status"], "paid")
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"],
                             60 if actor == "a" else 140)
            payment_path = f"/debt-payments/{payment['id']}"
            self.assertEqual((await self.call("DELETE", payment_path, other)).status_code, 404)
            cancelled = await self.call("DELETE", payment_path, actor, headers=header)
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual((await self.call("DELETE", payment_path, actor, headers=header)).status_code, 200)
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"], 100)
            self.assertEqual((await self.call("GET", path, actor)).json()["remaining_amount"], 40)
            self.assertEqual((await self.call("GET", path + "/payments", actor)).json(), [])
            self.assertEqual((await self.call("GET", movement_path, actor)).status_code, 404)
            self.assertEqual((await self.call("POST", "/debt-payments", actor, json=payload,
                                              headers=header)).status_code, 409)
            result = await self.call("POST", "/debt-payments/reconcile", actor,
                                     json=payload, headers=header)
            self.assertEqual(result.json()["status"], "cancelled")
            self.assertEqual((await self.call("DELETE", path, actor)).status_code, 200)
        self.assertNotEqual(receipts["a"]["id"], receipts["b"]["id"])
        self.assertEqual(self.database.debts.rows, [{"id": "legacy", "user_id": "default-user"}])
        self.auth.logout(self.tokens["a"])
        self.assertEqual((await self.call("POST", "/debt-payments", json={
            "debt_id": obligations["a"], "amount": 10,
        })).status_code, 401)

    async def test_bill_and_recurring_owner_scoped_settlement(self):
        self.database.transactions.rows.clear()
        for row in self.database.accounts.rows:
            row.update(initial_balance=100, current_balance=100)
        key = {"Idempotency-Key": "same"}
        resources = {}
        for actor in ("a", "b"):
            rp_input = {"name": "Subscription", "amount": 40, "frequency": "monthly",
                        "start_date": "2026-10-10", "account_id": actor}
            result = await self.call("POST", "/recurring-payments", actor,
                                     json=rp_input, headers=key)
            self.assertEqual(result.status_code, 200, result.text)
            rid = result.json()["id"]
            bill_input = {"name": "October", "amount": 40, "due_date": "2026-10-10",
                          "frequency": "monthly", "account_id": actor,
                          "recurring_payment_id": rid}
            result = await self.call("POST", "/bills", actor, json=bill_input, headers=key)
            self.assertEqual(result.status_code, 200, result.text)
            resources[actor] = (rid, result.json()["id"], rp_input, bill_input)
        for actor, other in (("a", "b"), ("b", "a")):
            rid, bid, rp_input, bill_input = resources[actor]
            rpath, bpath = f"/recurring-payments/{rid}", f"/bills/{bid}"
            self.assertEqual((await self.call("GET", bpath, other)).status_code, 404)
            self.assertEqual((await self.call("PUT", rpath, other, json=rp_input)).status_code, 404)
            self.assertEqual((await self.call("PUT", bpath, actor, json={
                **bill_input, "recurring_payment_id": resources[other][0],
            })).status_code, 404)
            self.assertEqual((await self.call("PUT", rpath, actor, json=rp_input)).status_code, 200)
            self.assertEqual((await self.call("PUT", bpath, actor, json=bill_input)).status_code, 200)
            self.assertEqual((await self.call("GET", bpath, actor)).json()["status"], "overdue")
            for who, account in ((other, other), (actor, other)):
                self.assertEqual((await self.call("POST", bpath + "/payments", who, json={
                    "account_id": account, "amount": 15,
                })).status_code, 404)
            payment = {"account_id": actor, "amount": 15, "date": "2026-10-10"}
            result = await self.call("POST", bpath + "/payments", actor, json=payment, headers=key)
            self.assertEqual(result.status_code, 200, result.text)
            pid = result.json()["id"]
            replay = await self.call("POST", bpath + "/payments", actor, json=payment, headers=key)
            self.assertEqual(replay.json()["id"], pid)
            detail = (await self.call("GET", bpath, actor)).json()
            self.assertTrue(detail["partial"])
            self.assertEqual(detail["remaining"], 25)
            self.assertEqual((await self.call("POST", rpath + "/payments", actor, json={
                "due_date": "2026-10-10", "mode": "expense", "amount": 25, "account_id": actor,
            })).status_code, 409)
            self.assertEqual(len(self.database.transactions.matching({"user_id": self.owners[actor]})), 1)
            self.assertEqual(len(self.database.recurring_payment_records.matching(
                {"user_id": self.owners[actor]})), 1)
            result = await self.call("POST", bpath + "/payments", actor, json={
                "account_id": actor, "amount": 25, "date": "2026-10-10",
            }, headers={"Idempotency-Key": "complete"})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()["next_bill_id"])
            self.assertEqual((await self.call("GET", bpath, actor)).json()["status"], "paid")
            calendar = await self.call("GET", "/calendar/summary?year=2026&month=10", actor)
            self.assertEqual(calendar.status_code, 200, calendar.text)
            self.assertEqual(calendar.json()["payments"], {"amount": 40, "count": 2})
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"], 60)
            result = await self.call("DELETE", f"/bills/payments/{pid}", actor)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"], 75)
            self.assertEqual((await self.call("POST", bpath + "/payments", actor,
                                              json=payment, headers=key)).status_code, 409)
            self.assertEqual((await self.call("DELETE", bpath, actor)).status_code, 200)
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"], 75)
            self.assertEqual(len(self.database.transactions.matching({"user_id": self.owners[actor]})), 1)
            self.assertEqual((await self.call("DELETE", rpath, actor)).status_code, 200)

    async def test_standalone_recurring_states_and_expense_reversal(self):
        self.database.transactions.rows.clear()
        for row in self.database.accounts.rows:
            row.update(initial_balance=100, current_balance=100)
        payload = {"name": "Standalone", "amount": 20, "start_date": "2026-10-10",
                   "frequency": "monthly", "account_id": "a"}
        created = await self.call("POST", "/recurring-payments", json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        rid = created.json()["id"]
        path = f"/recurring-payments/{rid}"
        self.assertEqual((await self.call("POST", path + "/pause", "b")).status_code, 404)
        self.assertEqual((await self.call("POST", path + "/pause")).json()["state"], "paused")
        self.assertEqual((await self.call("POST", path + "/resume")).json()["state"], "active")
        self.assertEqual((await self.call("GET", path + "/occurrences")).status_code, 200)
        self.assertEqual((await self.call("GET", path + "/occurrences", "b")).status_code, 404)
        self.assertEqual((await self.call("GET", "/recurring-payments/overview", "b")).json()["items"], [])
        body = {"due_date": "2026-10-10", "mode": "expense", "amount": 20, "account_id": "a"}
        key = {"Idempotency-Key": "standalone"}
        response = await self.call("POST", path + "/payments", json=body, headers=key)
        self.assertEqual(response.status_code, 200, response.text)
        pid = response.json()["id"]
        replay = await self.call("POST", path + "/payments", json=body, headers=key)
        self.assertEqual(replay.json()["id"], pid)
        self.assertEqual(len(self.database.transactions.rows), 1)
        self.assertEqual(self.database.accounts.rows[0]["current_balance"], 80)
        remove = f"/recurring-payments/payments/{pid}"
        self.assertEqual((await self.call("DELETE", remove, "b")).status_code, 404)
        self.assertEqual((await self.call("DELETE", remove)).status_code, 200)
        self.assertEqual(self.database.accounts.rows[0]["current_balance"], 100)
        self.assertEqual(self.database.transactions.rows, [])
        self.assertEqual((await self.call("POST", path + "/payments",
                                          json=body, headers=key)).status_code, 409)
        self.assertEqual((await self.call("POST", path + "/end")).json()["state"], "ended")
        self.auth.logout(self.tokens["a"])
        self.assertEqual((await self.call("DELETE", path)).status_code, 401)

    async def test_budget_period_and_calendar_totals_are_owner_scoped(self):
        for actor in ("a", "b"):
            self.database.categories.rows.append({
                "id": f"cat-{actor}", "user_id": self.owners[actor],
                "name": "Food", "type": "expense",
            })
        self.database.transactions.rows = [
            {"id": label, "user_id": owner, "category_id": category,
             "name": label, "type": kind, "date": day, "amount": amount}
            for label, owner, category, kind, day, amount in (
                ("a-expense", self.owners["a"], "cat-a", "expense", "2026-10-10", 15),
                ("a-outside", self.owners["a"], "cat-a", "expense", "2026-11-01", 50),
                ("a-debt", self.owners["a"], None, "debt_payment", "2026-10-11", 7),
                ("b-expense", self.owners["b"], "cat-a", "expense", "2026-10-10", 999),
                ("legacy", "default-user", "cat-a", "expense", "2026-10-10", 999),
            )
        ]
        body = {"category_id": "cat-a", "amount_limit": 100, "period": "custom",
                "start_date": "2026-10-01", "end_date": "2026-10-31"}
        key = {"Idempotency-Key": "same-budget"}
        self.assertEqual((await self.call("POST", "/budgets", "b", json=body)).status_code, 404)
        for actor in ("a", "b"):
            data = {**body, "category_id": f"cat-{actor}"}
            result = await self.call("POST", "/budgets", actor, json=data, headers=key)
            self.assertEqual(result.status_code, 200, result.text)
            path = f"/budgets/{result.json()['id']}"
            replay = await self.call("POST", "/budgets", actor, json=data, headers=key)
            self.assertEqual(replay.json()["id"], result.json()["id"])
            other = "b" if actor == "a" else "a"
            self.assertEqual((await self.call("GET", path + "/detail", other)).status_code, 404)
            self.assertEqual((await self.call("DELETE", path, other)).status_code, 404)
            self.assertEqual((await self.call("PUT", path, actor, json={
                **data, "amount_limit": 120,
            })).status_code, 200)
            summary = await self.call("GET", "/budgets/overview?year=2026&month=10", actor)
            self.assertEqual(summary.status_code, 200, summary.text)
            self.assertEqual(summary.json()["totals"]["spent"], 15 if actor == "a" else 0)
            detail = await self.call("GET", path + "/detail?year=2026&month=10", actor)
            self.assertEqual(detail.json()["spent"], 15 if actor == "a" else 0)
            self.assertEqual((await self.call("DELETE", path, actor)).status_code, 200)
        calendar = await self.call("GET", "/calendar/summary?year=2026&month=10")
        self.assertEqual(calendar.status_code, 200, calendar.text)
        self.assertEqual(calendar.json()["payments"], {"amount": 22, "count": 2})
        events = await self.call("GET", "/calendar/events?start=2026-10-01&end=2026-10-31")
        self.assertEqual(len(events.json()["events"]), 2)
        self.assertEqual((await self.call("GET", "/calendar/upcoming", None)).status_code, 401)

    async def test_goal_transfer_lifecycle_and_receipts_are_owner_scoped(self):
        self.database.transactions.rows.clear()
        for row in self.database.accounts.rows:
            row.update(initial_balance=100, current_balance=100)
        goals = {}
        for actor in ("a", "b"):
            target = f"target-{actor}"
            self.database.accounts.rows.append({
                "id": target, "user_id": self.owners[actor],
                "initial_balance": 0, "current_balance": 0, "name": target,
            })
            payload = {"name": "Goal", "target_amount": 30, "account_id": target}
            result = await self.call("POST", "/goals", actor, json=payload,
                                     headers={"Idempotency-Key": "same-goal"})
            self.assertEqual(result.status_code, 200, result.text)
            goals[actor] = (f"/goals/{result.json()['id']}", payload)
        for actor, other in (("a", "b"), ("b", "a")):
            path, goal = goals[actor]
            self.assertEqual((await self.call("GET", path, other)).status_code, 404)
            self.assertEqual((await self.call("PUT", path, other, json=goal)).status_code, 404)
            self.assertEqual((await self.call("PUT", path, actor, json=goal)).status_code, 200)
            contributions = path + "/contributions"
            body = {"kind": "deposit", "amount": 30, "account_id": actor, "real_movement": True}
            before = deepcopy(self.database.accounts.rows)
            for who, data in ((other, body), (actor, {**body, "account_id": other})):
                denied = await self.call("POST", contributions, who, json=data)
                self.assertEqual(denied.status_code, 404)
            self.assertEqual(self.database.accounts.rows, before)
            key = {"Idempotency-Key": "same-contribution"}
            result = await self.call("POST", contributions, actor, json=body, headers=key)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()["goal"]["completed"])
            replay = await self.call("POST", contributions, actor, json=body, headers=key)
            self.assertEqual(replay.json()["contribution"]["id"], result.json()["contribution"]["id"])
            withdrawal = await self.call("POST", contributions, actor, json={
                **body, "kind": "withdrawal", "amount": 10,
            })
            self.assertEqual(withdrawal.status_code, 200, withdrawal.text)
            self.assertFalse(withdrawal.json()["goal"]["completed"])
            self.assertEqual((await self.call("GET", contributions, actor)).json()["total"], 2)
            self.assertEqual((await self.call("GET", contributions, other)).status_code, 404)
            self.assertEqual(self.database.accounts.matching({"id": actor})[0]["current_balance"], 80)
            self.assertEqual(self.database.accounts.matching({"id": f"target-{actor}"})[0]["current_balance"], 20)
            self.assertEqual((await self.call("DELETE", path, actor)).status_code, 200)
            movements = self.database.transactions.matching({"user_id": self.owners[actor]})
            self.assertEqual(len(movements), 2)
            self.assertTrue(all("goal_id" not in movement for movement in movements))
        self.auth.logout(self.tokens["a"])
        self.assertEqual((await self.call("POST", "/goals", json=goals["a"][1])).status_code, 401)

    async def test_profile_does_not_provision_or_accept_identity_fields(self):
        self.database.users.rows.extend([
            {"id": self.owners[actor], "name": actor, "currency": "USD", "role": "internal"}
            for actor in ("a", "b")
        ])
        self.database.users.rows.append({"id": "default-user", "name": "Legacy"})
        profile = await self.call("GET", f"/user?id={self.owners['b']}")
        self.assertEqual(profile.json(), {"id": self.owners["a"], "name": "a", "currency": "USD"})
        before = deepcopy(self.database.users.rows)
        for field in ("id", "user_id", "role", "status", "email"):
            rejected = await self.call("PUT", "/user", json={field: self.owners["b"]})
            self.assertEqual(rejected.status_code, 422)
        self.assertEqual(self.database.users.rows, before)
        result = await self.call("PUT", f"/user?id={self.owners['b']}", json={"name": "New"})
        self.assertEqual(result.json()["name"], "New")
        self.assertEqual((await self.call("GET", "/user", "b")).json()["name"], "b")
        self.database.users.rows.pop(1)
        self.assertEqual((await self.call("GET", "/user", "b")).status_code, 404)
        self.assertEqual(self.database.users.rows[-1], {"id": "default-user", "name": "Legacy"})

    async def test_catalog_and_category_writes_are_owner_scoped(self):
        self.database.categories.rows.append({
            "id": "private", "user_id": "default-user", "type": "expense", "name": "Private",
        })
        for actor in ("a", "b"):
            first = await self.call("POST", "/categories/init-defaults", actor)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertGreater(first.json()["created"], 0)
            repeated = await self.call("POST", "/categories/init-defaults", actor)
            self.assertEqual(repeated.json()["total"], first.json()["total"])
            for field in ("created", "groups_created", "links"):
                self.assertEqual(repeated.json()[field], 0)
            listed = (await self.call("GET", "/categories", actor)).json()
            self.assertTrue(all(row["user_id"] == self.owners[actor] for row in listed))
            self.assertNotIn("Private", {row["name"] for row in listed})
        group = (await self.call("POST", "/categories", json={
            "name": "Own Group", "is_group": True,
        })).json()["id"]
        before = deepcopy(self.database.categories.rows)
        self.assertEqual((await self.call("POST", "/categories", "b", json={
            "name": "Foreign", "parent_id": group,
        })).status_code, 404)
        self.assertEqual((await self.call("PUT", f"/categories/{group}", "b", json={
            "name": "Foreign",
        })).status_code, 404)
        self.assertEqual((await self.call("DELETE", f"/categories/{group}", "b")).status_code, 404)
        self.assertEqual(self.database.categories.rows, before)
        child = (await self.call("POST", "/categories", json={
            "name": "Child", "parent_id": group,
        })).json()["id"]
        self.assertEqual((await self.call("PUT", f"/categories/{group}", json={
            "name": "Own Group", "parent_id": child,
        })).status_code, 409)
        self.assertEqual((await self.call("DELETE", f"/categories/{group}")).status_code, 409)
        self.database.budgets.rows.append({"user_id": self.owners["a"], "category_id": child})
        self.assertEqual((await self.call("DELETE", f"/categories/{child}")).status_code, 409)
        self.database.budgets.rows.clear()
        self.assertEqual((await self.call("DELETE", f"/categories/{child}")).status_code, 200)

    async def test_templates_are_configuration_only_and_seed_stays_excluded(self):
        original = deepcopy(self.database.transactions.rows)
        keys = {"Idempotency-Key": "same-template"}
        for actor, other in (("a", "b"), ("b", "a")):
            body = {"name": "Template", "amount": 10, "type": "expense",
                    "source_transaction_id": actor, "account_id": actor, "start_date": "2026-11-01"}
            denied = await self.call("POST", "/recurring", actor, json={**body, "source_transaction_id": other})
            self.assertEqual(denied.status_code, 404)
            result = await self.call("POST", "/recurring", actor, json=body, headers=keys)
            self.assertEqual(result.status_code, 200, result.text)
            rid = result.json()["id"]
            repeated = await self.call("POST", "/recurring", actor, json=body, headers=keys)
            self.assertEqual(repeated.json()["id"], rid)
            listed = (await self.call("GET", "/recurring", actor)).json()
            self.assertEqual([row["id"] for row in listed], [rid])
            self.assertEqual(listed[0]["start_date"], "2026-11-01")
            self.assertEqual((await self.call("DELETE", f"/recurring/{rid}", other)).status_code, 404)
            self.assertEqual((await self.call("DELETE", f"/recurring/{rid}", actor)).status_code, 200)
        for actual, expected in zip(self.database.transactions.rows, original, strict=True):
            self.assertEqual({k: v for k, v in actual.items() if k != "_reference_revision"}, expected)
        self.assertEqual(self.database.bills.rows + self.database.recurring_payment_records.rows, [])
        self.assertEqual((await self.call("POST", "/seed", "a")).status_code, 404)
        self.assertEqual((await self.call("POST", "/seed", None)).status_code, 401)
        self.auth.logout(self.tokens["a"])
        self.assertEqual((await self.call("POST", "/categories/init-defaults")).status_code, 401)

    async def test_legacy_inventory_requires_authentication_and_excludes_seed(self):
        source = Path(__file__).resolve().parents[1] / "server.py"
        methods = {"get", "post", "put", "delete"}
        legacy = {
            (decorator.func.attr.upper(), "/api" + decorator.args[0].value)
            for node in ast.parse(source.read_text()).body if isinstance(node, ast.AsyncFunctionDef)
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "api"
            and decorator.func.attr in methods
        } - {("GET", "/api/")}
        actual = {
            (method, route.path)
            for route in self.app.routes if "{unavailable:" not in route.path
            for method in route.methods
        }
        self.assertEqual(len(legacy), 72)
        self.assertEqual(legacy - actual, {("POST", "/api/seed")})
        for method, path in sorted(legacy):
            concrete = re.sub(r"\{[^}]+\}", "synthetic-id", path)
            response = await self.client.request(method, concrete)
            self.assertEqual(response.status_code, 401, (method, path, response.text))
