"""Bounded synthetic BSON diagnosis. No MongoDB adapter, clients, files or writes.

The source is a small-fixture oracle. A future driver must implement its read-only
batch contract and independently verify infrastructure and writer exclusion.
"""
from dataclasses import dataclass
from functools import cmp_to_key
import hashlib

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from fastapi import HTTPException

from backend.history_keys import derive_history_keys, inspect_history_keys, source_fingerprint
from backend.experiments.c3_history_provision_contract import (
    Authorization, Conflict, Observation, checkpoint, digest,
)

STATES = ("missing", "ready", "stale_or_corrupt", "unverifiable", "incompatible")
TOKEN_VERSION = 1
MAX_TOKEN_BYTES = 262144
MAX_IDENTITIES = 2048
MAX_BATCH_DOCUMENTS = 1000
MAX_BATCH_BYTES = 4194304


def typed_id(value):
    # PyMongo decodes BSON binary subtype 0 to bytes; restore its BSON wrapper
    # for the typed checkpoint contract without changing the encoded value.
    return Binary(value, 0) if type(value) is bytes else value


def physical_key(value):
    """Supported BSON _id subset under simple collation; not bytewise BSON sort.

    Numeric int32/Int64 compare by value, strings by UTF-8, Binary by length,
    subtype and bytes, ObjectId by bytes. Mixed types follow BSON type order.
    Unsupported types block; bool is not treated as an integer.
    """
    value = typed_id(value)
    checkpoint(value)
    if type(value) in (int, Int64):
        return (1, int(value))
    if type(value) is str:
        return (2, value.encode("utf-8"))
    if type(value) is Binary:
        return (3, len(value), value.subtype, bytes(value))
    if type(value) is ObjectId:
        return (4, value.binary)
    raise Conflict("unsupported_physical_id")


def compare_ids(left, right):
    a, b = physical_key(left), physical_key(right)
    return (a > b) - (a < b)


@dataclass(frozen=True)
class Batch:
    documents: tuple  # Encoded BSON, not mutable caller documents.
    has_more: bool
    revision: int


class SyntheticBsonSource:
    """Read-only bounded oracle, intentionally materializes/sorts small fixtures.

    Tests may replace the entire source between calls to simulate external writers.
    This is NOT scalable storage, a transaction snapshot or an operational tool.
    """
    def __init__(self, documents, observation, *, revision=0, fixture_bytes=8388608):
        if type(fixture_bytes) is not int or not 1 <= fixture_bytes <= 8388608:
            raise Conflict("invalid_fixture_limit")
        if type(revision) is not int or revision < 0:
            raise Conflict("invalid_source_revision")
        items, size = [], 0
        for encoded in documents:
            if type(encoded) not in (bytes, BSON):
                raise Conflict("expected_bson")
            size += len(encoded)
            if size > fixture_bytes:
                raise Conflict("fixture_limit")
            row = decode_row(encoded)
            physical_key(row.get("_id"))
            items.append((row["_id"], bytes(encoded)))
        items.sort(key=cmp_to_key(lambda a, b: compare_ids(a[0], b[0])))
        for left, right in zip(items, items[1:]):
            if compare_ids(left[0], right[0]) == 0:
                raise Conflict("duplicate_physical_id")
        self._items = tuple(items)
        self.observation = observation
        self.revision = revision

    def read_batch(self, after, max_documents, max_bytes):
        selected, size, more = [], 0, False
        for physical_id, encoded in self._items:
            if after is not None and compare_ids(physical_id, after) <= 0:
                continue
            if len(encoded) > max_bytes:
                # Pause at last successfully returned batch, never silently skip.
                raise Conflict("oversize_document")
            if selected and (len(selected) == max_documents or size + len(encoded) > max_bytes):
                more = True
                break
            selected.append(encoded)
            size += len(encoded)
        return Batch(tuple(selected), more, self.revision)


