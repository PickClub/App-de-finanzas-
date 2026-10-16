"""Offline structure/oracle checks; no MongoDB connection or production import."""
import copy
import unittest
from backend.experiments.c3_numbered_mongodb import (
    filtered_pipeline, items_pipeline, normalization, oracle, sort_fields, synthetic,
)


class PrototypeUnitTests(unittest.TestCase):
    def test_only_read_stages_and_no_javascript(self):
        pipeline=items_pipeline(*filtered_pipeline({"user_id":"default-user"}),"high",5000)
        self.assertTrue(all(set(stage)<= {"$match","$set","$project","$sort","$skip","$limit"} for stage in pipeline))
        self.assertFalse(any(word in str(pipeline) for word in ("$out","$merge","$function","$accumulator")))

    def test_twenty_results_and_compact_projection_before_sort(self):
        pipeline=items_pipeline(*filtered_pipeline({"user_id":"default-user"}),"recent",5000)
        self.assertEqual(pipeline[-1],{"$limit":20})
        self.assertEqual(pipeline[-2],{"$skip":99980})
        self.assertEqual(pipeline[-4],{"$project":{"_id":1,"id":1,"_x_time":1,"_x_amount":1}})

    def test_stable_tie_breaking_for_all_four_orders(self):
        self.assertEqual(sort_fields("recent"),{"_x_time":-1,"id":-1})
        self.assertEqual(sort_fields("oldest"),{"_x_time":1,"id":1})
        self.assertEqual(sort_fields("high"),{"_x_amount":-1,"_x_time":-1,"id":-1})
        self.assertEqual(sort_fields("low"),{"_x_amount":1,"_x_time":-1,"id":-1})
        with self.assertRaises(ValueError):sort_fields("unsupported")

    def test_filters_not_mutated_and_applied_first(self):
        query={"user_id":"default-user","account_id":"A"};before=copy.deepcopy(query)
        base,valid=filtered_pipeline(query,"2026-01-01T00:00:00Z","2027-01-01T00:00:00Z")
        self.assertEqual(base[0],{"$match":query});self.assertEqual(query,before)
        self.assertEqual(valid["$match"]["_x_time"]["$gte"],1767225600000000)

    def test_reference_has_all_results_without_500_limit(self):
        query={"user_id":"default-user"}
        for n in (501,2001,10001):
            recent=oracle(n,"recent",query);oldest=oracle(n,"oldest",query)
            self.assertEqual(len(recent),sum(synthetic(i,0)["user_id"]=="default-user" for i in range(n)))
            self.assertEqual(recent,list(reversed(oldest)))
            self.assertEqual(len(set(recent)),len(recent))

    def test_invalid_numbered_pages(self):
        for page in (0,-1,True,1.5,"last"):
            with self.assertRaises(ValueError):items_pipeline([],{},"recent",page)

    def test_microseconds_separate_from_bson_date_conversion(self):
        text=str(normalization())
        self.assertIn("$_x_fraction",text)
        self.assertIn("1000",text)
        self.assertNotIn("$dateFromString",text)


if __name__=="__main__":unittest.main()
