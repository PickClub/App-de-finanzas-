"""Experimental synchronous writer model; never imported by production routes.

Uses the approved offline oracle. This is not MoneyFlow's financial engine.
Only a caller-owned transaction is accepted; no nested transactions or clients.
"""
import copy
import hashlib
import json
import math

from backend.experiments.test_c3_history_keys_contract import build_keys, inspect_keys, public_model
from backend.shared_obligations import public_financial_document


class Conflict(Exception):
    pass


def public(value):
    return public_financial_document(public_model(value))


def fingerprint(payload):
    # Synthetic intent only. Never replaces production fingerprint algorithms.
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def materialized(row):
    result = copy.deepcopy(row)
    result["_history_keys"] = build_keys(result)
    return result


def require_session(session):
    if session is None or not session.in_transaction:
        raise RuntimeError("An existing transaction is required")


class Writer:
    def __init__(self, database):
        if not database.name.startswith("test_c3_history_atomic_"):
            raise RuntimeError("Synthetic database required")
        self.db = database

    def effects(self, row, sign, session):
        amount = row["amount"]
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
            raise Conflict("Synthetic financial validation")
        kind = row["type"]
        pairs = [(row["account_id"], sign * amount * (1 if kind == "income" else -1))]
        if kind == "transfer":
            if row["account_id"] == row["to_account_id"]:
                raise Conflict("Synthetic transfer validation")
            pairs.append((row["to_account_id"], sign * amount))
        for aid, delta in pairs:
            result = self.db.accounts.update_one({"_id": aid, "user_id": row["user_id"]},
                                                 {"$inc": {"balance": delta}}, session=session)
            if result.matched_count != 1:
                raise Conflict("Synthetic account missing")

    def create(self, row, operation_id, payload, session, fail=None):
        require_session(session)
        original = copy.deepcopy(row)
        digest = fingerprint(payload)
        receipt = self.db.receipts.find_one({"_id": operation_id}, session=session)
        if receipt:
            if receipt["request_fingerprint"] != digest or receipt["payload"] != payload:
                raise Conflict("Intent mismatch")
            if receipt["user_id"] != row["user_id"] or receipt["transaction_id"] != row["id"]:
                raise Conflict("Identity mismatch")
            return public(receipt)
        self.db.transactions.insert_one(materialized({**original, "_id": original["id"]}), session=session)
        if fail == "after_movement":
            raise RuntimeError("Synthetic intermediate failure")
        self.effects(original, 1, session)
        if fail == "after_balance":
            raise RuntimeError("Synthetic intermediate failure")
        receipt = {"_id": operation_id, "user_id": row["user_id"], "transaction_id": row["id"],
                   "request_fingerprint": digest, "payload": copy.deepcopy(payload), "state": "confirmed"}
        self.db.receipts.insert_one(receipt, session=session)
        self.db.synthetic_intents.insert_one({"_id": operation_id, "fingerprint": digest,
                                              "original_payload": copy.deepcopy(payload)}, session=session)
        if fail == "after_receipt":
            raise RuntimeError("Synthetic intermediate failure")
        return public(receipt)

    def edit(self, tid, changes, session, fail=False, on_read=None):
        require_session(session)
        old = self.db.transactions.find_one({"_id": tid}, session=session)
        if old is None:
            raise Conflict("Synthetic movement missing")
        if on_read:
            on_read(old)
        if any(k in changes for k in ("_id", "id", "user_id", "_history_keys", "request_fingerprint", "_shared_intent")):
            raise Conflict("Protected field")
        final = {**old, **copy.deepcopy(changes)}
        self.effects(old, -1, session)
        self.effects(final, 1, session)
        updated = {**copy.deepcopy(changes), "_history_keys": build_keys(final)}
        result = self.db.transactions.update_one({"_id": tid}, {"$set": updated}, session=session)
        if result.matched_count != 1 or fail:
            raise RuntimeError("Synthetic edit failure")
        return public(final)

    def unlink(self, tid, fields, session, restore=None):
        require_session(session)
        allowed = {"bill_id", "bill_payment_id", "recurring_payment_id", "recurring_record_id", "goal_id", "goal_contribution_id"}
        if not set(fields) <= allowed or not set(restore or {}) <= allowed:
            raise Conflict("Not an administrative link")
        updates = {}
        if fields:
            updates["$unset"] = {f: "" for f in fields}
        if restore:
            updates["$set"] = copy.deepcopy(restore)
        self.db.transactions.update_one({"_id": tid}, updates, session=session)

    def annul(self, operation_id, session, fail=False):
        require_session(session)
        receipt = self.db.receipts.find_one({"_id": operation_id}, session=session)
        if not receipt:
            raise Conflict("Intent missing")
        if receipt["state"] == "annulled":
            return public(receipt)
        row = self.db.transactions.find_one({"_id": receipt["transaction_id"]}, session=session)
        if row is None:
            raise Conflict("Broken synthetic link")
        self.effects(row, -1, session)
        self.db.transactions.delete_one({"_id": row["_id"]}, session=session)
        self.db.receipts.update_one({"_id": operation_id}, {"$set": {"state": "annulled"}}, session=session)
        if fail:
            raise RuntimeError("Synthetic annul failure")
        return public({**receipt, "state": "annulled"})

    def reconcile(self, operation_id, payload, session):
        require_session(session)
        receipt = self.db.receipts.find_one({"_id": operation_id}, session=session)
        if not receipt:
            return "unverifiable"  # Absence is never proof of rollback.
        if receipt["payload"] != payload or receipt["request_fingerprint"] != fingerprint(payload):
            raise Conflict("Intent mismatch")
        journal = self.db.synthetic_intents.find_one({"_id": operation_id}, session=session)
        if not journal or journal["original_payload"] != payload or journal["fingerprint"] != fingerprint(payload):
            return "unverifiable"
        if receipt["state"] == "annulled":
            return "annulled" if self.db.transactions.find_one({"_id": receipt["transaction_id"]}, session=session) is None else "unverifiable"
        row = self.db.transactions.find_one({"_id": receipt["transaction_id"]}, session=session)
        if row is None or inspect_keys(row, row.get("_history_keys")) not in {"ready", "unverifiable"}:
            return "unverifiable"
        return "confirmed"
