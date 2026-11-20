# R3 security architecture and legacy transition proposal

Status: PROPOSED — FINAL OWNER APPROVAL AND IMPLEMENTATION AUTHORIZATION REQUIRED.

This document is design only. Approval of the boundary in principle is not approval to implement this proposal. No production source, dependency, configuration, database, session or Android installation was changed to prepare it. RPR-005 remains PENDING; MFV-001 remains OPEN. R4 is outside scope.

## 1. Candidate, evidence and limits

Repository: PickClub/App-de-finanzas-. Required branch: conflict_280926_1750. Reviewed HEAD: 382edb64cc965c6db5ee419f3ff8fb5bbdea63ac plus existing saved local modifications, including R2. The original 64-case baseline remains 22 PASS / 12 FAIL / 30 BLOCKED. No historical case is promoted by this design.

Sources: REPAIR_BACKLOG.md RPR-005; ISSUES.md MFV-001; TEST_MATRIX.md MF-S5-05, MF-S5-06 and MF-S8-06; PROGRESS.md R2 evidence; RELEASE_READINESS.md; docs/financial-context.md; current backend/server.py, backend/config.py, backend/reference_integrity.py, backend/shared_obligations.py, backend/financial_context.py; frontend/src/api.ts, app/_layout.tsx, app/(tabs)/notes.tsx, src/utils/storage/index.ts and index.web.ts; dependency manifests.

Verified source observations:

| Boundary | Current observation | Design consequence |
|---|---|---|
| Server identity | server.py uses DEFAULT_USER_ID = default-user in models, handlers and helpers | Replace fixed request identity with an explicit verified principal; never mutate a global per request |
| Authentication | No active login/session implementation found in the inspected application paths; financial routes have no authentication dependency | Existing JWT/bcrypt/passlib requirements are not an implemented authentication system |
| Ownership | Many queries filter default-user; account update also has id-only queries | Filtering a fixed identity does not isolate callers; every operation and helper needs scoped review |
| Context | Financial context returns single_user and destination headers compare expected environment/user | Keep destination integrity separate from authentication; a header cannot select a principal |
| User creation | GET /user calls ensure_user(), which can create the default profile | Authenticated GET must not provision legacy identity or cause implicit profile writes |
| Financial boundaries | Existing transaction wrappers, reference-integrity coordination, history/idempotency and shared-obligation scope are present | Inject identity through these existing paths without changing arithmetic or weakening guards |
| Native storage | expo-secure-store is declared; native secure helpers exist but return fallback/false on errors | Reuse native capability with checked results and explicit auth-storage errors |
| Web storage | index.web.ts secure helpers fall back to ordinary AsyncStorage | Never use this fallback for authentication secrets |
| Notes | Main Notes screen persists moneyflow.notes.v1 locally, without backend Notes ownership | UI gating alone cannot satisfy backend-enforced Notes ownership; explicit scope decision required |
| Client | Central API wrapper sends no session bearer credential; payment flows also carry destination context/journals | Audit all HTTP transports, cached data and pending writes, not only the central wrapper |

These observations corroborate MFV-001. They are not proof of a successful cross-user attack. No live database query, authentication attempt, financial write or device test was performed for this proposal. Installed artifact details previously recorded in validation documents are historical evidence, not freshly reverified APK identity.

R2 evidence records four focused corrections complete at source/mocked-test level and explicitly retains real MongoDB/Android gaps. Preserve those source changes and all financial guarantees; do not repeat the full validation program.

## 2. Recommended identity mechanism

First-party email/password authentication is appropriate for this single FastAPI/MongoDB service if the owner accepts responsibility for credential lifecycle, abuse prevention, email delivery and incident response. Reuse FastAPI dependency injection, MongoDB transactions, existing profile fields and native SecureStore. No reusable complete authentication implementation was found. Do not introduce an OAuth provider, JWT implementation or second session system merely because libraries are listed.

Create a separate auth_users collection. Each new authenticated person gets a server-generated UUID that is never default-user and is immutable. The corresponding new profile uses that UUID as its existing users.id. Credential identity is not writable through PUT /user; name/currency/profile settings retain their existing meaning. New profiles and credentials are created together in one transaction. Existing profiles are not searched by email and silently linked.

Proposed email policy: validate syntax; trim surrounding whitespace; lowercase the entire address for login uniqueness, document this explicit product policy, retain the entered address for display. Do not apply provider-specific dot/plus alias rules. A partial or separate unique index on normalized email must affect auth_users only, avoiding collisions with historical users records.

