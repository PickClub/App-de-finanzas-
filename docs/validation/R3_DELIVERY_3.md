# R3 delivery 3: local Android authentication

Status: R3 DELIVERY 3 COMPLETED for the authorized local synthetic Android
authentication flow — closure recorded 2026-11-05. Production deployment and
standalone release acceptance remain separate. The earlier pending statements
below describe the original execution and are superseded by the closure record. The authenticated adapter runs as a separate loopback-only Uvicorn
instance at 127.0.0.1:8013. It requires the exact authorized synthetic URI
for r3_security_synthetic on 127.0.0.1:27118, verifies its single-member
replica identity, and never imports the ordinary FastAPI entrypoint. It reuses
the Mongo-backed store and transaction fence from replica certification.

HTTP endpoints: POST /api/auth/login, POST /api/auth/refresh, POST
/api/auth/logout, GET /api/auth/session, and POST /api/auth/invite/accept.
Invitation issuance and synthetic account provisioning are operator-only
commands outside HTTP. The provision command takes one synthetic email and
password JSON document on stdin and sends no email. There is no public
registration or recovery delivery. The financial router excludes seed and
requires verified bearer credentials.

The Android client opts in only with EXPO_PUBLIC_R3_AUTH=1. Credentials and
tokens can be sent only from an Android development bundle to
http://127.0.0.1:8013, intended for ADB reverse over USB. Access tokens remain
in memory; rotated refresh tokens are written to SecureStore before the new
access token is published. Refresh is single-flight. Only safe GET requests
are replayed once; rejected writes remain manual retries. The private
navigator stays unmounted until session restoration succeeds. Logout hides
the navigator and clears React Query before server confirmation. It attempts
both SecureStore removal and server revocation, reporting unconfirmed removal
if either fails.

Authenticated Notes use server CRUD without loading or migrating local
legacy Notes. Payment journals are scoped by environment and user, and the
captured session generation rejects work from a previous identity. Existing
global language and theme settings are retained. The sign-in gate uses the
existing theme and Montserrat assets, with English and Spanish strings.

Current authorized Samsung configuration uses ADB reverse for 8013 and 8081.
Metro on 8081 runs with EXPO_PUBLIC_R3_AUTH=1 and
EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8013. Its manifest identifies
127.0.0.1:8081. This configuration supersedes the earlier proposal to use a
separate Metro on 8082. It connects only to the synthetic authenticated
backend; the ordinary financial backend remains separate.

Historical automated verification: 39 backend tests passed, including a real HTTP test of the
standalone instance and the isolated replica regression. The HTTP smoke
covered login, wrong credentials, credential redaction, account isolation,
a transfer, Notes separation, read access across financial modules, refresh
and logout. Nine focused frontend scripts and TypeScript passed. ADB listed
no device. Cold restart, device SecureStore, deep-link and Back behavior,
keyboard, appearance and full native financial journeys remain pending.
Production auth transport, deployment and real email are outside this run.

## New-account category onboarding correction

QA A and B initially had no categories. The authenticated client did not call
the existing initializer; categories were previously provisioned only through
manual Restore defaults. Session installation now reads the verified user's
catalog before mounting financial screens. It calls POST
/api/categories/init-defaults only for an empty catalog, verifies the returned
catalog through a second read, and retains session-generation guards throughout.
Access-token renewal for an already installed identity skips onboarding.
Existing nonempty catalogs, including custom categories, are left untouched.

Both QA catalogs now contain 53 independently owned static categories (31
expense choices, 10 income choices, and 12 groups). B was initialized through
the updated session flow. A's empty catalog was also initialized through the
same static service under an explicit synthetic transaction. Financial
collection hashes stayed unchanged. Category-only integration fixtures created
two additional synthetic profiles; existing profiles were not edited.

Focused verification passed: onboarding and session client tests, category-only
real-replica HTTP integration (empty/repeated/custom/A-B), transaction-form
regression, TypeScript, and both i18n checks. Physical Samsung verification
observed expense choices Food/Groceries/Restaurants and income choices
Salary/Freelance/Business in the existing transaction form. No transaction was
submitted during verification. Metro delivered the changes through Fast Refresh.

## Delivery closure — 2026-11-05

### Owner-confirmed Samsung S25 observations

The owner explicitly confirmed these physical-device results in this chat.
They were recorded without repeating the already accepted flows:

- Successful sign-in.
- User B retains Banco Prueba with a balance of $900.
- User A cannot see B's financial data.
- Categories are available and independent for A and B.
- Session persists after closing and reopening Expo Go.
- Logout prevents access to financial screens until authentication succeeds.

These are owner-reported native observations, distinct from automated API
and replica tests. They supplement the earlier automatic session, refresh,
revocation, cache-isolation and Notes tests and the observed native category
pickers. Device access-token expiry and forced SecureStore failures were
not repeated as physical fault-injection tests.

### Remaining navigation acceptance checked during closure

The Samsung was confirmed signed out before testing. Opening each of these
Expo project links displayed Email, Password and Sign in, with no private
screen: /accounts, /transactions/new, /debts/synthetic-link-check/pay,
/notes, /calendar and /settings. Returning with Back and reopening a private
link retained the authentication barrier.

A focused runtime check of AuthGate confirmed that loading and signed-out
states omit the private navigator. A focused layout check confirmed that
the sole Stack navigator is inside that gate. These checks establish the
common boundary for internal routes rather than claiming that every possible
URI and payload was exercised on the device.

An additional external cold-start probe was inconclusive for launch usability:
a direct exp:// project URL with a private path returned to the Android
launcher instead of displaying the project. No private screen was observed.
Opening the base project URL restored the login screen, and warm private
links still displayed login. This launch limitation is retained for artifact
and external-link acceptance; it is not classified as an authentication bypass.
The device subsequently disconnected from ADB during the final return-to-login
check, so its final foreground screen could not be confirmed. This does not
invalidate the six completed warm-link checks or the owner's accepted results.

### Disposition

R3 DELIVERY 3 COMPLETED for the local synthetic Android authentication scope.
There is no demonstrated blocker remaining for the confirmed sign-in,
session restoration, user separation, logout and protected internal
navigation criteria. This closes Delivery 3, not public production readiness
or exhaustive physical validation of every financial payload and lifecycle.

No financial submission, database write, source edit, service reconfiguration,
commit or push was performed during this closure. Existing automated suites
were not rerun. Only the missing navigation evidence and documentation were
completed. MongoDB development at 27018 was not accessed.

The next indispensable release block is production readiness: deploy and
validate the authenticated backend over HTTPS with production-scoped
configuration, credential lifecycle, abuse controls, secrets and recovery
operations; then connect the matching production Android configuration and
validate a signed release artifact. Existing signing, privacy and distribution
gates remain tracked in R7. No next block was started.
