"""Offline P2 checks. Three known grammar gaps are explicit expected failures."""
import re
import unittest
from backend.experiments.c3_numbered_p2 import PATTERN, base, facet_pipeline, fixture, micros, oracle


class P2UnitTests(unittest.TestCase):
    def test_basic_iso_matches_extended_iso(self):
        self.assertTrue(re.fullmatch(PATTERN,"20261001T120000Z"))
        self.assertEqual(micros("20261001T120000Z"),micros("2026-10-01T12:00:00Z"))

    def test_offsets_with_seconds_and_fraction(self):
        self.assertTrue(re.fullmatch(PATTERN,"2026-10-01T12:00:00.123456+01:02:03"))
        self.assertEqual(micros("2026-10-01T12:00:00.123456+01:02:03"),micros("2026-10-01T10:57:57.123456Z"))
        self.assertEqual(micros("2026-10-01T12:00:00.123456-01:02:03"),micros("2026-10-01T13:02:03.123456Z"))

    def test_fraction_precision_and_pre_epoch(self):
        self.assertEqual(micros("2026-10-01T12:00:00.123456789Z"),micros("2026-10-01T12:00:00.123456Z"))
        self.assertEqual(micros("1969-12-31T23:59:59.999999Z"),-1)

    def test_filters_first_and_sort_outside_facet_for_numbers(self):
        p=facet_pipeline({"user_id":"default-user"},"recent",5000)
        self.assertEqual(p[0],{"$match":{"user_id":"default-user"}})
        self.assertEqual(p[-2],{"$sort":{"_x_time":-1,"id":-1}})
        self.assertIn({"$skip":99980},p[-1]["$facet"]["items"])
        self.assertIn({"$limit":20},p[-1]["$facet"]["items"])

    def test_hybrid_filters_intention_key_before_sort_limit(self):
        p=facet_pipeline({"user_id":"default-user"},"high",2,{"_x_amount":70,"_x_time":1,"id":"x"})
        self.assertNotIn("$sort",p[-2])
        branches=p[-1]["$facet"]["items"][1]["$match"]["$or"]
        self.assertEqual(len(branches),3)
        self.assertEqual(branches[-1],{"_x_amount":70,"_x_time":1,"id":{"$lt":"x"}})

    def test_synthetic_future_keys_do_not_change_original_dates(self):
        r=fixture(0)
        self.assertEqual(r["date"],"20261001T120000.123456Z")
        self.assertEqual(r["_p2_time"],micros(r["date"]))

    def test_four_oracles_keep_distinct_ids(self):
        q={"user_id":"default-user"}
        for order in ("recent","oldest","high","low"):
            ids=oracle(2001,order,q)
            self.assertEqual(len(ids),1883);self.assertEqual(len(ids),len(set(ids)))

    @unittest.expectedFailure
    def test_reject_mixed_date_separators(self):
        self.assertIsNone(re.fullmatch(PATTERN,"2026-1001T120000Z"))

    @unittest.expectedFailure
    def test_reject_mixed_time_separators(self):
        self.assertIsNone(re.fullmatch(PATTERN,"2026-10-01T12:0000Z"))

    @unittest.expectedFailure
    def test_accept_current_legacy_week_iso(self):
        self.assertIsNotNone(re.fullmatch(PATTERN,"2026-W40-4T12:00:00Z"))


if __name__=="__main__":unittest.main()