Proposed password policy: minimum 15 characters for this password-only flow, accept spaces/Unicode and at least 64 characters; maximum 128 Unicode code points and 1024 UTF-8 bytes to bound processing. No trimming, silent truncation, composition rules or periodic forced rotation. Normalize consistently only if explicitly documented; proposal is no password normalization. Allow password-manager paste/autofill. Do not persist the submitted password on device or server.

Use argon2-cffi Argon2id, encoded PHC hashes with library-generated random salts. Initial profile: memory_cost=65536 KiB, time_cost=3, parallelism=1; benchmark on deployment hardware under bounded concurrency before activation, never reduce below the cited OWASP minimum without new approval. Rehash on successful login if parameters are outdated. Bound password-hashing concurrency and move blocking work off the async event loop. Use a dummy hash for nonexistent users and generic login failures; this reduces obvious enumeration differences, not a promise of identical timing.

argon2-cffi is not declared in backend/requirements.txt. Adding and pinning the maintained package and lock/requirements changes requires explicit authorization; none is installed now. Existing bcrypt/passlib is not a reason to downgrade the proposed algorithm. No password pepper is proposed initially: deployment secret management would otherwise gain another mandatory rotation/recovery dependency.

Public self-registration is not automatically enabled. Recommended R3 starting mode: local operator creates synthetic or explicitly approved new users through a guarded process; these users still authenticate normally. Operator enrollment may not issue tokens without password verification or attach legacy data. Public registration requires verified-email delivery and abuse controls before activation. Password recovery/change design is in section 4; support is not allowed to reset passwords by editing MongoDB manually.

## 3. Session choice and lifecycle

| Option | Benefits | Costs for this application |
|---|---|---|
| Opaque access + rotating refresh tokens, server-managed | Immediate revocation, one server authority, no signing-key/claim-validation system | Indexed database reads; Mongo availability required |
| Signed short-lived access tokens + refresh records | Can verify access without a database lookup | Immediate revocation still needs state/version lookups; issuer/audience/key rotation/algorithm rules add complexity |

Recommendation: opaque access and refresh tokens only. The existing backend already depends on MongoDB, and immediate revocation matters more than stateless distribution. No JWT is issued or accepted by this design. Bearer authentication is a transport scheme, not a claim that this is an OAuth authorization server.

Generate independent 256-bit CSPRNG access/refresh secrets, URL-safe encoded and type-prefixed. Store SHA-256 digests only; fast hashing is appropriate for these high-entropy random tokens, not for passwords. Never put raw tokens in URLs, logs, metrics, crash reports, analytics or database documents.

Proposed limits, subject to approval:

- Access: 10 minutes, never sliding; validity also requires an active session family and enabled user.
- Refresh/session: 7-day inactivity limit and 30-day absolute limit from password login. Successful refresh extends inactivity only up to the absolute limit.
- One family per device login, maximum 10 active families per user; reject excess logins with a clear action to revoke existing sessions rather than silently evicting one.
- Logout revokes the current family immediately; logout-all and successful password changes/recovery revoke all families.
- Database/auth-state failure: fail closed with 503, never fall back to default-user or cached indefinite authorization. Expired/unknown/revoked credentials return 401, without revealing which check failed.

### Refresh rotation and replay

A MongoDB transaction verifies the current refresh digest, user status and family expiry, consumes the old generation, inserts exactly one next-generation token record, and replaces the family's active access digest/expiry. Old access is invalidated on rotation. Only one current refresh generation exists per family. Retain consumed digests until family absolute expiry so reuse can be detected; expiration is checked by application code, not TTL timing.

A second use of a consumed refresh token revokes the whole family, including the newly issued access/refresh credentials, and returns 401. Concurrent refresh attempts must not both succeed. Record the revocation transaction before returning an error; raising inside the transaction must not roll it back. If rotation's response is lost, the client must sign in again; it must not retry a consumed token or assume that the server rolled back. No grace window or encrypted response-replay cache is proposed. This intentionally favors a simple strict replay policy over uninterrupted recovery.

The client serializes refresh in one shared promise/lock; no background task or interceptor runs a second refresh. A stale in-flight access request after rotation may fail once and retry only a safe read with the new access token. A stolen valid access token can still be replayed until expiration/revocation; bearer tokens are not device-bound and rotation cannot prevent every theft scenario. TLS, short lifetime, safe storage and immediate family revocation mitigate that residual risk. Proof-of-possession/device attestation is not silently added to R3.

