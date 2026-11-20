"""R3 synthetic replica adapter. No implicit destination, server import, or dotenv."""

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

from backend.auth_mongodb import (
    OPTIONS,
    AbortedAuthTransaction,
    Fence,
    Store as SharedStore,
    Transaction as SharedTransaction,
    retry_auth,
)

TARGET = "mongodb://127.0.0.1:27120/pw_settlement_test?directConnection=true&replicaSet=pw_settlement_test_rs"
DATABASE = "pw_settlement_test"
MEMBER = "127.0.0.1:27120"
REPLICA = "pw_settlement_test_rs"


def connect(target):
    if target != TARGET:
        raise ValueError("Explicit authorized R3 destination required")
    client = MongoClient(target, serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        hello = client.admin.command("hello")
        if (
            hello.get("setName"),
            hello.get("hosts"),
            hello.get("isWritablePrimary"),
        ) != (REPLICA, [MEMBER], True):
            raise ValueError("Unexpected replica identity or topology")
        return client
    except BaseException:
        client.close()
        raise


def async_client(target):
    # Independently prove the same topology before constructing the Motor client.
    with connect(target):
        pass
    return AsyncIOMotorClient(target, serverSelectionTimeoutMS=3000, tz_aware=True)


class Transaction(SharedTransaction):
    profile_name = "Synthetic"


class Store(SharedStore):
    transaction_type = Transaction
