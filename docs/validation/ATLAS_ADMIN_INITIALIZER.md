# Atlas administrative initializer — offline preparation

## Status and scope

Prepared for `Pickwallet-prod` / `pickwallet_prod`. No connection, live dry-run,
initialization, deployment, or database write has been performed by this delivery.
The initializer is a separate administrative Python engine, not an application
startup hook or executable network command. It never constructs a MongoClient,
loads dotenv files, resolves DNS, provisions users, or sends mail.

Files:
- `backend/production_initializer.py`
- `backend/tests/test_production_initializer.py`

## Contract

`MongoTarget.load()` from `production_config.py` validates configuration without
network access. The initializer additionally requires the explicit production
marker, Atlas allowlist mode, and the exact database name. Collection names come
from `ACCOUNT_DATA_COLLECTIONS`, plus authentication, profile and metadata
collections. Index specifications are obtained directly from
`production_services.index_plan()`; there is no second index catalog.

The present contract contains 24 collections and 39 explicit indexes, in addition
to native `_id` indexes. Bootstrap inserts only one control document:
`moneyflow_metadata` / `_id=financial-context`, version 1, configured environment
UUID and UTC creation timestamp. It does not create application users, categories,
financial records, or QA fixtures. No seed endpoint is used.

## Mandatory execution protocol (future, separately authorized)

1. Obtain explicit authorization for live inspection first. Confirm the Atlas
   cluster label in its control plane: MongoDB `hello` cannot prove that label.
2. Configure `PW_MONGO_*` and `PW_ENVIRONMENT_ID` using the existing template and
   a secret store. Never put a URI in arguments, reports, source or output.
   The current contract requires explicit standard seed-list TLS configuration,
   not SRV. Use a temporary bootstrap identity, never the runtime identity.
3. Implement/review the live connector under a separate authorization. Before
   injecting its database handle, use `MongoTarget.verify_private_network()` and
   construct a TLS-validating client with `MongoTarget.mongo_options()`. Never
   disable certificate/hostname checks. Ensure the database handle actually uses
   those options. The engine cannot certify transport options of an injected
   handle. No live connector is included or executed in this delivery.
4. Stop application access to the target through an exclusive maintenance window;
   permit only one bootstrap operator. Initial DDL is not transactional and this
   engine is not a distributed lock. No application or competing administrator
   may write during inspection or initialization.
5. Construct `Initializer(environment, database)` and call `dry_run()`. This only
   inspects topology, collections, counts, metadata and indexes. Review its action
   list and state digest. This live inspection itself needs network authorization.
6. Obtain separate explicit approval of those actions before calling
   `apply(plan, authorized=True)` in the same operator instance. The boolean is
   an API guard, not user consent, an IAM permission or a security boundary.
   Apply rejects missing/foreign/consumed plans and changed preflight state.
7. Apply creates only missing collections/indexes and the absent control document.
   It verifies a new inspection has no remaining actions before returning success.
   Capture only sanitized outcome/action counts; do not log driver exceptions,
   credentials, collection contents or the environment mapping.
8. On any failure, report initialization as incomplete. Do not drop, truncate,
   repair or roll back collections. Review the partial state, obtain a new dry-run
   and explicit approval, and then resume. Repetition on a complete, empty schema
   performs zero writes. Populated databases are intentionally rejected.
9. Remove the bootstrap identity after verification. Separately validate backend
   readiness with the restricted runtime identity and existing `verify_database`.
   No automatic runtime activation is part of this procedure.

There is intentionally no ready-to-run real initialization command in this
preparation. Importing the module and running the offline test command cannot
connect to MongoDB.

## Refusal conditions

- Wrong production marker, mode, configuration, database handle or replica topology.
- Unknown collections, views, nonempty collection options, or unexpected indexes.
- Any application documents, even if they appear compatible. This includes user
  profiles, authentication records, financial data and rate-limit counters.
- Metadata with wrong UUID/version, additional documents or unsupported fields.
- Nonmatching required index options, including sparse/partial unique indexes.
- Changed state after dry-run, unavailable inspection or interrupted write.

The initializer does not infer compatibility, copy records, migrate schemas,
modify existing indexes, delete records, or adopt unrelated metadata. Empty
partial structures can be resumed. Existing data requires a separate review.

## Permissions to review before any live use

The temporary probe's collection-scoped `listIndexes` permission is insufficient.
The bootstrap custom role needs collection inventory (`listCollections`), `find`
for counts and metadata inspection, `listIndexes`, `createCollection`,
`createIndex`, and `insert` for the sole metadata write. Scope grants to the
approved database/collections and restrict the user to the approved Atlas cluster.
No delete, update, drop, user administration or unrestricted role is required.
Confirm actual Atlas privilege behavior with a separately authorized read-only
inspection. No privilege has been created or tested here.

Runtime privileges remain governed by the existing `verify_database` contract;
bootstrap permissions are intentionally different and must never be retained by
the application user.

## Offline verification

Run from the repository root:

```bash
python3 -B -m unittest backend.tests.test_production_initializer -v
```

Result: **18 tests passed**, zero test failures in the final run. All database
operations use in-memory doubles; socket construction, connection and DNS calls
are blocked during tests. The initial dependency-backed attempts could not load:
`backend/.venv` lacks PyMongo and system Python lacks Argon2. Nothing was installed.
The final suite evaluates the actual pure collection/index definitions via AST,
without importing unrelated authentication/driver dependencies. It exercises the
real initializer and configuration parser; it does not certify authentication,
Motor, PyMongo transport, TLS, Atlas permissions or server semantics.

Coverage includes all collection data guards, dry-run without mutations, complete
schema creation, exact index counts/options, no-op repetition, required approval,
plan origin/reuse, topology mismatch, metadata mismatch, incompatible structures,
stale state, sanitized failures, and resumable injected failures at five write
positions (including the metadata insert).

## Outstanding live gates

- Authorize/review a TLS connector, secrets, network allowlist and temporary role.
- Validate actual target inventory, replica members and permissions.
- Enforce an exclusive maintenance window; preflight checks cannot prevent a
  concurrent external writer after inspection.
- Test server DDL, acknowledged/ambiguous operation failures and recovery in an
  explicitly authorized disposable environment first.
- Verify runtime readiness, user isolation, transaction failover/ambiguous commit,
  backups and restore/deleted-account reconciliation separately before beta.

Offline success does not authorize or certify a real initialization.
