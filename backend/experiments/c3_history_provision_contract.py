"""Offline administrative state model, NOT a MongoDB adapter or executable CLI.

No clients, environment loading, file persistence or financial writes. Observations
and writer exclusion are supplied by tests; they do not prove real infrastructure.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId

from backend.financial_context import validate_environment_id, validate_metadata
from backend.history_keys import VERSION, derive_history_keys, inspect_history_keys, source_fingerprint


class Conflict(ValueError):
    """Fixed diagnostic code only, never interpolate source documents or URIs."""


def exact(value):
    return BSON.encode({"value": value})


def digest(value):
    return hashlib.sha256(exact(value)).hexdigest()


def metadata(row):
    return {"present": "_history_keys" in row,
            "value": deepcopy(row.get("_history_keys"))}


def checkpoint(value):
    # Preserve BSON scalar type. No JSON number coercion or date/amount cursor.
    if type(value) not in (str, int, Int64, ObjectId, Binary):
        raise Conflict("unsupported_checkpoint")
    return exact(value)


@dataclass(frozen=True)
class Target:
    uri: str                         # In-memory only; never in reports/manifests.
    database: str
    collection: str
    collection_uuid: Binary
    environment_id: str
    user_id: str = "default-user"

    def binding(self):
        validate_environment_id(self.environment_id)
        if (not self.uri.startswith("mongodb://") or "@" in self.uri
                or not self.database or not self.collection
                or type(self.collection_uuid) is not Binary
                or self.collection_uuid.subtype != 4 or len(self.collection_uuid) != 16
                or self.user_id != "default-user"):
            raise Conflict("invalid_target")
        # Prototype forbids credential-bearing URI; future adapter uses a secret
        # provider and a separately pinned, non-secret deployment identifier.
        return digest({"uri_digest": digest(self.uri), "database": self.database,
                       "collection": self.collection, "uuid": self.collection_uuid,
                       "environment_id": self.environment_id, "user_id": self.user_id})


@dataclass(frozen=True)
class Authorization:
    target: Target
    run_id: str
    revision: str
    version: int
    generation: int
    actions: tuple
    scope: str = "entire_effective_user"   # No implicit partial certificate.
    approved: bool = False
    replacement: bool = False              # Explicit approval of old metadata replacement.

    def check(self, action, observation):
        if (self.approved is not True or action not in self.actions
                or self.scope != "entire_effective_user" or not self.run_id
                or len(self.revision) != 40
                or any(c not in "0123456789abcdef" for c in self.revision)
                or type(self.version) is not int or self.version != VERSION
                or type(self.generation) is not int or not 1 <= self.generation <= 2147483647):
            raise Conflict("not_authorized")
        if self.target.binding() != observation.target.binding():
            raise Conflict("destination_changed")
        validate_metadata(observation.r6_metadata, self.target.environment_id)
        if observation.optimized_reads:
            raise Conflict("readers_must_be_disabled")
        if action in ("apply", "revert") and not observation.transactions:
            raise Conflict("transactions_required")

    def binding(self):
        return digest({"target": self.target.binding(), "run": self.run_id,
                       "revision": self.revision, "version": self.version,
                       "generation": self.generation, "scope": self.scope,
                       "replacement": self.replacement})


@dataclass(frozen=True)
class Observation:
    target: Target
    r6_metadata: dict
    transactions: bool = True
    optimized_reads: bool = False
    writers_excluded: bool = False
    exclusion_epoch: str | None = None
    complete_scan: bool = False
    maintained_writers: bool = False


@dataclass(frozen=True)
class Plan:
    authorization: str
    physical_id: bytes
    source: str
    before: dict
    after: dict
    seal: str


def plan_seal(binding, physical_id, source, before, after):
    return digest({"authorization": binding, "physical_id": Binary(physical_id),
                   "source": source, "before": before, "after": after})


def batches(rows, max_documents, max_bytes):
    """Iterator must come from a bounded, BSON-_id-ordered adapter in the future.

    This model bounds batch content, not input materialization/network buffering.
    Oversize document blocks traversal; never skip it to certify completeness.
    """
    if type(max_documents) is not int or max_documents < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise Conflict("invalid_batch_limits")
    batch, size = [], 0
    for row in rows:
        checkpoint(row["_id"])
        width = len(BSON.encode(row))
        if width > max_bytes:
            raise Conflict("oversize_document")
        if batch and (len(batch) == max_documents or size + width > max_bytes):
            yield batch
            batch, size = [], 0
        batch.append(row)
        size += width
    if batch:
        yield batch


def diagnose(auth, observation, rows, max_documents=100, max_bytes=1048576):
    auth.check("diagnose", observation)
    counts, seen, duplicate_count, last = {}, set(), 0, None
    # In-memory duplicate set is deliberately ONLY a small-fixture oracle. Future
    # adapter requires bounded external exact detection, not an unbounded set.
    for batch in batches(rows, max_documents, max_bytes):
        for row in batch:
            if row.get("user_id") != auth.target.user_id:
                raise Conflict("scope_mismatch")
            state = inspect_history_keys(row, auth.generation)
            candidate = derive_history_keys(row, auth.generation)
            if candidate["state"] == "unverifiable" and candidate["reason"] == "identity":
                state = "invalid_identity"
            counts[state] = counts.get(state, 0) + 1
            identity = digest({"user": row.get("user_id"), "id": row.get("id")})
            duplicate_count += identity in seen
            seen.add(identity)
            last = checkpoint(row["_id"])
    return {"counts": counts, "duplicates": duplicate_count, "checkpoint": last,
            "target": auth.target.binding(), "live_scan": True}


def prepare(auth, observation, row):
    auth.check("apply", observation)
    if row.get("user_id") != auth.target.user_id:
        raise Conflict("scope_mismatch")
    state = inspect_history_keys(row, auth.generation)
    if state == "ready":
        raise Conflict("already_ready_no_plan")
    if state not in ("missing", "unverifiable") and not auth.replacement:
        raise Conflict("replacement_requires_approval")
    after = derive_history_keys(row, auth.generation)
    # Marking an unverifiable row never turns it into an indexed-read candidate.
    if after["state"] != "ready":
        raise Conflict("source_unverifiable")
    physical_id, source, before = checkpoint(row["_id"]), source_fingerprint(row), metadata(row)
    binding = auth.binding()
    return Plan(binding, physical_id, source, before, after,
                plan_seal(binding, physical_id, source, before, after))


class MemoryLedger:
    """Toy transaction oracle. Nothing here connects to or provisions MongoDB."""
    def __init__(self, rows):
        self.rows = {checkpoint(r["_id"]): deepcopy(r) for r in rows}
        self.journal = {}
        self.revisions = {key: 0 for key in self.rows}

    def external_edit(self, physical_id, fields):
        self.rows[physical_id].update(deepcopy(fields))
        self.revisions[physical_id] += 1  # Even ABA or administrative writes.

    def apply(self, auth, observation, plan, fault=None):
        auth.check("apply", observation)  # Models revalidation inside transaction.
        binding = auth.binding()
        if (plan.authorization != binding or plan.seal != plan_seal(
                binding, plan.physical_id, plan.source, plan.before, plan.after)):
            raise Conflict("plan_changed")
        key = (auth.run_id, plan.physical_id)
        existing = self.journal.get(key)
        if existing:
            if existing["seal"] != plan.seal or existing["state"] == "revertido":
                raise Conflict("journal_conflict")
            return "confirmado"  # Original commit, not claim current coverage.
        current = self.rows.get(plan.physical_id)
        if (current is None or current.get("user_id") != auth.target.user_id
                or source_fingerprint(current) != plan.source
                or exact(metadata(current)) != exact(plan.before)
                or exact(derive_history_keys(current, auth.generation)) != exact(plan.after)):
            raise Conflict("concurrent_change")
        proposed = deepcopy(current)
        proposed["_history_keys"] = deepcopy(plan.after)
        record = {"seal": plan.seal, "state": "confirmado", "source": plan.source,
                  "before": deepcopy(plan.before), "after": deepcopy(plan.after),
                  "epoch": observation.exclusion_epoch if observation.writers_excluded else None,
                  "revision": self.revisions[plan.physical_id] + 1,
                  "authorization": binding}
        if fault == "before_commit":
            raise Conflict("aborted")  # Neither movement nor journal published.
        self.rows[plan.physical_id] = proposed
        self.revisions[plan.physical_id] = record["revision"]
        self.journal[key] = record  # Models atomic publication of both documents.
        return "incierto" if fault == "after_commit" else "confirmado"

    def reconcile(self, auth, observation, plan):
        auth.check("verify", observation)
        record = self.journal.get((auth.run_id, plan.physical_id))
        if record is None:
            return "incierto"  # Absence is not proof of rollback.
        if (record["seal"] != plan.seal or record["authorization"] != auth.binding()
                or plan.seal != plan_seal(auth.binding(), plan.physical_id, plan.source, plan.before, plan.after)):
            raise Conflict("journal_conflict")
        return record["state"]

    def revert(self, auth, observation, plan, fault=None):
        auth.check("revert", observation)
        record = self.journal.get((auth.run_id, plan.physical_id))
        if (not record or record["seal"] != plan.seal or record["authorization"] != auth.binding()):
            raise Conflict("journal_conflict")
        if record["state"] == "revertido":
            return "revertido"
        current = self.rows.get(plan.physical_id)
        if (not observation.writers_excluded or not record["epoch"]
                or observation.exclusion_epoch != record["epoch"]
                or self.revisions.get(plan.physical_id) != record["revision"]
                or current is None or source_fingerprint(current) != record["source"]
                or exact(metadata(current)) != exact({"present": True, "value": record["after"]})):
            raise Conflict("intermediate_writes_not_excluded")
        proposed = deepcopy(current)
        if record["before"]["present"]:
            proposed["_history_keys"] = deepcopy(record["before"]["value"])
        else:
            proposed.pop("_history_keys", None)
        if fault == "before_commit":
            raise Conflict("aborted")
        self.rows[plan.physical_id] = proposed
        self.revisions[plan.physical_id] += 1
        record["state"] = "revertido"
        return "incierto" if fault == "after_commit" else "revertido"


def verify(auth, observation, rows):
    auth.check("verify", observation)
    # Reuse read-only oracle with explicit diagnose permission as well.
    report = diagnose(auth, observation, rows)
    complete = (report["duplicates"] == 0 and set(report["counts"]) <= {"ready"}
                and observation.writers_excluded and bool(observation.exclusion_epoch)
                and observation.complete_scan and observation.maintained_writers)
    return {**report, "certified": complete, "indexed_reads_allowed": complete}
