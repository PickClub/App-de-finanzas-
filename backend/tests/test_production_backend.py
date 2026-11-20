"""Offline R7 tests. No client is allowed to connect to any MongoDB destination."""

from contextlib import asynccontextmanager
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import logging
import unittest
from uuid import uuid4

import httpx
from pymongo.errors import AutoReconnect, OperationFailure

from backend.auth_core import (
    AuthService,
    DeliveryUnavailable,
    InvalidCredentials,
    Purpose,
    StorageUnavailable,
)
from backend.auth_mongodb import Store, AbortedAuthTransaction, retry_auth
from backend.production_config import ProductionConfig, ConfigurationError
from backend.production_services import (
    SMTPDelivery,
    MongoRateLimiter,
    RateLimited,
    verify_database,
    index_plan,
)
from backend.production_api import build_app, create_app
from backend.tests.test_auth_core import MemoryStore, Delivery, PASSWORD, NEW_PASSWORD


def environment():
    # Explicitly synthetic fixture values; no deployment credentials.
    return dict(
        APP_ENV="production",
        PW_PUBLIC_ORIGIN="https://api.example.com",
        PW_ALLOWED_ORIGINS="https://app.example.com",
        PW_TRUSTED_PROXIES="127.0.0.1/32",
        PW_MONGO_URI="mongodb://fixture:fixture-database-password-123@db.internal:27017/pickwallet_prod?tls=true&replicaSet=pw_prod&authSource=pickwallet_prod&authMechanism=SCRAM-SHA-256",
        PW_MONGO_HOSTS="db.internal:27017",
        PW_MONGO_DATABASE="pickwallet_prod",
        PW_MONGO_REPLICA_SET="pw_prod",
        PW_ENVIRONMENT_ID=str(uuid4()),
        PW_SMTP_HOST="mail.example.com",
        PW_SMTP_USERNAME="fixture",
        PW_SMTP_PASSWORD="fixture-mail-password-123",
        PW_MAIL_FROM="accounts@example.com",
        PW_RATE_SECRET="0123456789abcdef" * 4,
    )


class ConfigurationTests(unittest.TestCase):
    def test_valid_config_and_bounded_tls_client_options(self):
        config = ProductionConfig.load(environment())
        self.assertTrue(config.mongo_options()["tls"])
        self.assertEqual(config.mongo_options()["w"], "majority")
        self.assertGreater(config.mongo_options()["waitQueueTimeoutMS"], 0)
        self.assertNotIn("fixture-mail-password-123", repr(config))
        self.assertNotIn("mongodb://", repr(config))

    def test_every_missing_setting_rejected_without_network(self):
        env = environment()
        for key in env:
            with self.subTest(key=key), patch(
                "backend.production_api.MongoClient"
            ) as client:
                with patch.dict(
                    "os.environ", {k: v for k, v in env.items() if k != key}, clear=True
                ):
                    with self.assertRaises(ConfigurationError):
                        create_app()
                client.assert_not_called()

    def test_insecure_configurations_rejected(self):
        for key, value in (
            ("APP_ENV", "test"),
            ("PW_PUBLIC_ORIGIN", "http://api.example.com"),
            ("PW_PUBLIC_ORIGIN", "https://localhost"),
            ("PW_ALLOWED_ORIGINS", "*"),
            ("PW_TRUSTED_PROXIES", "0.0.0.0/0"),
            ("PW_TRUSTED_PROXIES", "8.8.8.8/32"),
            ("PW_RATE_SECRET", "a" * 64),
            ("PW_SMTP_PASSWORD", "password"),
            ("PW_ENVIRONMENT_ID", str(uuid4()).replace("4", "5")),
            ("PW_MONGO_DATABASE", "r3_security_synthetic"),
        ):
            env = environment()
            env[key] = value
            if key == "PW_ENVIRONMENT_ID":
                env[key] = "00000000-0000-1000-8000-000000000000"
            with self.subTest(key=key, value=value), self.assertRaises(
                ConfigurationError
            ):
                ProductionConfig.load(env)
        for source, replacement in (
            ("tls=true", "tls=false"),
            ("tls=true", "tls=true&tlsAllowInvalidCertificates=true"),
            ("db.internal:27017", "127.0.0.1:27018"),
            ("fixture:fixture-database-password-123@", ""),
            ("tls=true", "tls=true&tls=true"),
        ):
            env = environment()
            env["PW_MONGO_URI"] = env["PW_MONGO_URI"].replace(source, replacement)
            with self.subTest(replacement=replacement), self.assertRaises(
                ConfigurationError
            ):
                ProductionConfig.load(env)

    def test_public_or_loopback_mongo_dns_rejected(self):
        config = ProductionConfig.load(environment())
        for address in ("8.8.8.8", "127.0.0.1", "169.254.1.1"):
            with patch(
                "backend.production_config.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", (address, 27017))],
            ):
                with self.assertRaises(ConfigurationError):
                    config.verify_private_network()
        with patch(
            "backend.production_config.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("10.20.30.40", 27017))],
        ):
            config.verify_private_network()

    def test_valid_factory_uses_shared_store_and_fence_and_closes_clients(self):
        env = environment()
        sync, motor = MagicMock(), MagicMock()
        database = MagicMock()
        with patch.dict("os.environ", env, clear=True), patch.object(
            ProductionConfig, "verify_private_network"
        ), patch(
            "backend.production_api.MongoClient", return_value=sync
        ) as sync_type, patch(
            "backend.production_api.AsyncIOMotorClient", return_value=motor
        ), patch(
            "backend.production_api.verify_database", return_value=database
        ):
            app = create_app()
            self.assertIsNotNone(app)
            self.assertTrue(sync_type.call_args.kwargs["tls"])
            self.assertFalse(app.debug)

            async def lifecycle():
                async with app.router.lifespan_context(app):
                    sync.close.assert_not_called()
                    motor.close.assert_not_called()

            asyncio.run(lifecycle())
            sync.close.assert_called_once()
            motor.close.assert_called_once()

    def test_driver_constructor_error_is_sanitized(self):
        env = environment()
        with patch.dict("os.environ", env, clear=True), patch.object(
            ProductionConfig, "verify_private_network"
        ), patch(
            "backend.production_api.MongoClient",
            side_effect=ValueError(env["PW_MONGO_URI"]),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "^Production startup validation failed$"
            ):
                create_app()

    def test_startup_outage_fails_without_credentials_in_error(self):
        env = environment()
        sync = MagicMock()
        with patch.dict("os.environ", env, clear=True), patch.object(
            ProductionConfig, "verify_private_network"
        ), patch("backend.production_api.MongoClient", return_value=sync), patch(
            "backend.production_api.verify_database",
            side_effect=RuntimeError(env["PW_MONGO_URI"]),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "^Production startup validation failed$"
            ):
                create_app()
            sync.close.assert_called_once()


