# R7 production backend runbook

Status: preparation only. No deployment authorized or performed. Existing development
and synthetic databases must not be used for this procedure.

## Entrypoints and configuration

Development retains `backend.server` and its existing development settings. Synthetic
R3 retains `backend.r3_local_api` and its exact destination allowlist. Production uses
`backend.production_api:create_app` exclusively; it imports neither entrypoint, reads
no dotenv, creates no metadata/indexes, and has no legacy/default-user fallback.
Start through `bash scripts/run-production-backend.sh` only after deployment approval.
The script binds loopback 8000, disables Uvicorn proxy rewriting and access logs, and
never enables reload. Use a dedicated unprivileged supervisor account, restart policy,
read-only code image, mounted runtime secrets, restricted filesystem and resource limits.
Install the repository's pinned requirements in the future deployment image; no
packages were installed for this lot. Do not assume the development Python runtime
is the production runtime; validate the locked image before beta.

Required environment variables (no real values belong in this repository):

| Variable | Contract |
| --- | --- |
| `APP_ENV` | Exactly `production` |
| `PW_PUBLIC_ORIGIN` | Canonical HTTPS API DNS origin, no path or trailing slash |
| `PW_ALLOWED_ORIGINS` | Comma-separated explicit HTTPS browser origins, no wildcard; CORS does not replace bearer authorization |
| `PW_TRUSTED_PROXIES` | Explicit private socket-peer CIDRs; use `127.0.0.1/32` with the supplied launcher/proxy |
| `PW_MONGO_URI` | Authenticated `mongodb://` seed list (dedicated password ≥16 characters), database path; exactly `tls=true&replicaSet=...&authSource=...&authMechanism=SCRAM-SHA-256` |
| `PW_MONGO_DATABASE` | New dedicated production database; never development or synthetic |
| `PW_MONGO_HOSTS` | Exact comma-separated replica hosts including `:27017`, matching URI and hello topology |
| `PW_MONGO_REPLICA_SET` | Explicit production replica name |
| `PW_ENVIRONMENT_ID` | New canonical UUID4, identical to pre-provisioned financial-context metadata |
| `PW_RATE_SECRET` | Independent cryptographically random secret, at least 64 characters; shared across workers |
| `PW_SMTP_HOST` | Approved email provider's implicit TLS SMTP endpoint, port 465 |
| `PW_SMTP_USERNAME`, `PW_SMTP_PASSWORD` | Dedicated provider credentials (secret ≥16 characters), injected by secret manager |
| `PW_MAIL_FROM` | Verified sender email address |

Generate secrets outside shell history and inject through the supervisor/secret
manager. Never put MongoDB URIs in command arguments, screenshots, logs or tracked
environment files. Configuration errors identify fields, never values. Secret fields
are excluded from dataclass representations. There is deliberately no SRV mode,
custom/insecure TLS override or automatic database fallback in this first adapter.

## HTTPS and trusted proxy boundary

`deploy/pickwallet-nginx.conf.example` is a review template, not installed configuration.
Supply DNS/certificate paths and check it in the future deployment environment. Only
HTTPS reaches the API. A backend request requires the actual socket peer in the
allowlist, exact canonical Host, `X-Forwarded-Proto: https`, and one parseable client IP.
The proxy must overwrite forwarded values, never append client-provided headers.
Duplicate critical headers, multi-hop XFF, untrusted peers, cleartext claims and
`Forwarded` headers fail closed. **Never enable Uvicorn proxy-header rewriting**: the
application must see the socket peer. The launcher enforces this choice. Reject
unknown virtual hosts at the infrastructure edge. Do not expose port 8000 publicly.

Responses have HSTS, no-store, nosniff, frame denial, referrer suppression and a
restrictive CSP. Authentication request bodies are bounded to 4096 bytes. The proxy
bounds other bodies to 1 MiB. Configure TLS renewal and certificate-expiry alerts.
A live certificate handshake, external header-spoof check and private network ACL
check remain deployment acceptance tests, not offline-certified properties.