### Authorization and revocation race

Authentication happens before financial handlers. For financial mutations, validate the session and user inside the existing financial transaction and perform a conditional session authorization-fence update on that family. Revocation/rotation updates the same family document, forcing concurrent writes to serialize/retry with the existing transaction retry rules. A financial operation authorized before a concurrent logout may commit before logout; once revocation commits, a retried/new operation cannot pass. Never perform hashing or refresh as part of a financial transaction. The fence changes security metadata only; existing financial writes stay in their current atomic unit. Synthetic race tests must verify this contract before claiming immediate revocation for writes.

## 4. API and credential lifecycle contracts

Proposed endpoints (new contracts requiring approval):

| Route | Authorization / behavior |
|---|---|
| POST /api/auth/login | Email/password, bounded verification; returns access/refresh pair and safe current-user summary; Cache-Control: no-store |
| POST /api/auth/refresh | Refresh credential only; atomic rotation; no financial action |
| POST /api/auth/logout | Current authenticated family; idempotent revocation; client discards credentials |
| POST /api/auth/logout-all | Valid session plus recent password verification; revoke all families |
| GET /api/auth/sessions | Current user only; safe device labels/timestamps, never token hashes |
| DELETE /api/auth/sessions/{id} | Current user's family only; generic 404 for foreign identifiers |
| POST /api/auth/password/change | Current session + current password; store new hash and revoke all sessions atomically; login again |
| POST /api/auth/register | Disabled until public registration/email policy approved; never claims legacy records |
| POST /api/auth/password/reset/request and /confirm | Disabled until secure email delivery is configured; generic request response, random hashed single-use token (15 minutes), verification + password update + revoke-all in a transaction |

Verification links/tokens must never be returned in public API responses or logs. Use an approved HTTPS link/app association, no embedded session credential in a deep link. Registration verification requires its own single-use hashed purpose-bound token, maximum 24 hours. Emails are not changed through the profile endpoint; email-change support is deferred until separately approved verification rules exist. Lost-password users in the initial operator-enrolled test deployment must be told recovery is unavailable; do not pretend a usable public account lifecycle exists.

Auth abuse controls must be shared across workers, not only in memory: atomic bounded per-IP/per-account sliding/fixed counters with expiry, trusted-proxy configuration, per-process hash-work semaphore and an ingress request cap. Proposed starting limits: 5 failed login attempts per normalized-email digest per 15 minutes, 30 per source IP per 15 minutes, capped 15-minute retry delay; refresh 60/minute/family and 120/minute/IP; enrollment/reset 3/hour/email and 10/hour/IP. Tune using synthetic tests and actual deployment constraints. No permanent account lockout. Attackers can still cause temporary denial of service by exhausting limits; this is an explicit residual tradeoff. Do not trust arbitrary X-Forwarded-For headers. Audit events contain event type, safe internal user/session IDs, timestamp and outcome, never passwords, raw email bodies, tokens or financial payloads. Limit audit retention; proposal 30 days.

Errors: 401 missing/invalid credentials, WWW-Authenticate: Bearer on protected API failures; 404 resource missing or foreign; 403 valid identity but prohibited policy; 409 existing financial conflict preserved; 422 existing input validation preserved where compatible; 429 throttled with Retry-After; 503 unavailable auth/database. Validation must not perform writes before authorization. Registration collisions use a generic response if public enrollment is enabled; do not leak existing accounts through diagnostics.

Only minimal health/liveness and explicitly approved auth entry points are public. All /api financial/profile/report/calendar/context/export/default-category/reset endpoints must be protected, including currently overlooked secondary paths. Public root must expose no user, environment, database or diagnostic secrets. CORS is not authentication. Disable or protect production debug/OpenAPI exposure according to deployment approval.

## 5. MongoDB additions and deployment rules

No schema/index/resource below is created during this design phase.

