# R7 lot 2 — Android preparation for Google Play

Date: 2026-11-05. Required/current branch: `conflict_280926_1750`.

## Verdict and scope

**R7 LOT 2 COMPLETED for source/configuration preparation. Closed-beta upload is NO-GO
until the release gates below have evidence.** No AAB/APK, prebuild, deployment,
publication, signing key, EAS project or Play Console object was created. No dependency
was installed and no dependency version was changed. No database was accessed. No running service was changed. No financial
rule, financial record, navigation route identifier, commit or push was changed.
Pre-existing staged/unstaged/untracked work was inspected and preserved.

ADB returned an empty device list. No Samsung acceptance or native keystore/backup
behavior is claimed for these changes. Prior R3 Samsung observations are historical
and do not substitute for a signed release-device test.

## Implemented changes

| Files | Result |
| --- | --- |
| `frontend/app.config.js`, `frontend/eas.json` | Dynamic PickWallet display name; existing package `com.emergent.moneyflowpreview.p1r033`, slug `frontend`, scheme `frontend`, version `1.0.0`, icons and splash retained. Development/debug, preview/test and production/store profiles. Production AAB, remote upload credentials and monotonically increasing remote version code; no submission configuration or auto-submit. Release requires an approved EAS project ID. |
| `.easignore` (repository root), `frontend/plugins/with-release-security.js` | Managed EAS builds deliberately exclude local native folders, dotenv, credentials and keystores; regenerate native configuration from reviewed Expo config/plugins. Disable native cleartext and backups; block storage/media/microphone/camera/overlay permissions. Existing native sources remain on disk. No prebuild ran. |
| `frontend/src/release-policy.cjs`, `frontend/src/runtime-config.ts` | Shared build/runtime validation. Non-development requires authenticated canonical HTTPS DNS origin and UUID4 environment ID. Release rejects development/missing/insecure configuration. No localhost, legacy backend, relative URL, redirect or alternate-origin fallback. Environment-separated refresh keys. Public environment variables contain configuration only, never secrets. |
| `frontend/src/auth-session.ts`, `frontend/src/api.ts` | Production authentication no longer requires `__DEV__` or the synthetic loopback origin. Every financial request validates target before networking. The release gate remains mandatory even if the auth flag is missing/off. Session installation pins the backend environment ID, preserves UUID/token validation, serialized SecureStore rotation, generation guards, query clearing, refresh single-flight and no automatic financial mutation replay. |
| `frontend/src/components/auth-gate.tsx`, `frontend/src/account-links.ts`, `frontend/app/account/[action].tsx` | Invitation/recovery code forms reuse existing auth styling; confirmation and 15–128-code-point password validation; exact R7 backend POST contracts. Clear sensitive form state on completion/form change and require explicit login afterward. External links select only a public form; credentials/codes in links are ignored. The private navigator remains inside AuthGate. After authentication, consume the public action route by replacing it with home. |
| `frontend/src/i18n/locales/en.json`, `es.json` | Centralized English/Spanish account labels; PickWallet auth brand. No device language selection, currency/financial content or stored category names changed. |
| `frontend/android/app/src/main/AndroidManifest.xml`, `res/values/strings.xml`, `build.gradle` | Local native main manifest disables cleartext/backups, removes unnecessary storage/overlay requests, display name PickWallet. Release no longer silently uses the debug key. Existing debug variants retain their development cleartext/overlay declarations. Local release signing remains deliberately unconfigured. |
| `frontend/package.json`, `frontend/package-lock.json` | Declared npm 10.9.7 to match the existing npm lock workflow. Repaired stale lock metadata offline from installed packages: added only the three existing localization packages and three missing transitive entries; no previously locked package version changed or entry was removed. |
| `frontend/scripts/test-android-release.cjs`, `test-account-forms.cjs`, `test-auth-session.cjs` | Offline release validation matrix, real account form/gate execution in English/Spanish, and extended local/production session tests. Existing auth script loader recognizes the shared policy module. |

## Build configuration contract

Run future Expo/EAS commands from `frontend/`. Supply these public build settings
through the selected EAS environment, not a tracked dotenv file:

- `PW_EAS_PROJECT_ID`: owner-approved existing/new EAS project UUID. No project is linked
  automatically by this lot. Review account ownership and slug before authorizing linking.
