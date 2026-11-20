# R7 beta operations and live acceptance plan

Status: **NOT EXECUTED**. Requires separate infrastructure/fault-test authorization.
Use only the new isolated beta deployment and synthetic A/B accounts. Never target
MongoDB 27018/27118 or developer/production financial records. Do not confuse a
written procedure, mocked test or R3 HTTP-response-loss test with a live PASS.

## Ownership and monitoring

Appoint a primary operator and backup contact with MFA, recovery instructions and
provider billing visibility. Inventory image/base digest, dependency lock/SBOM,
region, static egress, DNS/certificates, Atlas project/cluster/member IDs, financial
context UUID and separately scoped credentials; no secrets in the evidence inventory.
Record the actual approved RPO/RTO and maintenance windows before accepting users.

Configure, then deliberately trigger/test these alerts on disposable infrastructure:

| Signal | Initial beta threshold/action |
| --- | --- |
| External HTTPS liveness | Every 5 minutes, anonymous GET `/api/accounts` must be 401 with expected certificate/security headers; alert after two failed probes. This does not prove MongoDB is up. |
| Authenticated readiness | Approved synthetic monitor identity GET session/owned resource, with tokens managed outside logs; alerts on inability to renew/read. Authentication counters/sessions may change, no financial writes needed. Never publish a bearer token or log body. |
| TLS expiry and renewal | Alert at 14 days remaining, critical at 7; exercise renewal/reload and expiry failure before beta. |
| API VM CPU/burst balance/memory/disk | Investigate sustained >70% CPU/memory or low burst credit; storage >60% warning, >75% critical. Set conservative admission/load limits rather than disabling Argon2 or increasing worker count blindly. |
| Atlas disk/connections/replication lag | Alert on >60% storage, sustained connection pressure or replication lag; monitor both sync auth and async financial pools per worker/node. No automatic tier upgrade without budget approval. |
| Backups/PITR | Alert for missing daily snapshot, provider backup failure or recovery-window lag exceeding proposed 15-minute RPO. Check latest recoverable timestamp, not just a green backup toggle. |
| Authentication abuse/availability | Review aggregated 401/429/503 rates without raw credentials, bodies, financial IDs or arbitrary exception text. Do not enable full request/query profiling to obtain a metric. |
| Resend | Monitor rejection, bounces, domain verification and approach to 100/day or 3,000/month. Operator queues invitations; no automatic paid upgrade. |
| Costs | Provider forecasts plus combined daily ledger; warnings $90/$105/$115 against the $120 total. Include domain renewal month and disposable resources. Billing alerts are not hard caps. |

Use provider-included metrics and an approved free/capped external HTTPS monitor;
no paid monitoring/log product is assumed or provisioned. Cloudflare is DNS-only in
this design, so it is not the API's request metrics source. Container health is a
loopback TCP liveness probe, not business readiness. Logs are size bounded; any
required 30-day security retention needs an approved protected sink/rotation policy
and cost estimate. Never claim a size-bounded local log guarantees 30-day retention.
Disable email tracking and request/response/body/header capture in every external
collector; email provider bodies contain short-lived account codes and require
restricted access, documented processor retention and disclosure.

## Live network/TLS gate

1. Independently verify DNS-only A record, reserved/attached static IPv4 and actual
   outbound source. Check firewall from outside: 443 reachable; 8000, SSH outside the
   operator /32, Docker daemon ports and all MongoDB ports on the VM unreachable.
   No alternate AAAA or publicly exposed backend binding may bypass Nginx.
2. Export Atlas project accessList from its authenticated control plane using a
   separate read-only operator, timestamp/source the export, then run the offline
   `prepare.py --check-atlas-access-list` comparison. Final entries must be exactly
   the application /32. Test connection from a deliberately non-allowlisted external
   client is denied **using a temporary synthetic credential**, not a copied real
   user password. Revoke the test credential afterward. This is not proved by merely
   setting `PW_MONGO_EGRESS_CIDRS` or by a DNS lookup.
3. Verify external HTTPS hostname/chain/expiry and TLS >=1.2 from a normal Android
   trust store and another network. HTTP/invalid-host redirects must not be followed
   by API clients. Unknown Host is rejected by rendered Nginx. Obtain the actual
   effective config (`nginx -t`) and listening sockets; redact secrets.
4. Anonymous GET `/api/accounts`, `/api/transactions`, `/api/financial-context` must
   reject with 401. Invalid bearer must not authorize. Unauthenticated seed/docs/
   registration/issuance paths remain unavailable. Do **not** POST to a potentially
   exposed seed route as a probe: if misconfigured it might write. Offline routing
   tests cover POST absence, and deployed route/image identity must match them.