| New collection | Proposed fields and indexes |
|---|---|
| auth_users | id UUID, email_normalized, email_display, password_hash PHC, status, email_verified_at, created_at, password_changed_at; unique id and email_normalized |
| auth_sessions | id/family UUID, user_id, current_access_digest, access_expires_at, generation, created_at, last_refresh_at, idle_expires_at, absolute_expires_at, revoked_at, safe device label, authorization_fence; unique active access digest with partial index, user_id/status lookup, TTL cleanup_at |
| auth_refresh_tokens | digest unique, family_id, user_id, generation, consumed_at, expires_at, cleanup_at; unique family_id/generation, family lookup, TTL cleanup_at |
| auth_challenges | purpose, digest, user_id, expires_at, consumed_at; unique digest, TTL cleanup_at; only if verification/recovery enabled |
| auth_rate_limits | bounded hashed bucket id, count/window/expiry; unique bucket id, TTL expiry |
| auth_audit | safe security metadata only; TTL retention timestamp |
| notes (if approved) | UUID id, user_id, existing Notes content/format metadata, timestamps/revision; unique id, user_id/update lookup |

Existing financial collections retain fields, amounts, IDs and historical user_id values. New users create existing profile records only through explicit enrollment, not startup or GET. Existing globally unique financial ID/index constraints are retained unless a focused security implementation review proves an additional tenant index is necessary. Additive owner lookup indexes must be reviewed per collection; no blanket index replacement or rebuild. Auth TTL cleanup never deletes financial/profile records. A consumed refresh record's cleanup_at must be at least the absolute family expiration. Runtime expiry checks remain mandatory because TTL cleanup is asynchronous.

Separate credentials/profiles allow legacy users documents to remain byte-for-byte unchanged. Do not create a credential account with reserved id default-user. Do not allow request bodies to override user_id/id, auth status or session metadata. Authentication database permissions remain least privilege; application credentials are not shipped to devices. New collection/index provisioning is an explicit deployment action, not an automatic data migration or startup default-user seeding.

## 6. Ownership implementation strategy

Use an immutable CurrentUser principal returned by a shared FastAPI dependency. Protect the financial router by default and explicitly inject this principal into handlers/helpers. The public auth router is separately defined. Do not use a mutable module-level current user, a process environment variable, or string-replacement of DEFAULT_USER_ID that accidentally changes background/admin semantics. Remove model default ownership for new writes and require server assignment. Keep legacy constants only in explicitly read-only migration tooling/fixtures where approved.

For every existing route record: method/path, handler, collection reads/writes/aggregations, helpers, related-resource checks, principal propagation, existing transaction wrapper and regression assertions. This route coverage manifest is an implementation acceptance artifact inside RPR-005, not a new audit program. Fail route coverage tests when a newly registered financial route lacks protection.

| Domain | Required scope and reference checks |
|---|---|
| Accounts | List/read/update/delete by id AND principal; balance recomputation, linked-record guards and account history use the same principal |
| Transactions/transfers | Source/destination accounts, category, debt, payments, recurring references owned by principal; transfer endpoints both owned; never accept a foreign movement in update/delete/history |
| Debts and debt payments | Debt, payment, charged account, generated transaction, cancellation and reconciliation scoped together; preserve original idempotency key/payload and all deletion restrictions |
| Bills/invoices | Bill/series, account, category, payment/receipt/next occurrence owned; do not conflate one paid recurrence with whole series |
| Recurring payments/templates | Parent, occurrence, payment record, linked bill and transaction ownership checked within existing transactions; scheduled jobs iterate explicit owners, never default-user |
| Budgets | Budget/category scope and expense aggregation constrained to principal; preserve existing calculation windows |
| Savings goals | Goal, contribution, account and movement scope; retain contribution/balance semantics |
| Categories | Parent/group and transaction references owned; defaults generated only by explicit authenticated action, never claimed from legacy by matching names |
| Notes | Backend-owned notes for new authenticated records if approved; every read/write scoped; no cross-user local cache reuse |
| Reports/calendar/summary | Initial match, lookups and joined documents constrained by principal; no global totals, counts or leaked foreign lookup values |
| Other records | Recurring templates, journals/idempotency receipts, shared obligations, derived history/reference records and exports scoped; user profile resolves principal only |

Filter updates/deletes themselves by owner, not just a preceding existence check. Foreign/nonexistent related resources return the same safe error and perform zero financial writes. Resolve parent ownership before child history/receipt access. Check required related resources in the same existing transaction as financial writes, retaining existing coordination locks/retry behavior. Scope every aggregation lookup as well as the initial collection match. Financial idempotency/coordination keys and receipts include owner and environment where applicable; a key from another user must not disclose a receipt or deduplicate another user's write. Preserve existing keys; no automatic rewrite of legacy journals.

