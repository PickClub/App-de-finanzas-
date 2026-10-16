"""P3 canonical Python date adapter; offline only, no MongoDB, indexes or writes.

This does NOT replace P2's MongoDB parser or activate materialized keys.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.transaction_history import parse_instant as _reference_parse

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class DateKey:
    original: str
    instant: datetime
    utc_microseconds: int


def normalize_stored_date(value):
    """Exactly the C3 stored-date interpretation, never an independent grammar.

    HTTP 409 from the canonical reader propagates; no strip, guessing, repair,
    silent omission or rewriting. Signed integer arithmetic avoids float loss.
    """
    instant = _reference_parse(value, stored=True)
    delta = instant - EPOCH
    key = delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds
    if not -(2**63) <= key < 2**63:
        raise OverflowError("Date key outside signed 64-bit range")
    return DateKey(value, instant, key)


def inspect_date_keys(rows, predicate=lambda row: True, window=None):
    """Test-only projection: separate keys, never attach fields to originals.

    Filter before inspecting candidates; malformed dates fail rather than vanish.
    This is not numbered pagination or a persistence/indexing implementation.
    """
    lower = normalize_stored_date(window[0]).utc_microseconds if window and window[0] else None
    upper = normalize_stored_date(window[1]).utc_microseconds if window and window[1] else None
    for row in rows:
        if not predicate(row):
            continue
        normalized = normalize_stored_date(row.get("date"))
        if lower is not None and normalized.utc_microseconds < lower:
            continue
        if upper is not None and normalized.utc_microseconds >= upper:
            continue
        yield row["id"], normalized
