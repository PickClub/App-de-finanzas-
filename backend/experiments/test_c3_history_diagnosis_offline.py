"""Synthetic BSON-only diagnosis, bounded traversal and resume adversarial tests."""
from dataclasses import replace
import unittest
from uuid import UUID

from bson import BSON
from bson.binary import Binary
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from bson.objectid import ObjectId

from backend.history_keys import derive_history_keys
from backend.experiments.c3_history_provision_contract import Authorization, Observation, Target, Conflict
from backend.experiments.c3_history_diagnosis_offline import (
    Batch, MAX_IDENTITIES, SyntheticBsonSource, decode_progress, diagnose_bson,
    encode_progress, physical_key,
)

ENV = "5bba89b2-5968-41e0-b00f-2d96b4b3be4b"
OTHER = "bc2eaf24-f461-41da-881d-dbaef03a8cc1"


def document(physical=1, logical=None, **fields):
    return {"_id": physical, "id": logical or f"synthetic-{physical}",
            "user_id": "default-user", "date": "2026-10-01T12:00:00.123456+01:02:03",
            "amount": Decimal128("70.1200"), **fields}


def ready(physical=1, **fields):
    doc = document(physical, **fields)
    doc["_history_keys"] = derive_history_keys(doc, 1)
    return doc


class OfflineDiagnosisTests(unittest.TestCase):
    def setUp(self):
        target = Target("mongodb://127.0.0.1:27018/?replicaSet=synthetic", "synthetic_only",
                        "transactions", Binary(UUID(OTHER).bytes, 4), ENV)
        self.auth = Authorization(target, "offline-diagnosis", "2228c6fe29a3695b22d5446753aed60206dad9c4",
                                  1, 1, ("diagnose",), approved=True)
        self.obs = Observation(target, {"_id": "financial-context", "version": 1,
                                       "environment_id": ENV, "created_at": "2026-10-13T00:00:00Z"})

    def source(self, rows, observation=None, revision=0, **kwargs):
        return SyntheticBsonSource((BSON.encode(d) for d in rows), observation or self.obs,
                                   revision=revision, **kwargs)

    def run_diagnosis(self, rows, **kwargs):
        return diagnose_bson(self.auth, self.source(rows), **kwargs)

    def test_five_classifications_without_mutation(self):
        bad = ready(3); bad["amount"] = Decimal128("71")
        unverifiable = document(4, date="invalid")
        unverifiable["_history_keys"] = derive_history_keys(unverifiable, 1)
        incompatible = ready(5); incompatible["_history_keys"]["generation"] = 2
        rows = [document(1), ready(2), bad, unverifiable, incompatible]
        before = [BSON.encode(d) for d in rows]
        report, _ = self.run_diagnosis(rows, max_documents=2)
        self.assertEqual(report["counts"], dict.fromkeys(report["counts"], 1))
        self.assertEqual(report["generation_incompatible"], 1)
        self.assertEqual(report["source_unverifiable"], 1)
        self.assertEqual(before, [BSON.encode(d) for d in rows])

    def test_missing_but_unverifiable_source_reported(self):
        report, _ = self.run_diagnosis([document(date="invalid")])
        self.assertEqual(report["counts"]["missing"], 1)
        self.assertEqual(report["source_unverifiable"], 1)

    def test_version_and_generation_incompatible(self):
        docs = [ready(1), ready(2), document(3, _history_keys=None)]
        docs[0]["_history_keys"]["version"] = 2
        docs[1]["_history_keys"]["generation"] = Int64(1)
        report, _ = self.run_diagnosis(docs)
        self.assertEqual(report["counts"]["incompatible"], 3)
        self.assertEqual(report["generation_incompatible"], 1)

    def test_historical_formats_microseconds_decimal(self):
        rows = [ready(i, date=value) for i, value in enumerate((
            "20261001T120000.123456Z", "2026-W40-4T12:00:00Z",
            "2026-10-01T12:00:00.000001+01:02:03", "2026-10-01T12:00:00"), 1)]
        report, _ = self.run_diagnosis(rows)
        self.assertEqual(report["counts"]["ready"], 4)

    def test_bson_types_missing_null_and_decimal(self):
        rows = [ready(i, amount=value) for i, value in enumerate((None, 1, Int64(1), 1.0, "1", Decimal128("1")), 1)]
        missing = document(7); del missing["amount"]
        missing["_history_keys"] = derive_history_keys(missing, 1)
        report, _ = self.run_diagnosis(rows + [missing])
        self.assertEqual(report["counts"]["ready"], 7)

    def test_unsupported_source_no_leak(self):
        report, _ = self.run_diagnosis([document(amount={"sensitive": "not valid"})])
        self.assertEqual(report["source_unverifiable"], 1)
        self.assertNotIn("sensitive", str(report))

    def test_duplicates_across_batches_and_resume(self):
        rows = [document(1, "same"), document(2, "distinct"), document(3, "same")]
        source = self.source(rows)
        first, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=2)
        self.assertEqual(first["duplicates"], 0)
        final, _ = diagnose_bson(self.auth, source, token=token, max_documents=1)
        self.assertEqual(final["duplicates"], 1)
        self.assertEqual(final["visited"], 3)

    def test_equal_amounts_distinct_ids_not_deduplicated(self):
        report, _ = self.run_diagnosis([ready(1), ready(2)])
        self.assertEqual(report["duplicates"], 0)
        self.assertEqual(report["visited"], 2)

    def test_wrong_user_rejected(self):
        with self.assertRaisesRegex(Conflict, "scope_mismatch"):
            self.run_diagnosis([document(user_id="another-user")])

    def test_invalid_logical_identity_counted(self):
        report, _ = self.run_diagnosis([document(id=None)])
        self.assertEqual(report["invalid_identity"], 1)

    def test_sorted_physical_id_not_logical_date_or_amount(self):
        rows = [document(3, amount=1, date="2020-01-01"), document(1, amount=99), document(2)]
        source = self.source(rows)
        _, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=1)
        self.assertEqual(decode_progress(token, self.auth)["last_id"], 1)
        report, token = diagnose_bson(self.auth, source, token=token, max_documents=1)
        self.assertEqual(decode_progress(token, self.auth)["last_id"], 3)
        self.assertEqual(report["visited"], 3)

    def test_mixed_bson_type_order_and_typed_checkpoints(self):
        values = [ObjectId("000000000000000000000001"), Binary(b"ab", 0), Binary(b"a", 1),
                  Binary(b"a", 0), "é", "a", Int64(2), 1]
        source = self.source([document(v, logical=str(i)) for i, v in enumerate(values)])
        token, actual = None, []
        for _ in values:
            report, token = diagnose_bson(self.auth, source, token=token, max_documents=1, max_batches=1)
            actual.append(decode_progress(token, self.auth)["last_id"])
        expected = sorted(values, key=physical_key)
        self.assertEqual([BSON.encode({"id": x}) for x in actual], [BSON.encode({"id": x}) for x in expected])
        self.assertTrue(report["completed"])

    def test_equivalent_numeric_physical_id_rejected(self):
        with self.assertRaisesRegex(Conflict, "duplicate_physical_id"):
            self.source([document(1), document(Int64(1))])

    def test_unsupported_physical_id_rejected(self):
        for value in (None, True, 1.0, {}, []):
            with self.subTest(value=value):
                with self.assertRaises(Conflict):
                    self.source([document(value)])

    def test_bounded_batches_by_documents_and_bytes(self):
        rows = [document(i) for i in range(1, 11)]
        width = max(len(BSON.encode(d)) for d in rows)
        report, _ = self.run_diagnosis(rows, max_documents=3, max_bytes=width * 2)
        self.assertEqual(report["visited"], 10)
        self.assertLessEqual(report["peak_batch_documents"], 2)
        self.assertLessEqual(report["peak_batch_bytes"], width * 2)
        self.assertEqual(report["batches_this_call"], 5)

    def test_oversize_stops_not_skipped(self):
        with self.assertRaisesRegex(Conflict, "oversize_document"):
            self.run_diagnosis([document()], max_bytes=10)

    def test_invalid_budgets(self):
        for kwargs in ({"max_documents": 0}, {"max_bytes": True}, {"max_batches": 0},
                       {"max_documents": 1001}, {"max_bytes": 4194305}):
            with self.assertRaises(Conflict):
                self.run_diagnosis([], **kwargs)

    def test_fixture_memory_limit(self):
        with self.assertRaisesRegex(Conflict, "fixture_limit"):
            self.source([document()], fixture_bytes=10)

    def test_duplicate_detection_memory_limit(self):
        rows = [document(i) for i in range(MAX_IDENTITIES + 1)]
        with self.assertRaisesRegex(Conflict, "duplicate_detection_limit"):
            self.run_diagnosis(rows)

    def test_empty_and_last_page(self):
        report, token = self.run_diagnosis([])
        self.assertTrue(report["completed"])
        self.assertEqual(report["visited"], 0)
        self.assertIsNone(decode_progress(token, self.auth)["last_id"])
        source = self.source([ready(1), ready(2)])
        _, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=1)
        report, token = diagnose_bson(self.auth, source, token=token, max_documents=1)
        self.assertTrue(report["completed"])
        again, _ = diagnose_bson(self.auth, source, token=token)
        self.assertEqual(again["visited"], 2)
        self.assertEqual(again["batches_this_call"], 0)

    def test_corrupt_checkpoint(self):
        _, token = self.run_diagnosis([document()])
        for bad in (b"broken", token[:-1], b"x" * 262145):
            with self.assertRaisesRegex(Conflict, "invalid_or_unbound_checkpoint"):
                self.run_diagnosis([document()], token=bad)

    def test_checkpoint_invalid_counts_even_with_checksum(self):
        _, token = self.run_diagnosis([document()])
        state = decode_progress(token, self.auth)
        state["visited"] += 1
        with self.assertRaises(Conflict):
            self.run_diagnosis([document()], token=encode_progress(state))

    def test_checkpoint_bound_to_run_scope_generation_revision(self):
        source = self.source([document(1), document(2)])
        _, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=1)
        for auth in (replace(self.auth, run_id="other"), replace(self.auth, generation=2),
                     replace(self.auth, revision="a" * 40)):
            with self.assertRaises(Conflict):
                diagnose_bson(auth, source, token=token)

    def test_destination_collection_uuid_and_context_rejected(self):
        for target in (replace(self.auth.target, database="other"),
                       replace(self.auth.target, collection="other"),
                       replace(self.auth.target, collection_uuid=Binary(UUID(ENV).bytes, 4)),
                       replace(self.auth.target, uri="mongodb://127.0.0.1:9999")):
            with self.assertRaisesRegex(Conflict, "authorization_or_context_invalid"):
                diagnose_bson(self.auth, self.source([], observation=replace(self.obs, target=target)))
        metadata = {**self.obs.r6_metadata, "environment_id": OTHER}
        with self.assertRaisesRegex(Conflict, "authorization_or_context_invalid"):
            diagnose_bson(self.auth, self.source([], observation=replace(self.obs, r6_metadata=metadata)))

    def test_no_authorization_or_wrong_version(self):
        for auth in (replace(self.auth, approved=False), replace(self.auth, actions=()),
                     replace(self.auth, version=2), replace(self.auth, generation=True)):
            with self.assertRaises(Conflict):
                diagnose_bson(auth, self.source([]))

    def test_live_insert_before_checkpoint_not_current_snapshot(self):
        source = self.source([ready(2), ready(3)])
        _, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=1)
        changed = self.source([ready(1), ready(2), ready(3)], revision=1)
        report, _ = diagnose_bson(self.auth, changed, token=token)
        self.assertEqual(report["visited"], 2)  # New id=1 not pretended as visited.
        self.assertTrue(report["source_changed"])
        self.assertFalse(report["certified"])
        self.assertFalse(report["certification_eligible_in_fixture"])

    def test_live_edit_or_delete_after_first_batch(self):
        source = self.source([ready(1), ready(2)])
        _, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=1)
        changed = self.source([document(1, amount=9), document(3)], revision=1)
        report, _ = diagnose_bson(self.auth, changed, token=token)
        self.assertTrue(report["source_changed"])
        self.assertEqual(report["counts"]["ready"], 1)  # Visited old state of id=1.
        self.assertEqual(report["counts"]["missing"], 1)

    def test_controlled_scan_only_fixture_eligibility(self):
        obs = replace(self.obs, writers_excluded=True, exclusion_epoch="synthetic-window", maintained_writers=True)
        report, _ = diagnose_bson(self.auth, self.source([ready(1)], observation=obs))
        self.assertEqual(report["view"], "controlled_fixture")
        self.assertTrue(report["certification_eligible_in_fixture"])
        self.assertFalse(report["certified"])
        self.assertFalse(report["indexed_reads_allowed"])

    def test_controlled_resume_requires_same_window_and_revision(self):
        obs = replace(self.obs, writers_excluded=True, exclusion_epoch="synthetic-window", maintained_writers=True)
        source = self.source([ready(1), ready(2)], observation=obs)
        _, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=1)
        for new_obs, revision in ((replace(obs, writers_excluded=False), 0),
                                  (replace(obs, exclusion_epoch="other"), 0), (obs, 1)):
            with self.assertRaisesRegex(Conflict, "writer_window_changed"):
                diagnose_bson(self.auth, self.source([ready(1), ready(2)], observation=new_obs, revision=revision), token=token)

    def test_context_checked_again_after_read(self):
        source = self.source([document()])
        original = source.read_batch
        def changed(*args):
            result = original(*args)
            source.observation = replace(self.obs, target=replace(self.auth.target, collection="other"))
            return result
        source.read_batch = changed
        with self.assertRaisesRegex(Conflict, "authorization_or_context_invalid"):
            diagnose_bson(self.auth, source)

    def test_failure_between_batches_reuses_last_returned_checkpoint(self):
        source = self.source([document(1), document(2), document(3)])
        _, token = diagnose_bson(self.auth, source, max_documents=1, max_batches=1)
        original = source.read_batch
        def failed(*args):
            raise Conflict("synthetic_read_error")
        source.read_batch = failed
        with self.assertRaisesRegex(Conflict, "synthetic_read_error"):
            diagnose_bson(self.auth, source, token=token)
        source.read_batch = original
        report, _ = diagnose_bson(self.auth, source, token=token)
        self.assertEqual(report["visited"], 3)
        self.assertEqual(report["duplicates"], 0)

    def test_unordered_adapter_response_rejected(self):
        source = self.source([document(1), document(2)])
        source.read_batch = lambda *args: Batch((BSON.encode(document(2)), BSON.encode(document(1))), False, 0)
        with self.assertRaisesRegex(Conflict, "unordered_batch"):
            diagnose_bson(self.auth, source)

    def test_source_revision_changed_during_batch_rejected(self):
        source = self.source([document()])
        original = source.read_batch
        def changed(*args):
            result = original(*args)
            source.revision += 1
            return result
        source.read_batch = changed
        with self.assertRaisesRegex(Conflict, "source_changed_during_batch"):
            diagnose_bson(self.auth, source)

    def test_invalid_adapter_batch_cannot_bypass_limits(self):
        source = self.source([document()])
        for batch in (Batch((), True, 0), Batch((BSON.encode(document()),), False, 0)):
            source.read_batch = lambda *args, batch=batch: batch
            with self.assertRaisesRegex(Conflict, "invalid_batch"):
                diagnose_bson(self.auth, source, max_bytes=10)

    def test_ready_history_with_2001_documents(self):
        report, _ = self.run_diagnosis([ready(i) for i in range(2001)], max_documents=100)
        self.assertEqual(report["visited"], 2001)
        self.assertEqual(report["counts"]["ready"], 2001)
        self.assertEqual(report["batches_this_call"], 21)
        self.assertFalse(report["certified"])

    def test_checkpoint_boolean_version_rejected(self):
        _, token = self.run_diagnosis([])
        state = decode_progress(token, self.auth)
        state["token_version"] = True
        with self.assertRaises(Conflict):
            self.run_diagnosis([], token=encode_progress(state))

    def test_no_indexed_reader_while_diagnosing(self):
        source = self.source([], observation=replace(self.obs, optimized_reads=True))
        with self.assertRaises(Conflict):
            diagnose_bson(self.auth, source)

    def test_report_has_no_source_values_ids_or_checkpoint(self):
        report, token = self.run_diagnosis([document(1, logical="private-id", notes="private-note")])
        for value in ("70.1200", "2026-10", "private-id", "private-note", self.auth.target.uri, ENV):
            self.assertNotIn(value, str(report))
        self.assertNotIn("last_id", report)
        self.assertIs(type(token), bytes)

    def test_invalid_bson_error_is_generic(self):
        with self.assertRaisesRegex(Conflict, "invalid_bson"):
            SyntheticBsonSource([b"not BSON: private-document"], self.obs)


if __name__ == "__main__":
    unittest.main()
