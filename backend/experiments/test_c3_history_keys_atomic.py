"""Offline checks for the experimental writer; no client construction."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest

from backend.experiments.c3_history_keys_atomic import materialized, fingerprint, public, require_session, Writer
from backend.experiments.c3_history_keys_atomic_mongodb import Audit
from backend.experiments.test_c3_history_keys_contract import fixture, inspect_keys


class AtomicOffline(unittest.TestCase):
    def test_materialization_preserves_original_and_journal(self):
        row = fixture(_shared_intent={"payload": {"date": None}}, request_fingerprint="original")
        original = copy.deepcopy(row)
        result = materialized(row)
        self.assertEqual(row, original)
        self.assertEqual({k: v for k, v in result.items() if k != "_history_keys"}, original)
        self.assertEqual(inspect_keys(result, result["_history_keys"]), "ready")

    def test_invalid_date_does_not_rewrite_original(self):
        row = fixture(date="bad")
        self.assertEqual(materialized(row)["_history_keys"]["state"], "unverifiable")
        self.assertEqual(row["date"], "bad")

    def test_original_intent_independent_of_keys(self):
        payload = {"amount": 70, "date": None}
        before = fingerprint(payload)
        materialized(fixture(date="2026-10-02", amount=99))
        self.assertEqual(fingerprint(payload), before)
        self.assertNotEqual(fingerprint({**payload, "amount": 71}), before)

    def test_existing_transaction_required(self):
        for s in (None, SimpleNamespace(in_transaction=False)):
            with self.assertRaises(RuntimeError):
                require_session(s)
        require_session(SimpleNamespace(in_transaction=True))

    def test_only_synthetic_database_can_construct_writer(self):
        with self.assertRaises(RuntimeError):
            Writer(SimpleNamespace(name="development_local_finanzas"))

    def test_recursive_sanitizing_preserves_financial_fields(self):
        row = materialized(fixture(_shared_intent={"opaque": True}))
        result = public({"items": [row], "recovery": row})
        self.assertEqual(result["items"][0]["amount"], 70)
        self.assertNotIn("_history", repr(result))
        self.assertNotIn("_shared_intent", repr(result))

    def test_creation_metadata_check_allowed_only_in_new_database(self):
        audit = Audit("test_c3_history_atomic_synthetic")
        audit.started(SimpleNamespace(database_name=audit.name, command_name="listCollections", command={}))
        self.assertEqual(audit.violations, [])
        audit.started(SimpleNamespace(database_name="other", command_name="listCollections", command={}))
        self.assertEqual(len(audit.violations), 1)

    def test_audit_forbids_drop_indexes_other_database_and_unfiltered_list(self):
        audit = Audit("test_c3_history_atomic_synthetic")
        for database, command, body in ((audit.name, "dropDatabase", {}), (audit.name, "createIndexes", {}),
                                         ("other", "find", {}), ("admin", "listDatabases", {"nameOnly": True})):
            audit.started(SimpleNamespace(database_name=database, command_name=command, command=body))
        self.assertEqual(len(audit.violations), 4)

    def test_no_nested_transaction_or_new_client_in_adapter(self):
        path = Path(__file__).with_name("c3_history_keys_atomic.py")
        tree = ast.parse(path.read_text())
        names = [n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
                 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, (ast.Attribute, ast.Name))]
        self.assertFalse(set(names) & {"start_session", "start_transaction", "with_transaction", "MongoClient"})


if __name__ == "__main__":
    unittest.main()