- `EXPO_PUBLIC_APP_ENV`: `development`, `test` (preview) or `production`.
- `EXPO_PUBLIC_R3_AUTH=1`: required outside legacy development; release still gates
  authentication if this is accidentally absent or disabled.
- `EXPO_PUBLIC_BACKEND_URL`: exact approved HTTPS API origin, without trailing slash,
  path, query, credentials or alternate port. There is **no endpoint default** in the
  preview/production profiles. A missing endpoint fails validation rather than using
  the current synthetic or legacy server.
- `EXPO_PUBLIC_API_ENVIRONMENT_ID`: the backend's approved financial-context UUID4;
  returned sessions must match it. Keep test and production environments separate.

All `EXPO_PUBLIC_*` values are readable in the app bundle. Never put SMTP, MongoDB,
service-account, upload-key or private credentials there. They belong in their
respective secret stores. EAS profile settings override local development dotenv
values; the root `.easignore` also excludes dotenv from the uploaded archive. Validate the
actual resolved configuration and embedded bundle again before authorizing a build.

Development EAS profile uses `:app:assembleDebug`, not a falsely labeled release APK.
Current Expo Go workflow remains supported unchanged at the explicitly authorized
Android synthetic HTTP origin `127.0.0.1:8013`. Preview uses a separate authenticated
HTTPS test deployment. A Google Play closed-test artifact uses the production/store
profile against an approved isolated HTTPS beta deployment; it must never point to
R3's local replicas or require ADB reverse/Metro. Do not change profiles after building
and assume the already embedded endpoint changed; rebuild after approved changes.

EAS reads the ignore file from the Git repository root, above `frontend/`. An initial
frontend-only draft was replaced with a root allowlist; tests verify backend/secrets/
native/keystore exclusion and required source/config/asset inclusion. The real
EAS archive still requires inspection with the chosen CLI version before upload.

Managed EAS builds regenerate Android from Expo configuration because local native
folders contain development signing/setup. They do not upload `android/` or `ios/`.
Future native customizations must first become reviewed config plugins. No automatic
project linking, credential generation, EAS build, submit or OTA update was executed.
OTA updates are explicitly disabled. The original local debug keystore was preserved
and excluded from EAS, not repurposed as an upload key.

Before a first upload, the owner must confirm the existing package identifier is the
intended permanent Play identity. This lot preserves it rather than inventing a new
identity. Enable Play App Signing and use a distinct controlled upload key with secure
recovery/ownership procedures. EAS remote credentials require subsequent explicit
setup approval. No keystore password is kept in source. Version code `1` is the initial
local baseline; remote auto-increment must be initialized from the actual Play record
and checked before each upload. No existing Play record was assumed or queried.

The original manifest declared Yarn 1 but no Yarn lockfile existed, and the npm
lock omitted already-installed `expo-localization`, `i18next`, `react-i18next` and
three transitive packages. An offline `npm install --package-lock-only --ignore-scripts`
was run in a temporary copy with the existing node_modules tree; it installed nothing.
The candidate had zero changed existing versions and zero removals. Original libc
platform metadata dropped by npm 10 was restored; all previously locked package
records remain unchanged. Only the reviewed additive lockfile was copied back, and package-manager metadata was aligned to npm 10.9.7.
Release tests require manifest/lock parity and entries for every declared dependency.
The historical Yarn-only `resolutions` field is preserved, not translated into npm
overrides; npm consumes the reviewed lockfile. No dependency policy migration or
vulnerability certification is claimed. A clean builder install and actual EAS archive still require validation after build
authorization; the installed local tree is not proof of a cloud build.

## Account flows and external links

Closed-beta operator issues invitations/recovery using R7 lot 1's controlled CLI and
approved SMTP provider. The user enters the emailed `invite.<code>` or `recover.<code>`
in the matching form and chooses/confirms a password. Android sends only to:

- `POST /api/auth/invite/accept`: `{ invitation, password }`.
- `POST /api/auth/recovery/confirm`: `{ token, password }`.

There is no public registration, email-existence lookup or automatic recovery issuance.
The recovery screen accurately tells users to contact the closed-beta operator.
Expired/used/wrong-purpose codes fail without signing in. The server remains the
single-use/expiry authority; no offline test certifies actual provider delivery or
MongoDB concurrency. Success returns to login; no challenge becomes a session token.
No password, account code or token is put into storage, telemetry, URLs or navigation
params. Refresh credentials alone go to SecureStore; access credentials stay in memory.

