# Validation issue register

**CURRENT REPAIR R2 — four code defects resolved by focused offline evidence;17 previously confirmed OPEN becomes13 OPEN(P0 0/P1 2/P2 11/P3 0),eight resolved histories and three provisional entries. Original64-case baseline22/12/30 is unchanged;full integration/native acceptance remains pending. See latest R2 resolution below.**

**CURRENT FINAL CYCLE — S8-20261019-182837-CDT: Stage 8 CLOSED — 2 PASS / 3 FAIL / 3 BLOCKED / 0 NOT TESTED. All 64 cases classified: 22 PASS / 12 FAIL / 30 BLOCKED / 0 NOT TESTED. Public Google Play / Apple App Store release: NOT READY. iOS: NOT VERIFIED. Earlier entries below are historical; Stages 1–7 are preserved. This closes diagnosis, not the unresolved cases or bugs.**

Baseline: `382edb64cc965c6db5ee419f3ff8fb5bbdea63ac`; planning date: 2026-10-19. Stage 1 diagnostics completed under run `S1-20261019-030816-CDT`; no behavioral or financial test suite was executed in Stage 1. Subsequent Stage 2 dispatch attempts all stopped at imports before financial assertions. This register distinguishes inspected source/document facts, historical reported results and unverified effects. Evidence IDs beginning OBS refer to the source references below, not executed test evidence. Runtime findings must attach an EV-MF-* record before being accepted or closed.

No P0 corruption, data loss, unauthorized exploitation or destructive failure has been demonstrated by this planning task. Absence of a demonstrated P0 is not evidence of financial correctness or security.

| Issue ID | Severity | Finding / evidence confidence | Affected cases | Impact | Evidence reference | Status | Proposed next action / owner | Release blocker |
|---|---|---|---|---|---|---|---|---|
| MFV-001 | P1 | Confirmed design boundary: effective default-user/single_user context is not authentication. No new unauthorized-access probe executed | MF-S5-05, MF-S5-06, MF-S5-07, MF-S8-06 | A remote/untrusted multiuser deployment cannot rely on these identity headers to isolate private data | OBS-01 | OPEN — scope-specific blocker | Validation executor documents actual scope; product owner accepts trusted-LAN limits or separately authorizes security work; no authentication implementation in this program | YES for public/remote multiuser; does not by itself prohibit informed trusted personal LAN use |
| MFV-002 | P1 | Confirmed hazardous runner defaults: legacy requests suite uses a remote default URL and includes user updates, CRUD and /seed | MF-S1-03, MF-S1-04, MF-S8-03 | Broad test discovery could mutate an unapproved remote or personal backend; no such suite was run here | OBS-02 | OPEN — runner quarantined | Executor excludes this suite and verifies an explicit safe allowlist; owner separately approves exact isolated integration namespace | Blocks this runner and unverified integration batches; independent offline/static work can proceed |
| MFV-003 | P2 | Reproduced ESLint failure: 151 errors / 86 warnings, exit 1; TypeScript passes. Targeted parent comparison: settings 0 to 7 errors; sheets 9 to 11 errors and 0 to 1 warning. These are static diagnostics, not 151 demonstrated runtime defects | MF-S1-08, MF-S8-02 | Static quality gate is not known clean; a diagnostic alone does not prove runtime or financial failure | OBS-03 | OPEN — reproduced in Stage 1; no repair authorized | Owner authorizes a separate bounded lint triage; preserve the captured baseline and do not auto-fix | Not automatic P0/P1; blocks a clean-lint claim and requires explicit P2 disposition for readiness |
| MFV-004 | P2 | Confirmed coverage limit: Reports uses listTransactions and the legacy API defaults to 500 records; wrong displayed totals at larger volumes are NOT TESTED | MF-S4-06, MF-S7-04, MF-S8-04 | Possible incomplete financial reports beyond the fetched history; current personal data is not inspected for this issue | OBS-04 | OPEN — bounded correctness risk | Executor runs exactly the frozen 501/2001 synthetic report cases; escalate only if discrepancy demonstrated | A demonstrated significant total mismatch becomes P1 and blocks affected financial readiness; do not predeclare it passed |
| MFV-005 | P3 | Confirmed code patterns with unverified device impact: ScrollView maps, Deudas JS-state entry animation, scan-based pagination and conditional full shared-read snapshot | MF-S4-07, MF-S4-08, MF-S5-08, MF-S7-04, MF-S7-05, MF-S7-06 | May grow slowly with volume or cause frame drops; neither measured Android FPS nor a leak is established | OBS-05 | BACKLOG — fixed tests already allocated | Executor measures only frozen datasets/cycles in Stage 7; no speculative optimization or extra load suite | Not by speculation alone; measured ANR/core failure may create P1; required untested device cases still block certification |
| MFV-006 | P2 | Confirmed production artifact configuration gap: release build currently uses debug signing configuration; source rechecked in Stage 1; no release artifact built/inspected here | MF-S1-07, MF-S7-02, MF-S8-06 | Current configuration is for testing, not a production signing/release approval | OBS-06 | OPEN — production distribution blocker | Owner chooses intended artifact/deployment; build/install and any signing change need separate approval; never publish private keys | YES for production distribution; not a blocker for an explicitly approved internal test APK |
| MFV-007 | P3 | Evidence gap, not a demonstrated device defect: no accepted Samsung startup/frame/memory/restart/standalone evidence exists for this program | MF-S7-01 through MF-S7-08, MF-S8-05 | Cannot certify Android readiness from mocks, local API timings or host RAM | OBS-07 | OPEN — device evidence pending | Executor inventories authorized device/build capability in Stage 1; later Stage 7 requires separate execution authorization | YES to Android readiness until mandatory evidence exists; severity does not imply an observed crash |
| MFV-008 | P2 | Historical reported summary frontend visual-contract comparison failure; financial assertions and native behavior not retested in planning | MF-S1-03, MF-S4-06, MF-S8-02 | A legacy source comparator may obstruct regression reporting; do not suppress a real financial failure as a test defect | OBS-08 | OPEN — reproduction pending | Executor checks existing script and its baseline during allowlisting, then reproduces once under authorized case; no repeated audit or automatic test edit | Blocks an all-tests-pass claim; financial impact determines whether release is blocked |

## Observation references

1. OBS-01: `backend/server.py` declares `DEFAULT_USER_ID = "default-user"`; `docs/financial-context.md` explicitly states context headers are not authentication; `docs/local-samsung.md` describes trusted local use without authentication. Source/document confirmation only; no security exploit was attempted.
2. OBS-02: `backend/tests/test_moneyflow_api.py` derives BASE_URL from EXPO_PUBLIC_BACKEND_URL or a remote preview default, and its TestBasic/TestSeed cases write user data and POST /seed. `backend/pytest.ini` sets pytest-xdist options. Inspection is sufficient to quarantine execution; no test request was sent.
3. OBS-03: prior user-visible performance audit and commit review in this conversation; current source references `frontend/app/settings.tsx`, `frontend/src/components/sheets.tsx`, `frontend/src/components/date-range-sheet.tsx` and frontend hook mocks. Prior logs are not EV-MF evidence; current counts reproduced in EV-MF-S1-08; historical whole-change delta was not independently rerun in full.
4. OBS-04: `frontend/app/(tabs)/reports.tsx` uses `api.listTransactions`; `frontend/src/api.ts` requests `/transactions` without a larger limit; `backend/server.py:list_transactions(limit=500)` bounds that legacy response. The separately paginated All Transactions route is not the same reader.
5. OBS-05: `frontend/app/debts/index.tsx` subscribes entry progress to setEntryT with a JS-driven timing; Notes uses mapped cards and whole-array storage; `backend/transaction_history.py:read_page` iterates candidates; `backend/shared_obligations.py:_load_shared_snapshot` loads eleven collections when the shared-read branch is active. Earlier host/synthetic measurements are contextual only and are not Android evidence. No production optimization authorized.
6. OBS-06: `frontend/android/app/build.gradle`, release signingConfig references signingConfigs.debug; minification/shrink defaults are off. Config inspection establishes the distribution gap, not build success/failure.
7. OBS-07: Stage 1 evidence is embedded in PROGRESS.md; earlier session reports said ADB had no connected device. Stage 1 adb devices returned no connected device; inventory automatically started the ADB daemon only. No build, install or device test ran. Existing mock tests cannot close the gap.
8. OBS-08: earlier performance/commit conversation recorded a failure in `frontend/scripts/test-summary-totals.cjs` around visual normalization. The script reads HEAD and applies source transformations. This observation is historical and must not be promoted to a fresh test result.

