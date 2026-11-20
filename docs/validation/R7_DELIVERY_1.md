# R7 — Delivery 1: production backend preparation

Date: 2026-11-05. Branch: `conflict_280926_1750`.

## Verdict

**R7 LOT 1 COMPLETED for backend preparation; NOT authorized or certified for deployment.**
No public service, production database, email provider account, domain or build was
created. No existing MongoDB destination (27018 or 27118) was accessed. No running
service was altered. Existing local work was preserved; no Android/frontend,
financial logic, dependencies, commits or pushes were changed by this lot.

## Files belonging to this lot

- `backend/auth_mongodb.py`: shared R3 store, transient-abort retry classification and
  session fence extracted without introducing a second financial implementation.
- `backend/r3_local_store.py`: retains the exact synthetic allowlist and Synthetic
  profile default; reuses the shared adapter, preserving its existing imports.
- `backend/production_config.py`: explicit fail-closed production-only settings,
  secret validation/redacted representations, strict TLS MongoDB configuration,
  private DNS precheck, bounded client options and canonical HTTPS origins.
- `backend/production_services.py`: SMTP TLS delivery, shared HMAC-keyed atomic
  throttles, index plan and read-only topology/privilege/index/context readiness checks.
- `backend/production_api.py`: authenticated financial factory, auth route assembly,
  verified socket-peer proxy boundary, request bounds, CORS/security headers, sanitized
  failures/log events and lifecycle cleanup. No legacy server or seed import.
- `backend/production_operator.py`: controlled invite/recover CLI, recipient stdin,
  no public registration or issuance endpoint, no emails sent during tests.
- `backend/tests/test_production_backend.py`: focused offline production tests.
- `scripts/run-production-backend.sh`: explicit loopback backend launcher with no
  forwarded-header rewriting, access logs or reload; not executed.
- `deploy/pickwallet-nginx.conf.example`: uninstalled TLS proxy template.
- `docs/validation/R7_PRODUCTION_RUNBOOK.md`: configuration, deployment inputs,
  least privilege, persistence, backup/restore procedure and acceptance gates.
- This report and the scoped appended entry in `docs/validation/ISSUES.md`.

## Detect → record → continue → batch repair → verify

| Finding | Resolution/evidence | Remaining boundary |
| --- | --- | --- |
| R7-01: only a synthetic authenticated entrypoint existed | Separate production settings/factory/launcher; missing/insecure config tests reject before driver construction | Supply approved deployment secrets and infrastructure |
| R7-02: legacy unauthenticated entrypoint must never be exposed | Production composes R3 factory only; anonymous financial/seed routes reject, authorized seed/registration/issuance paths remain absent | Review actual deployed command and proxy routing |
| R7-03: arbitrary forwarded headers could establish fake TLS/client IP | Socket-peer allowlist, exact Host, proxy-overwritten single XFF and HTTPS required; spoof tests pass | External proxy/TLS and network ACL acceptance |
| R7-04: replica adapter was coupled to synthetic target | Shared store/fence preserve R3 transactions and owner checks; separate production connection validates private topology, privileges, metadata, indexes | Real production-equivalent adapter verification; no connection performed |
| R7-05: mail delivery only captured invitations in memory | Configurable verified SMTP TLS and operator invite/recovery; simulated delivery and single-use recovery/revocation tests | Sender/provider setup, user-facing code redemption client and sandbox end-to-end acceptance |
| R7-06: no production shared auth throttle | MongoDB atomic window counters, HMAC subjects, TTL cleanup, pre-parse IP and per-account/token limits; infrastructure failure rejects | Multi-worker concurrency/load verification on disposable replica |
| R7-07: uncertain transaction outcomes remain uncertified | Only labeled transient-aborted auth transactions retry; unknown outcomes fail closed; tests assert no body replay | Primary failover and MongoDB/driver ambiguous commit fault tests before beta |
| R7-08: production backups/restore had no operator contract | Separate identity, persistent encrypted volumes, consistent backups, isolated restore, RPO/RTO and restored-auth revocation procedure documented | Approve recovery targets, provision backups, execute measured restore drill |

The mail contract delivers a one-time code and its HTTPS POST endpoint. An early draft
link to a nonexistent account page was detected and removed before completion. No web
account page or Android account-redemption interface is asserted to exist. This is an
explicit release prerequisite outside this backend-only preparation scope.

## Verification

The final focused command, with all real-replica opt-ins removed:

```bash
env -u R3_SECURITY_TEST_TARGET -u R3_LOCAL_HTTP_TEST -u R3_CATEGORY_TEST_TARGET \
  PYTHONPATH="$(cat /tmp/moneyflow-auth-deps-path)" APP_ENV=test \
  python3 -B -m unittest \
  backend.tests.test_production_backend \
  backend.tests.test_auth_core \
  backend.tests.test_authenticated_api \
  backend.tests.test_r3_replica.DestinationTests -q
```

The temporary dependency path is the existing local R3 test harness, not a deployment
runtime requirement. No dependencies were installed. All storage and delivery used
offline doubles; the destination guard mocks client construction. No integration suite
was enabled against the existing replicas.

Final command result: **48 passed / 0 failed / 0 skipped** in 11.490 seconds: 19 production tests,
9 auth-core tests, 19 authenticated API tests and 1 destination allowlist test. The
final command output is the completion evidence; not the historical R3 real-replica
certification. Existing Python 3.14/FastAPI coroutine deprecation warnings do not fail
the tests; validate the chosen deployment runtime/image separately.

Additional checks: seven Python files format/compile checks, launcher shell syntax,
`git diff --check`, scoped new-file review, current branch and staged diff review.
No localization or Android code changed, so no device/localization suite was rerun.

Offline evidence covers configuration acceptance/rejection, shared MongoDB transaction
options/error classification, simulated TLS mail, one-use password reset with session
revocation, startup cleanup/failure redaction, spoofed proxy boundaries, auth-only route
exposure, throttles/fail-closed errors, CORS, body bounds, response headers and sensitive
validation/log/exception suppression. Existing R3 tests cover owner isolation,
unauthorized-write rejection and synthetic ledger/idempotency workflows. These results
do not certify actual distributed atomicity, TLS infrastructure or live delivery.

## Deployment inputs and gates

The owner must choose/provide the host/provider and deployment runtime, DNS/API origin,
TLS certificate management, explicit browser origins, trusted proxy peer, private
replica host inventory and set/database names, fresh environment UUID, least-privilege
MongoDB credentials, independent rate-limit secret, SMTP provider/sender credentials,
backup owner/destination/retention/RPO/RTO, monitoring and log-retention ownership.
Deliver secrets only through an approved secret manager, never in this chat or Git.

Before real beta: account-code client acceptance, production-equivalent R3 integration,
primary failover and ambiguous MongoDB commit tests, external HTTPS/proxy checks,
shared rate-limit concurrency/load checks and backup/restore drill. See the runbook for
exact contracts. No deployment is started and no next lot is initiated by this report.