Financial-context response must report the authenticated effective user. Proposed new explicit mode authenticated_user replaces the single_user literal for authenticated sessions; update shared-obligation Scope validation and client context parsers consistently. This is an intentional contract change requiring approval, not an unnoticed string change. Existing single_user metadata/documents stay untouched; new users cannot attach old shared obligations. The environment pin continues checking deployment destination and cannot authenticate users. If a guarded payload includes a different expected user, reject without rebinding. New startup jobs must never provision/claim legacy metadata or read another user's financial records for convenience.

## 7. Android and local-storage boundaries

Minimum new UI: sign-in form, session-expiry handling and logout/session controls; optional registration/reset forms only when enabled. These are additions requiring final authorization. Reuse current Montserrat, theme, buttons and English-first i18n with Spanish translations. Existing authenticated screen layouts, financial forms, navigation destinations and calculations remain unchanged.

Auth state machine: restoring -> authenticated, signed_out or temporarily_unavailable. On startup read the secure refresh record and renew; no protected requests, legacy ensure_user call, default seeding or financial journal replay before authenticated restoration succeeds. Network/503 errors must not be treated as bad credentials: preserve the secure refresh record and show retry, while keeping protected cached content hidden. A 401/revocation clears usable credentials and requires sign-in. Preserve unsaved drafts under their original identity; never submit them after another user logs in.

Password exists only in the input/request memory and is cleared on submission/unmount, never saved for remember-me. Access token is memory-only. Persist one versioned refresh/session record with Expo SecureStore under an environment/server identity namespace. Do not carry tokens to a different host/redirect; permit only the approved API origin and no cross-origin redirect forwarding. Verify secure write success before enabling persistent login; on rotation persist the new refresh credential before using the new access credential. Storage failure hides protected content, attempts family revocation if possible and requires sign-in. Never fall back to AsyncStorage. Test backup/restore and SecureStore invalidation: recovery requires sign-in, not a hidden device key.

On logout stop queries, hide data, cancel in-flight work, revoke the server family when online, erase secure credentials and clear in-memory query caches for that identity. If offline, local logout still erases credentials/hides data but must explicitly report server revocation is unconfirmed; stolen copies may remain valid until expiry/revocation. Logout-all requires network confirmation. Do not claim local deletion revokes the server. Namespace all persisted sensitive caches/drafts/notes by environment and user, hide foreign scopes, and reject late responses tagged with an old session/user generation. No global AsyncStorage.clear(), no automatic deletion or reassignment of old notes, drafts or payment journals. Pending financial submissions remain pinned to their original owner/environment and require normal reconciliation under that same identity.

Automatic retries: single-flight refresh; retry safe reads once. Do not replay POST/PUT/DELETE on generic network failures. A mutation rejected before its handler with 401 may be resubmitted only through an explicitly tested existing flow retaining its original identity/idempotency key; otherwise ask the user to retry after sign-in. Successful rotation/login must never trigger pending financial submissions automatically.

Notes decision: backend enforcement cannot be achieved by putting a user prefix on the existing local-only screen. Recommendation is authenticated Notes CRUD in the existing backend, preserving existing content block structure and UI, with owner-scoped local cache only. Existing moneyflow.notes.v1 stays intact and hidden from all new identities; explicit import requires a separately approved local-data claim. This adds a Notes API/storage path and is NOT authorized by the boundary alone. If declined, Notes must remain unavailable in authenticated multiuser mode and R3's full Notes acceptance stays pending; do not label local UI gating as backend authorization.

Web auth is not implemented through index.web.ts secure helpers. Recommended bounded R3 support is native Android/Expo only; fail closed for web authentication until a separate approved transport uses HttpOnly/Secure/SameSite cookies plus CSRF/origin protection. Do not implement two token systems now or put refresh tokens in browser localStorage. Existing unauthenticated financial web access cannot remain available on the secured backend.

## 8. Legacy preservation and safe transition

The secured server never maps a newly registered email, profile name, device or request parameter to default-user. Historical users, accounts, transactions, categories, debt/payment/bill/shared records and metadata remain unchanged and invisible to newly enrolled users. This is expected quarantine, not missing-data evidence. No routine enrollment/login/GET performs financial migration.

