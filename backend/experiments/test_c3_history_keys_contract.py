"""Executable contract ONLY: no production imports with startup, clients or writes.

Helpers live in this test file deliberately; they are not a production adapter.
Only transaction_history.parse_instant is reused from the canonical reader.
"""
import copy
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
import hashlib
import math
import unittest

from bson import BSON
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from fastapi import HTTPException

from backend.transaction_history import parse_instant

VERSION = 1
GENERATION = 1
SOURCE_FIELDS = ("id", "user_id", "date", "amount")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def source_fingerprint(row):
    # BSON scalar encoding preserves presence, type, literal string and float bits.
    # No whole-document hashing: coordination and journals are not key sources.
    source = []
    for field in SOURCE_FIELDS:
        if field not in row:
            source.append({"field": field, "present": False})
            continue
        value = row[field]
        if not (value is None or type(value) in (str, int, float, bool)
                or isinstance(value, (Int64, Decimal128))):
            raise ValueError("Unsupported source type")
        source.append({"field": field, "present": True,
                       "scalar_bson": BSON.encode({"value": value}).hex()})
    return hashlib.sha256(BSON.encode({"contract": VERSION, "source": source})).hexdigest()


def exact_amount(row):
    value = row.get("amount")
    # Existing visual fallback is amount || 0; absence/null/empty are sorting
    # zeros ONLY, never new financial amounts or validation of a ledger entry.
    if value is None or value == "":
        value = 0
    if isinstance(value, bool):
        raise ValueError("Boolean amount")
    if isinstance(value, Decimal128):
        decimal = value.to_decimal()
    elif type(value) in (int, float, str) or isinstance(value, Int64):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite amount")
        decimal = Decimal(str(value))
    else:
        raise ValueError("Unsupported amount")
    if not decimal.is_finite():
        raise ValueError("Non-finite amount")
    result = Decimal128(decimal)  # Existing driver traps lossy conversions.
    if result.to_decimal() != decimal:
        raise ValueError("Lossy amount conversion")
    return result


def build_keys(row):
    """Pure test model. Never attaches keys to row or normalizes its payload."""
    result = {"version": VERSION, "generation": GENERATION,
              "state": "unverifiable", "source_sha256": None}
    try:
        result["source_sha256"] = source_fingerprint(row)
    except (ValueError, OverflowError):
        return {**result, "reason": "source"}
    if any(not isinstance(row.get(f), str) or not 1 <= len(row[f]) <= 256
           for f in ("id", "user_id")):
        return {**result, "reason": "identity"}
    try:
        instant = parse_instant(row.get("date"), stored=True)
        delta = instant - EPOCH
        microseconds = delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds
        date_key = Int64(microseconds)
        BSON.encode({"date_us": date_key})  # Real signed Int64 range check.
    except (HTTPException, ValueError, OverflowError):
        return {**result, "reason": "date"}
    try:
        amount_key = exact_amount(row)
    except (ValueError, DecimalException, OverflowError):
        return {**result, "reason": "amount"}
    return {**result, "state": "ready", "date_us": date_key, "amount": amount_key}


def inspect_keys(row, keys):
    """Does not repair metadata. Full recomputation is the offline oracle."""
    if keys is None:
        return "missing"
    if not isinstance(keys, dict):
        return "incompatible"
    if (type(keys.get("version")) is not int or keys["version"] != VERSION
            or type(keys.get("generation")) is not int or keys["generation"] != GENERATION):
        return "incompatible"
    expected = build_keys(row)
    if keys.get("state") == "ready" and (type(keys.get("date_us")) is not Int64
                                          or type(keys.get("amount")) is not Decimal128):
        return "stale_or_corrupt"
    # Decimal128 equality preserves the declared exact stored representation.
    if keys != expected:
        return "stale_or_corrupt"
    return expected["state"]


