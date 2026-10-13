"""Private history key contract. Pure functions; no clients, queries or writes.

Nothing in this module activates persistence or optimized reads. Derive only
from the effective stored movement, never from a financial intent/journal.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
import hashlib
import math

from bson import BSON
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from fastapi import HTTPException

if __package__:
    from .transaction_history import parse_instant
else:
    from transaction_history import parse_instant

VERSION = 1
SOURCE_FIELDS = ("id", "user_id", "date", "amount")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
PUBLIC_PROJECTION = {"_history_keys": 0}


def _generation(value):
    if type(value) is not int or value < 1:
        raise ValueError("History generation must be a positive integer")
    return value


def source_fingerprint(document):
    source = []
    for field in SOURCE_FIELDS:
        if field not in document:
            source.append({"field": field, "present": False})
            continue
        value = document[field]
        if not (value is None or type(value) in (str, int, float, bool)
                or isinstance(value, (Int64, Decimal128))):
            raise ValueError("Unsupported history source type")
        source.append({"field": field, "present": True,
                       "scalar_bson": BSON.encode({"value": value}).hex()})
    return hashlib.sha256(BSON.encode({"contract": VERSION, "source": source})).hexdigest()


def _amount(document):
    value = document.get("amount")
    if value is None or value == "":
        value = 0  # Sorting fallback only, never a financial amount correction.
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
    result = Decimal128(decimal)
    if result.to_decimal() != decimal:
        raise ValueError("Lossy amount conversion")
    return result


def derive_history_keys(document, generation):
    result = {"version": VERSION, "generation": _generation(generation),
              "state": "unverifiable", "source_sha256": None}
    try:
        result["source_sha256"] = source_fingerprint(document)
    except (ValueError, OverflowError):
        return {**result, "reason": "source"}
    if any(not isinstance(document.get(f), str) or not 1 <= len(document[f]) <= 256
           for f in ("id", "user_id")):
        return {**result, "reason": "identity"}
    try:
        delta = parse_instant(document.get("date"), stored=True) - EPOCH
        date_us = Int64(delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds)
        BSON.encode({"date_us": date_us})
    except (HTTPException, ValueError, OverflowError):
        return {**result, "reason": "date"}
    try:
        amount = _amount(document)
    except (ValueError, DecimalException, OverflowError):
        return {**result, "reason": "amount"}
    return {**result, "state": "ready", "date_us": date_us, "amount": amount}


def inspect_history_keys(document, expected_generation):
    generation = _generation(expected_generation)
    if "_history_keys" not in document:
        return "missing"
    keys = document["_history_keys"]
    if not isinstance(keys, dict):
        return "incompatible"
    if (type(keys.get("version")) is not int or keys["version"] != VERSION
            or type(keys.get("generation")) is not int or keys["generation"] != generation):
        return "incompatible"
    if keys.get("state") == "ready" and (type(keys.get("date_us")) is not Int64
                                          or type(keys.get("amount")) is not Decimal128):
        return "stale_or_corrupt"
    expected = derive_history_keys(document, generation)
    return expected["state"] if keys == expected else "stale_or_corrupt"


def with_history_keys(document, generation):
    result = deepcopy(document)
    result["_history_keys"] = derive_history_keys(document, generation)
    return result


def history_update_fields(current, final, generation):
    """Prepare a private $set fragment, never perform a write or a backfill.

    Same source leaves missing/obsolete metadata alone. For unencodable sources,
    compare presence, Python type and value to avoid adopting administrative edits.
    Never normalize the caller's final financial document.
    """
    _generation(generation)
    try:
        unchanged = source_fingerprint(current) == source_fingerprint(final)
    except (ValueError, OverflowError):
        unchanged = all((f in current) == (f in final)
                        and (f not in current or (type(current[f]) is type(final[f]) and current[f] == final[f]))
                        for f in SOURCE_FIELDS)
    return {} if unchanged else {"_history_keys": derive_history_keys(final, generation)}


def strip_history_metadata(value):
    """Copy and recursively remove reserved metadata at the public boundary."""
    if isinstance(value, dict):
        return {key: strip_history_metadata(item) for key, item in value.items()
                if not key.startswith("_history")}
    if isinstance(value, (list, tuple)):
        return [strip_history_metadata(item) for item in value]
    return deepcopy(value)