Reference: [Uvicorn deployment proxy guidance](https://www.uvicorn.org/deployment/).

## MongoDB provisioning, indexes and least privilege

Use a private persistent replica set (recommended three data-bearing members across
failure domains) with authentication, trusted TLS certificates and durable encrypted
volumes. Require private DNS routing and ACLs for every replica member, including
future DNS/topology changes. Startup resolves all seeds to private non-loopback,
non-link-local addresses and checks exact replica membership, primary availability,
logical sessions, transaction-capable wire version, financial-context identity,
effective privileges and required indexes. DNS validation is defense in depth; it
cannot replace network enforcement. Arbiters/passive or changing memberships require
a reviewed topology/configuration update, not an automatic fallback.

A separately authorized DBA must create collections, indexes and metadata before
startup. Print the **offline plan** with:

```bash
python3 -c 'from backend.production_services import index_plan; import json; print(json.dumps(index_plan(), indent=2))'
```

Apply that plan only to the newly approved production destination. Provision
`moneyflow_metadata` document `_id: financial-context`, `version: 1`, fresh matching
`environment_id`, and an ISO timestamp `created_at`. Never copy development identities
or default-user records. Unique public IDs and auth emails/access digests are checked.
MongoDB's built-in unique `_id` indexes protect challenge digests, refresh digests and
owner-derived movement receipt IDs. Never TTL-delete financial idempotency receipts or
refresh-reuse evidence without a separately reviewed retention design. Add workload
indexes beyond the minimum plan only after measuring queries.

Create a custom runtime role with resource `{db: APPROVED_DB, collection: ""}` and
only `find`, `insert`, `update`, `remove`, `listIndexes` (optionally `killCursors`).
Grant no cluster/admin/other-database privileges or index/schema/drop management.
The startup verifier rejects broader effective grants, including built-in readWrite's
extra DDL privileges. Use a separate short-lived administrative identity for initial
provisioning and a separate backup/restore identity. Pre-create collections so runtime
transactions never depend on implicit collection creation.

The sync auth and async financial clients reuse their respective pools. For an initial
small beta, retain driver pool defaults; use 5s selection/connect/wait-queue and 30s
socket timeouts, primary reads and majority writes. Budget **both** clients per worker
per replica member before choosing worker count. Monitor pool wait/failures, transaction
abort rate, request latency and DB connection totals; tune from measured demand.
Financial writes retain snapshot/majority transactions and the R3 session fence.
Driver errors fail closed. Only explicitly transient-aborted auth transactions retry
fresh snapshots; unknown commit outcomes do not replay the auth transaction body.
Financial clients must retry the original idempotency key after uncertain outcomes.

Reference: [PyMongo TLS certificate verification](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/security/tls/).

## Controlled invitations, recovery and email

No public registration, invitation issuance, recovery issuance, seed or administrator
HTTP endpoint exists. An OS-authorized operator uses one explicit command with the
normalized recipient email on stdin, not in shell history:

```bash
python3 -m backend.production_operator invite
python3 -m backend.production_operator recover
```

The CLI reads one stdin line; do not run either command until authorized to send real
mail and write the new production destination. Operator access is an OS permission
boundary: restrict the service account, secret access and these commands. HTTP routes
cannot acquire the in-memory operator capability.

SMTP uses verified TLS on 465 with no plaintext fallback or debug logs. Challenges
remain hashed in MongoDB, purpose-bound, single use, invitation 24h/recovery 15m.
Recovery increments credential version and revokes all sessions atomically through R3.
Delivery failure returns a sanitized error; the pending identity/challenge can remain,
but no account activates and no password changes until successful challenge redemption.
The operator can explicitly retry under throttling. Mail contains a one-time code
and the exact HTTPS POST redemption endpoint, not a dead browser link or a token in a
URL. Recipients redeem through an approved API client using
`POST /api/auth/invite/accept` (`invitation`, `password`) or
`POST /api/auth/recovery/confirm` (`token`, `password`). JSON request bodies must never
be captured in telemetry. The backend redemption contract is tested with simulated
mail and no email is sent by tests. No web account page or Android redemption UI is
provided by this backend-only lot. A user-facing account-code redemption client and
its end-to-end usability/security validation are release prerequisites before
inviting nontechnical real users. Android was intentionally not changed.

Access/refresh HTTP contracts retain R3's 10-minute access, 7-day idle/30-day absolute
family expiry, rotation/reuse revocation, logout and maximum 10 active families. No
session credential is sent in email or links. Login throttles conservatively count all
attempts: 5/account/15m and 30/IP/15m. Shared auth-IP cap is 120/min before body parsing;
refresh and challenge caps are 60/token/min and 5/token/15m. Operator email issuance
is 3/recipient/hour per purpose. Counters are HMAC-keyed atomic MongoDB increments
with deterministic window IDs and TTL cleanup; database failure denies authentication.
IP is taken only from the verified socket proxy's overwritten XFF. Limits are shared
across workers, not process dictionaries. Review limit usability with the private beta.

Application security logs contain fixed event names only, no raw emails, payloads,
passwords, tokens or exception strings. Validation errors never echo request input;
unhandled exceptions return sanitized 503s and are suppressed at the outer boundary
after response handling to prevent server traceback disclosure. Keep access/debug/APM
body/header capture disabled at every external layer, including SMTP and MongoDB.
Set restricted event-log access and a 30-day security retention policy in infrastructure.
No durable audit sink or log-retention service is provisioned by this lot.

## Backups and restore procedure (not executed)

Before beta, choose owner, encrypted backup destination, retention, RPO and RTO. A
proposed starting target is daily consistent backups plus provider point-in-time
recovery, 30-day retention and a monthly restore drill; these targets need explicit
owner approval and evidence. Back up database data, auth/financial metadata and
idempotency receipts consistently; keep encryption recovery material separately.
Do not mix snapshots of different times. Persistent volumes are not backups.

1. Use the chosen provider's replica-consistent snapshot/PITR mechanism with a separate
   restricted backup principal. Alternatively use approved MongoDB Database Tools
   `mongodump --oplog` for a supported **whole-replica** backup after reviewing its scope
   and privileges; do not claim a `--db` dump plus `--oplog` is consistent or supported.
   Supply credentials through a protected external tools config/secret mount, not argv.
2. Encrypt backups, verify checksums, restrict access, record backup ID/time/cluster
   identity and alert on missed jobs. Ensure offsite protection and retention deletion
   are actually configured in the provider; no scheduler was created here.
3. Restore to a **new empty isolated replica**, never overwrite a live database. Use
   provider restore or approved `mongorestore --oplogReplay` for the matching full dump.
   Confirm destination allowlist, TLS and credentials before an operator executes it.
4. Verify financial-context identity, counts, index definitions and ledger/balance
   invariants with synthetic acceptance tests. Measure elapsed recovery and data-loss
   window against approved RTO/RPO; archive sanitized evidence.
5. Keep the restored API offline and revoke restored sessions/challenges through an
   explicitly authorized recovery procedure before any traffic cutover. Restoring old
   auth state can resurrect revoked sessions or consumed challenges. Rotate operational
   credentials as needed. No automatic cutover or automatic write recovery is provided.
6. Obtain explicit deployment/cutover approval, then perform authenticated A/B smoke
   checks against the restored isolated candidate before allowing real financial work.

## Mandatory remaining acceptance before a real beta

- Approved infrastructure, runtime image, private ACLs, TLS certificate and DNS.
- New production replica, scoped role, metadata/index setup and readiness checks against it.
- Provider sandbox test plus approved sender/SPF/DKIM/DMARC and account-code redemption client.
- Live TLS/proxy spoof tests, shared throttling concurrency check and resource/load limits.
- Backup restore drill with measured approved RPO/RTO and safe auth revocation procedure.
- **Primary failover** test on a disposable production-equivalent replica.
- **Ambiguous commit result between MongoDB and driver** fault test on that replica,
  including same-key reconciliation and no duplicate effect. R3's ASGI dropped-response
  test is not this guarantee. Neither test is certified by offline doubles.
- Independent credential/secret rotation and operational alerts/retention verification.

No production release, connection, purchase, email delivery or beta approval follows
from completing the preparation lot.

## R7 lot 3 deployment profile update (2026-11-05)

The original private-DNS mode remains the default. An explicit `atlas_allowlisted`
network mode now prepares Atlas standard seed-list TLS access restricted to dedicated
public IPv4 /32 egress, using Atlas SCRAM `authSource=admin` with unchanged database-only
authorization. It is not PrivateLink and does not configure/prove Atlas access lists.
See R7_BETA_INFRASTRUCTURE.md and R7_BETA_OPERATIONS.md for provider costs, exact
configuration, live network verification and backup/fault-test gates. No deployment
was authorized by this update.