def ordered(rows, order):
    if order not in {"recent", "oldest", "high", "low"}:
        raise ValueError("Invalid order")
    keys = [(row, build_keys(row)) for row in rows]
    if any(k["state"] != "ready" for _, k in keys):
        raise ValueError("Unverifiable history; never silently omit")
    if len({(r["user_id"], r["id"]) for r, _ in keys}) != len(keys):
        raise ValueError("Duplicate identity")
    # Stable secondary order: date/id descending for amount orders.
    keys.sort(key=lambda pair: (pair[1]["date_us"], pair[0]["id"]),
              reverse=order != "oldest")
    if order in {"high", "low"}:
        keys.sort(key=lambda pair: pair[1]["amount"].to_decimal(), reverse=order == "high")
    return [r["id"] for r, _ in keys]


def public_model(value):
    """Required future recursive sanitization, test model only."""
    if isinstance(value, list):
        return [public_model(v) for v in value]
    if isinstance(value, dict):
        return {k: public_model(v) for k, v in value.items() if not k.startswith("_history")}
    return value


def fixture(**changes):
    return {"id": "tx-a", "user_id": "default-user", "date": "2026-10-01T12:00:00Z",
            "amount": 70.0, "account_id": "A", "type": "expense", **changes}


class HistoryKeysContract(unittest.TestCase):
    def test_legacy_date_formats(self):
        values = ["20261001T120000Z", "2026-W40-4T12:00:00Z", "2026-10-01",
                  "2026-10-01T12:00:00", "20261001T120000.123456+010203",
                  "2026-10-01T12:00:00.123456+01:02:03",
                  "2026-10-01T12:00:00.123456-01:02:03"]
        for value in values:
            with self.subTest(value=value):
                row = fixture(date=value)
                keys = build_keys(row)
                self.assertEqual(keys["state"], "ready")
                utc = EPOCH + (parse_instant(value, stored=True) - EPOCH)
                delta = utc - EPOCH
                self.assertEqual(keys["date_us"], delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds)
                self.assertEqual(row["date"], value)

    def test_microseconds_and_submicrosecond_reference(self):
        a = build_keys(fixture(date="2026-10-01T12:00:00.123456Z"))
        b = build_keys(fixture(date="2026-10-01T12:00:00.123457Z"))
        c = build_keys(fixture(date="2026-10-01T12:00:00.123456789Z"))
        self.assertEqual(b["date_us"] - a["date_us"], 1)
        self.assertEqual(c["date_us"], a["date_us"])
        self.assertNotEqual(c["source_sha256"], a["source_sha256"])

    def test_equivalent_offsets_equal_keys_different_sources(self):
        a = build_keys(fixture(date="2026-10-01T12:00:00Z"))
        b = build_keys(fixture(date="2026-10-01T13:02:03+01:02:03"))
        self.assertEqual(a["date_us"], b["date_us"])
        self.assertNotEqual(a["source_sha256"], b["source_sha256"])

    def test_invalid_dates_no_repair(self):
        for value in (None, "", "2026-1001T120000Z", "2026-10-01T12:0000Z", "2026-02-29", "0001-01-01T00:00:00+01:00"):
            row = fixture(date=value)
            before = copy.deepcopy(row)
            keys = build_keys(row)
            self.assertEqual(keys["reason"], "date")
            self.assertNotIn("date_us", keys)
            self.assertEqual(row, before)

    def test_date_boundaries_and_before_epoch(self):
        values = ["0001-01-01T00:00:00Z", "1969-12-31T23:59:59.999999Z", "1970-01-01T00:00:00Z", "9999-12-31T23:59:59.999999Z"]
        keys = [build_keys(fixture(date=v))["date_us"] for v in values]
        self.assertEqual(keys[1:3], [-1, 0])
        self.assertEqual(keys, sorted(keys))
        self.assertTrue(all(-(2**63) <= k < 2**63 for k in keys))

    def test_actual_bson_int64_boundaries(self):
        for number in (-(2**63), 2**63 - 1):
            result = BSON(BSON.encode({"k": Int64(number)})).decode()["k"]
            self.assertIsInstance(result, Int64)
            self.assertEqual(result, number)
        for number in (-(2**63) - 1, 2**63):
            with self.assertRaises(OverflowError):
                BSON.encode({"k": Int64(number)})

    def test_exact_decimal_amounts_without_financial_rounding(self):
        for value in ("0.1", "70.0001", "1234567890123456789012345678901234", 0.1, -70, Decimal128("70.0001")):
            keys = build_keys(fixture(amount=value))
            expected = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
            self.assertEqual(keys["state"], "ready")
            self.assertEqual(keys["amount"].to_decimal(), expected)
        self.assertEqual(build_keys(fixture(amount=0.1 + 0.2))["amount"].to_decimal(), Decimal("0.30000000000000004"))

    def test_decimal128_extremes(self):
        for value in ("1E-6176", "9.999999999999999999999999999999999E+6144", "1E+6144", "-0"):
            keys = build_keys(fixture(amount=value))
            self.assertEqual(keys["state"], "ready", value)
            self.assertEqual(keys["amount"].to_decimal(), Decimal(value))
            roundtrip = BSON(BSON.encode(keys)).decode()
            self.assertEqual(roundtrip["amount"].to_decimal(), Decimal(value))
        for value in ("1E-6177", "1E+6145", "1.1234567890123456789012345678901234"):
            self.assertEqual(build_keys(fixture(amount=value))["reason"], "amount")

    def test_invalid_amounts(self):
        for value in (True, False, "not-money", "NaN", "Infinity", float("inf"), float("nan")):
            keys = build_keys(fixture(amount=value))
            self.assertEqual(keys["state"], "unverifiable")
            self.assertEqual(keys["reason"], "amount")
            self.assertNotIn("amount", keys)

    def test_missing_null_empty_zero_are_distinct_sources(self):
        rows = [fixture(amount=v) for v in (None, "", 0, 0.0, "0")]
        missing = fixture()
        del missing["amount"]
        rows.append(missing)
        keys = [build_keys(r) for r in rows]
        self.assertTrue(all(k["amount"].to_decimal() == 0 for k in keys))
        self.assertEqual(len({k["source_sha256"] for k in keys}), len(keys))

    def test_missing_null_all_source_fields(self):
        for field in SOURCE_FIELDS:
            absent, null = fixture(), fixture()
            absent.pop(field)
            null[field] = None
            self.assertNotEqual(source_fingerprint(absent), source_fingerprint(null))

    def test_deterministic_fingerprint_and_bson_numeric_types(self):
        row = fixture()
        self.assertEqual(source_fingerprint(row), source_fingerprint(dict(reversed(list(row.items())))))
        self.assertEqual(len(source_fingerprint(row)), 64)
        values = (70, Int64(70), 70.0, "70", Decimal128("70"))
        self.assertEqual(len({source_fingerprint(fixture(amount=v)) for v in values}), len(values))

    def test_effective_date_amount_identity_changes_require_recalculation(self):
        original = fixture()
        keys = build_keys(original)
        for field, value in (("date", "2026-10-02"), ("amount", 71), ("id", "other"), ("user_id", "other-user")):
            edited = {**original, field: value}
            self.assertEqual(inspect_keys(edited, keys), "stale_or_corrupt")
            self.assertEqual(inspect_keys(edited, build_keys(edited)), "ready")

    def test_administrative_filter_link_and_journal_changes_do_not_recalculate(self):
        row = fixture()
        updated = {**row, "account_id": "B", "category_id": "C", "type": "transfer", "to_account_id": "D",
                   "notes": "new", "_reference_revision": 9, "_payment_revision": 3,
                   "bill_id": "bill", "recurring_record_id": "receipt", "_shared_intent": {"payload": "opaque"},
                   "request_fingerprint": "original", "_history_keys": {"obsolete": True}}
        self.assertEqual(build_keys(row), build_keys(updated))

    def test_omitted_and_explicit_fields_use_effective_document(self):
        row = fixture(date="20261001T120000Z")
        self.assertEqual(build_keys({**row, "notes": "edited"}), build_keys(row))
        self.assertEqual(build_keys({**row, "date": None})["reason"], "date")
        self.assertEqual(build_keys({**row, "amount": None})["amount"].to_decimal(), 0)

    def test_no_source_mutation_including_journals(self):
        row = fixture(_shared_intent={"payload": {"date": None, "amount": 70}, "id": "original"},
                      request_fingerprint="original", idempotency_key="original")
        before = copy.deepcopy(row)
        keys = build_keys(row)
        inspect_keys(row, keys)
        public_model({"items": [{**row, "_history_keys": keys}]})
        self.assertEqual(row, before)

    def test_missing_metadata_no_automatic_adoption(self):
        row = fixture()
        before = copy.deepcopy(row)
        self.assertEqual(inspect_keys(row, None), "missing")
        self.assertEqual(row, before)

    def test_incompatible_version_generation_and_boolean_version(self):
        row = fixture()
        for field, value in (("version", 2), ("generation", 2), ("version", True), ("generation", "1")):
            self.assertEqual(inspect_keys(row, {**build_keys(row), field: value}), "incompatible")

    def test_unverifiable_and_corrupt_metadata_are_not_ready(self):
        row = fixture(date="invalid")
        self.assertEqual(inspect_keys(row, build_keys(row)), "unverifiable")
        good = fixture()
        keys = build_keys(good)
        for change in ({"date_us": Int64(0)}, {"amount": Decimal128("99")}, {"source_sha256": "wrong"}, {"extra": 1}):
            self.assertEqual(inspect_keys(good, {**keys, **change}), "stale_or_corrupt")

    def test_bson_types_required_even_when_numbers_compare_equal(self):
        row = fixture()
        keys = build_keys(row)
        self.assertEqual(inspect_keys(row, {**keys, "date_us": int(keys["date_us"])}), "stale_or_corrupt")
        self.assertEqual(inspect_keys(row, {**keys, "amount": 70.0}), "stale_or_corrupt")
        self.assertEqual(inspect_keys(row, BSON(BSON.encode(keys)).decode()), "ready")

    def test_out_of_bson_range_source_integer_is_unverifiable(self):
        row = fixture(amount=2**63)
        before = copy.deepcopy(row)
        self.assertEqual(build_keys(row)["reason"], "source")
        self.assertEqual(row, before)

    def test_nonrepresentable_source_is_reported_not_rewritten(self):
        row = fixture(amount={"unexpected": "object"})
        before = copy.deepcopy(row)
        keys = build_keys(row)
        self.assertIsNone(keys["source_sha256"])
        self.assertEqual(keys["reason"], "source")
        self.assertEqual(row, before)

    def test_deterministic_all_orders_and_two_equal_legitimate_payments(self):
        rows = [fixture(id="a", amount=40), fixture(id="b", amount=40),
                fixture(id="c", amount=60, date="2026-09-01"), fixture(id="d", amount=20, date="2026-11-01")]
        expected = {"recent": ["d", "b", "a", "c"], "oldest": ["c", "a", "b", "d"],
                    "high": ["c", "b", "a", "d"], "low": ["d", "b", "a", "c"]}
        for order, ids in expected.items():
            self.assertEqual(ordered(rows, order), ids)
            self.assertEqual(ordered(list(reversed(rows)), order), ids)
            self.assertEqual(len(ordered(rows, order)), 4)

    def test_unverifiable_or_duplicate_rows_never_silently_omitted(self):
        with self.assertRaises(ValueError):
            ordered([fixture(), fixture(id="bad", date="bad")], "recent")
        with self.assertRaises(ValueError):
            ordered([fixture(), fixture()], "high")

    def test_recursive_public_contract_including_recovery(self):
        keys = build_keys(fixture())
        response = {"items": [{**fixture(), "_history_keys": keys}],
                    "recovery": {"transaction": {**fixture(), "_history_keys": keys, "_history_debug": "secret"}}}
        before = copy.deepcopy(response)
        public = public_model(response)
        self.assertNotIn("_history_keys", public["items"][0])
        self.assertEqual(public["recovery"]["transaction"], fixture())
        self.assertEqual(response, before)


if __name__ == "__main__":
    unittest.main()