class InfrastructureTests(unittest.TestCase):
    def test_shared_store_transaction_options_and_error_labels(self):
        db = MagicMock()
        store = Store(db)
        session = db.client.start_session.return_value.__enter__.return_value
        with store.transaction() as transaction:
            self.assertIs(transaction.db, db)
        options = session.start_transaction.call_args.kwargs
        self.assertEqual(options["write_concern"].document, {"w": "majority"})
        self.assertEqual(options["read_concern"].document, {"level": "snapshot"})
        for labels, expected in (
            (["TransientTransactionError"], AbortedAuthTransaction),
            (["UnknownTransactionCommitResult"], StorageUnavailable),
        ):
            error = OperationFailure("private error", details={"errorLabels": labels})
            with self.assertRaises(expected) as caught:
                with store.transaction():
                    raise error
            self.assertNotIn("private error", str(caught.exception))
            if labels == ["UnknownTransactionCommitResult"]:
                self.assertNotIsInstance(caught.exception, AbortedAuthTransaction)
        operation = MagicMock(side_effect=StorageUnavailable("unknown commit outcome"))
        with self.assertRaises(StorageUnavailable):
            retry_auth(operation)
        operation.assert_called_once()

    def test_tls_email_delivery_and_sanitized_failure(self):
        config = ProductionConfig.load(environment())
        transport = MagicMock()
        delivery = SMTPDelivery(config, transport)
        delivery.deliver(
            "a@example.com",
            Purpose.RECOVERY,
            "private-token",
            datetime.now(timezone.utc),
        )
        self.assertEqual(transport.call_args.args[1], 465)
        self.assertTrue(transport.call_args.kwargs["context"].check_hostname)
        message = (
            transport.return_value.__enter__.return_value.send_message.call_args.args[0]
        )
        self.assertIn("account code: private-token", message.get_content())
        self.assertIn(
            "POST https://api.example.com/api/auth/recovery/confirm",
            message.get_content(),
        )
        self.assertNotIn("?token=", message.get_content())
        transport.side_effect = RuntimeError("password and raw token")
        with self.assertRaises(DeliveryUnavailable) as error:
            delivery.deliver(
                "a@example.com",
                Purpose.INVITATION,
                "secret",
                datetime.now(timezone.utc),
            )
        self.assertNotIn("password", str(error.exception))

    def test_shared_counter_hmac_and_failure_closed(self):
        db = MagicMock()
        limiter = MongoRateLimiter(db, b"fixture secret")
        db.auth_rate_limits.find_one_and_update.return_value = {"count": 2}
        with self.assertRaises(RateLimited):
            limiter.check("login", "a@example.com", 1, 60)
        call = db.auth_rate_limits.find_one_and_update.call_args
        self.assertNotIn("a@example.com", repr(call))
        self.assertTrue(call.kwargs["upsert"])
        db.auth_rate_limits.find_one_and_update.side_effect = AutoReconnect(
            "private details"
        )
        with self.assertRaisesRegex(
            StorageUnavailable, "^Authentication rate limiter unavailable$"
        ):
            limiter.check("login", "a@example.com", 1, 60)

    def test_readonly_readiness_checks_topology_metadata_privileges_and_indexes(self):
        config = ProductionConfig.load(environment())
        client = MagicMock()
        db = client.__getitem__.return_value
        hello = dict(
            setName=config.replica_set,
            hosts=list(config.mongo_hosts),
            isWritablePrimary=True,
            logicalSessionTimeoutMinutes=30,
            maxWireVersion=17,
        )
        privilege = {
            "resource": {"db": config.database, "collection": ""},
            "actions": ["find", "insert", "update", "remove", "listIndexes"],
        }

        def command(name, **kwargs):
            return (
                hello
                if name == "hello"
                else {"authInfo": {"authenticatedUserPrivileges": [privilege]}}
            )

        client.admin.command.side_effect = command
        db.moneyflow_metadata.find_one.return_value = dict(
            version=1, environment_id=config.environment_id
        )
        collections = {}
        for item in index_plan():
            collections.setdefault(item["collection"], MagicMock())
        for name, collection in collections.items():
            collection.list_indexes.return_value = [
                {
                    "key": dict(item["keys"]),
                    **{
                        k: v for k, v in item.items() if k not in ("keys", "collection")
                    },
                }
                for item in index_plan()
                if item["collection"] == name
            ]
        db.__getitem__.side_effect = collections.__getitem__
        self.assertIs(verify_database(client, config), db)
        self.assertFalse(
            any(
                "create_index" in str(call) or "update_one" in str(call)
                for call in db.mock_calls
            )
        )
        collections["auth_users"].list_indexes.return_value = []
        with self.assertRaises(StorageUnavailable):
            verify_database(client, config)
        hello["setName"] = "wrong"
        with self.assertRaises(StorageUnavailable):
            verify_database(client, config)
        hello["setName"] = config.replica_set
        privilege["actions"].append("dropDatabase")
        with self.assertRaises(StorageUnavailable):
            verify_database(client, config)


class ProductionHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = ProductionConfig.load(environment())
        self.delivery = Delivery()
        self.operator = object()
        self.auth = AuthService(
            MemoryStore(), self.delivery, lambda actor: actor is self.operator
        )
        self.auth.invite(self.operator, "a@example.com")
        self.invitation = self.delivery.messages[-1][2]
        self.limiter = MagicMock()

        @asynccontextmanager
        async def fence(principal):
            yield SimpleNamespace(in_transaction=True)

        self.app = build_app(
            self.config, self.auth, SimpleNamespace(), self.limiter, fence
        )
        self.headers = {"X-Forwarded-Proto": "https", "X-Forwarded-For": "192.0.2.55"}
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, client=("127.0.0.1", 12345)),
            base_url=self.config.public_origin,
            headers=self.headers,
        )
        self.addAsyncCleanup(self.client.aclose)

    async def enroll(self):
        response = await self.client.post(
            "/api/auth/invite/accept",
            json={"invitation": self.invitation, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 204, response.text)
        response = await self.client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_invitation_login_refresh_logout_and_required_auth(self):
        tokens = await self.enroll()
        self.assertEqual((await self.client.get("/api/auth/session")).status_code, 401)
        authorized = {"Authorization": "Bearer " + tokens["access"]}
        self.assertEqual(
            (
                await self.client.get("/api/auth/session", headers=authorized)
            ).status_code,
            200,
        )
        refreshed = await self.client.post(
            "/api/auth/refresh", json={"refresh": tokens["refresh"]}
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(
            (
                await self.client.get("/api/auth/session", headers=authorized)
            ).status_code,
            401,
        )
        await self.client.post(
            "/api/auth/logout", json={"refresh": refreshed.json()["refresh"]}
        )
        self.assertEqual(
            (
                await self.client.get(
                    "/api/auth/session",
                    headers={"Authorization": "Bearer " + refreshed.json()["access"]},
                )
            ).status_code,
            401,
        )

    async def test_recovery_simulated_mail_revokes_sessions_and_one_use(self):
        tokens = await self.enroll()
        self.auth.recover(self.operator, "a@example.com")
        recovery = self.delivery.messages[-1][2]
        payload = {"token": recovery, "password": NEW_PASSWORD}
        self.assertEqual(
            (
                await self.client.post("/api/auth/recovery/confirm", json=payload)
            ).status_code,
            204,
        )
        self.assertEqual(
            (
                await self.client.post("/api/auth/recovery/confirm", json=payload)
            ).status_code,
            401,
        )
        self.assertEqual(
            (
                await self.client.get(
                    "/api/auth/session",
                    headers={"Authorization": "Bearer " + tokens["access"]},
                )
            ).status_code,
            401,
        )
        self.assertEqual(
            (
                await self.client.post(
                    "/api/auth/login",
                    json={"email": "a@example.com", "password": NEW_PASSWORD},
                )
            ).status_code,
            200,
        )

    async def test_no_public_enrollment_seed_or_legacy_bypass(self):
        for path in (
            "/api/seed",
            "/api/auth/register",
            "/api/auth/invite",
            "/api/auth/recover",
            "/api/accounts",
        ):
            self.assertEqual(
                (await self.client.post(path, json={})).status_code, 401, path
            )
        tokens = await self.enroll()
        for path in (
            "/api/seed",
            "/api/auth/register",
            "/api/auth/invite",
            "/api/auth/recover",
        ):
            self.assertEqual(
                (
                    await self.client.post(
                        path,
                        json={},
                        headers={"Authorization": "Bearer " + tokens["access"]},
                    )
                ).status_code,
                404,
                path,
            )

    async def test_spoofed_proxy_headers_missing_tls_and_host_rejected(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, client=("198.51.100.10", 123)),
            base_url=self.config.public_origin,
        ) as untrusted:
            self.assertEqual(
                (
                    await untrusted.get("/api/auth/session", headers=self.headers)
                ).status_code,
                400,
            )
        for headers in (
            {"X-Forwarded-Proto": "http"},
            {"X-Forwarded-For": "192.0.2.1, 127.0.0.1"},
            {"Host": "attacker.example"},
            {"Forwarded": "proto=https"},
        ):
            self.assertEqual(
                (
                    await self.client.get("/api/auth/session", headers=headers)
                ).status_code,
                400,
            )

    async def test_validation_logs_errors_and_response_headers_do_not_echo_secrets(
        self,
    ):
        sentinel = "never-log-this-secret"
        response = await self.client.post(
            "/api/auth/login",
            json={"email": sentinel, "password": sentinel, "extra": sentinel},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(sentinel, response.text)
        with self.assertLogs("pickwallet.security", level=logging.INFO) as logs:
            response = await self.client.post(
                "/api/auth/login",
                json={"email": "absent@example.com", "password": sentinel},
            )
        self.assertNotIn(sentinel, repr(logs.output))
        self.assertNotIn("absent@example.com", repr(logs.output))
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("max-age=", response.headers["strict-transport-security"])

    async def test_unhandled_exception_never_escapes_with_secret_traceback(self):
        @self.app.get("/offline-failure")
        def failure():
            raise RuntimeError("private-financial-payload-and-password")

        with self.assertLogs("pickwallet.security", level=logging.ERROR) as logs:
            response = await self.client.get("/offline-failure")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-financial", response.text + repr(logs.output))

    async def test_throttle_and_storage_outage_fail_closed(self):
        self.limiter.check.side_effect = RateLimited()
        self.assertEqual((await self.client.get("/api/auth/session")).status_code, 429)
        self.limiter.check.side_effect = StorageUnavailable("private")
        self.assertEqual((await self.client.get("/api/auth/session")).status_code, 503)

    async def test_auth_body_limit_and_cors(self):
        self.assertEqual(
            (await self.client.post("/api/auth/login", content="x" * 4097)).status_code,
            413,
        )
        response = await self.client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(
            response.headers["access-control-allow-origin"], "https://app.example.com"
        )
        response = await self.client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)
