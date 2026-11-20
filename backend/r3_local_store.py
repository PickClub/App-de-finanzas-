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

TARGET = "mongodb://127.0.0.1:27118/r3_security_synthetic?directConnection=true&replicaSet=r3_security_test_rs"
DATABASE = "r3_security_synthetic"
MEMBER = "127.0.0.1:27118"
REPLICA = "r3_security_test_rs"


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
