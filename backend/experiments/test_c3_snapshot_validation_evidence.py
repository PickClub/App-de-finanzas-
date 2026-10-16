"""Offline checks of recorded synthetic evidence; never connects or reruns DBs."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent/'results'
SUCCESS='test_c3_snapshot_9e26a10fa77a4d24985a5c963b1bba1f.json'
FAILED='test_c3_snapshot_5025e56b1bd1482d9e4a0ee7937e510b.json'


class SnapshotEvidenceTests(unittest.TestCase):
    def setUp(self):self.r=json.loads((ROOT/SUCCESS).read_text())
    def test_complete_success_evidence(self):
        self.assertEqual(self.r['status'],'passed')
        self.assertEqual(len(self.r['scenarios']),14)
        self.assertTrue(all(v['passed'] for v in self.r['scenarios'].values()))
    def test_independent_full_document_digest_and_states(self):
        a=self.r['scenarios']['baseline_snapshot_walk'];b=self.r['scenarios']['independent_walk_same_T']
        self.assertEqual(a['digest'],b['digest']);self.assertEqual(a['states'],b['states'])
        self.assertEqual(a['count'],6001);self.assertEqual(sum(a['states'].values()),6001)
        self.assertEqual(a['pages'],151);self.assertEqual(b['pages'],7)
    def test_live_and_snapshot_really_differ(self):
        r=self.r['scenarios']['live_comparison']
        self.assertEqual((r['snapshot_count'],r['live_count']),(6001,6002))
        self.assertEqual((r['snapshot_duplicates'],r['live_duplicates']),(3000,2999))
        r=self.r['scenarios']['post_T_insert_edit_delete']
        self.assertTrue(r['new_rows_hidden'] and r['original_value_preserved'] and r['deleted_row_visible_at_T'])
    def test_no_inferred_or_wallclock_T(self):
        self.assertEqual(self.r['T']['source'],'atClusterTime returned by first snapshot find')
        self.assertGreater(self.r['T']['seconds'],0)
    def test_retention_limit_not_overclaimed(self):
        self.assertEqual(self.r['unavailable_snapshot']['code'],239)
        self.assertEqual(self.r['unavailable_snapshot']['code_name'],'SnapshotTooOld')
        self.assertFalse(self.r['retention_observation']['natural_expiry_of_T_observed'])
        self.assertFalse(self.r['certificate_issued'])
    def test_cursor_recovery_claim_limited(self):
        self.assertEqual(self.r['scenarios']['killed_cursor_failure']['mongo_code'],43)
        self.assertEqual(self.r['scenarios']['new_session_resume_same_T']['numeric_total'],2001)
        self.assertFalse(self.r['scenarios']['new_client_same_T']['physical_process_restart_tested'])
    def test_no_explicit_indexes_or_foreign_commands(self):
        self.assertEqual(self.r['explicit_indexes_created'],0)
        self.assertEqual(self.r['foreign_commands'],[])
        self.assertTrue(all(v==['_id_'] for v in self.r['indexes'].values()))
    def test_failed_attempt_retained_not_certified(self):
        r=json.loads((ROOT/FAILED).read_text())
        self.assertEqual(r['status'],'failed');self.assertFalse(r['certificate_issued'])
        self.assertEqual(len(r['scenarios']),2)
        self.assertIn('cannot set maxTimeMS on getMore',r['error'])


if __name__=='__main__':unittest.main()
