"""Offline proof cases for proposals, NOT evidence of actual MongoDB queries."""
from dataclasses import replace
import unittest
from uuid import UUID

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId

from backend.experiments.c3_history_provision_contract import Target, Authorization, Observation, Conflict
from backend.experiments.c3_history_diagnosis_offline import physical_key
from backend.experiments.c3_mongodb_diagnosis_design import (
    CheckpointAuthority, PARTITIONS, duplicate_stream_pipeline, pack_bounded,
    partition_for, read_filter, summarize_duplicate_stream, type_inventory_pipeline, validate_inventory,
)

ENV = "224748cd-914e-49a5-8441-88b0f98b6d75"
OTHER = "9fdbd468-06aa-46ca-90d9-267ec46cf03d"


class ProposalTests(unittest.TestCase):
    def setUp(self):
        target = Target("mongodb://127.0.0.1:27018/?replicaSet=synthetic", "synthetic_only", "transactions",
                        Binary(UUID(OTHER).bytes, 4), ENV)
        self.auth = Authorization(target, "synthetic-design", "4585e5293b7466f3a58c7faf783bd8707253d8ac",
                                  1, 1, ("diagnose",), approved=True)
        self.obs = Observation(target, {"_id": "financial-context", "version": 1,
                                       "environment_id": ENV, "created_at": "2026-10-13T00:00:00Z"})
        self.signer = CheckpointAuthority(b"synthetic-fixture-key-not-secret!!")

    def test_raw_gt_type_bracketing_can_omit_later_types(self):
        values = [1, Int64(2), "a", Binary(b"x", 0), ObjectId()]
        # Reference models documented type bracketing, not a MongoDB execution.
        naive = [x for x in values if partition_for(x) == partition_for(1) and physical_key(x) > physical_key(1)]
        global_successors = [x for x in values if physical_key(x) > physical_key(1)]
        self.assertEqual(len(naive), 1)
        self.assertEqual(len(global_successors), 4)

    def test_partitioned_walk_covers_mixed_ids(self):
        values = [ObjectId(), "é", Binary(b"z", 1), 3, Int64(2), "a", Binary(b"z", 0)]
        collected = []
        for part in range(len(PARTITIONS)):
            after = None
            while True:
                specification = read_filter("default-user", part, after)
                self.assertEqual(specification["_id"]["$type"], list(PARTITIONS[part]))
                matches = sorted([x for x in values if partition_for(x) == part
                                  and (after is None or physical_key(x) > physical_key(after))], key=physical_key)
                if not matches:
                    break
                after = matches[0]
                collected.append(after)
        self.assertEqual([BSON.encode({"v": x}) for x in collected],
                         [BSON.encode({"v": x}) for x in sorted(values, key=physical_key)])

    def test_numeric_int32_long_share_partition(self):
        self.assertEqual(partition_for(1), partition_for(Int64(1)))
        self.assertEqual(read_filter("default-user", 0, Int64(1))["_id"]["$type"], ["int", "long"])

    def test_wrong_partition_and_unsupported_type_block(self):
        for args in (("default-user", 0, "a"), ("other", 0, None), ("default-user", True, None)):
            with self.assertRaises(Conflict):
                read_filter(*args)
        for value in (None, True, 1.0, [], {}):
            with self.assertRaises(Conflict):
                partition_for(value)

    def test_inventory_does_not_hide_unsupported_types(self):
        self.assertEqual(validate_inventory({"int": 2, "long": 3, "objectId": 5}), 10)
        for counts in ({"double": 1}, {"null": 1}, {"bool": 1}, {"object": 1}, {"int": -1}):
            with self.assertRaises(Conflict):
                validate_inventory(counts)
        self.assertIn("$group", type_inventory_pipeline("default-user")[1])

    def test_checkpoint_preserves_int64_and_binary(self):
        token = self.signer.issue(self.auth, self.obs, partition=0, last_id=Int64(7), visited=1, exhausted=True)
        self.assertIs(type(self.signer.accept(self.auth, self.obs, token)["last_id"]), Int64)
        for part, value in ((1, "a"), (2, Binary(b"x", 0)), (3, ObjectId())):
            token = self.signer.issue(self.auth, self.obs, partition=part, last_id=value, visited=part+1, exhausted=True)
            recovered = self.signer.accept(self.auth, self.obs, token)["last_id"]
            self.assertEqual(BSON.encode({"x": recovered}), BSON.encode({"x": value}))

    def test_modified_payload_rejected_even_recomputed_checksum(self):
        token = self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1)
        env = BSON(token).decode()
        payload = BSON(env["payload"]).decode(); payload["last_id"] = 99999
        env["payload"] = Binary(BSON.encode(payload))
        with self.assertRaises(Conflict):
            self.signer.accept(self.auth, self.obs, BSON.encode(env))

    def test_other_signing_key_rejected(self):
        token = self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1)
        with self.assertRaises(Conflict):
            CheckpointAuthority(b"x"*32).accept(self.auth, self.obs, token)

    def test_replay_old_checkpoint_rejected(self):
        old = self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1)
        new = self.signer.issue(self.auth, self.obs, partition=0, last_id=2, visited=2)
        with self.assertRaises(Conflict):
            self.signer.accept(self.auth, self.obs, old)
        self.assertEqual(self.signer.accept(self.auth, self.obs, new)["last_id"], 2)

    def test_lost_registry_blocks_resume_even_with_same_key(self):
        token = self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1)
        restarted = CheckpointAuthority(b"synthetic-fixture-key-not-secret!!")
        with self.assertRaises(Conflict):
            restarted.accept(self.auth, self.obs, token)

    def test_context_run_generation_scope_changes_reject(self):
        token = self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1)
        for auth in (replace(self.auth, run_id="other"), replace(self.auth, generation=2),
                     replace(self.auth, revision="a"*40), replace(self.auth, scope="other")):
            with self.assertRaises(Conflict):
                self.signer.accept(auth, self.obs, token)
        changed = replace(self.obs, target=replace(self.auth.target, collection="other"))
        with self.assertRaises(Conflict):
            self.signer.accept(self.auth, changed, token)

    def test_unsigned_or_corrupt_tokens(self):
        for token in (b"bad", BSON.encode({"payload": b"bad", "mac": b"bad"}), b"x"*8193):
            with self.assertRaises(Conflict):
                self.signer.accept(self.auth, self.obs, token)

    def test_progress_cannot_move_backwards_or_skip_partition(self):
        self.signer.issue(self.auth, self.obs, partition=0, last_id=3, visited=1)
        for part, last, visited in ((0, 2, 2), (2, Binary(b"a", 0), 2), (0, 4, 0)):
            with self.assertRaises(Conflict):
                self.signer.issue(self.auth, self.obs, partition=part, last_id=last, visited=visited)

    def test_partition_change_requires_exhaustion_evidence(self):
        self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1)
        with self.assertRaisesRegex(Conflict, "partition_not_exhausted"):
            self.signer.issue(self.auth, self.obs, partition=1, last_id="a", visited=2)
        self.signer.issue(self.auth, self.obs, partition=0, last_id=2, visited=2, exhausted=True)
        token = self.signer.issue(self.auth, self.obs, partition=1, last_id="a", visited=3)
        self.assertEqual(self.signer.accept(self.auth, self.obs, token)["partition"], 1)

    def test_empty_final_batch_can_seal_same_checkpoint(self):
        self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1)
        token = self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1, exhausted=True)
        self.assertTrue(self.signer.accept(self.auth, self.obs, token)["exhausted"])
        token = self.signer.issue(self.auth, self.obs, partition=1, last_id=None, visited=1, exhausted=True)
        self.assertIsNone(self.signer.accept(self.auth, self.obs, token)["last_id"])

    def test_token_size_and_key_limits(self):
        with self.assertRaises(Conflict):
            CheckpointAuthority(b"short")
        self.signer.issue(self.auth, self.obs, partition=0, last_id=1, visited=1, exhausted=True)
        with self.assertRaisesRegex(Conflict, "checkpoint_limit"):
            self.signer.issue(self.auth, self.obs, partition=1, last_id="x"*9000, visited=2)

    def test_duplicates_exact_adjacent_not_amount_based(self):
        rows = ({"id": k, "user_id": "default-user"} for k in ["a", "a", "a", "b", "c", "c"])
        self.assertEqual(summarize_duplicate_stream(rows, "default-user"),
                         {"visited": 6, "duplicate_groups": 2, "extra_documents": 3})

    def test_duplicate_stream_100001_rows_constant_state(self):
        rows = ({"id": f"synthetic-{i:06}", "user_id": "default-user"} for i in range(100001))
        self.assertEqual(summarize_duplicate_stream(rows, "default-user")["visited"], 100001)

    def test_bad_duplicate_stream_not_silently_skipped(self):
        cases = [[{"id": "b", "user_id": "default-user"}, {"id": "a", "user_id": "default-user"}],
                 [{"id": "a", "user_id": "other"}], [{"id": None, "user_id": "default-user"}]]
        for rows in cases:
            with self.assertRaises(Conflict):
                summarize_duplicate_stream(rows, "default-user")

    def test_duplicate_pipeline_read_only_exact_scalar_filter(self):
        pipeline = duplicate_stream_pipeline("default-user")
        self.assertEqual(pipeline[0]["$match"]["$expr"]["$eq"][0], {"$type": "$id"})
        self.assertEqual(pipeline[-1], {"$sort": {"id": 1, "_id": 1}})
        self.assertFalse(any("$out" in stage or "$merge" in stage for stage in pipeline))

    def test_bytes_and_documents_bounded_stream(self):
        raw = BSON.encode({"_id": 1, "id": "synthetic"})
        batches = list(pack_bounded((raw for _ in range(11)), 3, len(raw)*2))
        self.assertEqual(sum(map(len,batches)), 11)
        self.assertTrue(all(len(b)<=2 and sum(map(len,b))<=len(raw)*2 for b in batches))

    def test_oversized_bson_and_invalid_limits_stop(self):
        with self.assertRaises(Conflict):
            list(pack_bounded([BSON.encode({"x": "y"})], 1, 1))
        with self.assertRaises(Conflict):
            list(pack_bounded([], 0, 1))

    def test_live_insert_in_previous_partition_still_not_certifiable(self):
        # Partitioning fixes type bracketing, not a changing live dataset.
        read_filter("default-user", 1, "a")
        late_insert = 4
        self.assertEqual(partition_for(late_insert), 0)
        self.assertLess(partition_for(late_insert), 1)


if __name__ == "__main__":
    unittest.main()
