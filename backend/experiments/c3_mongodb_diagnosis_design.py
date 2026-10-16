"""Pure proposal algorithms. No MongoDB client, network, files or persistence.

Query/pipeline objects are descriptions only; offline tests do not execute them.
HMAC registry is an in-memory oracle; losing it requires a complete new scan.
"""
from copy import deepcopy
import hashlib
import hmac

from bson import BSON
from bson.binary import Binary

from backend.experiments.c3_history_provision_contract import Conflict
from backend.experiments.c3_history_diagnosis_offline import physical_key, typed_id

PARTITIONS = (("int", "long"), ("string",), ("binData",), ("objectId",))
MAX_TOKEN_BYTES = 8192


def partition_for(value):
    return physical_key(value)[0] - 1


def read_filter(user_id, partition, after=None):
    if user_id != "default-user" or type(partition) is not int or not 0 <= partition < len(PARTITIONS):
        raise Conflict("invalid_scope_or_partition")
    operators = {"$type": list(PARTITIONS[partition])}
    if after is not None:
        if partition_for(after) != partition:
            raise Conflict("checkpoint_partition_mismatch")
        operators["$gt"] = typed_id(after)
    return {"user_id": user_id, "_id": operators}


def type_inventory_pipeline(user_id):
    if user_id != "default-user":
        raise Conflict("invalid_scope")
    return [{"$match": {"user_id": user_id}},
            {"$group": {"_id": {"$type": "$_id"}, "count": {"$sum": 1}}}]


def validate_inventory(counts):
    supported = {t for group in PARTITIONS for t in group}
    if any(type(n) is not int or n < 0 or (n and t not in supported) for t, n in counts.items()):
        raise Conflict("unsupported_physical_types")
    return sum(counts.values())


def duplicate_stream_pipeline(user_id):
    if user_id != "default-user":
        raise Conflict("invalid_scope")
    # Exact scalar string check, not query $type that also matches array elements.
    return [{"$match": {"user_id": user_id, "$expr": {"$eq": [{"$type": "$id"}, "string"]}}},
            {"$project": {"_id": 1, "id": 1, "user_id": 1}},
            {"$sort": {"id": 1, "_id": 1}}]


def summarize_duplicate_stream(rows, user_id):
    """Adjacent exact comparison on trusted simple-collation sorted stream.

    Retains one <=256-char logical ID. No hash/set of all IDs, no IDs in output.
    Physical order tie-break is provided by proposed MongoDB sort, not this helper.
    Invalid/out-of-scope or unordered input blocks; never silently skip.
    """
    if user_id != "default-user":
        raise Conflict("invalid_scope")
    previous, group_size, total, duplicate_groups, extra = None, 0, 0, 0, 0
    for row in rows:
        identity = row.get("id")
        if row.get("user_id") != user_id or type(identity) is not str or not 1 <= len(identity) <= 256:
            raise Conflict("invalid_duplicate_stream_identity")
        if previous is not None and identity.encode("utf-8") < previous.encode("utf-8"):
            raise Conflict("unordered_duplicate_stream")
        if identity == previous:
            extra += 1
            group_size += 1
            if group_size == 2:
                duplicate_groups += 1
        else:
            previous, group_size = identity, 1
        total += 1
    return {"visited": total, "duplicate_groups": duplicate_groups, "extra_documents": extra}


def pack_bounded(rows, max_documents, max_bytes):
    """Pure streaming BSON batch oracle; one-record lookahead, no full history."""
    if type(max_documents) is not int or max_documents < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise Conflict("invalid_batch_limits")
    batch, size = [], 0
    for raw in rows:
        if type(raw) not in (bytes, BSON):
            raise Conflict("expected_bson")
        if len(raw) > max_bytes:
            raise Conflict("oversize_document")
        if batch and (len(batch) == max_documents or size + len(raw) > max_bytes):
            yield tuple(batch)
            batch, size = [], 0
        batch.append(bytes(raw))
        size += len(raw)
    if batch:
        yield tuple(batch)


class CheckpointAuthority:
    """Synthetic HMAC issuer + volatile anti-replay registry, not a real service.

    Signing key stays out of tokens/reports. Production needs secret management.
    No registry persistence is implemented or authorized by this prototype.
    """
    def __init__(self, key):
        if type(key) is not bytes or len(key) < 32:
            raise Conflict("invalid_signing_key")
        self._key = key
        self._latest = {}
        self._progress = {}

    def issue(self, auth, observation, *, partition, last_id, visited, exhausted=False):
        auth.check("diagnose", observation)
        read_filter(auth.target.user_id, partition, last_id)
        if type(exhausted) is not bool or type(visited) is not int or not 0 <= visited <= 2147483647:
            raise Conflict("invalid_progress")
        binding = auth.binding()
        old = self._progress.get(binding)
        if old:
            if partition < old["partition"] or partition > old["partition"] + 1 or visited < old["visited"]:
                raise Conflict("non_monotonic_progress")
            if partition > old["partition"] and not old["exhausted"]:
                raise Conflict("partition_not_exhausted")
            if partition == old["partition"] and old["exhausted"]:
                raise Conflict("partition_already_exhausted")
            final_empty_batch = (exhausted and visited == old["visited"]
                                 and BSON.encode({"id": typed_id(last_id)}) == BSON.encode({"id": old["last_id"]}))
            if partition == old["partition"] and not final_empty_batch and (last_id is None or
                    (old["last_id"] is not None and physical_key(last_id) <= physical_key(old["last_id"]))):
                raise Conflict("non_monotonic_progress")
        elif partition != 0:
            raise Conflict("initial_partition_required")
        sequence = 0 if old is None else old["sequence"] + 1
        payload = {"version": 1, "binding": binding, "partition": partition,
                   "last_id": typed_id(last_id), "visited": visited, "sequence": sequence, "exhausted": exhausted}
        encoded = BSON.encode(payload)
        mac = hmac.new(self._key, b"c3-diagnose-checkpoint-v1\0" + encoded, hashlib.sha256).digest()
        token = bytes(BSON.encode({"payload": Binary(encoded), "mac": Binary(mac)}))
        if len(token) > MAX_TOKEN_BYTES:
            raise Conflict("checkpoint_limit")
        self._latest[binding] = hashlib.sha256(token).digest()
        self._progress[binding] = deepcopy(payload)
        return token

    def accept(self, auth, observation, token):
        auth.check("diagnose", observation)
        try:
            if type(token) not in (bytes, BSON) or len(token) > MAX_TOKEN_BYTES:
                raise ValueError()
            envelope = BSON(token).decode()
            if set(envelope) != {"payload", "mac"} or type(envelope["payload"]) is not bytes or type(envelope["mac"]) is not bytes:
                raise ValueError()
            raw = envelope["payload"]
            expected = hmac.new(self._key, b"c3-diagnose-checkpoint-v1\0" + raw, hashlib.sha256).digest()
            if not hmac.compare_digest(envelope["mac"], expected):
                raise ValueError()
            payload = BSON(raw).decode()
            if (set(payload) != {"version", "binding", "partition", "last_id", "visited", "sequence", "exhausted"}
                    or type(payload["version"]) is not int or payload["version"] != 1
                    or payload["binding"] != auth.binding()):
                raise ValueError()
            payload["last_id"] = typed_id(payload["last_id"])
            read_filter(auth.target.user_id, payload["partition"], payload["last_id"])
            if self._latest.get(auth.binding()) != hashlib.sha256(token).digest():
                raise ValueError()
            return payload
        except Exception:
            raise Conflict("checkpoint_unverifiable") from None
