# R7 lot 4B — privacy and browser account deletion

Branch `conflict_280926_1750`. The production ASGI factory serves these
same-origin resources through the existing trusted HTTPS proxy configuration.

| English | Spanish | Purpose |
| --- | --- | --- |
| `/privacy` | `/privacy/es` | HTML privacy policy draft |
| `/delete-account` | `/delete-account/es` | Browser deletion form |

The pages link to each other and switch language without third-party assets.
They have a responsive layout, associated input labels and a status region.
`POST /api/auth/account/delete-web` accepts JSON with email, current password
and explicit confirmation. It requires the exact public HTTPS Origin, uses
the same IP and normalized email attempt budgets as login, and verifies the
password with the existing Argon2id account check, including dummy verification
for unknown or inactive accounts. It then rechecks the verified identity and
uses the owner-scoped transactional cascade from lot 4A. The body cannot
supply an owner ID. The endpoint issues no session or tokens. No browser
cookie is needed. A request without the right Origin or confirmation cannot
delete anything. Invalid credentials, an unknown account and an already
deleted account receive the same 401 response for otherwise valid requests.

The site submits through first-party JavaScript with credentials omitted,
redirects rejected and caching disabled. It clears the password field at
submission, prevents parallel submits and treats only 204 as confirmed
deletion. No browser storage is used by the page. A server or network failure
shows an unconfirmed outcome. Re-entering valid credentials can retry a rolled
back transaction. A retry after commit cannot erase another account and does
not provide a deletion receipt. The static page CSP permits same-origin script,
style and connection while denying form navigation and framing. The API's
existing stricter CSP remains in place.

## Data inventory and Data Safety worksheet

Scope is the authenticated production candidate and the two new web pages.
Sources are the request models and owner filters in `backend/authenticated_api.py`,
`account_operations.py`, `catalog_operations.py` and the linked financial
modules, `auth_core.py`, `auth_mongodb.py`, `production_services.py`, and
the app paths noted below. These are candidate entries for Play Console review.

| Candidate Play type or review item | What the code shows | Purpose and review notes |
| --- | --- | --- |
| Personal info — email address and user IDs | Account email for invite, sign-in and recovery. Generated internal UUID ties session, profile and financial documents to an owner. The web form sends email and confirmation to the API. | Account management, app functionality and security. Email is required for authenticated account access. Verify classification of internal identifiers in the final form. |
| Personal info — name | Settings sends the editable profile name. Currency preference is stored on the profile. | App functionality. Name customization is user-entered. Confirm required/optional answers against the signed candidate. |
| Other financial info | User-entered account labels/types, initial and current balances, currencies, transaction amounts/dates/directions, debts, bills, recurring payments, budgets, savings goals and linked payments. Derived calendar and summaries use these records. | App functionality. Entry depends on feature use. Account models track credit-card balances and labels but lack dedicated card-number or bank-credential fields. Review purchase history classification for movement content. |
| Other user-generated content | Notes and free-text fields such as labels and descriptions. | App functionality. Optional entry may contain information the user chooses to disclose. |
| Photos or other profile content — confirm | The profile API accepts a `profile_photo` string. The current Settings editor sends only name or currency. No photo-picker/upload path was found in the reviewed authenticated UI. | Verify actual signed-client use and the field's intended representation before declaring photo collection or sharing. |
| Authentication and anti-abuse — confirm form mapping | Password and account codes reach the API. DB stores Argon2id password hashes, token/challenge digests, session metadata and expiry. Proxy observes client IP for rate limiting. Rate records store an HMAC key, counter and expiry. | Account management and fraud prevention/security. Map credentials, IP-derived signals and provider logs to the exact form choices after review. Digests do not make pseudonymous data automatically exempt. |
| Device-local storage | SecureStore holds the refresh credential. Owner-scoped payment journals, language and theme use local storage. The query cache is in memory. | Do not treat local storage alone as off-device collection. Related API calls still transmit session and financial information. Validate backup exclusions in the signed Android build. |
| SDK and diagnostic review | No advertising or analytics integration surfaced in the reviewed request paths and dependency/configuration files. Expo updates are disabled in the current app config. | This is source review. Verify the merged manifest, actual runtime traffic, built SDK behavior, crash reporting and provider logs before filing negative declarations. |

