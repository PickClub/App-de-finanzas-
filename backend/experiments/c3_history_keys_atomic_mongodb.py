"""Opt-in runner: one NEW retained synthetic database per invocation.

python3 -B -m backend.experiments.c3_history_keys_atomic_mongodb --run-mongo
No production endpoints, dotenv, existing database reads, failpoints or indexes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import patch
import uuid

from pymongo import MongoClient, monitoring, ReadPreference
from pymongo.errors import DuplicateKeyError, OperationFailure
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from pymongo.uri_parser import parse_uri

from backend.experiments.c3_history_keys_atomic import Writer, Conflict, materialized, public
from backend.experiments.test_c3_history_keys_contract import inspect_keys

URI = "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true"
PREFIX = "test_c3_history_atomic_"
ROOT = Path(__file__).resolve().parents[2]


class Audit(monitoring.CommandListener):
    def __init__(self, name):
        self.name, self.events, self.violations = name, [], []

    def started(self, event):
        entry = [event.database_name, event.command_name]
        self.events.append(entry)
        admin = {"hello", "listDatabases", "commitTransaction", "abortTransaction", "endSessions"}
        allowed = {"create", "listCollections", "insert", "find", "update", "delete", "aggregate", "getMore", "killCursors"}
        valid = ((event.database_name == "admin" and event.command_name in admin)
                 or (event.database_name == self.name and event.command_name in allowed))
        if event.command_name == "listDatabases":
            valid = valid and event.command.get("filter") == {"name": self.name} and event.command.get("nameOnly") is True
        if not valid:
            self.violations.append(entry)

    def succeeded(self, event):
        pass

    def failed(self, event):
        pass


def snapshot_files():
    files = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files
            if "history_keys_atomic" not in p and p != "docs/c3-history-keys-atomic.md"}


class MongoCases(unittest.TestCase):
    run_prefix = ""

    def setUp(self):
        self.prefix = self.run_prefix + self._testMethodName + "_"
        self.a, self.b = self.prefix + "A", self.prefix + "B"
        self.db.accounts.insert_many([{"_id": self.a, "user_id": "default-user", "balance": 1000},
                                      {"_id": self.b, "user_id": "default-user", "balance": 1000}])
        self.writer = Writer(self.db)

    def run_tx(self, operation, commit_fault=False):
        # Same driver semantics (sync equivalent), existing majority/snapshot/PRIMARY.
        # Does not change or call production financial transaction handlers.
        for attempt in range(2):
            try:
                with self.client.start_session() as session:
                    options = dict(read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority"),
                                   read_preference=ReadPreference.PRIMARY)
                    if not commit_fault:
                        return session.with_transaction(operation, **options)
                    real_commit, calls = session.commit_transaction, []

                    def lost_confirmation():
                        real_commit()
                        calls.append(1)
                        if len(calls) == 1:
                            raise OperationFailure("Synthetic lost commit confirmation", details={"errorLabels": ["UnknownTransactionCommitResult"]})

                    with patch.object(session, "commit_transaction", side_effect=lost_confirmation):
                        result = session.with_transaction(operation, **options)
                    self.assertGreaterEqual(len(calls), 2)
                    return result
            except DuplicateKeyError:
                if attempt:
                    raise

    def row(self, name="movement", kind="expense", **changes):
        return {"id": self.prefix + name, "user_id": "default-user", "date": "20261001T120000.123456+010203",
                "amount": 70, "type": kind, "account_id": self.a, **changes}

    def create(self, row=None, payload=None, fail=None, commit_fault=False):
        row = row or self.row()
        payload = payload or {"date": row["date"], "amount": row["amount"], "mode": "expense"}
        result = self.run_tx(lambda s: self.writer.create(row, row["id"], payload, s, fail), commit_fault)
        return row, payload, result

    def balance(self, aid):
        return self.db.accounts.find_one({"_id": aid})["balance"]

    def movement(self, row):
        return self.db.transactions.find_one({"_id": row["id"]})

    def assert_synced(self, row, state="ready"):
        stored = self.movement(row)
        self.assertEqual(inspect_keys(stored, stored.get("_history_keys")), state)
        return stored

    def scoped_snapshot(self):
        # Only this newly created synthetic database, never an existing database.
        return {name: list(self.db[name].find({}).sort("_id", 1))
                for name in ("accounts", "transactions", "receipts", "synthetic_intents")}

    def test_01_origins_and_transfer_both_accounts(self):
        for origin in ("expense", "income", "debt", "bill", "goal", "recurring", "r4_bill", "r4_recurring"):
            with self.subTest(origin=origin):
                kind = "income" if origin == "income" else "transfer" if origin == "goal" else "expense"
                row = self.row(origin, kind, to_account_id=self.b) if kind == "transfer" else self.row(origin, kind)
                if origin.startswith("r4"):
                    row.update(_shared_obligation_id="synthetic", _shared_intent={"payload": {"date": None}})
                before_a, before_b = self.balance(self.a), self.balance(self.b)
                original = copy.deepcopy(row)
                self.create(row)
                stored = self.assert_synced(row)
                self.assertEqual({k: v for k, v in stored.items() if k not in {"_id", "_history_keys"}}, original)
                self.assertEqual(self.balance(self.a), before_a + (70 if kind == "income" else -70))
                self.assertEqual(self.balance(self.b), before_b + (70 if kind == "transfer" else 0))

    def test_02_edit_final_document_and_idempotent_original(self):
        row, payload, original_response = self.create()
        receipt = self.db.receipts.find_one({"_id": row["id"]})
        journal = self.db.synthetic_intents.find_one({"_id": row["id"]})
        self.run_tx(lambda s: self.writer.edit(row["id"], {"amount": 80, "date": "2026-W40-5T12:00:00Z"}, s))
        stored = self.assert_synced(row)
        self.assertEqual(stored["amount"], 80)
        self.assertEqual(stored["date"], "2026-W40-5T12:00:00Z")
        self.assertEqual(self.balance(self.a), 920)
        self.assertEqual(self.create(row, payload)[2], original_response)
        self.assertEqual(self.db.receipts.find_one({"_id": row["id"]}), receipt)
        self.assertEqual(self.db.synthetic_intents.find_one({"_id": row["id"]}), journal)
        self.assertEqual(self.balance(self.a), 920)

    def test_03_unverifiable_date_is_not_financial_rejection(self):
        row = self.row(date="2026-1001T120000Z")
        self.create(row)
        self.assertEqual(self.assert_synced(row, "unverifiable")["date"], row["date"])
        self.assertEqual(self.balance(self.a), 930)
        self.run_tx(lambda s: self.writer.edit(row["id"], {"date": "2026-10-01"}, s))
        self.assert_synced(row)
        self.assertEqual(self.balance(self.a), 930)

    def test_04_missing_and_null_date_preserved(self):
        for absent in (True, False):
            row = self.row(str(absent), date=None)
            if absent:
                row.pop("date")
            self.create(row, {"amount": 70, "date": None})
            stored = self.assert_synced(row, "unverifiable")
            self.assertEqual("date" in stored, not absent)
        self.assertEqual(self.balance(self.a), 860)

    def test_05_unlink_restore_and_admin_revision_without_rekey(self):
        row, _, _ = self.create(self.row(bill_id="bill", bill_payment_id="receipt", recurring_payment_id="rec", recurring_record_id="record"))
        original = self.assert_synced(row)["_history_keys"]
        self.run_tx(lambda s: self.writer.unlink(row["id"], ["bill_id", "bill_payment_id", "recurring_payment_id", "recurring_record_id"], s))
        self.run_tx(lambda s: self.writer.unlink(row["id"], [], s, {"recurring_payment_id": "rec", "recurring_record_id": "record"}))
        self.run_tx(lambda s: self.db.transactions.update_one({"_id": row["id"]}, {"$inc": {"_reference_revision": 1}}, session=s))
        self.assertEqual(self.assert_synced(row)["_history_keys"], original)
        self.assertEqual(self.balance(self.a), 930)

    def test_06_delete_and_late_replay_preserve_tombstone(self):
        row, payload, _ = self.create()
        self.run_tx(lambda s: self.writer.annul(row["id"], s))
        self.run_tx(lambda s: self.writer.annul(row["id"], s))
        self.assertIsNone(self.movement(row))
        self.assertEqual(self.balance(self.a), 1000)
        self.assertEqual(self.create(row, payload)[2]["state"], "annulled")
        self.assertIsNone(self.movement(row))
        self.assertEqual(self.balance(self.a), 1000)

    def test_07_create_rollback_after_each_write(self):
        for fail in ("after_movement", "after_balance", "after_receipt"):
            before = self.scoped_snapshot()
            with self.assertRaises(RuntimeError):
                self.create(self.row(fail), fail=fail)
            self.assertEqual(self.scoped_snapshot(), before)

    def test_08_edit_rollback_and_delete_rollback(self):
        row, _, _ = self.create()
        before = self.scoped_snapshot()
        with self.assertRaises(RuntimeError):
            self.run_tx(lambda s: self.writer.edit(row["id"], {"amount": 99, "date": "2030-01-01"}, s, fail=True))
        self.assertEqual(self.scoped_snapshot(), before)
        with self.assertRaises(RuntimeError):
            self.run_tx(lambda s: self.writer.annul(row["id"], s, fail=True))
        self.assertEqual(self.scoped_snapshot(), before)

    def test_09_original_intent_repeated_or_changed(self):
        row, payload, response = self.create()
        before = self.scoped_snapshot()
        self.assertEqual(self.create(row, payload)[2], response)
        with self.assertRaises(Conflict):
            self.create(row, {**payload, "amount": 71})
        self.assertEqual(self.scoped_snapshot(), before)

    def test_10_concurrent_edits_retry_fresh_read(self):
        row, _, _ = self.create()
        barrier = threading.Barrier(2)
        attempts, lock = {}, threading.Lock()

        def worker(name):
            attempts[name] = 0
            def operation(session):
                with lock:
                    attempts[name] += 1
                    first = attempts[name] == 1
                def read(old):
                    if first:
                        barrier.wait(timeout=15)
                old = self.db.transactions.find_one({"_id": row["id"]}, session=session)
                return self.writer.edit(row["id"], {"amount": old["amount"] + 1}, session, on_read=read)
            return self.run_tx(operation)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ("one", "two")))
        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(sum(attempts.values()), 3)
        self.assertEqual(self.assert_synced(row)["amount"], 72)
        self.assertEqual(self.balance(self.a), 928)
        self.measurements["edit_attempts"] = attempts

    def test_11_concurrent_same_intent_no_duplicate(self):
        row = self.row()
        barrier = threading.Barrier(2)
        def worker(_):
            barrier.wait(timeout=15)
            return self.create(row)[2]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.db.transactions.count_documents({"_id": row["id"]}), 1)
        self.assertEqual(self.balance(self.a), 930)
        self.assert_synced(row)

    def test_12_concurrent_distinct_equal_intents_two_movements(self):
        barrier = threading.Barrier(2)
        def worker(n):
            barrier.wait(timeout=15)
            return self.create(self.row(str(n)))[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(worker, range(2)))
        for row in rows:
            self.assert_synced(row)
        self.assertEqual(self.balance(self.a), 860)
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])

    def test_13_driver_retries_unknown_commit_without_callback_replay(self):
        calls = []
        row, payload = self.row(), {"amount": 70, "date": None}
        def operation(session):
            calls.append(1)
            return self.writer.create(row, row["id"], payload, session)
        self.run_tx(operation, commit_fault=True)
        self.assertEqual(len(calls), 1)
        self.assert_synced(row)
        self.assertEqual(self.balance(self.a), 930)

    def test_14_lost_response_and_restart_manual_recovery(self):
        row, payload, _ = self.create(payload={"amount": 70, "date": None})
        # Real commit already happened; simulate loss at the application boundary.
        saved_intent = json.loads(json.dumps({"id": row["id"], "payload": payload}))
        self.writer = Writer(self.db)  # New adapter, no volatile intent state.
        before = self.scoped_snapshot()
        self.assertEqual(self.run_tx(lambda s: self.writer.reconcile(saved_intent["id"], saved_intent["payload"], s)), "confirmed")
        self.assertEqual(self.scoped_snapshot(), before)
        self.create(row, saved_intent["payload"])
        self.assertEqual(self.scoped_snapshot(), before)

    def test_15_transient_failure_aborts_and_retries_whole_callback(self):
        row, attempts = self.row(), []
        def operation(session):
            attempts.append(1)
            result = self.writer.create(row, row["id"], {"amount": 70}, session)
            if len(attempts) == 1:
                raise OperationFailure("Synthetic transient", details={"errorLabels": ["TransientTransactionError"]})
            return result
        self.run_tx(operation)
        self.assertEqual(len(attempts), 2)
        self.assert_synced(row)
        self.assertEqual(self.balance(self.a), 930)

    def test_16_public_insert_edit_recovery_no_private_keys(self):
        row, _, response = self.create(self.row(_shared_intent={"payload": "opaque"}))
        detail = public(self.assert_synced(row))
        edited = self.run_tx(lambda s: self.writer.edit(row["id"], {"notes": "description"}, s))
        for result in (response, detail, edited, public({"items": [self.movement(row)], "recovery": self.movement(row)})):
            text = repr(result)
            self.assertNotIn("_history", text)
            self.assertNotIn("_shared_intent", text)

    def test_17_no_transaction_no_write(self):
        before = self.scoped_snapshot()
        with self.assertRaises(RuntimeError):
            self.writer.create(self.row(), "id", {}, None)
        self.assertEqual(self.scoped_snapshot(), before)

    def test_18_concurrent_annul_exactly_once(self):
        row, _, _ = self.create()
        barrier = threading.Barrier(2)
        def worker(_):
            barrier.wait(timeout=15)
            return self.run_tx(lambda s: self.writer.annul(row["id"], s))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertTrue(all(r["state"] == "annulled" for r in results))
        self.assertIsNone(self.movement(row))
        self.assertEqual(self.balance(self.a), 1000)

    def test_19_missing_account_partial_transfer_rollback(self):
        row = self.row(kind="transfer", to_account_id=self.prefix + "missing")
        before = self.scoped_snapshot()
        with self.assertRaises(Conflict):
            self.create(row)
        self.assertEqual(self.scoped_snapshot(), before)

    def test_20_change_account_transfer_and_omitted_date(self):
        row, _, _ = self.create()
        self.run_tx(lambda s: self.writer.edit(row["id"], {"account_id": self.b}, s))
        self.assertEqual(self.balance(self.a), 1000)
        self.assertEqual(self.balance(self.b), 930)
        self.assertEqual(self.assert_synced(row)["date"], row["date"])
        self.run_tx(lambda s: self.writer.edit(row["id"], {"type": "transfer", "to_account_id": self.a}, s))
        self.assert_synced(row)
        self.assertEqual(self.balance(self.a), 1070)
        self.assertEqual(self.balance(self.b), 930)

    def test_21_reader_never_sees_intermediate_financial_or_key_state(self):
        row, _, _ = self.create()
        before = self.scoped_snapshot()
        written, release = threading.Event(), threading.Event()
        def operation(session):
            result = self.writer.edit(row["id"], {"amount": 99, "date": "2027-01-01"}, session)
            written.set()
            if not release.wait(timeout=15):
                raise RuntimeError("Synthetic observer timeout")
            return result
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_tx, operation)
            try:
                self.assertTrue(written.wait(timeout=15))
                self.assertEqual(self.scoped_snapshot(), before)
            finally:
                release.set()
            future.result(timeout=15)
        self.assertEqual(self.assert_synced(row)["amount"], 99)
        self.assertEqual(self.balance(self.a), 901)

    def test_22_concurrent_same_id_different_intent_rejected(self):
        row, barrier = self.row(), threading.Barrier(2)
        def worker(amount):
            barrier.wait(timeout=15)
            try:
                self.create({**row, "amount": amount}, {"amount": amount, "date": row["date"]})
                return "confirmed"
            except Conflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, (60, 70)))
        self.assertEqual(sorted(results), ["confirmed", "conflict"])
        stored = self.assert_synced(row)
        self.assertEqual(self.balance(self.a), 1000 - stored["amount"])
        self.assertEqual(self.db.receipts.count_documents({"_id": row["id"]}), 1)

    def test_23_unresolved_application_confirmation_is_not_rollback(self):
        row, payload = self.row(), {"date": None, "amount": 70}
        try:
            self.create(row, payload)
            raise OperationFailure("Synthetic application confirmation lost", details={"errorLabels": ["UnknownTransactionCommitResult"]})
        except OperationFailure as error:
            self.assertTrue(error.has_error_label("UnknownTransactionCommitResult"))
            local_state = "uncertain"
        self.assertEqual(local_state, "uncertain")
        self.assert_synced(row)
        self.assertEqual(self.balance(self.a), 930)
        before = self.scoped_snapshot()
        self.assertEqual(self.run_tx(lambda s: self.writer.reconcile(row["id"], payload, s)), "confirmed")
        self.assertEqual(self.scoped_snapshot(), before)

    def test_24_r4_administrative_mark_no_movement_or_balance_change(self):
        before = self.scoped_snapshot()
        original_payload = {"mode": "mark", "settles": True, "date": None, "amount": 70}
        def operation(session):
            self.db.synthetic_intents.insert_one({"_id": self.prefix + "mark", "original_payload": original_payload,
                                                 "administrative": True}, session=session)
        self.run_tx(operation)
        after = self.scoped_snapshot()
        self.assertEqual(after["transactions"], before["transactions"])
        self.assertEqual(after["accounts"], before["accounts"])
        self.assertEqual(after["receipts"], before["receipts"])
        self.assertEqual(len(after["synthetic_intents"]), len(before["synthetic_intents"]) + 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-mongo", action="store_true", required=True)
    parser.parse_args()
    assert subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() == "conflict_280926_1750"
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == "768a333c41a2e20e63ccfdffba52f63240eeb161"
    parsed = parse_uri(URI)
    assert parsed["nodelist"] == [("127.0.0.1", 27018)] and parsed["database"] is None
    assert parsed["options"]["replicaset"] == "app_finanzas_dev_rs" and parsed["options"]["directconnection"]
    name = PREFIX + uuid.uuid4().hex
    assert name.startswith(PREFIX) and len(name) == len(PREFIX) + 32
    before = snapshot_files()
    audit = Audit(name)
    # Two workers plus main; one reused client. Bounds only for this short local experiment.
    client = MongoClient(URI, connect=False, event_listeners=[audit], maxPoolSize=4,
                         serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=30000)
    report = {"database": name, "uri": URI, "retained": True, "synthetic": True,
              "started_at": datetime.now(timezone.utc).isoformat(), "production_connected": False}
    output = Path(__file__).parent / "results" / (name + ".json")
    print("NEW_SYNTHETIC_DATABASE", name, flush=True)
    try:
        hello = client.admin.command("hello")
        assert client.address == ("127.0.0.1", 27018) and hello.get("isWritablePrimary")
        assert hello.get("setName") == "app_finanzas_dev_rs" and hello.get("logicalSessionTimeoutMinutes")
        assert hello.get("maxWireVersion", 0) >= 7
        assert not client.admin.command({"listDatabases": 1, "filter": {"name": name}, "nameOnly": True})["databases"]
        # Only handle supplied to the writer; no target selectable from env/arguments.
        db = client[name]
        for collection in ("accounts", "transactions", "receipts", "synthetic_intents"):
            db.create_collection(collection)
        MongoCases.client, MongoCases.db, MongoCases.measurements = client, db, {}
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(MongoCases)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        report.update(tests=result.testsRun, failures=[t.id() for t, _ in result.failures],
                      errors=[t.id() for t, _ in result.errors], measurements=MongoCases.measurements,
                      passed=result.testsRun - len(result.failures) - len(result.errors),
                      command_counts={command: sum(c == command for _, c in audit.events) for _, command in audit.events},
                      databases_accessed=sorted({d for d, _ in audit.events}), violations=audit.violations,
                      previous_files_unchanged=before == snapshot_files())
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        print("REPORT", output)
        assert not audit.violations and report["previous_files_unchanged"]
        if not result.wasSuccessful():
            raise SystemExit(1)
    finally:
        client.close()  # Never drop data or databases, including failed experiments.


if __name__ == "__main__":
    main()