5. Spoof `X-Forwarded-Proto`, `X-Forwarded-For`, `Forwarded` and Host from the external
   client. Nginx must overwrite/remove them and app limits must use the actual client
   peer, not supplied values. Compare safe observable outcomes/approved diagnostics
   rather than enabling credential-bearing access logs. Test rejection from an
   untrusted backend peer in an isolated replica of the network setup.
6. Database unavailable/TLS mismatch must deny auth and financial operations without
   alternate DB/HTTP fallback or writes. A TCP-health green result is not a PASS.

No external endpoint exists today. None of the above steps has a live result.

## Backup and isolated restore drill

Proposed targets: **RPO <=15 minutes, RTO <=4 hours**; owner approval pending. Atlas
Cloud Backup + continuous PITR, daily retained 7 days and weekly retained 4 weeks,
subject to actual feature/region quote. Confirm encryption, key ownership/recovery,
retention and usable recovery window. VM snapshots are for host recovery and do not
replace transaction-consistent database backups. Copying separate collections at
different times is not a consistent financial backup.

1. On a disposable beta-equivalent database, create synthetic A/B records and a small
   known ledger via authenticated APIs with unique idempotency keys. Record sanitized
   expected counts, balances, linked histories, owner scopes and receipt identifiers.
   Confirm a known recovery timestamp and record the provider backup/snapshot ID.
2. Use the Atlas backup restore UI/API with a separate temporary restore role to create
   a **new empty M10 cluster**, never overwrite the source. Budget duration (the plan
   allows ~$3 of starting-rate cluster hours plus usage allowance) and set an expiry
   reminder; no automatic deletion while evidence still needs review. Compare source
   and restore MongoDB versions/compatibility before choosing the target.
3. Keep the restored API private/offline. Restrict its network/users just as tightly.
   Verify metadata, indexes, collection counts, ledger totals, linked movements and
   same-key idempotency reconciliation at the selected recovery point. Record actual
   lag/data-loss interval and elapsed restore time; compare to approved RPO/RTO.
4. Restoring auth data can resurrect revoked sessions/consumed recovery codes and old
   passwords. Before any cutover, obtain explicit authorization to invalidate restored
   sessions/challenges and require safe credential recovery where the backup could
   reintroduce old credentials. Retain reuse evidence/receipts. Use a reviewed
   restore-specific admin procedure, not a broad untested migration or seed command.
   Demonstrate pre-restore tokens/codes cannot authorize after recovery.
5. Validate runtime role, external TLS and A/B with synthetic data on the restored
   candidate. Inspect the financial-context UUID and mobile pin: do not silently
   change it or route clients to a different environment. Any endpoint/UUID change
   needs a coordinated approved mobile configuration update.
6. Source remains authoritative until a separate cutover decision. Archive sanitized
   evidence; remove temporary credentials/ACLs and disposable resources only after
   explicit evidence/cleanup approval. No destructive cleanup is automated here.

A provider saying "backup enabled" is not a restore test. A VM snapshot with a stale
secret file needs credential rotation before reuse, not blind restoration as a live
host. Regional/provider account disaster recovery remains limited without an approved
independent export strategy and extra storage; it is not certified by same-region
snapshots. Review that risk before admitting real financial data.

## Primary failover rehearsal — actual Atlas replica

Use the newly authorized **disposable M10** and synthetic accounts, not the current
local replicas or active tester records. Establish baseline primary/node topology,
known balances and driver versions. Send controlled financial operations with stable
owner-specific idempotency keys and concurrent session revoke/refresh cases.

Invoke Atlas **Test Resilience → Primary Failover → Restart Primary** using the
separate operator role. Record old/new primary, election time, request outcomes and
recovery delay. Retry only with the original key and compatible payload. Each ledger
mutation must be exactly zero or one committed effect and reconcile with receipts;
rejected/aborted transfers must leave both accounts unchanged. Verify A/B separation,
revoked-session rejection and no fallback to another environment before and after
election. A transient 503 can be safe; successful recovery alone does not prove totals.