Safe development cutover: prepare and verify auth with synthetic users in the existing authorized isolated target; keep existing trusted development services untouched until a separately authorized cutover. After approval, deploy matching frontend/backend together, authenticate a new UUID user and create only explicitly approved synthetic records. New users initially see an empty owned dataset. No APP_ENV=development anonymous fallback, secret header, embedded APK password, automatic default-user login or LAN-only auth exemption is permitted. Existing local legacy data remains stored but is not accessible through the secured API until a separate claim design is approved and executed. If continued in-app legacy visibility is mandatory immediately, cutover is BLOCKED; do not solve it with a bypass.

Future claim/migration process — design only, NOT an approved R3 operation:

1. Owner authorizes exact source database/environment, candidate destination identity, record groups and whether access delegation or actual owner reassignment is intended. Email similarity is not evidence of ownership.
2. Operator verifies control of the local dataset independently and destination user performs recent password authentication. No public self-service claim-default-user endpoint.
3. Read-only inventory includes related resources, journal/shared-obligation keys, categories, notes and references; provide counts/checksums and conflict report without private details in logs.
4. Obtain a restorable protected backup, stop affected writes through an approved maintenance window, and record a one-time signed/operator-approved plan. No claim runs on startup.
5. Prefer a separately reviewed explicit legacy-access grant if preserving every original owner field is required; assess all helper/idempotency implications first. Any actual user_id reassignment requires separate authorization overriding preservation for the named records; this proposal authorizes neither method.
6. Execute only the separately approved implementation, verify counts, references, balances and journal recoverability, then test access and rollback. Large datasets may need bounded batches and maintenance protections rather than pretending one unlimited transaction is safe.

Until that future decision, there is no automatic migration and no access grant. Never rekey old local journals or notes to the new UUID as part of login. Existing financial amounts/history must remain exact, including after rejected claims.

## 9. Existing APK and transport impact

The currently documented standalone APK has no implemented login/bearer session flow. It will receive 401 from a secured backend and cannot remain fully compatible. Do not keep anonymous endpoints for it. Source changes do not update a compiled release APK. A separately authorized new APK will be required for standalone Android use after the frontend implementation; no build/install is authorized now. Expo Go may run the updated client if its installed SDK/runtime supports the project's existing dependencies; verify that at implementation time. SecureStore is already declared, but declaration alone is not runtime/device proof.

Existing records/routes and financial response shapes remain where compatible; auth requirements, new auth endpoints and authenticated context mode are deliberate breaking changes requiring coordinated deployment. Report incompatible clients clearly, without leaking data. No credentials/server secrets belong in EXPO_PUBLIC variables or APK assets.

Credentials/bearer tokens require HTTPS, including Wi-Fi login traffic. Current historical development destination uses plain LAN HTTP; it is not adequate for password/token testing over Wi-Fi. Minimum Android testing recommendation: approved USB ADB reverse to a loopback-bound test backend for synthetic credentials only, if the APK/Expo configuration supports it, or a separately approved local HTTPS endpoint with valid device trust. ADB USB transport is a local testing restriction, not a production TLS substitute. Never install a trust-all certificate handler, disable TLS verification, change global trust/firewall settings or use a public tunnel without separate approval. Current installed APK's embedded LAN destination does not automatically use ADB reverse. HTTPS/trust/origin deployment decisions remain explicit gates.

## 10. Threats, mitigations and residual risks

| Threat | Required mitigation | Remaining limitation |
|---|---|---|
| Arbitrary identity / IDOR | Verified server session; owner scope on all reads/writes/joins/references | Route/helper completeness must be demonstrated with tests |
| Password guessing / enumeration | Argon2id, generic errors, shared throttles, hash concurrency bounds | First-party password-only auth lacks MFA/phishing resistance |
| Token theft / replay | TLS, SecureStore, memory access tokens, digest-only DB, refresh rotation/reuse revocation | Valid bearer access can be replayed until rejected/expired |
| Refresh race/lost response | Atomic rotation, one client refresh, no automatic replay, reauthenticate on ambiguity | May require login after benign transport loss |
| Revocation race | Session fence in financial transaction, scoped retries | Operations committed before revocation are not undone |
| Mongo/cache failure | Fail closed, explicit expiry, no anonymous fallback | Authentication depends on DB availability |
| Cross-user cache/journal | Identity namespaces, late-response guards, no automatic replay/import | Rooted/compromised devices can expose local data; not solved by R3 |
| Historical claim abuse | Legacy remains unclaimed, operator approval and evidence required | Existing dataset unavailable through secured API until separate decision |
| Browser token exposure / CSRF | No web persistent tokens; web auth deferred | Web login unavailable until separate design |
| Log/backup disclosure | Redaction, bounded security audit, secure backup/restore, least privilege | DB compromise still exposes historical financial data; encryption-at-rest policy belongs to deployment review |
| Recovery/enrollment abuse | Verified email before public activation, single-use hashes, revoke-all, no manual DB resets | Public release blocked until operational email/recovery controls pass |

