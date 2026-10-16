"""P3 strict equivalence. Prior 18 cases replayed OFFLINE; no MongoDB access."""
import ast
import copy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import random
import re
import sys
import unittest

from fastapi import HTTPException
from backend.transaction_history import parse_instant
from backend.experiments.c3_date_p3 import normalize_stored_date, inspect_date_keys, EPOCH
from backend.experiments.c3_numbered_p2 import PATTERN, fixture
from backend.tests.test_transaction_history import matches

ROOT = Path(__file__).resolve().parents[2]
DATES = [
    "20261001T120000Z", "20261001T120000.123456+010203",
    "2026-10-01T12:00:00.123456+01:02:03", "2026-10-01T12:00:00.123456-01:02:03",
    "2026-10-01T12:00:00+00:00:00.5", "2026-10-01T12:00:00+00:99",
    "1969-12-31T23:59:59.999999Z", "2024-02-29",
    "2026-10-01T12:00:00.123456789Z", "2026-10-01T25:00:00Z",
    "2026-02-29T12:00:00Z", "2026-1001T120000Z",
    "2026-10-01T12:0000Z", "2026-W40-4T12:00:00Z",
]


@lru_cache(maxsize=1)
def legacy_reference():
    # Exact current server function, no module startup/dotenv/client import.
    tree = ast.parse((ROOT / "backend/server.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_parse_dt")
    ns = {"datetime": datetime, "timezone": timezone}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<actual _parse_dt AST>", "exec"), ns)
    return ns["_parse_dt"]


def expected_key(value):
    # Independent adaptation of current legacy server parser for stored strings.
    result = legacy_reference()(value)
    if result is None:
        return None
    try:
        utc = result.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None
    delta = utc - EPOCH
    return delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds


class PriorAdversarial18(unittest.TestCase):
    def assert_date(self, value):
        required = expected_key(value)
        if required is None:
            with self.assertRaises(HTTPException) as captured:
                normalize_stored_date(value)
            self.assertEqual(captured.exception.status_code, 409)
        else:
            observed = normalize_stored_date(value)
            self.assertEqual(observed.utc_microseconds, required)
            self.assertEqual(observed.instant, parse_instant(value, stored=True))
            self.assertEqual(observed.original, value)

    def assert_combined(self):
        rows = [fixture(i, 0) for i in range(2001)]
        rows += [dict(fixture(3000, 0), type="transfer", account_id="A", to_account_id="B", user_id="default-user"),
                 dict(fixture(3001, 0), type="transfer", account_id="B", to_account_id="A", user_id="default-user")]
        before = copy.deepcopy(rows)
        q = {"user_id": "default-user", "category_id": "C0", "type": {"$in": ["expense", "transfer"]},
             "$or": [{"account_id": "A"}, {"type": "transfer", "to_account_id": "A"}]}
        window = ("2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z")
        actual = dict(inspect_date_keys(rows, lambda r: matches(r, q), window))
        required = {r["id"]: expected_key(r["date"]) for r in rows if matches(r, q)
                    and expected_key(window[0]) <= expected_key(r["date"]) < expected_key(window[1])}
        self.assertEqual({k: v.utc_microseconds for k, v in actual.items()}, required)
        self.assertEqual(rows, before)

    def test_18_both_transfer_extremes(self):
        self.assert_combined()
        rows = [dict(id="incoming", date="2026-W40-4", type="transfer", account_id="B", to_account_id="A"),
                dict(id="outgoing", date="20261001", type="transfer", account_id="A", to_account_id="B"),
                dict(id="ordinary", date="2026-10-01", type="expense", account_id="B", to_account_id="A")]
        q = {"$or": [{"account_id": "A"}, {"type": "transfer", "to_account_id": "A"}]}
        self.assertEqual({i for i, _ in inspect_date_keys(rows, lambda r: matches(r, q))}, {"incoming", "outgoing"})


def date_case(value):
    def run(self): self.assert_date(value)
    return run


for i, value in enumerate(DATES, 1):
    setattr(PriorAdversarial18, f"test_{i:02d}_prior_date", date_case(value))
for i, label in enumerate(("baseline", "optimized", "stored_keys"), 15):
    # Same prior scenario, adapted keys in memory; NOT a rerun of those Mongo plans.
    setattr(PriorAdversarial18, f"test_{i:02d}_prior_combined_{label}", PriorAdversarial18.assert_combined)


class ExpandedCases(unittest.TestCase):
    def test_reproduce_p2_gaps_and_correct_p3(self):
        for value in ("2026-1001T120000Z", "2026-10-01T12:0000Z"):
            self.assertIsNotNone(re.fullmatch(PATTERN, value))
            with self.assertRaises(HTTPException): normalize_stored_date(value)
        value = "2026-W40-4T12:00:00Z"
        self.assertIsNone(re.fullmatch(PATTERN, value))
        self.assertEqual(normalize_stored_date(value).instant,
                         datetime(2026, 10, 1, 12, tzinfo=timezone.utc))

    def test_week_year_boundaries_and_invalid_week_53(self):
        self.assertEqual(normalize_stored_date("2020-W53-5").instant,
                         datetime(2021, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(normalize_stored_date("2020W535").utc_microseconds,
                         normalize_stored_date("2021-01-01").utc_microseconds)
        with self.assertRaises(HTTPException): normalize_stored_date("2021-W53-1")

    def test_microseconds_pre_epoch_and_offsets(self):
        self.assertEqual(normalize_stored_date("1969-12-31T23:59:59.999999Z").utc_microseconds, -1)
        a = normalize_stored_date("2026-10-01T12:00:00.000001+01:02:03")
        b = normalize_stored_date("2026-10-01T10:57:57.000001Z")
        self.assertEqual(a.utc_microseconds, b.utc_microseconds)
        self.assertEqual(normalize_stored_date("2026-10-01T10:57:57.000002Z").utc_microseconds-a.utc_microseconds, 1)

    def test_boundary_and_invalid_normalization(self):
        for value in ("0001-01-01", "9999-12-31T23:59:59.999999Z"):
            result = normalize_stored_date(value)
            self.assertTrue(-(2**63) <= result.utc_microseconds < 2**63)
        for value in (None, "", 0, True, {}, "not-a-date", "0001-01-01T00:00:00+01:00",
                      "9999-12-31T23:59:59-01:00"):
            with self.assertRaises(HTTPException): normalize_stored_date(value)

    def test_relative_order_and_equal_instants_distinct_identifiers(self):
        values = [v for v in DATES if expected_key(v) is not None]
        expected = sorted(enumerate(values), key=lambda pair: (expected_key(pair[1]), str(pair[0])))
        actual = sorted(enumerate(values), key=lambda pair: (normalize_stored_date(pair[1]).utc_microseconds, str(pair[0])))
        self.assertEqual(actual, expected)
        equal = ["20261001T120000Z", "2026-W40-4T12:00:00Z", "2026-10-01T08:00:00-04:00"]
        self.assertEqual(len({normalize_stored_date(v).utc_microseconds for v in equal}), 1)
        self.assertEqual(len(equal), 3)

    def test_no_document_or_intention_rewrite(self):
        record = {"id":"synthetic", "date":"2026-W40-4T12:00:00Z", "amount":70,
                  "_shared_intent":{"payload":{"date":None},"key":"original"},
                  "journal":{"date":"20261001T120000Z","id":"original"}}
        before = json.dumps(record, sort_keys=True)
        projected = list(inspect_date_keys([record]))
        self.assertEqual(json.dumps(record, sort_keys=True), before)
        with self.assertRaises(FrozenInstanceError): projected[0][1].original = "other"

    def test_bad_candidate_fails_and_does_not_disappear(self):
        rows = [{"id":"bad", "date":"2026-1001"}, {"id":"good", "date":"2026-10-01"}]
        before = copy.deepcopy(rows)
        with self.assertRaises(HTTPException): list(inspect_date_keys(rows))
        self.assertEqual(rows, before)

    def test_generated_format_equivalence(self):
        rng = random.Random(31013)
        for _ in range(300):
            year, month, day = rng.randrange(1900, 2100), rng.randrange(1, 13), rng.randrange(1, 29)
            h, m, s, micro = rng.randrange(24), rng.randrange(60), rng.randrange(60), rng.randrange(1000000)
            dt = datetime(year, month, day, h, m, s, micro)
            iso = dt.isoformat()
            compact = dt.strftime("%Y%m%dT%H%M%S") + f".{micro:06d}Z"
            week = dt.isocalendar()
            iso_week = f"{week.year:04d}-W{week.week:02d}-{week.weekday}T{h:02d}:{m:02d}:{s:02d}.{micro:06d}Z"
            for value in (iso, iso+"Z", compact, iso_week, iso+"+01:02:03", iso.replace("T", "🙂")):
                with self.subTest(value=value):
                    self.assertEqual(normalize_stored_date(value).utc_microseconds, expected_key(value))


if __name__ == "__main__": unittest.main()