`frontend://account/invite` and `frontend://account/recover` (also triple-slash variants)
select forms when signed out. Query/fragment credential links and unrelated schemes
are not interpreted as auth instructions. A signed-in session is not changed by an
external account link. Any custom scheme can be claimed by another app; these links
carry no credential and are not evidence of sender identity. No verified HTTPS App
Links/domain association is claimed; a domain and signing certificate would be needed
for that optional follow-up. Manual email-code entry works without App Links.

The sole private Stack remains under AuthGate for loading, logout and signed-out
states. The new public-action route redirects to home only after the gate permits
private navigation. Owner authorization is still enforced on the backend regardless
of any navigation path. Future device acceptance must test cold/warm links to account,
accounts, movement, settings and notes paths while signed out, followed by logout,
back-button, cold restart, expired/revoked refresh and account switch.

SecureStore writes retain platform-protected refresh storage with unlocked/device-only
accessibility intent where supported. Production/test refresh keys differ from each
other and from the historical synthetic key. This is not a claim that ordinary query
caches/journals in AsyncStorage are encrypted, or that device transfer behavior has
been tested. Backup is disabled in main/config; SecureStore's plugin exclusions remain.
Verify the **merged signed manifest**, native storage and OEM backup/device-transfer
behavior on the actual artifact. Logout hides private state immediately and attempts
both revocation and durable removal; failure retains the existing explicit warning.

## Verification evidence

Focused source tests, each exiting zero:

1. `node frontend/scripts/test-android-release.cjs`: canonical HTTPS rejection matrix,
   environment-key separation, account-link allowlist, EAS package/scheme/AAB settings,
   missing project-ID rejection and local native signing/permission guards.
2. `node frontend/scripts/test-auth-session.cjs`: existing synthetic lifecycle plus
   production origin/no-fallback, redemption payloads/purpose/password validation,
   environment pinning, session clearing and no auto-login after redemption.
3. `node frontend/scripts/test-account-forms.cjs`: real form/gate module with isolated
   hooks in English/Spanish; password confirmation blocks calls, invite/recovery
   handlers submit correct purpose, sensitive state clears, account links select forms,
   credential-bearing links are ignored and loading/signed-out/logout hide private UI.
4. `node frontend/scripts/test-category-onboarding.cjs`: retained empty-only setup,
   custom preservation and A/B catalog separation.
5. `node frontend/scripts/check-i18n.cjs`: 1256 matching keys, interpolation parity;
   dynamic keys/computed labels remain subject to explicit tests and device acceptance.
6. `node frontend/scripts/test-i18n.cjs`: default explicit locale, persistence/switching,
   pluralization/formatting and existing UI regressions.
7. `node frontend/scripts/test-profile-settings.cjs`: retained settings behavior.
8. `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json`.

Expo production `config --type introspect --json`, with fixture HTTPS origin/project
and environment IDs, evaluated successfully from `frontend/`. Assertions confirmed
cleartext=false, allowBackup=false and effective requested permissions INTERNET and
VIBRATE, with explicit blocked permissions. Output is in the local temporary artifact
`/tmp/pickwallet-r7-android-config.json`. This evaluates config mods; it is **not** an
assembled/merged dependency manifest, a signed build or a device run. An initial
introspection invocation from repository root failed because package.json is in
frontend; correcting the working directory resolved it without a code workaround.

No full audit, database integration suite, R6, financial rule suite or backend suite
was repeated. Final diff/branch/staged/new-file reviews and `git diff --check` passed.
Final focused result: seven test scripts, TypeScript and Expo config introspection
passed; zero final failing checks. No Android/device PASS is recorded: ADB detected no device.

## Technical acceptance still required before upload

Installed React Native's version catalog currently declares compile/target API 36;
Expo SDK remains 57.0.19, with no upgrade. Google currently requires API 36+ for new
phone submissions. Inspect the final manifest to confirm this rather than treating
source settings as a Play certification. Check 64-bit ABIs, bundled native libraries'
16 KB page alignment and runtime behavior on a 16 KB device/emulator. No AAB was
produced, so final size, signing certificate, manifest merging, SDK audit, ABI/page-size
compatibility and Play pre-launch report remain unverified.