## Finding protocol and backlog rule

Every new finding gets a stable MFV ID, affected test, evidence ID, severity justified by actual impact, status, owner and deployment-specific blocker decision before deeper work. Record expected and actual behavior. Preserve the exact failing synthetic fixture. P0 or serious blocking P1 allows only the smallest diagnostic cause investigation inside the remaining timebox. No repair is authorized by a finding. P2/P3 ideas do not expand the frozen matrix; they remain backlog until a separate scope is approved.

No known issue is closed or repaired by this planning task. Historic C3/APPLY lab artifacts are preserved and excluded from execution; operational APPLY/VERIFY/REVERT, provisioning, migrations and personal-data repair remain prohibited. Unverified cross-user mutation, financial truncation consequences, leaks and frame drops are hypotheses/coverage gaps until their frozen cases produce evidence.

## Stage 1 disposition and reproduction details

Evidence: [Stage 1 run](PROGRESS.md#ev-mf-s1-01), [runner boundaries](PROGRESS.md#ev-mf-s1-03), [static checks](PROGRESS.md#ev-mf-s1-08).

Confirmed findings counted for this run: **P0 0, P1 2, P2 2, P3 0**. MFV-001, MFV-002, MFV-003 and MFV-006 are confirmed source/static findings. MFV-004/005/007/008 remain provisional risks, historical observations or evidence gaps; they are not additional demonstrated defects. No financial corruption or exploit was demonstrated. None was repaired.

| ID / module | Concrete reproduction or evidence | Expected | Actual | Stage 1 case | Suggested correction, description only | Status |
|---|---|---|---|---|---|---|
| MFV-001 / backend identity | Inspect DEFAULT_USER_ID in server.py, request dependencies and financial-context documentation; no exploit request | Future public multiuser access requires authenticated, enforced ownership | Default-user/context identity is not authentication; trusted local use is a distinct scope | MF-S1-02, MF-S1-06 | Separately design and verify authentication and per-user authorization before public deployment | OPEN P1, public multiuser blocker |
| MFV-002 / legacy API test runner | Inspect test_moneyflow_api.py remote fallback, requests calls and seed/user/CRUD writes; do not run | Tests must have an approved isolated destination and no implicit remote writes | Existing runner can target remote/default backend and perform mutations | MF-S1-03, MF-S1-04 | Separately authorize destination guards/explicit safe invocation; maintain quarantine meanwhile | OPEN P1, affected runner blocked |
| MFV-003 / frontend static gate | Run read-only ESLint API lintFiles(['.']) without fix/cache; see exact totals/rules in evidence | Clean static gate or explicit reviewed disposition | Exit 1, 151 errors and 86 warnings; TypeScript exit 0 | MF-S1-08 | Separate targeted triage of functional significance; no automatic cleanup | OPEN P2 |
| MFV-006 / Android release configuration | Inspect release signingConfig in frontend/android/app/build.gradle | Production artifact uses approved production signing, not bundled debug configuration | release references signingConfigs.debug; no artifact built | MF-S1-07 | Separate authorized production signing setup; never version private signing keys | OPEN P2, production distribution blocker |

MFV-006 severity changed from planning P1 to P2: the demonstrated fact is a production configuration gap, not an observed core runtime/financial failure. This does not waive the production distribution gate. No test APK or release is approved.

MFV-004: expected complete report totals, actual runtime discrepancy unknown; only the source reader limit is established. MFV-005: expected responsive native behavior, actual device performance unknown. MFV-007: expected physical-device evidence, actual no ADB device attached. MFV-008: expected a passing relevant regression, actual only a historical failure report; it was not rerun because behavioral suites are outside Stage 1. Their original affected cases, impacts and proposed bounded next actions above remain unchanged.

## Stage 2 finding — S2-20261019-033541-CDT

| ID | Module | Severity | Concrete evidence / reproduction | Expected | Actual | Related cases | User impact | Suggested correction, not applied | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| MFV-009 | Stage 2 sandbox dependency/import environment | P2 | Existing control.sandbox(meta, 'run', case), once for each MF-S2-01 through MF-S2-08. All exit 1 after the isolation PASS line. Seven end with ModuleNotFoundError: httpx; MF-S2-03 ends with ModuleNotFoundError: typing_extensions through FastAPI/Pydantic. Evidence is recorded under the eight EV-MF-S2 anchors in PROGRESS.md. | Prepared executor imports required dependencies and reaches the allowlisted financial assertions | Every dispatch stops before test methods or real-case ledger assertions. Import unavailability is demonstrated; host installation state and deeper causes were not investigated. | MF-S2-01 through MF-S2-08 | Stage 2 acceptance cannot proceed. This is a laboratory runtime defect, not demonstrated incorrect money movement or a production dependency failure. | Separately authorize a minimal laboratory-only import/dependency visibility repair and import smoke check without weakening isolation; then authorize rerun of the same eight cases. No automatic installation. | RESOLVED — S2R2 dependency-path repair verified; original failure evidence retained |

Count one shared runtime-preparation defect, not eight financial bugs or two independent package defects. Preparation's LISTO claim verified isolation/fixtures but overstated executable readiness: required financial imports had not run. The execution evidence supersedes that readiness claim.

New Stage 2 confirmed issues: **P0 0 / P1 0 / P2 1 / P3 0**. Cumulative confirmed findings: **P0 0 / P1 2 / P2 3 / P3 0**, namely MFV-001/002/003/006/009. Historical/provisional MFV-004/005/007/008 are excluded from confirmed counts. No financial inconsistency, loss, duplicate charge or cross-module financial failure was established because financial assertions never ran; this also means those invariants have not passed.

No suberror investigation, installation, executor repair, production edit or Stage 3 execution followed. All eight cases received BLOCKED disposition; no retry was performed.

## MFV-009 resolution and Stage 2 rerun — S2R2-20261019-034105-CDT

**MFV-009: RESOLVED** for the current laboratory runtime. Host Python imports proved httpx resides in /usr/lib/python3.14/site-packages/httpx and typing_extensions in /usr/lib/python3.14/site-packages/typing_extensions.py. Existing worker.py used Python -S and only explicitly exposed /site (user packages), /repo and its own directory. -S intentionally omits automatic site-package discovery; required packages under the already mounted read-only /usr tree were therefore absent from sys.path.

Authorized repair changes only worker.py's dependency path setup and an imports smoke mode, plus control.py's explicit imports action. It appends existing /usr site-package directories returned by site.getsitepackages(), without calling site.main() or processing .pth startup hooks. No package installation, virtual environment, new mount, production edit, privilege/network change or global Python configuration was required. The same sandbox imported httpx, typing_extensions, FastAPI, Pydantic, Motor and all allowlisted harness modules successfully without running a test method. Isolation verify passed again; all eight financial dispatches passed their guards and reached tests without the prior import failures.

The MFV-009 row above preserves its first-run observation with its current status updated to RESOLVED; this resolution supersedes the original OPEN disposition. Closure does not make all Stage 2 rows PASS.

| ID | Module | Severity | Concrete evidence / reproduction | Expected | Actual | Related case | Impact | Suggested correction, not applied | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| MFV-010 | Account creation input validation / API error handling | P2 | Existing isolated MF-S2-01 adapter first completed six account types with openings 0/1000/-100, then POST /accounts with name Synthetic invalid and type invalid. cases.py:86 calls request(success=False), whose line 65 accepts 400/404/409/422. Trace ends AssertionError: ('POST', '/accounts', 500). | Unsupported account type receives a handled validation rejection; no record is inserted | HTTP 500 observed. The subsequent no-insert count assertion was not reached, so record absence is not independently certified by this run. | MF-S2-01; EV-MF-S2-01-R2 | Invalid account input becomes an internal server error. No incorrect balance, loss or unauthorized record mutation was demonstrated. | Separately authorize a minimal validation/error-handling review; do not repair production in this task. Preserve the failing synthetic fixture. | OPEN; confirmed isolated API-contract failure, no repair or deeper investigation |

Stage 2 rerun outcomes: four full rows PASS, MF-S2-01 FAIL, three rows BLOCKED only for remaining frontend evidence (MF-S2-02 UI cancel, MF-S2-05 localized rejection/input preservation, MF-S2-07 direct-read frontend fixture). These gaps are not new financial defects. The corresponding backend executions all exited 0.

New confirmed issue this rerun: P0 0 / P1 0 / P2 1 / P3 0 (MFV-010). Current OPEN confirmed counts: **P0 0 / P1 2 / P2 3 / P3 0** (001/002/003/006/010). Cumulative ever-confirmed counts including resolved MFV-009: P0 0 / P1 2 / P2 4 / P3 0. No financial corruption, lost money or incorrect transfer total was demonstrated. Do not confuse current open counts with historical counts or backlog hypotheses.

## Stage 2 frontend completion — S2FE-20261019-034732-CDT

Only the three pending rows MF-S2-02/05/07 were addressed. Existing scripts test-account-transactions.cjs, test-expense-account.cjs and test-transaction-direct-read.cjs each exited0 in the existing laboratory network namespace with read-only project mounts, zero capabilities, NoNewPrivs and no database credentials. No financial Python case was rerun. No production or test code was edited.

MF-S2-05 now PASS: existing actual-save-handler mocks verify EN/ES source-account feedback, preserved draft fields, blocked invalid submission, double-tap guard and rejected-request behavior, supplementing the already accepted isolated backend checks. MF-S2-07 now PASS: existing direct-read frontend fixture verifies encoded identity, API error propagation, edit/omitted-payload behavior, drafts and cache identity, supplementing prior isolated ledger checks. These are automated Node/VM/mocked API results, not Android or live HTTP end-to-end observations.

MF-S2-02 remains BLOCKED: the account-transactions script covers navigation/filtering/paging, not cancellation of the actual account edit form. ADB inventory returned zero attached/authorized devices. The private laboratory exposes no HTTP endpoint or isolated app session to the phone. Source shows the account Back callback uses router.back(), but static inspection cannot establish actual edit cancellation/data preservation. Exact pending manual steps and prerequisites are in EV-MF-S2-02-FE. This is an evidence gap, not a confirmed financial defect, and no new issue/severity is invented.

No new errors. MFV-009 stays RESOLVED; MFV-010 stays OPEN P2 and was not repaired or rerun. Current confirmed OPEN counts remain P0 0 / P1 2 / P2 3 / P3 0; speculative/historical backlog remains separate. Stage 2 latest totals6 PASS /1 FAIL /1 BLOCKED; no authorization to start Stage 3 follows.

## Stage 3 findings — S3-20261019-035444-CDT

Only existing Stage 3 methods/scripts were executed in the existing private laboratory network/readonly filesystem, with fake databases/storage and no MongoDB credentials. No real Stage 3 financial write was attempted. A required real-replica integration adapter/fixture set is absent; all eight full cases remain BLOCKED despite passing offline portions. An unavailable adapter is a documented prerequisite gap, not a new financial defect.

| ID | Affected functionality | Severity | Reproduction / concrete evidence | Expected | Actual | Related cases | Financial impact | Possible correction — not applied | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| MFV-011 | Payment consistency harness / cancellation-to-summary integration evidence | P2 | Explicit PaymentTests.test_retry_after_delete_does_not_resurrect_payment in isolated Python unittest group MF-S3-05. Trace at test_payment_consistency.py:412 GET /summary: Collection lacks aggregate; cleanup then reports Session lacks end_session. | Existing fake implements methods required by current summary so the final cancellation/report assertion can run | One unittest ERROR; summary assertion not reached. Other two methods in the group pass. | MF-S3-05; EV-MF-S3-05 | Blocks summary integration evidence after cancellation. Does not establish a real MongoDB/API financial error, second refund or incorrect total. | Separately authorize a minimal test-double compatibility update and rerun of the affected existing test. Do not change production summary logic to fit the fake. | OPEN — laboratory test defect; no repair/investigation beyond captured trace |
| MFV-012 | Frontend R6 safety fixture / extracted save handler | P2 | test-r6-final-safety.cjs exits1 after six PASS lines; main:83 invokes extracted save and gets ReferenceError: completedRef is not defined in VM. | Fixture supplies the actual handler's required context and reaches its final safety assertions | VM execution stops on an undefined reference; final checks incomplete | MF-S3-07; EV-MF-S3-07 | Missing test evidence; no device/runtime financial corruption demonstrated. Earlier read-only/replay mock assertions passed. | Separately authorize inspection/update of the extracted-handler fixture context, preserving existing safeguards and production behavior. | OPEN — test VM blocker; no repair |
| MFV-013 | Debt summary source-contract comparator | P2 | test-debt-summary-flip.cjs:22 exits1 with AssertionError: Shared Back controls retain the existing list route; actual false /expected true | Comparator reaches directional-summary assertions with a valid source contract check | Exact-source header assertion fails before summary numeric/animation assertions execute | MF-S3-03/08; EV-MF-S3-03 and EV-MF-S3-08 | No incorrect financial summary or native navigation was demonstrated. The blocked source assertion cannot certify those outputs. | Separately review the expected source pattern versus current header contract; preserve actual navigation and financial behavior. Do not automatically relax the check. | OPEN — comparator failure; no repair |

MFV-011's aggregate/end_session errors are one incomplete fake-contract defect, not two financial issues. MFV-012 and MFV-013 have different reproduction sites and failure mechanisms. MFV-008 remains the historical observation for a different summary comparator (test-summary-totals.cjs); it was not rerun and no identical underlying cause is assumed.

New confirmed Stage 3 findings: **P0 0 /P1 0 /P2 3 /P3 0**, all test-infrastructure/comparator issues. No confirmed financial inconsistency. Current OPEN confirmed register counts: **P0 0 /P1 2 /P2 6 /P3 0** (001/002/003/006/010/011/012/013); resolved MFV-009 and provisional backlog observations are excluded. Stage 2 remains exactly6 PASS /1 FAIL /1 BLOCKED. No production repair, fixture repair, new stage or recursive investigation was performed.

## Single authorized infrastructure repair/rerun — S3R2-20261019-040326-CDT

Owner authorized only MFV-011/012/013 test-infrastructure fixes, scoped Stage 3 adapters, one rerun of the eight cases, no production changes and no second repair cycle. This resolution/disposition supersedes the historical OPEN rows above.

| Existing issue | Current disposition | Authorized change and actual verification |
|---|---|---|
| MFV-011 | BLOCKED — partially repaired, not resolved | Payment fake gained bounded duplicate-ID aggregate, projected reads, cursor timing/batching/close and session end support. The original missing-method errors no longer occur. The same cancellation-summary method now stops at NameError: Decimal is not defined in the extracted summary namespace. Two other group methods pass. No additional repair was made after the rerun. |
| MFV-012 | RESOLVED | R6 UI fixture supplies completedRef and dismissTo navigation. Assertions now follow the current completed/dismissed form contract rather than obsolete in-place recovery flags, retaining exact-key, no-second-send checks and checking repeated press after completion. Entire test-r6-final-safety.cjs passes inside MF-S3-07, followed by passing real context/reconciliation checks. |
| MFV-013 | RESOLVED | Summary fixture inspects JSX named properties via TypeScript AST, verifies title/existing actions, and invokes the extracted Back handler to assert router.back once. It no longer requires an exact attribute order. All original amount/directional/animation assertions remain; the complete summary script passes inside MF-S3-08. |

MFV-011 remains one incomplete test-environment contract issue; the newly reached missing Decimal name is not a new application/financial defect or separate duplicate issue. Its remaining global dependency was not fixed after this single attempt. No conclusion about other unexecuted cleanup/import paths is invented.

| ID | Module | Severity | Reproduction / evidence | Expected | Actual | Related case | Financial impact | Possible correction, not applied | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| MFV-014 | New Stage 3 invalid-account adapter expectation | P2 | Existing isolated Stage 3 rerun: stage3_cases.py:185 requests POST /debt-payments using account_id=missing and expects422; request helper at105 records404 with detail Account not found. | Adapter accepts the established missing-resource rejection contract and continues with no-write/settlement assertions | API rejects the invalid account with404; adapter aborts before its following snapshot/full-settlement/post-settlement assertions | MF-S3-04; EV-MF-S3-04-R2 | No incorrect charge or accepted invalid payment demonstrated. This is an over-specific status expectation in the new test adapter, not a Pickwallet financial failure. Missing-account no-write snapshot assertion after the call was not reached. | Under new authorization, align only this adapter expectation with the existing404 contract and rerun the affected frozen case. No production status change or relaxed rejection invariant. | OPEN — test adapter blocker; no further repair in this attempt |

Six child executions exit0; MF-S3-04/05 exit1 for test infrastructure. Full matrix outcomes are5 PASS /0 FAIL /3 BLOCKED because MF-S3-08 still requires native filter evidence despite passing automation/real DB. No new Pickwallet financial defect confirmed. New issue this attempt: P0 0 /P1 0 /P2 1 /P3 0 (MFV-014). Current OPEN confirmed counts: **P0 0 /P1 2 /P2 5 /P3 0** (001/002/003/006/010/011/014), excluding resolved009/012/013 and unverified backlog. MFV-010 and Stage 2 outcomes remain unchanged. No second repair cycle, production fix or Stage 4 execution.

## Stage 4 diagnostic disposition — S4-20261019-092323-UTC

Stage4 complete classification:0 PASS /2 FAIL /6 BLOCKED /0 NOT TESTED. Evidence EV-MF-S4-01 through08 in PROGRESS.md; no production changes or repair. All new entries below are P2; severity reflects bounded wrong-date/filter behavior or test evidence obstruction, not proven financial corruption. Missing Stage4 real adapters/fixtures are explicit prerequisites, not invented application defects.

| Issue ID | Module / severity | Expected versus actual and reproducible evidence | Financial impact / affected case | Status / possible correction (not implemented) |
|---|---|---|---|---|
| MFV-015 | Bills filter frontend test fixture, P2 | Existing test-four-ui-fixes.cjs exits1 at28:84 because its Accounts VM require allowlist lacks @/src/components/header-actions. Expected fixture reaches Bills paid-only filter assertions; actual abort occurs before those assertions. EV-MF-S4-01 records full trace. | Blocks filter evidence; does not demonstrate wrong bill counts or account behavior. MF-S4-01. | OPEN test infrastructure only. Separately authorize adding the existing shared-header mock to the fixture; do not modify production headers or filters. |
| MFV-016 | Category initialization source comparator, P2 | Existing test-category-initialization.cjs exits1 at45:14. Its normalized current transaction save handler is compared against HEAD's unnormalized handler, which already includes the approved original-field preservation branch. Expected source comparator accepts the current intended preservation contract; actual normalization removes that branch only on one side and changes finalName only on one side. EV-MF-S4-05 records mismatch. | Blocks final initialization/restore evidence; no duplicate default category or financial write is demonstrated. MF-S4-05. | OPEN test comparator only. Separately review consistent comparison/reference contract; do not weaken validation or edit production transaction saving. |
| MFV-017 | Recurring payment local date, P2 | Existing test-history-date-contract.cjs executes the actual recurring/[id].tsx todayIso expression with TZ=America/Chicago and clock2026-01-01T05:30:00Z. Local date expected2025-12-31; UTC-derived value is2026-01-01. Strict pending assertion logs EXPECTED DEFECT: recurring today must use local date at month/year boundary. EV-MF-S4-02/08 preserve command output. | Local day/period may be selected one day ahead near midnight; no recorded payment, balance mutation or duplicate event was tested/observed. MF-S4-02 FAIL. | OPEN confirmed extracted-expression runtime defect, not Android/DB evidence. Possible separately authorized correction: preserve local calendar-day semantics when constructing today; do not reinterpret persisted dates/history. |
| MFV-018 | Transaction history seven-day range, P2 | Same existing script executes actual transactions/all.tsx startOfDay/endOfDay/range expressions at2026-03-09T05:30:00Z in America/Chicago with period7d. Expected local startMarch3; six fixed86400000ms subtractions cross DST and produce startMarch2. Strict pending assertion logs EXPECTED DEFECT: 7-day calendar filter cannot subtract fixed24-hour intervals across spring DST. EV-MF-S4-08. | An extra local calendar day can enter the range, changing which historical movements are displayed/included. No stored transaction, account balance or backend amount was changed. MF-S4-08 FAIL. | OPEN confirmed extracted-expression date-filter defect. Possible separately authorized correction: local calendar-day arithmetic preserving documented inclusive range; do not modify money calculations or records. |

MFV-008: existing historical summary comparator failure is freshly reproduced by test-summary-totals.cjs, exit1 at111:12 after eight successful mock groups. The current-source normalization of old reserved rows/colors differs from HEAD's already updated JSX. This is confirmed P2 test-only evidence obstruction for MF-S4-06, not a new ID or incorrect numeric summary. Its prior provisional status is superseded by this reproduction; not repaired. MFV-004 Reports500-record limit is still a source-confirmed risk, with actual displayed501/2001 agreement NOT TESTED; no promotion to a confirmed incorrect financial total.

New issues: P0 0 /P1 0 /P2 4 /P3 0 (015–018). One pre-existing provisional issue008 is now confirmed/reproduced test-only. Current confirmed OPEN counts: P0 0 /P1 2 /P2 10 /P3 0 (001/002 P1;003/006/008/010/011/014/015/016/017/018 P2). MFV-010 remains OPEN; MFV-011 BLOCKED,012/013 RESOLVED,014 OPEN infrastructure blocker. No previous issue or evidence was removed. Missing real Stage4 adapters/fixtures affect all eight cases and were not repaired. No P0/P1 financial integrity defect was demonstrated by these partial tests; this does not certify financial correctness.

## Stage 5 diagnostic disposition — S5-20261019-092939-UTC

Results0 PASS/1 FAIL/7 BLOCKED/0 NOT TESTED. No new issue IDs: new P0 0/P1 0/P2 0/P3 0. Existing MFV-001 P1 is corroborated, not duplicated. Current confirmed OPEN counts remain P0 0/P1 2/P2 10/P3 0; previous issue010–018 dispositions are unchanged and no fix was attempted.

### MFV-001 — public multiuser release blocker reconfirmed

Affected test MF-S5-06 FAIL; related ownership coverage MF-S5-05 BLOCKED. Expected for public multiuser use: authenticated independent principals and authorization at financial boundaries. Actual current API: fixed default-user identity; no authentication dependencies or global auth middleware; CORS only. Existing FinancialContextTests.test_context_readonly_aliases_and_backend_restart accepts no-credential ASGI GET /financial-context and returns default-user/single_user for different Host aliases. Existing test_network_failure_and_legacy_compatibility accepts synthetic legacy POST /debt-payments without context headers even when optional metadata/pin protection is absent; expected-context headers validate destination, not caller authentication. Both tests pass their existing single-user contract, so the public distribution acceptance criterion FAILS. Evidence EV-MF-S5-06 contains actual commands/methods, timestamps and output. Static global route inspection corroborates that the harness did not omit an existing app authentication dependency.

Impact: the present single-user API cannot be advertised as authenticated or tenant-isolated for public multiuser distribution. No remote exploitation, real-account access, personal-data read or cross-user financial write was attempted or demonstrated. Do not relabel this as a new P0 exploit. Trusted private-LAN operation is a distinct deployment boundary, not public-release approval. Potential future corrective direction only: separately authorize an authenticated identity/ownership design and its regression scope; no authentication or production code is modified here.

MF-S5-05 additionally records source-level account-update queries by id without user_id and missing two-user route coverage. This is an unverified ownership consequence within the existing MFV-001 review scope; no successful cross-user mutation is claimed or new defect counted without a synthetic route reproducer. Guarded debt context and foreign expense references passed their memory checks; that does not supply global user isolation.

### Evidence gaps, not new product defects

MF-S5-01/02/03/04/05/07/08 lack required scoped Stage5 real-replica/HTTP fixtures and dispatch in the existing Stage2/3 executor. No repair cycle was started.41 existing Python memory methods and2 frontend mock scripts pass; they do not establish real MongoDB rollback, deletion races, concurrent keyed operations, interrupted commits or public API protections. MF-S5-07 narrow tracked-source scan found only three reviewed synthetic URI fixture candidates and no matching private-key/provider token; complete deployed-secret/error/public-exposure evidence is absent. Existing development listeners were inspected read-only, not probed externally or reconfigured.

No new financial-integrity inconsistency confirmed; production data never accessed. Existing failed/blocked cases, including MFV-010/011/014/017/018, are not waived. Public multiuser release remains NOT READY; Stage6 not executed. See EV-MF-S5-01 through08 for exact missing prerequisites.

## Stage 6 diagnostic disposition — S6-20261019-093655-UTC

0 PASS/0 FAIL/8 BLOCKED/0 NOT TESTED.20 of22 scripts and TypeScript pass. Every frozen Stage6 case requires Android evidence, unavailable: adb inventory0 connected/authorized devices and no separate synthetic handset/backend/storage session. Source/VM success is not device/end-to-end acceptance. Prior issue/result dispositions remain intact.

| Issue ID | Severity / module | Reproduction and expected versus actual | Related case / impact | Status / possible next action, not performed |
|---|---|---|---|---|
| MFV-019 | P2 test-only payment resource-state fixture | Existing command node frontend/scripts/test-payment-resource-states.cjs exits1 with TypeError Cannot read properties of null (reading props) at73:30. During debt loading it expects find(debt-pay-back) to expose Back. Helper57–64 searches literal testID/children, but localeMocks represents MoneyFlowHeaderActions as an opaque string whose Back is in backTestID/onBack props. Actual debt route115 supplies those props. Expected fixture traverses the shared header and reaches Back/retry/journal assertions; actual VM tree lookup returns null and aborts. Full output/source evidence EV-MF-S6-08. | MF-S6-08 BLOCKED, not a proven application Back failure. Remaining bill/debt resource states and mutation guards are not certified by this aborted script. Independent debt form/header mock checks pass. No financial or stored-data effect demonstrated. | OPEN infrastructure blocker. Separately authorize fixture traversal using the existing shared-header mock contract if desired; do not change the real header/navigation to accommodate the test. No repair/new test/rerun in this task. |

Existing MFV-008 reproduced by summary script111:12 after eight successful groups, same source/HEAD visual normalization blocker as Stage4; no duplicate issue. No new confirmed frontend application defect, localization failure, GO_BACK warning or content loss was demonstrated in the available tests. Native keyboard/animation/touch/stack/persistence remains unverified, not assumed correct.

New issues P0 0/P1 0/P2 1/P3 0 (019 test-only). Current confirmed OPEN counts P0 0/P1 2/P2 11/P3 0. Earlier MFV-001 public multiuser blocker and all prior findings remain unchanged. No financial/backend/production source or testing infrastructure was modified; only the four validation records. Manual prerequisites and exact per-case steps are recorded in EV-MF-S6-01 through08. No Stage7, repair cycle, dependency installation, commit or push.


## Stage 6 Android resumption — S6A-20261019-124341-CDT

No new issue or severity assignment. All eight cases remain BLOCKED: phone absent from ADB; installed APK/destination unverified; existing test replica stopped; normal backend/Metro/Mongo ports not listening; no proven isolated Android HTTP/storage context. These are environmental/prerequisite gaps,not demonstrated frontend defects or deleted financial data. Local APK artifact exists but is not proof of installed build/version. MFV-019/008 and all previous dispositions remain unchanged. No repair,service restart,app launch,personal-data access or test mutation attempted. See PROGRESS.md for actual read-only evidence and safe connection steps.


## Stage 6 connected-device resumption — S6B-20261019-125305-CDT

| Issue ID | Severity/module | Reproduction and expected versus actual | Cases/impact | Status/next action |
|---|---|---|---|---|
| MFV-020 | P2 isolated laboratory availability | Existing control.py start attempts only original owned container and Podman returns125. verify reports container stopped. Read-only State.Error identifies missing /tmp/pickwallet-stage2-stz3uedv/key; original state/credentials.json and /data/db bind source also absent. Expected retained private state allows original replica to start and pass isolation; actual required runtime resources unavailable. | MF-S6-01 through08 synthetic Android isolation gate BLOCKED. No development/personal data loss or frontend defect demonstrated; temporary-state disappearance cause unverified. | OPEN environmental prerequisite. Stop per no-recreation restriction; owner must separately authorize an explicit recovery decision,without development DB fallback,new laboratory or automatic credential/data regeneration. |

New issues P0 0/P1 0/P2 1/P3 0 (020 infrastructure only). Current confirmed OPEN P0 0/P1 2/P2 12/P3 0. Existing issue dispositions preserved. Samsung now authorized,installed/local release hash matches and phone HTTP schema request succeeds; these resolve prior connection/identity prerequisites only,not synthetic state isolation or frontend case acceptance. No state-changing Android tests,bug fixes,app storage changes,normal financial writes or Stage7.

## MFV-020 resolution — R20-20261019-125941-CDT

MFV-020 RESOLVED for original laboratory availability. Root cause: controller intentionally placed all replica data/key/credentials in tempfile.mkdtemp under /tmp; filesystem is tmpfs and the host rebooted after original creation. Missing state is consistent with that volatile lifetime; no process-specific deletion audit is asserted. README already warned about reboot/cleanup. Development data was not implicated.

Explicit owner authorization allowed regeneration only of missing owned temporary resources. Verified original label/session/mount paths/no foreign references and total state absence. Reused original container,image,replica,DB/network/session; fresh credentials/key and exclusive absent-only creation. Original synthetic financial contents were already unavailable and were not restored,overwritten or re-run. Bootstrap skips fixtures; new recovered-state guard disables historical financial dispatch. Only private replica/auth administrative initialization performed,no financial writes. Existing auth/network/foreign-database negative guards pass; no non-system collections exist. Repeated recovery,bootstrap/financial replay probes safely reject. Full evidence in PROGRESS.md and lab README.

No new defect ID. Current confirmed OPEN counts P0 0/P1 2/P2 11/P3 0 after closing020; historical020 evidence retained. Stage6 remains8 BLOCKED because Android synthetic HTTP/storage context is still unavailable; this separate prerequisite is not silently declared solved by Mongo readiness. No Stage6 tests,production fix,APK/storage change,commit or push.

## Stage 6 real Android — S6REAL-20261019-131245-CDT

Current Stage6:3 PASS /2 FAIL /3 BLOCKED. Earlier findings/results remain historical and are not repaired. New issues:P0 0/P1 0/P2 1/P3 0. Current confirmed OPEN counts:P0 0/P1 2/P2 12/P3 0; MFV-020 stays RESOLVED.

### MFV-021 — Notes preview retains stale Pin action after a successful pin

- Severity: **P2**, confirmed on Samsung SM-S931U, installed release com.emergent.moneyflowpreview.p1r033, version1.0.0/code1. Related cases **MF-S6-03 and MF-S6-04 FAIL**.
- Reproduce: create a synthetic plain note; open its preview; open three dots; select **Fijar nota**; reopen the menu without closing the preview. Actual label remains **Fijar nota**. Close/reopen the same note; the label becomes **Desfijar nota**. Expected: the open preview's contextual action immediately reflects the persisted pinned state.
- Native evidence: `/tmp/pickwallet-s6-android-20261019-131245/qa-note-context-menu.{png,xml}`, `qa-note-pinned-menu.{png,xml}` (stale), `qa-note-refreshed-pin-menu.{png,xml}` (correct after reopen). QA note id mvflgpm4t7q4pm. Action/capture timestamps in actions.jsonl. No second pin action was performed while the label was stale.
- Bounded source corroboration: frontend/app/(tabs)/notes.tsx togglePin around512 persists the new confirmedNotes/list state; the preview actions around790–793 read previewNote.pinned, which togglePin does not synchronize. No production edit or recursive investigation performed.
- Impact: misleading action state in an open note preview; no financial effect, lost note content or failed pin persistence demonstrated. Potentially confusing subsequent action; no claim of an observed accidental unpin.
- Status: **OPEN; not fixed**. Possible separately authorized correction: synchronize the preview's entity state with the confirmed pin update, preserving failure handling and content. Retest the same native reproduction and existing Notes persistence/menu regressions before closing.

No other new product defect is confirmed. Automation target assumptions, a call interruption, bulk ADB text injection not delivering its intended 5001 characters, and unsupported am CLI flag syntax are not classified as app defects. No-history/fault-injection/device capability gaps remain blockers, not invented failures. Previous financial/security defects are unchanged; no new financial inconsistency was demonstrated by the exercised QA flows.

## Stage 7 partial diagnostic — S7-20261019-190006-UTC

New issues: **P0 0/P1 0/P2 0/P3 0**. MFV-021 and all earlier findings/dispositions remain unchanged; confirmed OPEN counts remainP0 0/P1 2/P2 12/P3 0. Stage7 has0 PASS/0 FAIL/1 BLOCKED/7 NOT TESTED.

Actual Expo Go samples show screenshot-based cold median balance visibility4.7408s/successful Tools interaction5.6253s; warm2.3086s/2.6859s. These are upper bounds including host ADB polling, normal Expo launcher/project selection, visible financial amount settling and successful navigation, not exact first-interactive measurements. They therefore do not by themselves prove an app-specific violation of the proposed3s/1.5s first-interactive budget. Development/Expo-host and release behavior are not conflated. No new app performance defect is assigned without the missing timing attribution.

Two preliminary direct-URL/reference-calibration attempts did not reach their visual oracle; they are excluded, not counted as app crashes. Successful final ten samples completed before19:08:44UTC. No scoped post-run crash/ANR trace could be collected after the phone disappeared. Historical gfxinfo counters, Android launcher time and a single RSS/CPU sample do not prove frame pacing, sustained CPU, leaks or absence of crashes.

A pre-existing Tools header/status-bar overlap was visible in the initial retained screen, but scroll/inset state and a fresh reproduction were not established. It is an unconfirmed observation, not a new defect or an amendment to Stage6. No repair or nested investigation was started. Device unavailability/timebox expiry is an execution blocker, not a product issue. Exact evidence/next prerequisites are in EV-MF-S7-01…08 in PROGRESS.md.


## Stage 7 retry confirmed findings — S7R2-20261019-230103-UTC

New P0 0 / P1 0 / P2 2 / P3 0. Confirmed OPEN cumulative counts nowP0 0/P1 2/P2 14/P3 0. Earlier issue evidence and MFV-021 are preserved, not fixed. Stage7 1 PASS/2 FAIL/5 BLOCKED. Raw temporary evidence root /tmp/pickwallet-s7-retry-20261019-230103/untouched/; essential actual values are duplicated below and in PROGRESS.md.

### MFV-022 — Android animation/elastic-scroll missed-frame budget exceeded

- **P2, OPEN; MF-S7-05 FAIL.** Samsung SM-S931U Android17/API37, installed release1.0.0/code1, artifact SHA-256aab254e37713011e759d65efe55ec3e6376c0a7141a58d5b6a9949fbeb1f66c5, local healthy backend/fixed100-row QA fixture plus12 unchanged baseline transactions. Display mode120Hz, captured frame interval about8.33ms, thermal status0, USB charging. No video encoder during measured windows.
- Reproduction: reset this package's gfxinfo counters; from Home scroll to Recent Transactions and open/close its calendar10 times; capture gfxinfo. Separately reset counters and execute four existing elastic downward pulls. Repeat the existing animation set with transition_animation_scale0/restarted app, restoring1.0 afterward. No app source mutation or financial submit.
- Expected: frozen Stage7<=5% missed/janky frames and p95<=two active-refresh intervals, responsive final layout. Actual normal calendar78/1335 frames5.84%, Android aggregate p95 10ms; normal elastic57/25022.80%,p95 12ms; reduced elastic36/20717.39%,p95 15ms. These violate the missed-frame criterion even where percentile duration is below two8.33ms intervals. Other Profile small-window percentages are documented but are not the basis for claiming sustained jank.
- Evidence: normal-calendar-gfxinfo.txt, normal-elastic-gfxinfo.txt, reduced-elastic-gfxinfo.txt and corresponding metrics JSON; separate visual-normal/reduced-animations.mp4. Counts are Android process/window HWUI observations, not uniquely presented frames, exact app FPS or JS FPS. CSV ring truncation and automation overhead are documented. No ANR/freeze or financial inconsistency demonstrated.
- Impact: measurable frame-pacing inconsistency in the tested transitions/scroll interactions; cause not attributed to an unmeasured JS/layout/driver bottleneck. Existing MFV-005 remains a related provisional code-pattern risk, not a duplicate confirmed root-cause finding. Possible separately authorized correction: correlate UI/render work in these same operations, then optimize only the identified bottleneck and repeat the fixed native comparison. No fix implemented.

### MFV-023 — Profile Name editor and Save are covered by the Android keyboard

- **P2, OPEN; MF-S7-08 FAIL.** Same Samsung/Android/release artifact; default font0.9, also encountered during enlarged-font walkthrough; reproduced in English and Spanish with Light theme. No entered name was changed or saved.
- Reproduction: open Profile→Personal information→Name; tap the existing name input; leave keyboard visible. Actual editor remains below the keyboard rather than moving into its usable area. After a settled screenshot and XML capture, IME visible frame[0,1474][1080,2340] covers input[45,1957][1035,2092], Cancel[45,2133][538,2249] and Save[569,2133][1035,2249]; mInputShown=true. Expected: focused input and primary save/cancel actions remain visible/reachable while typing.
- Evidence: keyboard-confirm-after-xml.png, keyboard-confirm-settled.xml, keyboard-confirm.json and independent layout-default-en-US/es-name-keyboard captures. No source diagnosis or fix performed. Hiding keyboard makes controls reachable and cancel works; no content loss or financial side effect observed. This is a confirmed keyboard-overlap defect, not an unsupported inference from a missing accessibility node.
- Possible separately authorized correction: preserve the existing sheet transition and save handler while making its keyboard avoidance/insets work for this native modal; retest settled Android input/Save/Cancel in both languages/font sizes. Not implemented. Stage6 3/2/3 is frozen; this later finding does not rewrite prior statuses.

Other retry evidence: standalone startup medians are conservative upper bounds (cold successful interaction1.9299s, warm1.4411s); exact response-relative readiness and navigation500ms acceptance remain BLOCKED. The interrupted/user-operated CPU sample is excluded. No new crash,GO_BACK exception,OOM,ANR,financial loss or duplicate charge confirmed. Absence of confirmation is not a release certification. MF-S7-07 read-only22.255s outage recovered on the same backend PID with loopback/LAN HTTP200 and verified independent watchdog; no financial write during outage. Payment-loss-after-commit and HTTP503 variants remain blocked.


## Canonical final issue disposition — S8-20261019-182837-CDT

This table supersedes historical status/count statements without erasing evidence.24 unique IDs total:17 confirmed OPEN (P0 0/P1 2/P2 15/P3 0),3 provisional risk/evidence/optional entries,4 RESOLVED. New registration MFV-024 P2; no new P0/P1. Severity counts exclude provisional004/005/007 and resolved009/012/013/020. Seven confirmed product behavior defects:010/017/018/021/022/023/024; these are not seven money-corruption findings. App quality003, release/security001/006 and infrastructure002/008/011/014/015/016/019 are separated. Proposed owner denotes responsibility for a future authorized change,not an assignment/message or release-risk acceptance.

| ID / current status | Severity / category / module | Evidence and user impact | Recommended next action / proposed owner | Public release block |
|---|---|---|---|---|
| MFV-001 OPEN | P1 security; identity/authorization | OBS01,EV-S5-06,S8-06: fixed default-user; fresh local unauthenticated financial-context200/single_user; no demonstrated tenant security | Owner/backend security: authorize authenticated identity and per-resource ownership design; validate existing05/06 security cases | YES, public multiuser; private trusted-LAN scope distinct |
| MFV-002 OPEN, quarantined | P1 infrastructure; legacy API runner | OBS02,S8-03: remote fallback plus CRUD/seed; not executed | Test maintainer: retain quarantine; separately scope destination guards/explicit allowlist | Unsafe runner/validation gate; not a proven shipped runtime vulnerability |
| MFV-003 OPEN | P2 static quality; frontend | S1-08,S8-02:151 errors/86 warnings; TS passes; not151 runtime bugs | Frontend owner: bounded rule triage, functional significance first; no automatic sweeping fix | Clean gate/disposition required; no waiver recorded |
| MFV-004 OPEN risk | P2 provisional financial reporting limit | OBS04,S8-04: legacy500-reader cap; displayed high-volume mismatch NOT VERIFIED | Financial/test owners: verify only frozen report-volume/reconciliation cases before correction | Evidence gate; do not claim observed financial corruption |
| MFV-005 BACKLOG | P3 optional/provisional scalability | OBS05; source patterns not measured root causes; S7 memory bounded PASS does not establish large-volume safety | Frontend/backend owners: retain optional backlog; tie any later change to a measured existing case | Not independently; mandatory scalability evidence remains blocked |
| MFV-006 OPEN | P2 release configuration/signing | S8-06 actual APK verifies with Android Debug signer; embedded local backend, no production artifact approval | Release owner: separately authorize production signing/destination/privacy configuration and artifact validation | YES, production distribution |
| MFV-007 OPEN evidence gap | P3 Android/native coverage | S7 actual samples now exist; startup attribution,volume,recovery,TalkBack and source-build provenance incomplete | Device/test owners: use existing blocked IDs/evidence list, not another broad audit | YES to full Android certification; not a proven crash |
| MFV-008 OPEN | P2 test comparator; summary visuals | S4-06,S8-02: normalization/HEAD comparison fails111:12; numeric mocks before it succeed | Test maintainer: align comparator to intended source contract without weakening numeric assertions | Complete regression gate blocked; incorrect money not demonstrated |
| MFV-010 OPEN | P2 app/API account validation | S2-01: invalid type yields500, expected handled4xx; no-insert assertion not reached | Backend owner: narrowly validate unsupported type/error mapping; rerun S2-01 | Affected financial-input correctness unresolved; no balance corruption proven |
| MFV-011 BLOCKED/OPEN | P2 infrastructure; payment-summary fake | S8-03 exact method still ERROR: Decimal undefined in extracted summary;96 other methods OK | Test maintainer: supply actual namespace contract, then affected S3-05/S8-03 only | Financial cancellation-summary evidence gate |
| MFV-014 OPEN | P2 infrastructure; Stage3 adapter | S3-04: valid missing-account404 rejected by fixture expecting422 | Test maintainer: align accepted missing-resource rejection, retain no-write assertion | Settlement/negative evidence gate,not wrong charge |
| MFV-015 OPEN | P2 infrastructure; Bills/Accounts VM | S8-02: header-actions require missing at28:84 before bill assertions | Test maintainer: existing shared-header mock only,rerun affected case | Bills-filter regression evidence gate |
| MFV-016 OPEN | P2 infrastructure; category source comparator | S8-02: asymmetric normalized/current vs HEAD handler45:14 | Test maintainer: consistent source contract comparator; no production save changes | Category-initialization regression evidence gate |
| MFV-017 OPEN | P2 app/financial date; recurring detail | S4-02/08,S8-02 strict expression: at Jan1 05:30Z Chicago expects Dec31,uses Jan1 UTC | Frontend owner: preserve intended local calendar day,retain stored date meanings | Date/period correctness; no monetary write discrepancy proven |
| MFV-018 OPEN | P2 app/financial date; history range | S4-08,S8-02: 7-day filter spans extra local day across March2026 DST | Frontend owner: calendar-day arithmetic; rerun same frozen date/history variants | Displayed/report period correctness unresolved |
| MFV-019 OPEN | P2 infrastructure; resource-state header mock | S8-02 null.props73:30 from opaque shared-header fixture; native missing Back not proven | Test maintainer: traverse shared header with existing helper,retain recovery guards | Loading/error/retry regression evidence gate |
| MFV-021 OPEN | P2 app; Notes Pin menu | S6-03/04 native preview retains Fijar label after pin until reopened; one defect,two cases | Frontend owner: synchronize confirmed preview entity state; preserve persistence/errors | P2 functional disposition required; no note/financial loss shown |
| MFV-022 OPEN | P2 app; Android frame pacing | S7-05: calendar5.84%,elastic22.80% normal/17.39% reduced missed HWUI deadlines | Frontend owner: correlate measured work then narrow optimization; repeat existing fixed trace | Android performance acceptance fails; no FPS/leak claim |
| MFV-023 OPEN | P2 app; Profile Name keyboard | S7-08 native IME1474–2340 covers input1957–2092 and Save/Cancel2133–2249 | Frontend owner: correct sheet keyboard/inset behavior only; verify EN/ES/fonts | Android usability acceptance fails; hiding keyboard workaround |
| MFV-024 OPEN | P2 app/financial date presentation; debt detail | S8-02 strict existing formatDateLong('2026-01-01') preservation assertion fails in Chicago; due-date row uses helper | Frontend owner: distinguish local all-day dates from real instants; existing date regression only | Date correctness unresolved; no stored-data/money mutation shown |

Resolved historical issues remain archived, not retested into new IDs:009 dependency-path visibility;012 R6 fixture context;013 debt-summary comparator;020 owned temporary-lab runtime restored.012/013 scripts exit0 in S8,existing isolation guard verifies020 availability; no closure of missing financial fixtures is inferred. No obsolete OPEN history is deleted. MFV-007 is narrowed to remaining native evidence rather than incorrectly retaining an assertion that no Android measurement exists.

### MFV-024 — All-day debt due-date formatter does not preserve calendar date

New registry entry, existing-harness defect rather than a new Stage8 code regression. P2; MF-S8-02 FAIL. Exact existing command node frontend/scripts/test-history-date-contract.cjs invokes fresh timezone children. In America/Chicago its strict pending assertion expects formatDateLong('2026-01-01') === 'January 01, 2026' and fails; generic UTC and Pacific/Kiritimati groups do not run this Chicago-only assertion. The script deliberately catches AssertionError and labels EXPECTED DEFECT,so its exit0 is not behavior acceptance. Stage4 previously logged this output as outside that stage's scope without registering a defect; the final frontend/i18n/date regression now records it once. Do not duplicate017 (recurring today expression) or018 (DST range arithmetic).

Bounded source corroboration only: frontend/src/format.ts40–46 constructs new Date(iso),then formats in local locale; frontend/app/debts/[id]/index.tsx149 passes d.due_date to it. A date-only ISO string is parsed as UTC midnight and can render the prior local day; this explains the failed all-day preservation assertion. No new reproducer,Android claim,stored-date rewrite or financial operation. Actual fixture expected-preservation failure is observed; exact handset label and monetary impact are unverified. Proposed next action under separate permission: preserve all-day local dates while maintaining actual timestamp semantics; rerun the existing affected date/i18n/debt display assertions. No fix performed.

### Non-issue release evidence gaps

No new MFV ID is invented for missing S8 real-financial batch,combined ledger/display fixture,restart/fault transport,production privacy/data-handling/store declarations or iOS evidence. These remain explicit BLOCKED/NOT VERIFIED gates,not demonstrated money loss,legal violations or failed iOS behavior. Local read-only endpoint200 is not authentication or public Internet exposure proof. Narrow secret scans are not a complete audit. No issue was silently accepted or waived by the diagnostic.


## R2 resolution — MFV-010,MFV-017,MFV-018,MFV-024

Owner authorized only RPR-001–004. All four are RESOLVED at their bounded code/focused offline acceptance level; existing full-case integration/native gaps are not closed. Evidence: [R2 red/green verification](PROGRESS.md#r2-financial-corrections). Earlier OPEN statements are historical and retained,not silently erased. No new MFV or severity escalation.

| Issue | Current resolution | Acceptance evidence / remaining evidence boundary |
|---|---|---|
| MFV-010 | RESOLVED — request-model validation | Matching six-value Literal rejects invalid POST/PUT at422/body.type before writes;18 valid create combinations/default and valid derived-balance edits pass extracted-route memory ASGI. Existing live Uvicorn not reloaded;full real-Mongo account matrix remains RPR-018/MF-S2-01,not a newly earned case PASS. |
| MFV-017 | RESOLVED — local recurring today | Existing local-day helper used;documented Chicago midnight plus UTC/Kiritimati leap/year fixtures pass actual expression. Full recurring real schedule/lifecycle remains RPR-020/MF-S4-02. |
| MFV-018 | RESOLVED — seven-day local-calendar range | Day−6 constructor preserves exact seven inclusive local days across spring/fall DST and boundaries;page/date-clear mocks pass. Real large history/whole MF-S4-08 remains RPR-020;other periods untouched. |
| MFV-024 | RESOLVED — date-only long formatting | Strict date-only local midnight;EN/ES day/leap/year0099 tests pass in three zones;Z/offset/local timestamp rendering retained. No stored-date rewrite;Android display confirmation not claimed. |

Current24-ID registry:13 confirmed OPEN(P0 0/P1 2/P2 11/P3 0),eight RESOLVED(009/010/012/013/017/018/020/024),three provisional004/005/007. Three confirmed application behavior defects remain OPEN:021/022/023. Authentication001,signing006,static003 and infrastructure002/008/011/014/015/016/019 remain unchanged. No observed lost money,incorrect balance or duplicate charge in targeted tests;absence is not complete integration proof. No R3 or broader repair was performed.

## R4 bounded repair disposition — MFV-021 and MFV-023

MFV-021: RESOLVED for confirmed stale Pin/Unpin preview state. Persistence-confirmed functional update by matching note ID; delayed/failing storage and neighbor/closed preview tests pass; native Expo Go synthetic pin/unpin/repin menu updates verified without reopening.

MFV-023: RESOLVED for confirmed Name/Save/Cancel keyboard overlap. Name-only opt-in native keyboard avoidance preserves existing sheet appearance/transition. Actual Samsung Android17 Expo Go checks pass in EN/ES at font0.9 and1.3; input/actions bottom<=1384 above IME1474. Original font and app locale restored. Native Save checked with unchanged name only; changed-name/error persistence covered by synthetic actual-handler tests. No personal profile replacement.

See [R4 evidence](PROGRESS.md#r4-notes-and-name-keyboard-repairs). Historical issue entries/case failures retained. RPR-019 broader native evidence and R3/MFV-001 remain pending; no blanket frontend or public-release certification.

## R5 measurement-only disposition

MFV-022 remains OPEN P2. Current Expo normal-calendar4.78%/9ms,reduced-calendar5.23%/10ms,normal-elastic2.11%/14ms,reduced-elastic1.27%/13ms. Different12-transaction dataset and development host prevent direct improvement claims against historical APK112-row run. Secondary instrumented normal-calendar5.41%/9ms is separately labeled and not substituted for baseline. No mounting/layout/JS/gesture root cause confirmed. MFV-007 remains missing attribution/evidence,not a newly demonstrated startup defect; MFV-005 speculative patterns unchanged. No new issue ID or financial defect. [R5 measured evidence](PROGRESS.md#r5-performance-diagnosis-20261019). No code optimization,R3,R6/R7,dependency/build/commit/push.

## R5 final focused replication

MFV-022 remains OPEN P2: current reduced calendar5.22/5.53/4.83%,normal controls5.16/4.85/5.59%,two of three exceed5% in both modes. Reduced mean5.1933% versus normal5.20%;no reduced-specific root cause demonstrated. Native layout/mount/JS attribution pending. Debugger401 cause confirmed as missing allowed Origin;accepted normal local-origin handshake does not provide a working runtime profile. No security changes,new defect ID or code fix. Native navigation overhead partially separated,not visual500ms acceptance. [R5 final focused evidence](PROGRESS.md#r5-final-focused-investigation-20261020).

## R3 delivery 2 partial authorization disposition

MFV-001 remains open. The detached authenticated API scopes the enabled reads
and Notes to the verified UUID. Legacy financial handlers still assume a fixed
owner, so unsupported routes are blocked rather than mounted behind an
authentication check. Remaining work includes scoped writes and references,
totals and histories, tenant-specific idempotency and replica-backed session
fencing. No duplicate issue is opened.

MFV-001 follow-up: owner-scoped account writes, ordinary movement creation and
paginated transaction history now have synthetic A/B coverage in the detached
API. The issue remains open for the outstanding routes, tenant idempotency,
and real replica verification. See R3_DELIVERY_2.md for the route count.

MFV-001 batch 2C: debt and loan lifecycle, linked payments and cancellations,
reconciliation and summary ownership are covered in the detached API. Real
replica guarantees and the remaining modules still block activation. The
summary fixture now executes the shared calculation with its original fixed
clock and resource budgets; the payment rollback fixtures inject failures at
the shared recomputation service. No duplicate issue was opened.

MFV-001 batch 2D: owner-scoped bills and recurring payment routes are present
in the detached API; real replica acceptance and remaining routes still
block activation. The focused batch also detected and corrected three
undefined legacy model defaults introduced by the 2C extraction. No new
issue is needed for the corrected regression.

MFV-001 batch 2E: budgets, savings goals and calendar are owner-scoped in the
detached API. The remaining routes and real-replica acceptance still block
activation. No new issue was identified in the focused offline run.

MFV-001 batch 2F: the detached route inventory now covers 71 of 72 legacy
private pairs. The only excluded pair is demo seed by design. Offline
functional route coverage is closed; real replica certification and
coordinated activation remain open under the same issue.

MFV-001 isolated R3 integration: final run passed nine real replica scenarios
and one destination guard. Initial refresh contention required a bounded
fresh-snapshot retry for known transient aborts in the integration adapter
to verify strict reuse revocation. Production wiring and topology-specific
failure modes remain pending. See R3_REPLICA_CERTIFICATION.md.

MFV-001 R3 delivery 3: standalone synthetic HTTP authentication and the
client session lifecycle passed automated checks. Updated legacy VM fixtures
to mock the new auth dependency while preserving their prior assertions.
Physical Android acceptance remains pending because ADB detected no device.
No production activation or new issue was recorded.

MFV-001 R3 onboarding correction: new QA identities had empty catalogs because
the authenticated client never invoked the existing static category initializer.
Session bootstrap now provisions only an empty owned catalog before exposing
the financial UI. Nonempty/custom catalogs are preserved. Focused client,
isolated category integration and Samsung income/expense picker checks passed.

MFV-001 Delivery 3 closure, 2026-11-05: owner-confirmed native sign-in,
A/B separation, persistent session and logout observations were added to
R3_DELIVERY_3.md. Focused signed-out private-link and navigation-gate checks
passed. Delivery 3 is complete for the local synthetic scope. The additional
external Expo cold-start link probe returned to the launcher, exposing no
private screen; release link handling remains unverified. Production
readiness remains open under the existing release gates.

R7 lot 1, 2026-11-05: production-only authenticated factory, strict configuration,
shared R3 MongoDB adapter, trusted HTTPS proxy boundary, TLS SMTP operator account
operations and shared authentication throttles implemented. Scoped R7-01 through
R7-08 findings, resolutions and remaining acceptance boundaries are recorded in
R7_DELIVERY_1.md; no general audit was repeated. Production deployment remains
unauthorized. Real replica failover, ambiguous driver commit, backup restore,
provider delivery, account-code client and external HTTPS acceptance remain open.
No existing database or running service was accessed or modified by this lot.

R7 lot 2, 2026-11-05: Android source/configuration preparation completed on the
required branch. Added production HTTPS/environment pinning, EAS AAB profiles,
root archive allowlist, native permission/backup/signing protections and localized
invitation/recovery code forms. Repaired the existing stale npm lock offline without
installing packages or changing any previously locked package version; aligned the
package-manager declaration with npm. Scoped checks and outstanding Play/privacy,
account-deletion, credentials, backend and signed-device acceptance gates are in
R7_DELIVERY_2.md. ADB detected no phone; no device PASS, build, database access,
deployment, upload, publication or next-lot activation is asserted.

R7 lot 3, 2026-11-05: prepared Lightsail/static-/32 + Atlas M10 + Resend + Cloudflare
beta infrastructure candidates and scoped Atlas authentication/network settings.
Default private mode remains intact; no broad public MongoDB allowlist was enabled.
Worst-month and annual-domain-payment estimates, provider comparisons, contracting
sequence and backup/restore/fault/monitoring gates are documented in
R7_BETA_INFRASTRUCTURE.md and R7_BETA_OPERATIONS.md. No resource, live infrastructure
PASS, database access, image build, purchase or deployment is implied. Monetary
figures are conditional estimates; an aggregate $120 hard cap is not provider-enforced.
