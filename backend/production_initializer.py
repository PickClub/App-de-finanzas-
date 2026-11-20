"""Administrative bootstrap engine. No client construction, CLI, DNS, or startup hook.

The database is injected by an explicitly authorized operator. Offline tests inject
an in-memory double. A future live connector must use MongoTarget.mongo_options(),
verify_private_network(), and an exclusive maintenance window before injection.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from backend.auth_mongodb import ACCOUNT_DATA_COLLECTIONS
from backend.financial_context import validate_metadata
from backend.production_config import MongoTarget
from backend.production_services import index_plan


class InitializationBlocked(RuntimeError):
    """Sanitized failure; never forward driver errors or document contents."""


COLLECTIONS = tuple(sorted(set(ACCOUNT_DATA_COLLECTIONS) | {
    "users", "auth_users", "auth_sessions", "auth_refresh", "auth_challenges",
    "auth_rate_limits", "moneyflow_metadata",
}))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def index_signature(index):
    """Ignore only server bookkeeping and the arbitrary index name."""
    return {
        key: value for key, value in index.items()
        if key not in {"name", "ns", "v", "background"}
    }


@dataclass(frozen=True)
class DryRun:
    state_digest: str
    actions: tuple


class Initializer:
    """Empty-database-only, resumable bootstrap. Never repairs populated databases."""

    def __init__(self, env, database):
        self.config = MongoTarget.load(env)
        if (env.get("PW_MONGO_TARGET") != "Pickwallet-prod"
                or self.config.database != "pickwallet_prod"
                or self.config.mongo_network_mode != "atlas_allowlisted"):
            raise InitializationBlocked("Explicit Atlas production target required")
        self.database = database
        self._approved_plan = None

    def _inspect(self):
        db, config = self.database, self.config
        if db.name != config.database:
            raise InitializationBlocked("Database handle target mismatch")
        hello = db.client.admin.command("hello")
        if (hello.get("setName") != config.replica_set
                or set(hello.get("hosts", ())) != set(config.mongo_hosts)
                or not hello.get("isWritablePrimary")
                or hello.get("logicalSessionTimeoutMinutes") is None
                or hello.get("maxWireVersion", 0) < 7):
            raise InitializationBlocked("Replica topology mismatch")
        inventory = list(db.list_collections())
        names = {item["name"] for item in inventory}
        if names - set(COLLECTIONS):
            raise InitializationBlocked("Unexpected collections; manual review required")
        expected = index_plan()
        state, actions = [], []
        for item in sorted(inventory, key=lambda row: row["name"]):
            name = item["name"]
            if item.get("type") != "collection" or item.get("options", {}):
                raise InitializationBlocked("Unsupported collection type or options")
            collection = db[name]
            count = collection.count_documents({})
            if name == "moneyflow_metadata":
                context = collection.find_one({"_id": "financial-context"})
                if count:
                    if (count != 1 or not context
                            or set(context) - {"_id", "version", "environment_id", "created_at"}):
                        raise InitializationBlocked("Incompatible environment metadata")
                    try:
                        # Reuse the financial read contract, including an aware ISO timestamp.
                        validate_metadata(context, config.environment_id)
                    except Exception:
                        raise InitializationBlocked("Incompatible environment metadata") from None
            elif count:
                raise InitializationBlocked("Existing application data; bootstrap refused")
            signatures = []
            allowed = [{"key": {"_id": 1}}] + [
                {"key": dict(spec["keys"]), **{
                    k: v for k, v in spec.items() if k not in {"collection", "keys"}
                }} for spec in expected if spec["collection"] == name
            ]
            for actual in collection.list_indexes():
                signature = index_signature(actual)
                if signature not in allowed:
                    raise InitializationBlocked("Incompatible or unexpected index")
                signatures.append(signature)
            state.append((name, count,
                          sorted(signatures, key=lambda row: json.dumps(row, sort_keys=True)),
                          context if name == "moneyflow_metadata" else None))
        for name in COLLECTIONS:
            if name not in names:
                actions.append(("collection", name))
        for offset, spec in enumerate(expected):
            desired = {"key": dict(spec["keys"]), **{
                k: v for k, v in spec.items() if k not in {"collection", "keys"}
            }}
            if spec["collection"] not in names or not any(
                index_signature(actual) == desired
                for actual in db[spec["collection"]].list_indexes()
            ):
                actions.append(("index", offset))
        if "moneyflow_metadata" not in names or not db["moneyflow_metadata"].count_documents({}):
            actions.append(("metadata", "financial-context"))
        identity = (config.database, config.mongo_hosts, config.replica_set, config.environment_id)
        return DryRun(fingerprint((identity, state)), tuple(actions))

    def dry_run(self):
        """Read-only inspection. No mutation is permitted until this succeeds."""
        self._approved_plan = None
        try:
            self._approved_plan = self._inspect()
            return self._approved_plan
        except InitializationBlocked:
            raise
        except Exception:
            raise InitializationBlocked("Inspection failed; no initialization authorized") from None

    def apply(self, plan, *, authorized=False):
        """Requires fresh dry-run from this instance AND separate operator authorization.

        DDL is not atomic. Failure leaves only partial structures, never deletes or
        repairs them. Reinspect and approve a fresh plan before resuming.
        """
        if not authorized or plan is None or plan is not self._approved_plan:
            raise InitializationBlocked("Prior dry-run and explicit authorization required")
        self._approved_plan = None
        try:
            if self._inspect() != plan:
                raise InitializationBlocked("Database changed after dry-run")
            specs = index_plan()
            for kind, value in plan.actions:
                if kind == "collection":
                    self.database.create_collection(value)
                elif kind == "index":
                    spec = specs[value]
                    self.database[spec["collection"]].create_index(
                        spec["keys"], **{k: v for k, v in spec.items() if k not in {"collection", "keys"}}
                    )
                else:
                    self.database["moneyflow_metadata"].insert_one({
                        "_id": "financial-context", "version": 1,
                        "environment_id": self.config.environment_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
            if self._inspect().actions:
                raise InitializationBlocked("Initialization incomplete")
        except InitializationBlocked:
            raise
        except Exception:
            raise InitializationBlocked("Initialization incomplete; inspect before retrying") from None
