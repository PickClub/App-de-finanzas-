"""Shared transactional authentication store and financial session fence."""

from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from time import sleep
from uuid import UUID

from pymongo import ReadPreference
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from backend.auth_core import (
    AccountStatus,
    Challenge,
    Identity,
    InvalidCredentials,
    Purpose,
    Refresh,
    Session,
    StorageUnavailable,
)

OPTIONS = dict(
    read_concern=ReadConcern("snapshot"),
    write_concern=WriteConcern("majority"),
    read_preference=ReadPreference.PRIMARY,
)


ACCOUNT_DATA_COLLECTIONS = (
    "accounts",
    "transactions",
    "categories",
    "debts",
    "debt_payments",
    "bills",
    "bill_payments",
    "recurring_payments",
    "recurring_payment_records",
    "recurring_templates",
    "budgets",
    "saving_goals",
    "goal_contributions",
    "notes",
    "shared_obligations",
    "shared_tracking_intents",
    "movement_receipts",
)


class Transaction:
    profile_name = "PickWallet"

    def __init__(self, database, session):
        self.db, self.tx = database, session

    def load(self, collection, query, model):
        doc = self.db[collection].find_one(query, session=self.tx)
        return self.decode(doc, model) if doc is not None else None

    @staticmethod
    def decode(doc, model):
        fields = {
            key: value
            for key, value in doc.items()
            if key in model.__dataclass_fields__
        }
        if model is Identity:
            fields["status"] = AccountStatus(fields["status"])
        if model is Challenge:
            fields["purpose"] = Purpose(fields["purpose"])
        return model(**fields)

    def save(self, collection, key, value):
        doc = asdict(value)
        if isinstance(value, Identity):
            doc["status"] = value.status.value
        if isinstance(value, Challenge):
            doc["purpose"] = value.purpose.value
        self.db[collection].update_one(
            {"_id": key}, {"$set": doc}, upsert=True, session=self.tx
        )

    def erase_account(self, user_id):
        try:
            identifier = UUID(user_id)
        except (TypeError, ValueError, AttributeError):
            raise InvalidCredentials("Invalid credentials") from None
        if identifier.version != 4 or str(identifier) != user_id:
            raise InvalidCredentials("Invalid credentials")

        # Lock the identity and every family before touching financial rows. Login,
        # recovery, rotation and the financial write fence contend on these writes.
        removed = self.db.auth_users.delete_one(
            {"_id": user_id, "status": AccountStatus.ACTIVE.value}, session=self.tx
        )
        if removed.deleted_count != 1:
            raise InvalidCredentials("Invalid credentials")
        owner = {"user_id": user_id}
        families = self.db.auth_sessions.find(owner, {"_id": 1}, session=self.tx)
        for family in families:
            self.db.auth_refresh.delete_many(
                {"family_id": family["_id"]}, session=self.tx
            )
        self.db.auth_sessions.delete_many(owner, session=self.tx)
        self.db.auth_challenges.delete_many(owner, session=self.tx)
        for name in ACCOUNT_DATA_COLLECTIONS:
            self.db[name].delete_many(owner, session=self.tx)
        self.db.users.delete_many({"id": user_id}, session=self.tx)

    def identity(self, user_id):
        return self.load("auth_users", {"_id": user_id}, Identity)

    def identity_by_email(self, email):
        return self.load("auth_users", {"email": email}, Identity)

    def save_identity(self, identity):
        self.save("auth_users", identity.id, identity)
        if identity.status is AccountStatus.ACTIVE:
            self.db.users.update_one(
                {"id": identity.id},
                {
                    "$setOnInsert": {
                        "id": identity.id,
                        "name": self.profile_name,
                        "currency": "USD",
                    }
                },
                upsert=True,
                session=self.tx,
            )

    def session(self, family_id):
        return self.load("auth_sessions", {"_id": family_id}, Session)

    def session_by_access(self, digest):
        return self.load("auth_sessions", {"access_digest": digest}, Session)

    def sessions(self, user_id):
        # Same identity write serializes session creation, password changes and revoke-all.
        self.db.auth_users.update_one(
            {"_id": user_id}, {"$inc": {"revision": 1}}, session=self.tx
        )
        return [
            self.decode(doc, Session)
            for doc in self.db.auth_sessions.find({"user_id": user_id}, session=self.tx)
        ]

    def save_session(self, session):
        self.save("auth_sessions", session.id, session)

    def refresh(self, digest):
        return self.load("auth_refresh", {"_id": digest}, Refresh)

    def save_refresh(self, digest, refresh):
        self.save("auth_refresh", digest, refresh)

    def challenge(self, digest):
        return self.load("auth_challenges", {"_id": digest}, Challenge)

    def save_challenge(self, digest, challenge):
        # A concurrent deletion must conflict with issuance, even when there is
        # no existing challenge row for the deletion transaction to lock.
        result = self.db.auth_users.update_one(
            {
                "_id": challenge.user_id,
                "credential_version": challenge.credential_version,
            },
            {"$inc": {"revision": 1}},
            session=self.tx,
        )
        if result.matched_count != 1:
            raise InvalidCredentials("Invalid credentials")
        self.save("auth_challenges", digest, challenge)


class AbortedAuthTransaction(StorageUnavailable):
    """A driver-labeled transient abort can retry with a fresh snapshot."""


def retry_auth(operation, *args):
    for attempt in range(5):
        try:
            return operation(*args)
        except AbortedAuthTransaction:
            if attempt == 4:
                raise
            sleep(0.01 * (attempt + 1))


class Store:
    transaction_type = Transaction

    def __init__(self, database):
        self.db = database
        self.unavailable = False

    @contextmanager
    def transaction(self):
        if self.unavailable:
            raise StorageUnavailable("Authentication unavailable")
        try:
            with self.db.client.start_session() as session:
                with session.start_transaction(**OPTIONS):
                    yield self.transaction_type(self.db, session)
        except PyMongoError as error:
            if error.has_error_label(
                "TransientTransactionError"
            ) and not error.has_error_label("UnknownTransactionCommitResult"):
                raise AbortedAuthTransaction(
                    "Authentication transaction aborted"
                ) from None
            raise StorageUnavailable("Authentication transaction unavailable") from None


class Fence:
    def __init__(self, database):
        self.db = database
        self.before = None
        self.after = None

    @asynccontextmanager
    async def __call__(self, principal):
        async with await self.db.client.start_session() as session:
            async with session.start_transaction(**OPTIONS):
                if self.before:
                    await self.before(principal)
                now = datetime.now(timezone.utc)
                result = await self.db.auth_sessions.update_one(
                    {
                        "_id": principal.family_id,
                        "user_id": principal.user_id,
                        "access_digest": principal.access_digest,
                        "revoked": False,
                        "access_expires": {"$gt": now},
                        "idle_expires": {"$gt": now},
                        "absolute_expires": {"$gt": now},
                    },
                    {"$inc": {"fence": 1}},
                    session=session,
                )
                identity = await self.db.auth_users.find_one(
                    {
                        "_id": principal.user_id,
                        "status": "active",
                    },
                    session=session,
                )
                if result.matched_count != 1 or identity is None:
                    raise InvalidCredentials("Invalid credentials")
                yield session
                if self.after:
                    await self.after(principal)