Sources checked on 2026-11-05:
[Google target API requirements](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en),
[Android 16 KB compatibility](https://developer.android.com/guide/practices/page-sizes),
[Expo EAS profiles](https://docs.expo.dev/build/eas-json/),
[Expo archive ignore rules](https://docs.expo.dev/build-reference/easignore/),
[Expo signing credentials](https://docs.expo.dev/app-signing/app-credentials/),
[Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/).
Use the installed SDK57 implementation for behavior; latest online docs also describe
newer Expo SDKs and are not an instruction to upgrade.

## Privacy, deletion and Google Play declarations — pending

These are release blockers, not forms completed or legal assurances:

- Owner-approved privacy policy, publicly accessible HTTPS URL and discoverable in-app
  access; developer/legal entity and contact, purposes, collected data, processors,
  regions, retention, security and rights/deletion process. No policy URL was invented.
- **Account deletion is not implemented.** Provide an in-app request path and a working
  external web request URL as applicable to Play account-creation rules. Specify
  identity verification, session revocation, linked financial data and notes,
  idempotency receipts, required retention exceptions and backup expiry. Deleting an
  individual financial account or logging out is not deleting the user account.
  Do not promise immediate erasure from retained backups. No deletion API or database
  write was introduced in this lot.
- Complete Data Safety for the closed track based on the actual deployment and all
  bundled SDKs: email/name/identity, financial records and free-text notes/descriptions,
  optional profile content, auth/network information and provider processing require
  review. HTTPS configuration alone does not prove deployed transit encryption or
  justify declaring that no data is collected/shared. Do not classify service providers,
  passwords or ephemeral processing without evaluating Google's exact definitions.
- Complete Financial features declaration accurately: bookkeeping/debt tracking does
  not by itself mean the app issues loans or moves real bank money. Do not claim bank
  linking, lending, payment processing or financial advice absent those services.
- Play developer verification, app content/access instructions and valid reviewer
  accounts, content rating, target audience, ads declaration, countries, support
  contact and store listing assets/text must be supplied by the owner. Do not give
  reviewers a local-only backend or publicize production user credentials.

Sources:
[Google account deletion](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en),
[Google Data Safety including closed testing](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en),
[Financial features declaration](https://support.google.com/googleplay/android-developer/answer/13849271?hl=en),
[Testing requirements for qualifying personal accounts](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en).
For qualifying personal accounts, 12 opted-in testers for 14 continuous days precede
the application for **production access**; that is not evidence that the first closed
track has already run or an unconditional prerequisite to start the closed test.

## Ordered path to the first closed beta

1. Owner confirms permanent package, EAS ownership/project and Play developer account;
   supplies support identity, distribution countries and intended tester group.
2. Authorize and provision an isolated HTTPS beta backend/email/replica deployment.
   Complete R7 lot 1 gates: private networking/TLS, indexes/scoped role, backups and
   measured restore, primary failover and ambiguous-driver-commit tests. This lot
   does not authorize deployment or touch either existing local MongoDB.
3. Finish privacy/deletion implementation and policy URLs; complete Data Safety,
   financial features, reviewer access and store setup.
4. Configure approved public EAS endpoint/environment ID and upload credentials;
   explicitly authorize a store-profile candidate AAB build. Inspect merged permissions,
   target/ABI/16 KB support, certificate/version and embedded endpoint/no-fallback.
5. Perform signed-candidate native acceptance on Samsung and a 16 KB environment,
   including new code flows, SecureStore/logout/restart, links, A/B and read-only
   financial smoke checks with synthetic data. Review Play pre-launch results.
6. Obtain explicit authorization to upload/release to the closed track; collect tester
   feedback. No upload/build/publication or next lot starts automatically here.

## Android identity migration

The managed Android configuration uses the PickWallet display name, the
`com.pickclub.pickwallet` package, and the `pickwallet` scheme. The account
form links are `pickwallet://account/invite` and `pickwallet://account/recover`,
including their triple-slash variants. The historical `frontend://` links
recorded above are no longer accepted by the account form parser. Links
select public forms and carry no account codes or session credentials.

Expo Go continues to open the project through Metro for testing account forms.
Opening the custom scheme from Android requires an installed PickWallet build.
The existing native Android tree remains a local reference outside the managed
EAS upload. EAS project linkage and the production HTTPS origin are pending.
