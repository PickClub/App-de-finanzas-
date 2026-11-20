"""Production infrastructure adapters; constructors do not deliver mail."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import smtplib
import ssl

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from backend.auth_mongodb import ACCOUNT_DATA_COLLECTIONS
from backend.auth_core import DeliveryUnavailable, StorageUnavailable


class SMTPDelivery:
    """Implicit TLS on 465; no SMTP debug output or plaintext downgrade."""

    def __init__(self, config, transport=smtplib.SMTP_SSL):
        self.config, self.transport = config, transport

    def deliver(self, email, purpose, token, expires):
        try:
            message = EmailMessage()
            message["From"] = self.config.mail_from
            message["To"] = email
            message["Subject"] = (
                "PickWallet account invitation"
                if purpose.value == "invite"
                else "PickWallet password recovery"
            )
            invitation = purpose.value == "invite"
            endpoint = self.config.public_origin + (
                "/api/auth/invite/accept"
                if invitation
                else "/api/auth/recovery/confirm"
            )
            field = "invitation" if invitation else "token"
            message.set_content(
                f"Your single-use PickWallet account code: {token}\n"
                f"Expires: {expires.isoformat()}\n"
                f"Use the approved account client to submit this code as '{field}' with your new password "
                f"to POST {endpoint}. This address is an API endpoint, not a browser page.\n"
                "Never send your password to support. If unexpected, ignore this email."
            )
            with self.transport(
                self.config.smtp_host,
                465,
                timeout=10,
                context=ssl.create_default_context(),
            ) as smtp:
                smtp.login(self.config.smtp_username, self.config.smtp_password)
                smtp.send_message(message)
        except Exception:
            raise DeliveryUnavailable("Account message delivery unavailable") from None


class RateLimited(Exception):
    pass


class MongoRateLimiter:
    """Shared fixed-window counters. TTL cleanup is not relied upon for correctness."""

    def __init__(self, database, secret, clock=lambda: datetime.now(timezone.utc)):
        self.database, self.secret, self.clock = database, secret, clock

    def check(self, category, subject, limit, seconds):
        now = self.clock()
        window = int(now.timestamp()) // seconds
        key = hmac.new(
            self.secret, f"{category}:{subject}:{window}".encode(), hashlib.sha256
        ).hexdigest()
        try:
            row = self.database.auth_rate_limits.find_one_and_update(
                {"_id": key},
                {
                    "$inc": {"count": 1},
                    "$setOnInsert": {"expires": now + timedelta(seconds=seconds * 2)},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError:
            raise StorageUnavailable(
                "Authentication rate limiter unavailable"
            ) from None
        if row["count"] > limit:
            raise RateLimited()


# Separate administrative setup from least-privilege runtime. Never create indexes at startup.
UNIQUE_INDEXES = {
    "auth_users": (("email",),),
    "auth_sessions": (("access_digest",),),
    **{
        name: (("id",),)
        for name in (
            "users",
            "accounts",
            "transactions",
            "debts",
            "debt_payments",
            "bills",
            "recurring_payments",
            "budgets",
            "saving_goals",
            "categories",
            "notes",
            "recurring_templates",
            "bill_payments",
            "recurring_payment_records",
            "goal_contributions",
            "shared_obligations",
        )
    },
}


def index_plan():
    """Pure data for separately authorized DBA provisioning."""
    return [
        dict(collection=name, keys=[(key, 1) for key in keys], unique=True)
        for name, indexes in UNIQUE_INDEXES.items()
        for keys in indexes
    ] + [
        dict(
            collection="auth_rate_limits", keys=[("expires", 1)], expireAfterSeconds=0
        ),
        dict(collection="auth_sessions", keys=[("user_id", 1)]),
        dict(collection="auth_challenges", keys=[("user_id", 1)]),
        dict(collection="movement_receipts", keys=[("user_id", 1)]),
        dict(collection="auth_refresh", keys=[("family_id", 1)]),
        *[
            dict(collection=name, keys=[("user_id", 1)])
            for name in ACCOUNT_DATA_COLLECTIONS
            if name != "movement_receipts"
        ],
    ]


def verify_database(client, config):
    """Read-only readiness checks. Never initializes metadata or creates indexes."""
    try:
        hello = client.admin.command("hello")
        if (
            hello.get("setName") != config.replica_set
            or not hello.get("isWritablePrimary")
            or set(hello.get("hosts", ())) != set(config.mongo_hosts)
            or hello.get("logicalSessionTimeoutMinutes") is None
            or hello.get("maxWireVersion", 0) < 7
        ):
            raise StorageUnavailable("Production replica readiness check failed")
        privileges = client.admin.command("connectionStatus", showPrivileges=True).get(
            "authInfo", {}
        )
        allowed = {"find", "insert", "update", "remove", "listIndexes", "killCursors"}
        grants = privileges.get("authenticatedUserPrivileges", [])
        if (
            not grants
            or any(
                grant.get("resource") != {"db": config.database, "collection": ""}
                or not set(grant.get("actions", ())).issubset(allowed)
                for grant in grants
            )
            or not {"find", "insert", "update", "remove", "listIndexes"}.issubset(
                set().union(*(set(grant.get("actions", ())) for grant in grants))
            )
        ):
            raise StorageUnavailable(
                "Dedicated least-privilege database identity required"
            )
        db = client[config.database]
        context = db.moneyflow_metadata.find_one({"_id": "financial-context"})
        if (
            not context
            or context.get("environment_id") != config.environment_id
            or context.get("version") != 1
        ):
            raise StorageUnavailable("Production environment identity mismatch")
        for item in index_plan():
            found = False
            for actual in db[item["collection"]].list_indexes():
                if list(actual["key"].items()) != item["keys"]:
                    continue
                if item.get("unique") and (
                    not actual.get("unique")
                    or actual.get("sparse")
                    or actual.get("partialFilterExpression")
                ):
                    continue
                if (
                    "expireAfterSeconds" in item
                    and actual.get("expireAfterSeconds") != 0
                ):
                    continue
                found = True
            if not found:
                raise StorageUnavailable("Required production index missing")
        return db
    except PyMongoError:
        raise StorageUnavailable("Production database unavailable") from None