Financial records and accounts are stored beyond a single request. Do not mark
these ephemeral. Record each declared type's required/optional status and
purpose in Play Console. Google defines collection by off-device transmission,
including SDKs. Verify whether the actual providers act solely as service
providers before applying any sharing exception. [Google Play Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)

Configured service roles are the trusted HTTPS proxy/API, MongoDB storage and
SMTP for invitation/recovery. SMTP receives recipient address, sender and
message including the one-time code and expiry. No financial records are sent
by that adapter. Lightsail, Atlas, Resend and Cloudflare DNS are R7 candidates.
The actual operator, providers, regions, contractual roles, logs, subprocessors
and retention still require confirmation. Use the final deployment evidence to
answer sharing, transit encryption and deletion questions. Source configuration
requires HTTPS/TLS for the candidate paths. The deployed endpoints and signed
candidate still need verification.

## Retention and restore gate

- The confirmed transaction erases active owner rows, profile, identity, access
  and refresh records, and invitation/recovery records listed in 4A. Failed and
  unconfirmed submissions do not receive a success claim. The web path cannot
  clear a journal stored on another device.
- Current validity limits are ten minutes for access tokens, seven days idle
  and thirty days maximum for sessions, twenty-four hours for invitations and
  fifteen minutes for recovery codes. Expiry controls usability. Confirm any
  separate database maintenance schedule for expired authentication rows.
- Rate-limit records expire after twice the configured window, subject to
  MongoDB TTL processing. The shared login IP/email windows are fifteen
  minutes. Production template disables Nginx access logs and limits its error
  log level. Confirm runtime, proxy and provider log retention and what fields
  are actually retained. Review SMTP message retention and processor erasure.
- R7's proposed backup schedule is seven daily and four weekly retention
  points, with actual Atlas snapshot/PITR settings pending. A successful
  request concerns the active database. Set and disclose the measured maximum
  backup recovery window and verified processor timelines before publication.
- Require independently durable, access-controlled evidence of every committed
  deletion from Android and web before permitting a restore to serve users.
  Retain only the owner identifier and deletion ordering needed for
  reconciliation. Cover ambiguous outcomes through an authoritative commit
  record and keep evidence until relevant recovery points expire.
- Restore to isolation. Reconcile deletions after the recovery point, erase
  those owners' restored data and invalidate restored sessions and challenges.
  Verify erased identities cannot sign in, refresh or redeem a restored code
  while unrelated owners remain intact. Cutover requires that evidence. The
  independent deletion ledger and restore automation are pending. A backup
  that cannot be reconciled must stay isolated.

## Publication handoff

Confirm the developer/operator identity as listed in Play, privacy and support
contact, effective date, hosting and processors, locations, retention periods,
exceptions and the identity-verified recovery/support process for users who
cannot sign in. The checked-in pages mark missing information. The deletion
form works for users with current credentials. It does not expose a public
email lookup or a public recovery issuance endpoint.

After those details are approved, serve the pages on the trusted API HTTPS
origin using the existing proxy, verify links, headers and form submission
from a real browser, then use the stable public privacy and deletion URLs in
Play Console. The browser flow must remain usable without the app. Complete
Data Safety from the signed release and actual processor setup. Privacy policy
access inside the app, if missing in the release candidate, is a release task
outside this Android-free lot. [Google Play account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en)

## Verification and files

54 Python tests passed, including 10 integration tests on a new disposable
MongoDB replica, of which 4 exercise the web path. They cover authorization,
uniform negative responses, origin/confirmation, owner isolation, repeat
submission, rollback, token revocation, bilingual pages and CSP. The actual
form script also passed a synthetic DOM/fetch test for confirmation, credential
clearing, duplicate clicks and failure handling. Browser integration with
deployed TLS and Play Console submission remain unverified.

- `backend/auth_core.py` and `backend/production_api.py` contain the shared
  password check, browser deletion route and fixed page routes.
- `backend/privacy_web/` contains four HTML pages, shared CSS and form script.
- `.dockerignore` includes the exact static directory and asset types in the
  restricted image context.
- `backend/tests/test_account_deletion_isolated.py` adds web integration cases.
  `backend/tests/test_privacy_form.cjs` exercises the form.
- This delivery record contains the inventory, worksheet, pending information
  and restoration gate.
