# Administrative connector — offline preparation

Date: 2026-11-08. Target: Pickwallet-prod / pickwallet_prod.
No Atlas/VPS connection, real database access, initialization, dependency install,
image rebuild, deployment, credential persistence, commit or push was performed.
The proposed production UUID was displayed for approval only, not saved here or
in any configuration. Existing synthetic fixture UUIDs remain test-only.

## Scope and code

- `backend/production_admin_connector.py` is a separate context-managed adapter.
  Import has no DNS, client construction, CLI or dotenv side effects. The default
  call rejects before I/O. Explicit `connection_authorized=True` is an operator
  gate; it is not an IAM permission or a substitute for the owner's approval.
- The adapter reuses `MongoTarget.load`, `verify_private_network`, `mongo_options`
  and the existing `Initializer`. It preserves standard seed-list TLS/SCRAM,
  certificate validation, network policy and existing timeouts. SRV remains denied.
- A client is built lazily (`connect=False`) after network validation. Effective
  bootstrap permissions are inspected, then `Initializer.dry_run()` verifies the
  topology and schema without writing. The adapter yields that initializer/plan.
  It never calls `apply`, creates a database user, or changes database roles.
- Every exit closes the client and invalidates its plan. Another approved session
  needs a new dry-run. Errors are sanitized and no URI, environment map, password,
  driver exception or document contents are logged by the adapter.
- Runtime FastAPI, financial rules, development and Emergent configuration are
  unchanged. The adapter and initializer remain excluded from the runtime image.

## Separate temporary administrative identity

The connector intentionally rejects the application runtime role. For a future
approved bootstrap identity, effective MongoDB grants must be:

| Resource | Required actions |
| --- | --- |
| `{db: pickwallet_prod, collection: ""}` | `find`, `listCollections`, `listIndexes`, `createCollection`, `createIndex` |
| `{db: pickwallet_prod, collection: moneyflow_metadata}` | `insert` |

The metadata resource may additionally carry `find`/`listIndexes`. `killCursors`
is tolerated on these resources. All other actions/resources are refused,
including database-wide insert/update/remove, drop privileges, cluster/global
rights and access to QA or another collection. No inherited administrative role
is needed. Atlas uses uppercase custom-role action names for these same actions;
no role was created or modified during this preparation.

The future temporary identity needs cluster restriction and short expiration;
verify the actual Atlas grant expansion during a separately authorized read-only
inspection. Do not broaden `pickwallet_app_prod` or replace its runtime role.

## Metadata correction

The initializer now calls the existing financial-context `validate_metadata`
helper for preexisting control documents. That enforces version type/value,
canonical matching UUID and `created_at` as an ISO datetime string with timezone.
Missing/null/non-string/invalid dates, impossible calendar values, naive dates or
timestamps and invalid offsets are rejected without repair. Unknown fields and
extra metadata documents remain rejected. Valid UTC `Z`, explicit offsets and
fractional seconds are accepted. No change was made to the financial helper.

The inspected metadata also participates in the dry-run fingerprint, so changing
an otherwise valid timestamp after review invalidates that plan. New metadata
creation still uses the existing UTC `datetime.now(timezone.utc).isoformat()`.
No existing document is rewritten.

## Offline tests

A regression first reproduced nine rejected-date cases being incorrectly accepted
by the old initializer. After the correction, **40 tests pass, 0 fail**:
21 initializer tests (18 existing plus 3 new) and 19 connector tests.

Tests use only in-memory database doubles, mocked PyMongo construction and blocked
socket/DNS calls. The existing local Stage 2 image supplies already installed
Python 3.12 dependencies. It runs without networking or a writable root filesystem;
only the current administrative sources and tests are mounted read-only. There is
no registry pull, real MongoDB process, host DB/socket mount or production secret.
The cached Stage 2 image itself is neither rebuilt nor changed by these mounts.

From the repository root:

```bash
podman run --rm --pull never --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user 10001:10001 \
  -v "$PWD/backend/tests:/app/backend/tests:ro,Z" \
  -v "$PWD/backend/production_initializer.py:/app/backend/production_initializer.py:ro,Z" \
  -v "$PWD/backend/production_admin_connector.py:/app/backend/production_admin_connector.py:ro,Z" \
  localhost/pickwallet-stage2:382edb6 python -B -m unittest \
  backend.tests.test_production_initializer backend.tests.test_production_admin_connector -v
```

Tests cover default/truthy authorization refusal, target/SRV/secret validation,
DNS/client failures, actual reused TLS options, effective privilege restrictions,
read-only dry-run, cleanup and plan expiry, topology mismatch, existing-data
refusal, metadata dates, sanitized errors and the existing idempotent schema and
partial-failure simulations. A connection approval does not authorize `apply`.

## Remaining gates

- Owner approval of the proposed UUID; then separately authorize configuration.
- Review and authorize a temporary bootstrap identity/secret mechanism; no password
  should enter source, chat, files in the repository or persistent logs.
- Authorize a real read-only inspection separately. Offline doubles do not certify
  DNS/TLS, actual Atlas privileges, replica topology or MongoDB DDL behavior.
- Secure an exclusive maintenance window. DDL is nontransactional and preflight
  does not provide a distributed lock or prevent a concurrent external writer.
- Review the live dry-run, then obtain explicit separate authorization for its
  exact structures before any `apply`. No bootstrap or deployment is authorized
  by this document. The earlier backup/failover/ambiguous-commit gates remain.
