"""Offline adversarial contract tests. No server import, MongoClient or files."""
from copy import deepcopy
from dataclasses import replace
import unittest
from uuid import UUID

from bson import BSON
from bson.binary import Binary
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from bson.objectid import ObjectId

from backend.history_keys import derive_history_keys, strip_history_metadata
from backend.experiments.c3_history_provision_contract import (
    Authorization, Conflict, MemoryLedger, Observation, Target, batches,
    checkpoint, diagnose, exact, metadata, prepare, verify,
)

ENV = "7ac21532-658e-438b-a5c8-c08b382673a2"
OTHER_ENV = "38c7280b-92c5-4ee1-8e81-248c729f5a54"
REVISION = "1f5836618880ed1c660923b32147cb8c2d1f5b0d"


def row(**fields):
    return {"_id": ObjectId(), "id": "movement-1", "user_id": "default-user",
            "date": "20261001T120000.123456Z", "amount": Decimal128("70.1200"),
            "account_id": "synthetic-account", "_shared_intent": {"original": "unchanged"},
            "request_fingerprint": "original", **fields}


def financial_bytes(document):
    return BSON.encode({k: v for k, v in document.items() if k != "_history_keys"})


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.target = Target("mongodb://127.0.0.1:27018/?replicaSet=synthetic", "synthetic_contract",
                             "transactions", Binary(UUID(ENV).bytes, 4), ENV)
        self.auth = Authorization(self.target, "synthetic-run", REVISION, 1, 1,
                                  ("diagnose", "apply", "verify", "revert"), approved=True)
        self.obs = Observation(self.target, {"_id": "financial-context", "version": 1,
                                             "environment_id": ENV,
                                             "created_at": "2026-10-13T00:00:00+00:00"},
                               writers_excluded=True, exclusion_epoch="exclusive-window-1",
                               complete_scan=True, maintained_writers=True)
        self.doc = row()
        self.ledger = MemoryLedger([self.doc])

    def plan(self, document=None, auth=None):
        return prepare(auth or self.auth, self.obs, document or self.doc)

    def test_missing_diagnosis_is_read_only_and_redacted(self):
        before = exact(self.doc)
        result = diagnose(self.auth, self.obs, [self.doc])
        self.assertEqual(result["counts"], {"missing": 1})
        self.assertEqual(before, exact(self.doc))
        self.assertNotIn("70.1200", str(result))
        self.assertNotIn(self.target.uri, str(result))
        self.assertNotIn("movement-1", str(result))

    def test_ready_document(self):
        self.doc["_history_keys"] = derive_history_keys(self.doc, 1)
        self.assertEqual(diagnose(self.auth, self.obs, [self.doc])["counts"], {"ready": 1})
        self.assertTrue(verify(self.auth, self.obs, [self.doc])["certified"])

    def test_ready_row_not_rewritten(self):
        self.doc["_history_keys"] = derive_history_keys(self.doc, 1)
        before = exact(self.doc)
        with self.assertRaisesRegex(Conflict, "already_ready_no_plan"):
            self.plan()
        self.assertEqual(before, exact(self.doc))

    def test_reconciliation_rejects_tampered_original_plan(self):
        plan = self.plan()
        self.ledger.apply(self.auth, self.obs, plan)
        with self.assertRaisesRegex(Conflict, "journal_conflict"):
            self.ledger.reconcile(self.auth, self.obs, replace(plan, source="changed"))

    def test_corrupt_and_stale(self):
        for value in ({"version": 1, "generation": 1, "state": "ready"},
                      {**derive_history_keys(self.doc, 1), "source_sha256": "bad"}):
            with self.subTest(value=value):
                doc = {**self.doc, "_history_keys": value}
                self.assertEqual(diagnose(self.auth, self.obs, [doc])["counts"], {"stale_or_corrupt": 1})
                self.assertFalse(verify(self.auth, self.obs, [doc])["indexed_reads_allowed"])
                with self.assertRaises(Conflict):
                    self.plan(doc)

    def test_incompatible_generations(self):
        for value in (None, "bad", derive_history_keys(self.doc, 2),
                      {**derive_history_keys(self.doc, 1), "version": 2}):
            with self.subTest(value=value):
                doc = {**self.doc, "_history_keys": value}
                self.assertEqual(diagnose(self.auth, self.obs, [doc])["counts"], {"incompatible": 1})
                with self.assertRaises(Conflict):
                    self.plan(doc)

    def test_unverifiable_not_repaired_or_certified(self):
        for fields in ({"date": "invalid"}, {"amount": Decimal128("NaN")}):
            doc = row(**fields)
            doc["_history_keys"] = derive_history_keys(doc, 1)
            before = exact(doc)
            self.assertEqual(diagnose(self.auth, self.obs, [doc])["counts"], {"unverifiable": 1})
            self.assertFalse(verify(self.auth, self.obs, [doc])["certified"])
            with self.assertRaises(Conflict):
                self.plan(doc)
            self.assertEqual(before, exact(doc))

    def test_legacy_dates_and_decimal128(self):
        for date in ("20261001T120000Z", "2026-W40-4T12:00:00.123456+01:02:03",
                     "2026-10-01T12:00:00.000001", "2026-10-01T12:00:00-05:00"):
            with self.subTest(date=date):
                doc = row(date=date)
                plan = self.plan(doc)
                self.assertEqual(plan.after["state"], "ready")
                self.assertIs(type(plan.after["date_us"]), Int64)
                self.assertEqual(plan.after["amount"].to_decimal(), doc["amount"].to_decimal())

    def test_absent_null_and_bson_types_have_distinct_fingerprints(self):
        docs = [row(amount=v) for v in (None, 1, Int64(1), 1.0, "1", Decimal128("1"))]
        missing = row()
        del missing["amount"]
        plans = [self.plan(d) for d in [missing] + docs]
        self.assertEqual(len({p.source for p in plans}), 7)

    def test_duplicate_id_within_user_blocks_certificate(self):
        second = row(amount=1)
        result = verify(self.auth, self.obs, [self.doc, second])
        self.assertEqual(result["duplicates"], 1)
        self.assertFalse(result["certified"])

    def test_invalid_identity_blocks_application(self):
        doc = row(id=None)
        self.assertEqual(diagnose(self.auth, self.obs, [doc])["counts"], {"invalid_identity": 1})
        with self.assertRaises(Conflict):
            self.plan(doc)

    def test_count_and_byte_limits(self):
        rows = [row(id=str(i)) for i in range(8)]
        bound = max(len(BSON.encode(d)) for d in rows) * 2
        grouped = list(batches(iter(rows), 3, bound))
        self.assertEqual(sum(len(b) for b in grouped), 8)
        for batch in grouped:
            self.assertLessEqual(len(batch), 3)
            self.assertLessEqual(sum(len(BSON.encode(d)) for d in batch), bound)

    def test_oversize_document_not_silently_skipped(self):
        with self.assertRaisesRegex(Conflict, "oversize_document"):
            list(batches([self.doc], 1, 10))

    def test_invalid_batch_limits(self):
        for count, size in ((0, 100), (1, 0), (True, 100)):
            with self.assertRaises(Conflict):
                list(batches([self.doc], count, size))

    def test_checkpoints_preserve_bson_type(self):
        values = [1, Int64(1), "1", ObjectId(), Binary(b"a", 0)]
        self.assertEqual(len({checkpoint(v) for v in values}), len(values))
        for value in values:
            self.assertEqual(exact(BSON(checkpoint(value)).decode()["value"]), exact(value))
        with self.assertRaises(Conflict):
            checkpoint(True)

    def test_apply_changes_only_private_block(self):
        plan = self.plan()
        before = financial_bytes(self.doc)
        self.assertEqual(self.ledger.apply(self.auth, self.obs, plan), "confirmado")
        current = self.ledger.rows[plan.physical_id]
        self.assertEqual(before, financial_bytes(current))
        self.assertEqual(exact(current["_history_keys"]), exact(plan.after))
        self.assertEqual(current["_shared_intent"], self.doc["_shared_intent"])

    def test_source_concurrent_change_rejected(self):
        plan = self.plan()
        self.ledger.external_edit(plan.physical_id, {"amount": Decimal128("71")})
        before = exact(self.ledger.rows[plan.physical_id])
        with self.assertRaisesRegex(Conflict, "concurrent_change"):
            self.ledger.apply(self.auth, self.obs, plan)
        self.assertEqual(before, exact(self.ledger.rows[plan.physical_id]))
        self.assertFalse(self.ledger.journal)

    def test_concurrent_type_change_same_numeric_value_rejected(self):
        doc = row(amount=1)
        ledger, plan = MemoryLedger([doc]), self.plan(doc)
        ledger.external_edit(plan.physical_id, {"amount": Int64(1)})
        with self.assertRaises(Conflict):
            ledger.apply(self.auth, self.obs, plan)

    def test_concurrent_metadata_change_rejected(self):
        plan = self.plan()
        self.ledger.external_edit(plan.physical_id, {"_history_keys": None})
        with self.assertRaises(Conflict):
            self.ledger.apply(self.auth, self.obs, plan)

    def test_administrative_change_preserved_by_apply(self):
        plan = self.plan()
        self.ledger.external_edit(plan.physical_id, {"note": "later"})
        self.ledger.apply(self.auth, self.obs, plan)
        self.assertEqual(self.ledger.rows[plan.physical_id]["note"], "later")

    def test_changed_collection_or_destination_rejected(self):
        for target in (replace(self.target, database="another"),
                       replace(self.target, collection="another"),
                       replace(self.target, collection_uuid=Binary(UUID(OTHER_ENV).bytes, 4)),
                       replace(self.target, uri="mongodb://127.0.0.1:9999"),
                       replace(self.target, environment_id=OTHER_ENV)):
            with self.subTest(target=target):
                with self.assertRaises(Conflict):
                    self.ledger.apply(self.auth, replace(self.obs, target=target), self.plan())

    def test_changed_r6_metadata_rejected(self):
        obs = replace(self.obs, r6_metadata={**self.obs.r6_metadata, "environment_id": OTHER_ENV})
        with self.assertRaises(Exception):
            self.ledger.apply(self.auth, obs, self.plan())
        self.assertFalse(self.ledger.journal)

    def test_wrong_user_rejected(self):
        with self.assertRaises(Conflict):
            self.plan(row(user_id="another-user"))

    def test_no_valid_authorization(self):
        for auth in (replace(self.auth, approved=False), replace(self.auth, actions=()),
                     replace(self.auth, scope="partial_unknown"), replace(self.auth, version=2),
                     replace(self.auth, generation=True), replace(self.auth, generation=2147483648),
                     replace(self.auth, revision="unversioned")):
            with self.subTest(auth=auth):
                with self.assertRaises(Conflict):
                    prepare(auth, self.obs, self.doc)
                self.assertFalse(self.ledger.journal)

    def test_credentials_not_accepted_in_offline_target(self):
        target = replace(self.target, uri="mongodb://secret:secret@localhost")
        with self.assertRaisesRegex(Conflict, "invalid_target"):
            target.binding()

    def test_transactions_and_reader_gates(self):
        for obs in (replace(self.obs, transactions=False), replace(self.obs, optimized_reads=True)):
            with self.assertRaises(Conflict):
                self.ledger.apply(self.auth, obs, self.plan())
            self.assertFalse(self.ledger.journal)

    def test_tampered_plan_or_generation_rejected(self):
        plan = self.plan()
        with self.assertRaisesRegex(Conflict, "plan_changed"):
            self.ledger.apply(self.auth, self.obs, replace(plan, after={**plan.after, "generation": 2}))
        with self.assertRaises(Conflict):
            self.ledger.apply(replace(self.auth, generation=2), self.obs, plan)

    def test_abort_preserves_document_and_journal(self):
        plan, before = self.plan(), exact(self.doc)
        with self.assertRaisesRegex(Conflict, "aborted"):
            self.ledger.apply(self.auth, self.obs, plan, "before_commit")
        self.assertEqual(before, exact(self.ledger.rows[plan.physical_id]))
        self.assertFalse(self.ledger.journal)
        self.assertEqual(self.ledger.reconcile(self.auth, self.obs, plan), "incierto")

    def test_unknown_commit_reconciles_original_without_rewrite(self):
        plan = self.plan()
        self.assertEqual(self.ledger.apply(self.auth, self.obs, plan, "after_commit"), "incierto")
        revision = self.ledger.revisions[plan.physical_id]
        self.assertEqual(self.ledger.reconcile(self.auth, self.obs, plan), "confirmado")
        self.assertEqual(self.ledger.apply(self.auth, self.obs, plan), "confirmado")
        self.assertEqual(self.ledger.revisions[plan.physical_id], revision)
        self.assertEqual(len(self.ledger.journal), 1)

    def test_partial_run_can_resume_per_document(self):
        doc2 = row(id="second")
        ledger = MemoryLedger([self.doc, doc2])
        plan1, plan2 = self.plan(), self.plan(doc2)
        ledger.apply(self.auth, self.obs, plan1)
        with self.assertRaises(Conflict):
            ledger.apply(self.auth, self.obs, plan2, "before_commit")
        self.assertEqual(len(ledger.journal), 1)
        ledger.apply(self.auth, self.obs, plan2)
        self.assertEqual(len(ledger.journal), 2)

    def test_revert_missing_null_and_corrupt_exactly(self):
        for old in ({"present": False, "value": None}, {"present": True, "value": None},
                    {"present": True, "value": {"broken": Int64(7)}}):
            with self.subTest(old=old):
                doc = deepcopy(self.doc)
                if old["present"]:
                    doc["_history_keys"] = old["value"]
                auth = replace(self.auth, replacement=True)
                ledger, plan = MemoryLedger([doc]), self.plan(doc, auth)
                before = exact(doc)
                ledger.apply(auth, self.obs, plan)
                ledger.revert(auth, self.obs, plan)
                self.assertEqual(before, exact(ledger.rows[plan.physical_id]))
                self.assertEqual(ledger.revert(auth, self.obs, plan), "revertido")

    def test_revert_does_not_recreate_deleted_movement(self):
        plan = self.plan()
        self.ledger.apply(self.auth, self.obs, plan)
        del self.ledger.rows[plan.physical_id]
        with self.assertRaises(Conflict):
            self.ledger.revert(self.auth, self.obs, plan)
        self.assertNotIn(plan.physical_id, self.ledger.rows)

    def test_revert_requires_uninterrupted_writer_exclusion(self):
        plan = self.plan()
        self.ledger.apply(self.auth, self.obs, plan)
        for obs in (replace(self.obs, writers_excluded=False),
                    replace(self.obs, exclusion_epoch="new-window")):
            with self.assertRaises(Conflict):
                self.ledger.revert(self.auth, obs, plan)

    def test_aba_writes_block_revert_despite_equal_keys(self):
        plan = self.plan()
        self.ledger.apply(self.auth, self.obs, plan)
        self.ledger.external_edit(plan.physical_id, {"_history_keys": deepcopy(plan.after)})
        with self.assertRaises(Conflict):
            self.ledger.revert(self.auth, self.obs, plan)

    def test_administrative_intermediate_write_blocks_revert(self):
        plan = self.plan()
        self.ledger.apply(self.auth, self.obs, plan)
        self.ledger.external_edit(plan.physical_id, {"note": "new"})
        with self.assertRaises(Conflict):
            self.ledger.revert(self.auth, self.obs, plan)
        self.assertEqual(self.ledger.rows[plan.physical_id]["note"], "new")

    def test_revert_abort_and_unknown_commit(self):
        plan = self.plan()
        self.ledger.apply(self.auth, self.obs, plan)
        before = exact(self.ledger.rows[plan.physical_id])
        with self.assertRaises(Conflict):
            self.ledger.revert(self.auth, self.obs, plan, "before_commit")
        self.assertEqual(before, exact(self.ledger.rows[plan.physical_id]))
        self.assertEqual(self.ledger.revert(self.auth, self.obs, plan, "after_commit"), "incierto")
        self.assertEqual(self.ledger.reconcile(self.auth, self.obs, plan), "revertido")
        self.assertEqual(financial_bytes(self.doc), financial_bytes(self.ledger.rows[plan.physical_id]))

    def test_incomplete_or_live_scan_not_certified(self):
        doc = {**self.doc, "_history_keys": derive_history_keys(self.doc, 1)}
        for obs in (replace(self.obs, complete_scan=False), replace(self.obs, writers_excluded=False),
                    replace(self.obs, maintained_writers=False)):
            self.assertFalse(verify(self.auth, obs, [doc])["certified"])

    def test_sanitized_nested_response(self):
        doc = {**self.doc, "_history_keys": derive_history_keys(self.doc, 1)}
        public = strip_history_metadata({"items": [doc], "nested": {"_history_run": "private"}})
        self.assertNotIn("_history", str(public))
        self.assertEqual(public["items"][0]["amount"], doc["amount"])


if __name__ == "__main__":
    unittest.main()
