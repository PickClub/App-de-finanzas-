"""Destructive integration tests confined to a fresh named disposable replica."""

import asyncio
from ipaddress import ip_network
import os
import re
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import OperationFailure

from backend.auth_core import (
    AuthService,
    InvalidCredentials,
    StorageUnavailable,
    token_digest,
)
from backend.auth_mongodb import ACCOUNT_DATA_COLLECTIONS, Fence, Store, Transaction
from backend.production_api import build_app
from backend.tests.test_auth_core import Delivery, PASSWORD


@unittest.skipUnless(
    os.getenv("PW_DELETION_TEST_REPLICA"), "requires fresh disposable replica"
)
class DeletionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        replica = os.environ["PW_DELETION_TEST_REPLICA"]
        port = int(os.environ["PW_DELETION_TEST_PORT"])
        if (
            not re.fullmatch(r"pickwallet-delete-[0-9a-f]{12}", replica)
            or not 32768 <= port <= 65535
        ):
            raise RuntimeError("Unexpected disposable replica")
        uri = f"mongodb://127.0.0.1:{port}/?replicaSet={replica}&directConnection=true"
        mongo = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        self.addCleanup(mongo.close)
        hello = mongo.admin.command("hello")
        self.assertEqual(hello.get("setName"), replica)
        self.assertEqual(hello.get("hosts"), ["localhost:27017"])
        db_name = "pw_deletion_" + uuid4().hex
        self.db = mongo[db_name]
        motor = AsyncIOMotorClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        self.addCleanup(motor.close)
        self.async_db = motor[db_name]
        self.fence = Fence(self.async_db)
        self.delivery = Delivery()
        self.operator = object()
        self.auth = AuthService(
            Store(self.db), self.delivery, lambda actor: actor is self.operator
        )
        self.config = SimpleNamespace(
            environment_id=str(uuid4()),
            public_origin="https://api.example.com",
            allowed_origins=("https://api.example.com",),
            trusted_proxies=(ip_network("127.0.0.1/32"),),
        )
        app = build_app(self.config, self.auth, self.async_db, MagicMock(), self.fence)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
            base_url=self.config.public_origin,
            headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "192.0.2.55"},
        )
        self.addAsyncCleanup(self.client.aclose)
        self.a = self.enroll("a@example.com")
        self.b = self.enroll("b@example.com")
        self.owner_a = self.auth.authenticate(self.a.access).user_id
        self.owner_b = self.auth.authenticate(self.b.access).user_id
        self.auth.recover(self.operator, "a@example.com")
        self.challenge = self.delivery.messages[-1][2]
        self.second_a = self.auth.login("a@example.com", PASSWORD)
        self.rotated_a = self.auth.rotate(self.second_a.refresh)
        self.collections = (
            *ACCOUNT_DATA_COLLECTIONS,
            "users",
            "auth_users",
            "auth_sessions",
            "auth_challenges",
            "auth_refresh",
        )
        for name in ACCOUNT_DATA_COLLECTIONS:
            self.db[name].insert_many(
                [
                    {"user_id": self.owner_a, "reference": "same-reference"},
                    {"user_id": self.owner_b, "reference": "same-reference"},
                    {"user_id": "default-user", "reference": "same-reference"},
                ]
            )
        self.db.auth_rate_limits.insert_one({"_id": "unrelated-counter"})
        self.db.moneyflow_metadata.insert_one({"_id": "shared-marker"})
        self.family_b = self.auth.authenticate(self.b.access).family_id

    def enroll(self, email):
        self.auth.invite(self.operator, email)
        self.auth.accept_invitation(self.delivery.messages[-1][2], PASSWORD)
        return self.auth.login(email, PASSWORD)

    def snapshot(self):
        return {
            name: list(self.db[name].find().sort("_id")) for name in self.collections
        }

    async def delete(self, access=None, payload=None):
        headers = {"Authorization": "Bearer " + access} if access else {}
        return await self.client.post(
            "/api/auth/account/delete",
            headers=headers,
            json=payload or {"password": PASSWORD},
        )

    async def web_delete(self, **changes):
        origin = changes.pop("origin", self.config.public_origin)
        headers = {"Origin": origin} if origin is not None else {}
        body = {"email": "a@example.com", "password": PASSWORD, "confirmed": True}
        body.update(changes)
        return await self.client.post(
            "/api/auth/account/delete-web", headers=headers, json=body
        )

    async def test_web_rejects_unverified_requests_without_enumerating(self):
        before = self.snapshot()
        wrong = await self.web_delete(password="wrong synthetic password")
        missing = await self.web_delete(email="unknown@example.com")
        self.assertEqual((wrong.status_code, wrong.json()), (401, missing.json()))
        self.assertEqual(missing.status_code, 401)
        for options in (
            {"origin": "https://other.example.com"},
            {"origin": None},
            {"confirmed": False},
        ):
            self.assertEqual((await self.web_delete(**options)).status_code, 403)
        supplied_owner = await self.web_delete(user_id=self.owner_b)
        self.assertEqual(supplied_owner.status_code, 422)
        self.assertNotIn(PASSWORD, supplied_owner.text)
        self.assertEqual(self.snapshot(), before)

    async def test_web_verified_owner_only_and_repeated_request(self):
        response = await self.web_delete()
        self.assertEqual(response.status_code, 204)
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(response.content, b"")
        for name in ACCOUNT_DATA_COLLECTIONS:
            self.assertEqual(
                self.db[name].count_documents({"user_id": self.owner_a}), 0
            )
            self.assertEqual(
                self.db[name].count_documents({"user_id": self.owner_b}), 1
            )
        with self.assertRaises(InvalidCredentials):
            self.auth.rotate(self.a.refresh)
        self.assertEqual(self.auth.authenticate(self.b.access).user_id, self.owner_b)
        after = self.snapshot()
        repeat = await self.web_delete()
        unknown = await self.web_delete(email="unknown@example.com")
        self.assertEqual((repeat.status_code, repeat.json()), (401, unknown.json()))
        self.assertEqual(self.snapshot(), after)

    async def test_web_rolls_back_failure_before_commit(self):
        before = self.snapshot()
        original = Transaction.erase_account

        def erase_then_fail(tx, user_id):
            original(tx, user_id)
            raise OperationFailure("synthetic web rollback")

        with patch.object(Transaction, "erase_account", erase_then_fail):
            self.assertEqual((await self.web_delete()).status_code, 503)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((await self.web_delete()).status_code, 204)

    async def test_web_pages_are_bilingual_and_use_restricted_security_headers(self):
        for path in (
            "/privacy",
            "/privacy/es",
            "/delete-account",
            "/delete-account/es",
        ):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                'lang="es"' if path.endswith("/es") else 'lang="en"', response.text
            )
            self.assertIn(
                "form-action 'none'", response.headers["content-security-policy"]
            )
            self.assertIn(
                "connect-src 'self'", response.headers["content-security-policy"]
            )
            self.assertEqual(response.headers["cache-control"], "no-store")
        script = await self.client.get("/privacy-assets/delete.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("javascript", script.headers["content-type"])
        api = await self.client.get("/api/auth/session")
        self.assertEqual(
            api.headers["content-security-policy"],
            "default-src 'none'; frame-ancestors 'none'",
        )

    async def test_complete_isolated_and_retry_safe(self):
        before = self.snapshot()
        self.assertEqual((await self.delete(self.a.access)).status_code, 204)
        for name in ACCOUNT_DATA_COLLECTIONS:
            self.assertEqual(
                list(self.db[name].find().sort("_id")),
                [row for row in before[name] if row["user_id"] != self.owner_a],
            )
        for name, key in (
            ("users", "id"),
            ("auth_users", "_id"),
            ("auth_sessions", "user_id"),
            ("auth_challenges", "user_id"),
        ):
            self.assertEqual(
                list(self.db[name].find().sort("_id")),
                [row for row in before[name] if row[key] != self.owner_a],
            )
        self.assertEqual(
            list(self.db.auth_refresh.find().sort("_id")),
            [
                row
                for row in before["auth_refresh"]
                if row["family_id"] == self.family_b
            ],
        )
        self.assertEqual(self.db.auth_rate_limits.count_documents({}), 1)
        self.assertEqual(self.db.moneyflow_metadata.count_documents({}), 1)
        for token in (self.a.access, self.rotated_a.access):
            with self.assertRaises(InvalidCredentials):
                self.auth.authenticate(token)
        for token in (self.a.refresh, self.second_a.refresh, self.rotated_a.refresh):
            with self.assertRaises(InvalidCredentials):
                self.auth.rotate(token)
        with self.assertRaises(InvalidCredentials):
            self.auth.reset_password(self.challenge, PASSWORD)
        with self.assertRaises(InvalidCredentials):
            self.auth.login("a@example.com", PASSWORD)
        self.assertEqual(self.auth.authenticate(self.b.access).user_id, self.owner_b)
        after = self.snapshot()
        self.assertEqual((await self.delete(self.a.access)).status_code, 401)
        self.assertEqual(self.snapshot(), after)

    async def test_requires_current_password_and_server_identity(self):
        before = self.snapshot()
        self.assertEqual((await self.delete()).status_code, 401)
        response = await self.delete(
            self.a.access, {"password": "wrong password fixture"}
        )
        self.assertEqual(response.status_code, 401)
        response = await self.delete(
            self.a.access, {"password": PASSWORD, "user_id": self.owner_b}
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(PASSWORD, response.text)
        self.assertEqual(self.snapshot(), before)

    async def test_failure_rolls_back_every_collection_and_allows_retry(self):
        before = self.snapshot()
        original = Transaction.erase_account

        def erase_then_fail(tx, user_id):
            original(tx, user_id)
            raise OperationFailure("synthetic failure before commit")

        with patch.object(Transaction, "erase_account", erase_then_fail):
            self.assertEqual((await self.delete(self.a.access)).status_code, 503)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.auth.authenticate(self.a.access).user_id, self.owner_a)
        self.assertEqual((await self.delete(self.a.access)).status_code, 204)

    async def test_unknown_result_is_never_reported_as_success(self):
        original = self.auth.delete_account

        def lose_confirmation(*args):
            original(*args)
            raise StorageUnavailable("synthetic lost commit confirmation")

        with patch.object(self.auth, "delete_account", lose_confirmation):
            self.assertEqual((await self.delete(self.a.access)).status_code, 503)
        self.assertEqual((await self.delete(self.a.access)).status_code, 401)
        self.assertIsNone(self.db.auth_users.find_one({"_id": self.owner_a}))
        self.assertEqual(self.auth.authenticate(self.b.access).user_id, self.owner_b)

    async def test_stale_recovery_issuance_cannot_recreate_a_challenge(self):
        late_digest = "a" * 64
        with self.assertRaises(StorageUnavailable):
            with self.auth.store.transaction() as tx:
                old = tx.challenge(token_digest(self.challenge, "recover"))
                self.assertIsNotNone(old)
                self.assertEqual((await self.delete(self.a.access)).status_code, 204)
                tx.save_challenge(late_digest, old)
        self.assertIsNone(self.db.auth_challenges.find_one({"_id": late_digest}))

    async def test_inflight_financial_write_cannot_leave_orphan(self):
        owner = self.auth.authenticate(self.a.access)
        staged = asyncio.Event()
        finish = asyncio.Event()

        async def write():
            async with self.fence(owner) as session:
                await self.async_db.notes.insert_one(
                    {"user_id": self.owner_a, "reference": "concurrent"},
                    session=session,
                )
                staged.set()
                await finish.wait()

        pending = asyncio.create_task(write())
        await asyncio.wait_for(staged.wait(), 3)
        deleting = asyncio.create_task(self.delete(self.a.access))
        await asyncio.sleep(0.08)
        finish.set()
        await pending
        result = await deleting
        if result.status_code == 503:
            result = await self.delete(self.a.access)
        self.assertEqual(result.status_code, 204)
        self.assertEqual(self.db.notes.count_documents({"user_id": self.owner_a}), 0)
        with self.assertRaises(InvalidCredentials):
            async with self.fence(owner):
                self.fail("Revoked session obtained a financial write fence")