No production readiness claim follows from selecting this design. Existing R7 signing/privacy/deployment requirements and R6 evidence blockers remain independent.

## 11. Bounded implementation sequence after final approval

These are work packages inside R3/RPR-005, not new repair phases or added validation stages. None begins under this design-only authorization.

1. Freeze approved decisions and route coverage inventory; approve the exact dependency addition and test destination. Exit: no unresolved identity/legacy/Notes/transport decision affecting implementation.
2. Add credential/session schemas, Argon2id, throttling and auth endpoints with offline tests. Exit: login/rotation/revocation/expiry/race/storage-error contracts pass; no financial route activated prematurely.
3. Inject principal throughout protected routes, helpers, aggregates and existing financial transactions, including the session fence and context mode. Exit: complete protected route coverage and zero-write rejection assertions; existing financial regressions unchanged except explicit identity fixtures/contracts.
4. Add minimal native auth UI/client state/storage, cache/journal ownership and approved Notes backend integration. Exit: matching client/server behavior, no secrets in ordinary storage, no automatic legacy import/replay.
5. Execute focused isolated MongoDB and Android evidence, preserving original case history. Exit: all acceptance gates below pass or remain explicitly pending; no public cutover if mandatory isolation/auth/financial gates fail.
6. Separately authorize coordinated local cutover and, if desired, APK build. Exit: known secure transport, backup/rollback plan, matching client, old clients fail closed. No public deployment or legacy claim is implicit.

Likely production touchpoints: backend/server.py, config.py, new small auth modules and dependency manifest, financial_context.py, shared_obligations.py and only necessary ownership-aware history/reference helpers; frontend/src/api.ts, root auth boundary, native auth state/storage, new minimal auth routes, i18n resources and identity-scoped cache/journal integration. Notes API and its existing storage adapter are conditional on approval. Exact file list is determined by the bounded route manifest; do not refactor unrelated financial modules or touch experiments.

## 12. Tests and acceptance gates

Reuse existing test infrastructure; no new laboratory. Before any integration write, verify exact APP_ENV=test database name, restricted credentials, replica set, database-write confinement, remote-network blocking and production/development denial. If unavailable, stop integration tests and label evidence BLOCKED; offline tests cannot certify real MongoDB.

| Acceptance | Required evidence |
|---|---|
| Missing, malformed, wrong-type, expired, disabled-user and revoked credentials | Route-level ASGI tests; protected endpoints reject with no financial/profile writes; only approved public routes work anonymously |
| Password handling | Argon2id PHC/unique salts, valid/invalid verification, input limits, dummy path and throttle tests; no raw password storage/logging |
| Access expiry / logout | Controlled-clock tests and real isolated session reads; access rejected after expiry/revocation and logout-all; disabled-user behavior consistent |
| Refresh rotation/replay | Sequential + concurrent real MongoDB tests; exactly one generation succeeds, consumed reuse revokes family; lost response forces sign-in; revocation is not rolled back by exception handling |
| Cross-user CRUD | Synthetic A/B same collection fixtures; enumerate every protected route, foreign IDs/filters/child history/cursors/exports/counts/aggregations denied; no response leaks |
| Related resources | Foreign source/destination accounts, categories/parents, debt/payment, bill/recurring links and goal/contributions rejected; exact collection snapshots unchanged |
| Financial integrity | Existing focused expense/income/transfer/account, debt/payment cancellation, bill/recurring and contribution regressions under authenticated users; exact balances/history preserved |
| Atomicity / auth races | Real isolated fault injection and concurrent logout/refresh versus writes; no partial writes/duplicate effects; prior financial retry/idempotency rules retained |
| Tenant idempotency | Identical A/B keys cannot return foreign receipts; repeated authorized request changes ledger once; cross-user reconciliation rejected |
| Legacy | Pre/post hash/count fixtures for default-user and unowned records identical; new users cannot list/read/claim them; GET and startup do not create legacy profiles |
| Android | Actual supported Samsung/Expo client login, restoration, refresh, expiry, logout/offline logout, secure-store failure, user switching, background/foreground and pending-draft/journal behavior over approved transport |
| Notes | New authenticated Notes A/B CRUD + mixed formatting/persistence; local legacy key unchanged and not displayed/imported; backend checks, not only UI guards |
| Secrets / logs | Capture synthetic sentinel credentials and verify absence from server/client logs, responses, AsyncStorage, crash payloads and APK source/config; hash fields excluded from public profile |
| Localization/static | TypeScript, check-i18n.cjs, test-i18n.cjs and focused regressions for touched flows; no theme/layout changes outside approved auth additions |