def decode_row(encoded):
    try:
        return BSON(encoded).decode()
    except Exception:
        raise Conflict("invalid_bson") from None


def _check(auth, observation):
    try:
        auth.check("diagnose", observation)
    except (HTTPException, ValueError, TypeError, AttributeError, KeyError):
        raise Conflict("authorization_or_context_invalid") from None


def _initial(auth, observation, revision):
    return {"token_version": TOKEN_VERSION, "authorization": auth.binding(),
            "last_id": None, "counts": {state: 0 for state in STATES}, "visited": 0,
            "duplicates": 0, "invalid_identity": 0, "source_unverifiable": 0,
            "generation_incompatible": 0, "seen": [], "initial_revision": revision,
            "source_changed": False, "initial_epoch": observation.exclusion_epoch,
            "controlled": observation.writers_excluded and bool(observation.exclusion_epoch),
            "completed": False}


def encode_progress(state):
    # Integrity checksum is not an authorization signature. Tokens are private
    # in-process evidence only; never accept them as external certificates.
    payload = BSON.encode(state)
    encoded = BSON.encode({"payload": Binary(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    if len(encoded) > MAX_TOKEN_BYTES:
        raise Conflict("checkpoint_limit")
    return bytes(encoded)


def decode_progress(token, auth):
    try:
        if type(token) not in (bytes, BSON) or len(token) > MAX_TOKEN_BYTES:
            raise ValueError()
        envelope = BSON(token).decode()
        if set(envelope) != {"payload", "sha256"} or type(envelope["payload"]) is not bytes:
            raise ValueError()
        payload = envelope["payload"]
        if envelope["sha256"] != hashlib.sha256(payload).hexdigest():
            raise ValueError()
        state = BSON(payload).decode()
        expected = _initial(auth, Observation(auth.target, {}), 0)
        if (set(state) != set(expected) or type(state["token_version"]) is not int or state["token_version"] != TOKEN_VERSION
                or state["authorization"] != auth.binding()):
            raise ValueError()
        if state["last_id"] is not None:
            state["last_id"] = typed_id(state["last_id"])
            physical_key(state["last_id"])
        for name in ("visited", "duplicates", "invalid_identity", "source_unverifiable",
                     "generation_incompatible", "initial_revision"):
            if type(state[name]) is not int or state[name] < 0:
                raise ValueError()
        if (set(state["counts"]) != set(STATES) or any(type(v) is not int or v < 0 for v in state["counts"].values())
                or sum(state["counts"].values()) != state["visited"]
                or type(state["seen"]) is not list or len(state["seen"]) > MAX_IDENTITIES
                or len(set(state["seen"])) != len(state["seen"])
                or any(type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
                       for v in state["seen"])):
            raise ValueError()
        if any(type(state[k]) is not bool for k in ("source_changed", "controlled", "completed")):
            raise ValueError()
        if state["initial_epoch"] is not None and type(state["initial_epoch"]) is not str:
            raise ValueError()
        return state
    except Exception:
        raise Conflict("invalid_or_unbound_checkpoint") from None


def diagnose_bson(auth: Authorization, source: SyntheticBsonSource, *, token=None,
                  max_documents=100, max_bytes=1048576, max_batches=None):
    """Read-only diagnosis; returns (aggregated public report, private BSON token).

    At most max_batches per call, unless None. Resumption counts visited rows,
    not a current snapshot of a changing dataset. No real certification issued.
    """
    if (type(max_documents) is not int or not 1 <= max_documents <= MAX_BATCH_DOCUMENTS
            or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BATCH_BYTES
            or (max_batches is not None and (type(max_batches) is not int or max_batches < 1))):
        raise Conflict("invalid_batch_limits")
    _check(auth, source.observation)
    state = decode_progress(token, auth) if token is not None else _initial(auth, source.observation, source.revision)
    seen = set(state["seen"])
    batches_read, peak_documents, peak_bytes = 0, 0, 0
    while True:
        observation = source.observation
        _check(auth, observation)  # Recheck before every batch, not only startup.
        controlled_now = observation.writers_excluded and bool(observation.exclusion_epoch)
        if state["controlled"] and (not controlled_now or observation.exclusion_epoch != state["initial_epoch"]
                                    or source.revision != state["initial_revision"]):
            raise Conflict("writer_window_changed")
        state["source_changed"] |= source.revision != state["initial_revision"]
        if state["completed"]:
            break
        batch = source.read_batch(state["last_id"], max_documents, max_bytes)
        if batch.revision != source.revision:
            raise Conflict("source_changed_during_batch")
        _check(auth, source.observation)
        if state["controlled"] and (not source.observation.writers_excluded
                                    or source.observation.exclusion_epoch != state["initial_epoch"]
                                    or batch.revision != state["initial_revision"]):
            raise Conflict("writer_window_changed")
        width = sum(len(b) for b in batch.documents)
        if len(batch.documents) > max_documents or width > max_bytes or (batch.has_more and not batch.documents):
            raise Conflict("invalid_batch")
        peak_documents, peak_bytes = max(peak_documents, len(batch.documents)), max(peak_bytes, width)
        for encoded in batch.documents:
            row = decode_row(encoded)
            if row.get("user_id") != auth.target.user_id:
                raise Conflict("scope_mismatch")
            physical_id = typed_id(row.get("_id"))
            physical_key(physical_id)
            if state["last_id"] is not None and compare_ids(physical_id, state["last_id"]) <= 0:
                raise Conflict("unordered_batch")
            status = inspect_history_keys(row, auth.generation)
            derived = derive_history_keys(row, auth.generation)
            # Explicitly exercise canonical fingerprint, never expose it in report.
            try:
                if source_fingerprint(row) != derived["source_sha256"]:
                    raise Conflict("canonical_fingerprint_disagreement")
            except (ValueError, OverflowError):
                if derived.get("reason") != "source":
                    raise Conflict("canonical_fingerprint_disagreement") from None
            state["counts"][status] += 1
            state["source_unverifiable"] += derived["state"] == "unverifiable"
            valid_id = isinstance(row.get("id"), str) and 1 <= len(row["id"]) <= 256
            state["invalid_identity"] += not valid_id
            if valid_id:
                identity = digest({"user_id": row["user_id"], "id": row["id"]})
                if identity in seen:
                    state["duplicates"] += 1
                else:
                    if len(seen) >= MAX_IDENTITIES:
                        raise Conflict("duplicate_detection_limit")
                    seen.add(identity)
            keys = row.get("_history_keys")
            state["generation_incompatible"] += (isinstance(keys, dict)
                and (type(keys.get("generation")) is not int or keys["generation"] != auth.generation))
            state["visited"] += 1
            state["last_id"] = physical_id
        batches_read += 1
        state["completed"] = not batch.has_more
        if state["completed"] or (max_batches is not None and batches_read >= max_batches):
            break
    state["seen"] = sorted(seen)
    clean = (set(k for k, v in state["counts"].items() if v) <= {"ready"}
             and not state["duplicates"] and not state["invalid_identity"])
    eligible = (state["completed"] and state["controlled"] and not state["source_changed"]
                and source.observation.maintained_writers and clean)
    report = {"counts": dict(state["counts"]), "visited": state["visited"],
              "duplicates": state["duplicates"], "invalid_identity": state["invalid_identity"],
              "source_unverifiable": state["source_unverifiable"],
              "generation_incompatible": state["generation_incompatible"],
              "completed": state["completed"], "source_changed": state["source_changed"],
              "view": "controlled_fixture" if state["controlled"] else "live",
              "certification_eligible_in_fixture": bool(eligible), "certified": False,
              "indexed_reads_allowed": False, "evidence": "offline_synthetic",
              "batches_this_call": batches_read, "peak_batch_documents": peak_documents,
              "peak_batch_bytes": peak_bytes}
    return report, encode_progress(state)
