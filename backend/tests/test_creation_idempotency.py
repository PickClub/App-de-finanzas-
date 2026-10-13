"""R5: exact route AST, synthetic storage, no startup/dotenv/live MongoDB."""
import ast
from pathlib import Path
import unittest

from backend.tests import test_payment_consistency as memory
from backend.tests.test_reference_integrity import Database, context, ReferenceCases


class CreationCases:
    async def prepare(self):
        return await ReferenceCases.fixture(self)

    request = ReferenceCases.request
    snapshot = ReferenceCases.snapshot

    def payload(self, kind, fixture, amount=100):
        if kind == "budget":
            return dict(name="R5 synthetic", amount_limit=amount, category_id=fixture["category"], period="monthly")
        return dict(name="R5 synthetic", amount=amount, due_date="2026-10-20", frequency="once")

    async def create(self, kind, payload, key="original"):
        return await self.request("POST", "/budgets" if kind == "budget" else "/bills", payload, key)

    async def test_same_key_same_payload_no_write(self):
        f = await self.prepare()
        for kind in ("budget", "bill"):
            p = self.payload(kind, f)
            a = await self.create(kind, p)
            self.assertEqual(a.status_code, 200, a.text)
            before = await self.snapshot()
            b = await self.create(kind, p)
            self.assertEqual(b.status_code, 200, b.text)
            self.assertEqual(a.json(), b.json())
            self.assertEqual(await self.snapshot(), before)
            self.assertNotIn("request_fingerprint", b.text)

    async def test_changed_payload_rejected_without_writes(self):
        f = await self.prepare()
        for kind in ("budget", "bill"):
            p = self.payload(kind, f)
            a = await self.create(kind, p)
            self.assertEqual(a.status_code, 200, a.text)
            for changed in (self.payload(kind, f, 250), dict(p, name="Different")):
                before = await self.snapshot()
                b = await self.create(kind, changed)
                self.assertEqual(b.status_code, 409, b.text)
                self.assertEqual(await self.snapshot(), before)

    async def test_different_category_same_key_conflict(self):
        f = await self.prepare()
        await self.insert("categories", dict(id="other", user_id="default-user", name="Other", type="expense", is_group=False))
        for kind in ("budget", "bill"):
            p = dict(self.payload(kind, f), category_id=f["category"])
            self.assertEqual((await self.create(kind, p)).status_code, 200)
            before = await self.snapshot()
            r = await self.create(kind, dict(p, category_id="other"))
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.snapshot(), before)

    async def test_original_request_survives_edit(self):
        f = await self.prepare()
        for kind in ("budget", "bill"):
            p = self.payload(kind, f)
            a = await self.create(kind, p)
            path = ("/budgets/" if kind == "budget" else "/bills/") + a.json()["id"]
            edited = dict(p, name="Edited")
            r = await self.request("PUT", path, edited)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertNotIn("request_fingerprint", r.text)
            before = await self.snapshot()
            b = await self.create(kind, p)
            self.assertEqual(b.status_code, 200, b.text)
            self.assertEqual(b.json()["id"], a.json()["id"])
            self.assertEqual(b.json()["name"], "Edited")
            self.assertEqual((await self.create(kind, edited)).status_code, 409)
            self.assertEqual(await self.snapshot(), before)

    async def test_default_dates_are_not_new_intentions(self):
        f = await self.prepare()
        p = self.payload("budget", f)
        a = await self.create("budget", p)
        self.assertEqual(a.status_code, 200, a.text)
        before = await self.snapshot()
        self.ctx.ns["now_iso"] = lambda: "2030-01-01T00:00:00+00:00"
        b = await self.create("budget", p)
        self.assertEqual(a.json(), b.json())
        explicit = dict(p, start_date=a.json()["start_date"])
        self.assertEqual((await self.create("budget", explicit)).status_code, 409)
        self.assertEqual(await self.snapshot(), before)

    async def test_legacy_unverifiable_records_not_adopted(self):
        f = await self.prepare()
        for kind in ("budget", "bill"):
            p = self.payload(kind, f)
            a = await self.create(kind, p)
            col = self.db.budgets if kind == "budget" else self.db.bills
            async def remove_hash(session):
                await col.update_one({"id": a.json()["id"]}, {"$unset": {"request_fingerprint": ""}}, session=session)
            await self.ctx.ns["payment_transaction"](remove_hash)
            before = await self.snapshot()
            r = await self.create(kind, p)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(await self.snapshot(), before)

    async def test_old_budget_key_and_random_id_preserved(self):
        f = await self.prepare()
        await self.insert("budgets", dict(id="legacy", user_id="default-user", idempotency_key="original", **self.payload("budget", f)))
        before = await self.snapshot()
        self.assertEqual((await self.create("budget", self.payload("budget", f))).status_code, 409)
        self.assertEqual(await self.snapshot(), before)

    async def test_duplicate_legacy_keys_are_ambiguous(self):
        f = await self.prepare()
        for n in ("one", "two"):
            await self.insert("budgets", dict(id=n, user_id="default-user", idempotency_key="original", request_fingerprint="synthetic", **self.payload("budget", f)))
        before = await self.snapshot()
        self.assertEqual((await self.create("budget", self.payload("budget", f))).status_code, 409)
        self.assertEqual(await self.snapshot(), before)

    async def test_bill_creation_without_key_stays_independent(self):
        f = await self.prepare()
        p = self.payload("bill", f)
        a = await self.create("bill", p, None)
        b = await self.create("bill", p, None)
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertNotEqual(a.json()["id"], b.json()["id"])

    async def test_every_original_field_and_default_is_fingerprinted(self):
        f = await self.prepare()
        changes = {
            "budget": dict(period="weekly", start_date="2026-10-01", end_date="2026-11-01", alerts_enabled=False, alert_threshold=90),
            "bill": dict(provider="Other", account_id=f["a"], due_date="2026-11-20", frequency="monthly", reminder_days=1,
                         description="Other", recurring_payment_id="missing", icon="cash", color="#000000"),
        }
        for kind, mutations in changes.items():
            p = self.payload(kind, f)
            self.assertEqual((await self.create(kind, p)).status_code, 200)
            before = await self.snapshot()
            for field, value in mutations.items():
                with self.subTest(kind=kind, field=field):
                    self.assertEqual((await self.create(kind, dict(p, **{field:value}))).status_code, 409)
                    self.assertEqual(await self.snapshot(), before)

    async def test_verifiable_replay_needs_no_new_reference_validation(self):
        f = await self.prepare()
        p = self.payload("bill", f)
        p["category_id"] = f["category"]
        a = await self.create("bill", p)
        self.assertEqual(a.status_code, 200)
        # Synthetic legacy corruption only. Replay must not create/repair anything.
        async def remove(session):
            await self.db.categories.delete_one({"id":f["category"]}, session=session)
        await self.ctx.ns["payment_transaction"](remove)
        before = await self.snapshot()
        b = await self.create("bill", p)
        self.assertEqual(b.status_code, 200, b.text)
        self.assertEqual(b.json()["id"], a.json()["id"])
        self.assertEqual(await self.snapshot(), before)

    async def test_budget_list_and_bill_detail_hide_fingerprint(self):
        f = await self.prepare()
        budget = await self.create("budget", self.payload("budget", f))
        bill = await self.create("bill", self.payload("bill", f))
        self.assertEqual((budget.status_code, bill.status_code), (200, 200))
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "list_budgets")
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<R5 budget list>", "exec"), self.ctx.ns)
        listing = await self.ctx.ns["list_budgets"]()
        self.assertEqual(len(listing), 1)
        self.assertNotIn("request_fingerprint", listing[0])
        self.assertNotIn("idempotency_key", listing[0])
        detail = await self.request("GET", "/bills/"+bill.json()["id"])
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertNotIn("request_fingerprint", detail.text)


class CreationMemoryTests(CreationCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database()
        self.collections = tuple(self.db.data)
        self.ctx = context(self.db, memory.Client(self.db))

    async def insert(self, collection, doc):
        self.db.data[collection].append(dict(doc, _id=doc["id"]))

    async def test_failure_rolls_back_and_lost_commit_response_reuses_id(self):
        f = await self.prepare()
        for kind in ("budget", "bill"):
            p = self.payload(kind, f)
            before = await self.snapshot()
            self.db.writes = 0
            self.db.fail_at = 1
            self.assertEqual((await self.create(kind, p)).status_code, 503)
            self.assertEqual(await self.snapshot(), before)
            self.db.fail_at = None
            self.db.commit_then_error = True
            self.assertEqual((await self.create(kind, p)).status_code, 503)
            committed = await self.snapshot()
            self.assertEqual((await self.create(kind, p)).status_code, 200)
            self.assertEqual(await self.snapshot(), committed)