Source: [Atlas primary failover test (M10+)](https://www.mongodb.com/docs/atlas/tutorial/test-resilience/test-primary-failover/).
No primary was restarted or test cluster created by this lot.

## Ambiguous MongoDB commit result — separate mandatory fault test

R3's HTTP response loss **after confirmed MongoDB commit** does not establish this
property. A random TCP disconnect or primary election also does not prove that the
specific commit request was applied and its reply was lost between server and driver.

The authorized fault harness must:

1. Run the exact candidate driver/adapter image against a disposable authenticated,
   TLS-enabled replica and synthetic namespace. Use a separate controlled fault proxy
   or sanctioned provider mechanism. Atlas does not promise customer access to
   arbitrary server failpoints; do not request broad production admin privileges or
   add a TLS bypass to make this test possible.
2. Target the **commitTransaction wire exchange**. Forward the request, confirm the
   upstream success reply in the controlled proxy, then deliberately close/drop the
   downstream connection before the driver receives that reply. Keep other scenarios
   separate: command not delivered, abort before commit and eventual commit retry.
   A TLS-terminating fault proxy requires isolated test CA/hostname/trust setup and
   approval confined to the disposable test client; never install that CA on the
   real beta host or weaken `tlsAllowInvalidCertificates` in production settings.
3. Capture sanitized phase/driver error-label evidence, including whether the driver
   resolved uncertainty by retrying **commit only**. Never persist passwords, access/
   refresh/challenge tokens or financial payloads in packet/proxy logs. If the harness
   cannot distinguish a commit-reply loss from another disconnect, mark BLOCKED.
4. Assert the application never replays the entire financial body under a fresh key.
   Retry/reconcile using the original owner/key/payload after reconnect. There must
   be one receipt and one set of effects; other users reusing the key remain isolated.
   For unresolved unknown outcomes return safe unavailability/uncertainty, not an
   invented success or automatic financial reversal. Verify auth unknown-commit
   outcomes are not classified as transient-aborted body retries.
5. Publish image/driver/server versions, exact fault point, outcome labels, observer
   proof of upstream commit and independent before/after ledger checks. Run on a real
   disposable MongoDB replica first; if the proxy cannot be used with Atlas, record
   that the Atlas-specific fault path remains unverified rather than extending a
   self-hosted result into an Atlas certification.

No fault harness or test CA was installed, and no uncertain commit was injected here.
Harness implementation/proxy provisioning and its exact Atlas feasibility remain a
live-test gate requiring authorization and engineering, not a claimed finished test.

## Email acceptance

With verified sending DNS and approved synthetic recipients, use the operator CLI
`invite`/`recover` on the beta host, recipient email through stdin. Confirm receipt,
From/SPF/DKIM/DMARC, code purpose/expiry and one-use redemption in Android; wrong or
expired code must not open finance. Confirm recovery revokes existing sessions and a
new password works. Simulate provider outage/quota exhaustion using a test adapter or
isolated network rule: delivery errors stay sanitized and no account silently gains
a session. Disable provider tracking and restrict message/dashboard retention.

A mocked SMTP test checks application behavior, not deliverability or provider
account permissions. No real recipients or credentials were used in this lot.

## Recovery and rollback without data loss

- API outage: inspect only fixed/sanitized events, deployment image, CPU/memory,
  certificate and connectivity. Restart/rollback to the approved previous immutable
  app image after authorization, preserving the same database and metadata. Do not
  seed, reset, migrate or replay ambiguous financial operations during restart.
- Lost/replaced VM: attach the reserved IP to an approved patched replacement, verify
  actual egress and Atlas /32, recreate secrets from the authorized store, renew/check
  TLS, validate the candidate image and only then move traffic. Detached static IPs
  can be billed; the reserved address is an availability dependency.
- DB outage: deny operations while unavailable; use provider incident/failover
  procedures. Do not make a standalone MongoDB node or a local development DB a
  fallback. Restore only through the isolated procedure and explicit cutover approval.
- Suspected credential leak: restrict traffic, rotate the relevant scoped key,
  revoke auth sessions as appropriate and preserve non-sensitive evidence. A DB
  password rotation must be coordinated for sync and async clients, not logged.
- Budget overrun forecast: stop optional tests/new invitations, review usage and
  obtain an approved replan. Do not erase records, disable backups or stop a running
  financial transaction as an automatic cost-control action.

## Evidence register to complete after authorization

For each live test record: date/operator, approved target IDs, image/config digest,
synthetic dataset ID, preconditions, procedure, safe outcome/metrics, PASS/FAIL/BLOCKED
and limitations. Required entries: external HTTPS/header spoof/closed ports, actual
Atlas allowlist/denied external source, effective runtime role, transactional A/B,
measured restore/PITR, primary election, ambiguous driver commit, real email and
certificate renewal/monitor alert delivery. All are currently **NOT RUN**.