Map new focused assertions to existing MF-S5-05/06 and MF-S8-06 plus affected original financial cases, without expanding the 64-case program. Do not convert previously blocked cases to PASS based on partial mocked evidence. RPR-018/RPR-021 integration prerequisites remain dependencies; do not silently launch an infrastructure repair.

Completion requires all approved ownership/session behavior implemented, relevant offline and isolated integration gates passing, and explicit Android evidence or an honest pending disposition. No R3 COMPLETE if mandatory backend isolation, legacy preservation or financial atomicity fails. Public release remains blocked by missing account lifecycle/transport and other existing release requirements even if scoped R3 code is complete.

## 13. Rollback and incident strategy

Before cutover authorize a recoverable backup and capture source/config candidate, schema/index plan and read-only financial counts/checksums. Do not take or restore database backups during this design task. Deployment must coordinate client/server; no partial anonymous compatibility period.

Safe rollback disables protected API availability or retains the last secure backend, revokes newly issued sessions, and reports maintenance. Never restore the unauthenticated backend on a publicly or LAN-accessible financial endpoint as an auth rollback. A previous unsecured binary may be used only in an explicitly isolated, separately approved offline recovery process, not as a hidden runtime feature. New auth collections/indexes can remain inert; do not drop collections or restore whole financial databases to undo auth. Financial operations already committed remain intact and are reconciled normally; rollback is not financial reversal.

If session state is suspect, revoke affected/all families and require login. Do not recover raw refresh tokens or alter legacy ownership. Failed credential storage/rotation cannot be repaired by writing a default token. Data-corruption suspicion stops affected writes and requires separate recovery authorization, not automatic migration.

## 14. Final authorization checklist

Owner decisions required before implementation:

1. Approve first-party Argon2id and opaque access/refresh sessions only; approve proposed lifetimes, strict refresh-reuse policy and logout race contract.
2. Approve adding/pinning argon2-cffi; no package installation follows from this design document alone.
3. Approve operator-enrolled R3 test users first, or explicitly include public registration + verified email + recovery delivery. Select email delivery/HTTPS deployment before public activation; approve password/email/rate/retention policies.
4. Approve minimal sign-in/logout/session UI and secure native integration. Native-only auth is recommended initially; web auth remains disabled pending its own approved transport.
5. Approve backend Notes CRUD for new identities with existing UI/content structure; otherwise accept an explicit Notes blocker and no claim of full backend ownership.
6. Approve quarantining all existing default-user data and local legacy Notes/journals unchanged. A new user sees only new owned data. Any legacy visibility/claim remains separately designed and authorized; no automatic access grant.
7. Approve authenticated_user context contract and coordinated backend/client cutover, acknowledging the existing APK is incompatible. Authorize any new APK build separately.
8. Select approved synthetic test target and Android transport: restricted existing isolated MongoDB; USB loopback testing or approved local HTTPS. No plain Wi-Fi credentials, network exposure, system trust changes or new laboratory.
9. Approve the bounded work packages and acceptance/rollback gates. Confirm unresolved mandatory gates stop implementation/cutover rather than enabling a bypass.

Approval of this document must explicitly distinguish design acceptance from authorization to edit production code, install the named dependency, provision auth collections/indexes, restart services, execute isolated tests or build an APK. No such operation has occurred now. Stop here for owner review; do not start R3 implementation or R4.

## 15. External design references

Consulted for this proposal; these support recommendations, not claims of implemented compliance:

- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id and parameter baseline. The proposed 64 MiB/3 configuration is a project proposal requiring measurement.
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): unpredictable session identifiers, expiry/revocation and safe transport/storage.
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html): refresh-token rotation/replay principles used as design guidance; this first-party API does not claim OAuth conformance.
- [Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/): native secret storage and platform/backup caveats; verify compatibility with the project's pinned SDK during implementation.
