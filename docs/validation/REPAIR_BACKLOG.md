# Pickwallet consolidated repair backlog — R1

**CURRENT — R2 COMPLETE: RPR-001–004 COMPLETE at their bounded offline acceptance level;22 other tasks PENDING. Full integration/device case closure remains with the named R6 dependencies. R3 has not started. The R1 planning baseline below is historical.**

## Baseline and authority

Source of truth: [MASTER_PLAN.md](MASTER_PLAN.md),[TEST_MATRIX.md](TEST_MATRIX.md),[ISSUES.md](ISSUES.md),[PROGRESS.md](PROGRESS.md),[RELEASE_READINESS.md](RELEASE_READINESS.md). The first diagnostic cycle remains22 PASS/12 FAIL/30 BLOCKED across64 cases; no validation stage is repeated or reclassified here. Candidate branch conflict_280926_1750,HEAD382edb64cc965c6db5ee419f3ff8fb5bbdea63ac plus existing saved local work. Previous issue evidence/IDs and resolved histories remain authoritative; no new MFV is created in R1.

This plan is not permission to implement,execute tests/write fixtures,change identity/data ownership,configure infrastructure,install/build/sign/publish or modify persistent settings. Each future phase needs explicit authorization for its narrow tasks and test/data boundary. Current public release remains NOT READY; iOS NOT VERIFIED. No live MongoDB/API/Android access is needed or performed for this planning task.

## Findings without double counting

| Classification | Existing IDs | Meaning / finite disposition |
|---|---|---|
| Confirmed application behavior defects | MFV-010,017,018,021,022,023,024 | Seven distinct defects,not seven corrupt ledgers. Same Pin defect affects two cases. |
| Financial correctness subset | MFV-010,017,018,024 | Four of those seven: handled-input validation,date/period filtering and due-date presentation. No confirmed lost money,wrong balance or duplicate charge; complete integration remains missing. |
| Authentication/multiuser blocker | MFV-001 P1 | Fixed identity is not authenticated tenant isolation; public release blocked. Detailed design is a dependency inside R3,not an R1 implementation or new phase. |
| Android UI/performance subset | MFV-021,023,022 P2 | Three of the seven: Notes action state,keyboard occlusion and measured frame pacing. MFV-007 remaining evidence is separate. |
| Confirmed testing-infrastructure defects | MFV-002 P1; MFV-008,011,014,015,016,019 P2 | Seven. Remote runner remains quarantined; fake/comparator failures are not product financial failures. |
| Static quality gate | MFV-003 P2 |151 errors/86warnings baseline,not151 confirmed runtime bugs; finite disposition,not automatic whole-app cleanup. |
| Provisional risk / missing evidence / optional hypothesis | MFV-004 P2 risk,MFV-007 P3 evidence,MFV-005 P3 optional | Reports cap consequence remains unverified; device evidence partial; no speculative optimization authorized. |
| Release/store requirements | MFV-006 P2; existing privacy/deployment/iOS gaps without invented IDs | Debug-signed LAN artifact is not production approval; actual privacy/store/platform evidence required. |
| Resolved historical infrastructure | MFV-009,012,013,020 | Keep history; no repair tasks,reopening or blanket retesting. Missing fixtures do not reopen restored-runtime020. |

Canonical counts are unchanged:24 MFV IDs,17 confirmed OPEN(P0 0/P1 2/P2 15/P3 0),3 provisional entries,4 resolved. Categories overlap only where stated as subsets; do not add them to inflate counts. All20 non-resolved registry entries map to tasks below; evidence-only tasks with no MFV do not invent app defects.

## Exactly eight repair phases

| Phase | Scope | Planned tasks / exit |
|---|---|---|
| R1 | Consolidated repair backlog | This document,traceability and finite dependencies only; COMPLETE. |
| R2 | Financial correctness and date handling | RPR-001–004; narrow offline-first corrections,remaining integration tracked explicitly. |
| R3 | Multiuser authentication and authorization | RPR-005; owner-approved design precedes implementation inside this phase. |
| R4 | Android functionality and UI defects | RPR-006–007; original native reproductions only. |
| R5 | Performance and reliability | RPR-008–009; fixed measurements,budgets and bounded attribution. |
| R6 | Complete blocked integration evidence | RPR-010–023; infrastructure corrections only as dependencies for the original missing evidence. |
| R7 | Store and production readiness | RPR-024–026; separately approved artifacts/privacy/platform evidence. |
| R8 | Targeted regression and final approval | No new repair task or ninth stage. Reassess only changed/affected original case IDs and release gates; owner decision required. |

Task numbers are tickets,not phases. No nested phases. Follow R2→R3→R4→R5→R6→R7→R8. Start dependencies differ from full-case closure dependencies: an offline R2 fix can begin before R6 supplies real integration; its full case stays unresolved until required evidence exists. Do not create a backwards phase dependency to justify starting R6 early. P1 public-risk priority does not authorize skipping the agreed phase order. An unavailable prerequisite is recorded once and the affected work stops; no automatic repair loop.

## Task index

| Repair ID | Proposed phase | Classification | Linked findings | Status |
|---|---|---|---|---|
| RPR-001 | R2 | Confirmed application / financial-input defect | MFV-010 | COMPLETE |
| RPR-002 | R2 | Confirmed application / financial-date defect | MFV-017 | COMPLETE |
| RPR-003 | R2 | Confirmed application / financial-filter defect | MFV-018 | COMPLETE |
| RPR-004 | R2 | Confirmed application / financial-date presentation defect | MFV-024 | COMPLETE |
| RPR-005 | R3 | Confirmed public-multiuser security blocker | MFV-001 | PENDING |
| RPR-006 | R4 | Confirmed Android application defect | MFV-021 | COMPLETE |
| RPR-007 | R4 | Confirmed Android UI defect | MFV-023 | COMPLETE |
| RPR-008 | R5 | Confirmed Android performance defect | MFV-022 | PENDING |
| RPR-009 | R5 | Missing Android performance evidence; optional hypotheses excluded | MFV-007, MFV-005 | PENDING |
| RPR-010 | R6 | Confirmed testing-infrastructure hazard | MFV-002 | PENDING |
| RPR-011 | R6 | Confirmed testing-infrastructure defect | MFV-008 | PENDING |
| RPR-012 | R6 | Confirmed testing-infrastructure defect | MFV-011 | PENDING |
| RPR-013 | R6 | Confirmed testing-infrastructure defect | MFV-014 | PENDING |
| RPR-014 | R6 | Confirmed testing-infrastructure defect | MFV-015 | PENDING |
| RPR-015 | R6 | Confirmed testing-infrastructure defect | MFV-016 | PENDING |
| RPR-016 | R6 | Confirmed testing-infrastructure defect | MFV-019 | PENDING |
| RPR-017 | R6 | Confirmed static-quality gate failure,not151 proven app bugs | MFV-003 | PENDING |
| RPR-018 | R6 | Missing isolation/fixture prerequisites,not a product defect | Existing evidence gap; no new MFV | PENDING |
| RPR-019 | R6 | Missing Android evidence plus dependencies on known repaired UI defects | MFV-007, MFV-019, MFV-021, MFV-023 | PENDING |
| RPR-020 | R6 | Missing real financial-module evidence; known date/fixture dependencies | MFV-015, MFV-016, MFV-017, MFV-018 | PENDING |
| RPR-021 | R6 | Missing Mongo/ownership/fault evidence,not confirmed financial loss | MFV-001, MFV-011, MFV-014 | PENDING |
| RPR-022 | R6 | Missing combined financial/native evidence | MFV-007 | PENDING |
| RPR-023 | R6 | Provisional Reports risk and missing scale evidence | MFV-004, MFV-005, MFV-007, MFV-008 | PENDING |
| RPR-024 | R7 | Confirmed release-signing/destination blocker and provenance gap | MFV-006, MFV-007 | PENDING |
| RPR-025 | R7 | Unverified release/store requirements plus security dependencies | MFV-001, MFV-006 | PENDING |
| RPR-026 | R7 | Unverified Apple platform/store requirement,not an iOS defect | Existing evidence gap; no new MFV | PENDING |

## Detailed finite tasks

Every task below is a proposal,not an executed repair. Required tests are future targeted reruns,not commands executed by R1. Existing matrix inputs/acceptance remain frozen. When a repaired EXPECTED DEFECT starts succeeding,convert only that repaired assertion into normal acceptance; do not drop it,relax it or silently accept unrelated expected failures. A passing unit/fake check never closes a case that still needs MongoDB/HTTP/native evidence.

### RPR-001 — Reject unsupported account types safely

- **Suggested phase / status:** R2 / COMPLETE.
- **Completion evidence:** [R2 focused verification](PROGRESS.md#r2-financial-corrections). Offline code acceptance passed; no claim of complete real-Mongo/native case acceptance.
- **Linked issues:** MFV-010.
- **Original case IDs:** MF-S2-01.
- **Classification / severity / impact:** Confirmed application / financial-input defect; P2. Unsupported type returns HTTP500; no-insert assertion was not reached. No balance corruption demonstrated.
- **Affected modules:** backend/server.py account model/create_account; existing account-route fixtures.
- **Narrow correction or evidence scope:** Correct only unsupported-type validation/error mapping; retain six supported types, valid openings, API identifiers and normal creation. No blanket exception suppression or balance-rule changes.
- **Dependencies:** Start: explicit R2 authorization and existing synthetic offline harness. Full isolated API closure requires RPR-018; this does not prevent starting the offline correction.
- **Acceptance criteria and stopping condition:** Unsupported types receive the documented handled validation4xx; rejected input inserts nothing, valid types/openings retain behavior. Stop after one narrow patch and targeted offline/ASGI checks; hand off any unavailable real-DB variant to RPR-018, never mark the full case PASS prematurely.
- **Tests to rerun:** Existing account adapter from cases.py and account validation regression within MF-S2-01 only; real account matrix once an approved target exists. No legacy remote runner.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s2-01-r2); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-002 — Preserve recurring local calendar day

- **Suggested phase / status:** R2 / COMPLETE.
- **Completion evidence:** [R2 focused verification](PROGRESS.md#r2-financial-corrections). Offline code acceptance passed; no claim of complete real-Mongo/native case acceptance.
- **Linked issues:** MFV-017.
- **Original case IDs:** MF-S4-02, MF-S4-08, MF-S8-02.
- **Classification / severity / impact:** Confirmed application / financial-date defect; P2. Recurring today is one local day ahead at the documented Chicago year boundary; monetary writes were not tested.
- **Affected modules:** frontend/app/recurring/[id].tsx todayIso; existing history-date-contract script.
- **Narrow correction or evidence scope:** Use the existing intended local calendar-day convention for today only. Preserve schedule rules, persisted dates and historical receipts.
- **Dependencies:** Explicit R2 authorization; no dependency on new DB infrastructure for the expression fix. Remaining real lifecycle evidence belongs to RPR-020.
- **Acceptance criteria and stopping condition:** At 2026-01-01T05:30Z in America/Chicago today is 2025-12-31; existing UTC/positive-offset controls remain valid. Stop at the corrected expression and its existing boundary assertions.
- **Tests to rerun:** test-history-date-contract.cjs affected recurring assertion; turn only the repaired expected-defect assertion into a normal acceptance check. Existing recurring lifecycle variants only when RPR-020 prerequisites are met.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s4-02); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-003 — Use calendar-day arithmetic for seven-day history

- **Suggested phase / status:** R2 / COMPLETE.
- **Completion evidence:** [R2 focused verification](PROGRESS.md#r2-financial-corrections). Offline code acceptance passed; no claim of complete real-Mongo/native case acceptance.
- **Linked issues:** MFV-018.
- **Original case IDs:** MF-S4-08, MF-S8-02.
- **Classification / severity / impact:** Confirmed application / financial-filter defect; P2. DST arithmetic includes an extra local calendar day in the seven-day range; no stored movement changed.
- **Affected modules:** frontend/app/transactions/all.tsx range helpers; date/history regressions.
- **Narrow correction or evidence scope:** Replace only fixed24h day subtraction where it violates the documented inclusive local seven-day range. Preserve timestamp values, ordering, filters and cursor contracts.
- **Dependencies:** Explicit R2 authorization; large real history evidence is RPR-020, not a prerequisite for offline correction.
- **Acceptance criteria and stopping condition:** The documented Chicago spring-DST fixture starts March3,not March2; inclusive end and clearing both bounds remain correct. Stop after targeted range/date-clear/paging guard checks; no unrelated calendar rewrite.
- **Tests to rerun:** test-history-date-contract.cjs affected DST assertion, test-transaction-history-page.cjs and test-transaction-description-date-clear.cjs affected contracts; full missing real traversal belongs to RPR-020.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s4-08); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-004 — Preserve all-day debt due dates in display

- **Suggested phase / status:** R2 / COMPLETE.
- **Completion evidence:** [R2 focused verification](PROGRESS.md#r2-financial-corrections). Offline code acceptance passed; no claim of complete real-Mongo/native case acceptance.
- **Linked issues:** MFV-024.
- **Original case IDs:** MF-S8-02.
- **Classification / severity / impact:** Confirmed application / financial-date presentation defect; P2. The all-day preservation assertion fails in Chicago; handset label and monetary impact remain unverified.
- **Affected modules:** frontend/src/format.ts formatDateLong; debt-detail due-date consumer; existing date/i18n fixtures.
- **Narrow correction or evidence scope:** Distinguish supported date-only calendar values from actual instants without rewriting records, changing all timestamp semantics or redesigning labels.
- **Dependencies:** Explicit R2 authorization; use the existing strict fixture and verify consumers before changing a shared helper.
- **Acceptance criteria and stopping condition:** 2026-01-01 remains January01,2026 in the existing Chicago fixture; real timestamp/UTC-instant behavior and EN/ES presentation remain intact. Stop at the narrow formatter/consumer correction and affected checks.
- **Tests to rerun:** test-history-date-contract.cjs affected formatter assertion, check-i18n.cjs, test-i18n.cjs and directly affected debt-date display checks; native confirmation remains evidence,not an assumed PASS.
- **Existing evidence:** [ISSUES.md](ISSUES.md#mfv-024--all-day-debt-due-date-formatter-does-not-preserve-calendar-date); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-005 — Establish authenticated identity and ownership

- **Suggested phase / status:** R3 / PENDING.
- **Linked issues:** MFV-001.
- **Original case IDs:** MF-S5-05, MF-S5-06, MF-S8-06.
- **Classification / severity / impact:** Confirmed public-multiuser security blocker; P1. Fixed default-user and destination headers do not authenticate a caller or isolate tenants; no real exploit was demonstrated.
- **Affected modules:** Backend identity/dependencies and resource queries; frontend session/API integration; financial-context contract.
- **Narrow correction or evidence scope:** Within R3 first obtain owner approval of an identity/session/ownership design and existing-user compatibility/data-preservation decisions; then implement only that approved boundary. No provider choice, account migration, new identity assignment or security feature is preauthorized by R1.
- **Dependencies:** Explicit R3 design/implementation authorization. Design approval is an internal dependency of this one task,not a new phase. Real two-user evidence requires RPR-018/RPR-021.
- **Acceptance criteria and stopping condition:** Anonymous/forged identity cannot authorize protected data; two synthetic principals cannot read or mutate each other’s resources; context pins remain destination checks. Stop if provider,credential,existing-data ownership or compatibility decisions lack approval. Keep legacy data unchanged; complete only the approved design and affected frozen security assertions.
- **Tests to rerun:** Existing financial-context/reference/reconciliation suites; exact synthetic user/foreign-reference/context variants in MF-S5-05/06 and scope review MF-S8-06. No real-user or remote probe.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s5-06); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-006 — Refresh Notes preview Pin action state

- **Suggested phase / status:** R4 / COMPLETE (bounded repair acceptance; broader original cases unchanged).
- **Linked issues:** MFV-021.
- **Original case IDs:** MF-S6-03, MF-S6-04.
- **Classification / severity / impact:** Confirmed Android application defect; P2. An open preview retains Fijar after a successful pin until reopened; persistence succeeds,content loss not shown.
- **Affected modules:** frontend/app/(tabs)/notes.tsx preview entity/togglePin; existing Notes regressions.
- **Narrow correction or evidence scope:** Synchronize only confirmed preview/list state while preserving failure recovery,local storage and existing content.
- **Dependencies:** Explicit R4 authorization and a known synthetic Notes context; no account/backend change. Remaining content/menu variants are RPR-019.
- **Acceptance criteria and stopping condition:** Pin/unpin label reflects the confirmed selected note immediately; rejected persistence does not falsely update state or affect a neighbor. Stop after the native reproduction and targeted Notes checks; do not redesign editor/cards.
- **Tests to rerun:** Existing Notes persistence/modal/menu regressions and the exact native pin→reopen-menu reproduction; complete previously missing variants only through RPR-019.
- **Existing evidence:** [ISSUES.md](ISSUES.md#mfv-021--notes-preview-retains-stale-pin-action-after-a-successful-pin); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

- **R4 verified evidence:** [PROGRESS.md](PROGRESS.md#r4-notes-and-name-keyboard-repairs). Source/regression and Samsung Expo Go checks completed for this repair; remaining original case variants stay with RPR-019.

### RPR-007 — Keep Profile Name editor visible above keyboard

- **Suggested phase / status:** R4 / COMPLETE (bounded repair acceptance; broader original cases unchanged).
- **Linked issues:** MFV-023.
- **Original case IDs:** MF-S7-08.
- **Classification / severity / impact:** Confirmed Android UI defect; P2. IME covers Name input and Save/Cancel; hiding keyboard is a workaround.
- **Affected modules:** Profile Name editor and directly used sheet keyboard/inset presentation.
- **Narrow correction or evidence scope:** Correct only keyboard avoidance/insets for the existing modal while retaining transition,style,name validation/save/cancel and other selectors.
- **Dependencies:** Explicit R4 authorization; authorized Samsung/synthetic profile. A newly changed shared sheet requires only its directly affected selector checks,not redesign.
- **Acceptance criteria and stopping condition:** Settled Name input and Save/Cancel remain visible/reachable with keyboard in EN/ES/default/enlarged font; typing,cancel and confirmed save preserve behavior. Stop after the reproduced overlap and direct shared-sheet regression checks; broader accessibility evidence is RPR-019.
- **Tests to rerun:** Existing test-profile-motion.cjs/test-profile-settings.cjs and native keyboard bounds/reproduction from MF-S7-08; no real name overwrite.
- **Existing evidence:** [ISSUES.md](ISSUES.md#mfv-023--profile-name-editor-and-save-are-covered-by-the-android-keyboard); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

- **R4 verified evidence:** [PROGRESS.md](PROGRESS.md#r4-notes-and-name-keyboard-repairs). Source/regression and Samsung Expo Go checks completed for this repair; remaining original case variants stay with RPR-019.

### RPR-008 — Correct measured calendar/elastic frame pacing

- **Suggested phase / status:** R5 / PENDING.
- **Linked issues:** MFV-022.
- **Original case IDs:** MF-S7-05.
- **Classification / severity / impact:** Confirmed Android performance defect; P2. Measured calendar5.84% and elastic22.80% normal/17.39% reduced missed HWUI deadlines exceed the fixed target; no ANR/FPS/leak claim.
- **Affected modules:** Recent Transactions calendar and measured elastic interaction; only an evidenced immediate dependency.
- **Narrow correction or evidence scope:** Correlate the existing fixed trace with actual rendering work,then make the smallest demonstrated bottleneck correction. MFV-005 hypotheses are not permission for a global list/animation rewrite.
- **Dependencies:** Explicit R5 authorization; same candidate-linked device,fixture,thermal/refresh/observer conditions; R4 changes affecting the measured path must be settled.
- **Acceptance criteria and stopping condition:** Same existing operation set meets <=5% jank and p95<=two actual-refresh intervals,final layout/input preserved,reduced motion honored. Stop after one bounded correction/measurement comparison; if attribution is not possible,record the exact blocker instead of speculative patches.
- **Tests to rerun:** MF-S7-05 exact calendar/Profile/theme/debt/elastic and reduced-motion variants; existing animation regressions for changed components. Do not rerun unrelated lifecycle suites or relax measured budgets.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#s7r2-20261019-230103); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

- **R5 measurement update (not repair completion):** Current reduced-calendar5.23% jank; root-cause attribution pending; no optimization authorized/applied. Status remains PENDING; [R5 measured evidence](PROGRESS.md#r5-performance-diagnosis-20261019).

- **Final focused R5 diagnosis:** Reduced calendar exceeds5% in2/3 repetitions;normal controls also2/3. Cause unproven;no optimization authorized. Status stays PENDING; [R5 final focused evidence](PROGRESS.md#r5-final-focused-investigation-20261020).

### RPR-009 — Complete startup and navigation timing evidence

- **Suggested phase / status:** R5 / PENDING.
- **Linked issues:** MFV-007, MFV-005.
- **Original case IDs:** MF-S7-01, MF-S7-02, MF-S7-03.
- **Classification / severity / impact:** Missing Android performance evidence; optional hypotheses excluded; Evidence gate; inherited P3 context,not a new defect. Screenshot timing bounds do not settle first-interactive/API-relative or500ms navigation acceptance.
- **Affected modules:** Existing startup/navigation capture method; Expo Go and installed candidate-linked release APK.
- **Narrow correction or evidence scope:** Improve only measurement attribution/resolution for the three original cases; separate Expo host/Metro overhead from standalone and input-to-settled timing. No app optimization without a confirmed failing metric.
- **Dependencies:** Explicit R5 measurement authorization; exact candidate/artifact and safe synthetic device/backend context. New build/install or backend interruption requires specific authorization; otherwise retain BLOCKED.
- **Acceptance criteria and stopping condition:** Five cold/warm samples at required scope and API-relative timing are accountable;20 cycles/five rapid menus/background variants have precise p95 or a stated blocker. Stop after one attempt per missing listed variant,not an expanding benchmark campaign.
- **Tests to rerun:** Only missing MF-S7-01/02/03 variants; preserve prior successful route evidence. Existing memory MF-S7-06 PASS is not rerun unless a relevant lifecycle change justifies it. Volume is RPR-023.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#s7r2-20261019-230103); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

- **R5 measurement update (not repair completion):** Five cold/five warm per current Expo/installed reference artifact and20 navigation cycles/five rapid menus captured; exact first-interactive/API-relative/source-to-release evidence remains blocked. Status remains PENDING; [R5 measured evidence](PROGRESS.md#r5-performance-diagnosis-20261019).

- **Final focused R5 diagnosis:** Native input-command/ADB overhead partially separated;visual-settlement/device-clock alignment still unavailable;no500ms PASS. Status stays PENDING; [R5 final focused evidence](PROGRESS.md#r5-final-focused-investigation-20261020).

### RPR-010 — Make the legacy runner fail closed

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-002.
- **Original case IDs:** MF-S1-03, MF-S1-04, MF-S8-03.
- **Classification / severity / impact:** Confirmed testing-infrastructure hazard; P1. Remote fallback plus mutating/seed requests makes unguarded discovery unsafe; not a shipped runtime exploit.
- **Affected modules:** backend/tests/test_moneyflow_api.py invocation/destination guards only.
- **Narrow correction or evidence scope:** Retain quarantine; add only reviewed explicit target authorization/fail-closed invocation controls if this runner must be used. No default remote execution,seed permission or broad discovery.
- **Dependencies:** Explicit R6 test-only authorization; no production changes. Target guards must be proven without financial writes before any allowed run.
- **Acceptance criteria and stopping condition:** Absent,remote,wrong or unapproved target is rejected before requests; explicit permitted commands/namespace are documented. Stop after guard negatives and exact reviewed invocation; leaving the runner quarantined is safer than bypassing guards.
- **Tests to rerun:** Existing environment-safety/target guard checks and MF-S1-03/04 safety gates; S8-03 only after RPR-018. Never execute its unsafe default to demonstrate the defect.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s1-03); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-011 — Repair summary visual-contract comparator

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-008.
- **Original case IDs:** MF-S4-06, MF-S8-02.
- **Classification / severity / impact:** Confirmed testing-infrastructure defect; P2. Asymmetric source/HEAD normalization aborts the visual comparison; no numeric summary failure established.
- **Affected modules:** frontend/scripts/test-summary-totals.cjs.
- **Narrow correction or evidence scope:** Compare intended equivalent source contracts consistently; retain all amount/inclusion assertions and meaningful visual invariants.
- **Dependencies:** Explicit R6 test-only authorization; frozen intended source contract. RPR-023 owns real Reports evidence.
- **Acceptance criteria and stopping condition:** Comparator reaches and preserves all intended numeric/visual checks without deleting assertions or changing production to fit the test. Stop after this script once; report any genuine newly reached failure without repairing it automatically.
- **Tests to rerun:** test-summary-totals.cjs; relevant MF-S8-02 batch subset. Full report case closure is RPR-023.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-02); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-012 — Complete payment-summary fake namespace

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-011.
- **Original case IDs:** MF-S3-05, MF-S8-03.
- **Classification / severity / impact:** Confirmed testing-infrastructure defect; P2. Cancellation-summary method ERRORs because Decimal is absent in the extracted namespace; no second refund demonstrated.
- **Affected modules:** backend/tests/test_payment_consistency.py summary extraction/test double only.
- **Narrow correction or evidence scope:** Supply the missing actual summary namespace dependency; do not modify production summary or fake accounting outcomes.
- **Dependencies:** Explicit R6 test-only authorization; preserve existing local edits. Full real cancellation evidence is RPR-021 after RPR-018.
- **Acceptance criteria and stopping condition:** test_retry_after_delete_does_not_resurrect_payment reaches its final summary assertions and passes with existing rollback/replay protections retained. Stop after this method and directly affected fake regressions once; no recursive fake expansion.
- **Tests to rerun:** Exact failing PaymentTests method plus directly affected payment-summary checks; full MF-S3-05 real variants through RPR-021.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-03); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-013 — Align missing-account adapter rejection contract

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-014.
- **Original case IDs:** MF-S3-04.
- **Classification / severity / impact:** Confirmed testing-infrastructure defect; P2. Adapter expects422 while established missing resource rejects404; no invalid payment was accepted.
- **Affected modules:** docs/validation/stage2-lab/stage3_cases.py invalid-account assertion only.
- **Narrow correction or evidence scope:** Accept the established documented missing-resource404 for that specific branch; retain rejection,no-write,settlement and post-settlement assertions.
- **Dependencies:** Explicit R6 adapter authorization; RPR-018 fresh approved fixtures,not old execution-claim replay. Real case completion is RPR-021.
- **Acceptance criteria and stopping condition:** Invalid reference remains rejected and exact no-write snapshot/full settlement assertions are reached. Stop after the affected case once; a newly reached financial mismatch is recorded,not accommodated by weaker assertions.
- **Tests to rerun:** MF-S3-04 existing adapter and payment validation fixture only under approved target; no production status change.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s3-04-r2); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-014 — Supply existing header mock in Bills/Accounts fixture

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-015.
- **Original case IDs:** MF-S4-01, MF-S8-02.
- **Classification / severity / impact:** Confirmed testing-infrastructure defect; P2. VM require lacks header-actions and aborts before Bills filters.
- **Affected modules:** frontend/scripts/test-four-ui-fixes.cjs fixture require/mock only.
- **Narrow correction or evidence scope:** Reuse the existing shared-header test contract; keep production Accounts/Bills unchanged and retain pagination/filter assertions.
- **Dependencies:** Explicit R6 test-only authorization. RPR-020 supplies real bill ledger/UI evidence.
- **Acceptance criteria and stopping condition:** Existing script reaches all intended bill paid-only counters and account pagination/total-balance assertions. Stop at its result; do not change real filters to satisfy a mock.
- **Tests to rerun:** test-four-ui-fixes.cjs once; missing full MF-S4-01 variants through RPR-020.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-02); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-015 — Repair category initialization comparator

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-016.
- **Original case IDs:** MF-S4-05, MF-S8-02.
- **Classification / severity / impact:** Confirmed testing-infrastructure defect; P2. Current normalized handler is compared with incompatible HEAD form; initialization evidence aborts.
- **Affected modules:** frontend/scripts/test-category-initialization.cjs comparator only.
- **Narrow correction or evidence scope:** Use a consistent intended preservation/source contract on both sides,retaining custom-content/default-init checks.
- **Dependencies:** Explicit R6 test-only authorization; no transaction-save or category production edit.
- **Acceptance criteria and stopping condition:** Existing initialization test reaches preservation/default/restore assertions without weakening user-authored name or reference protections. Stop after this script and directly linked category-save check once.
- **Tests to rerun:** test-category-initialization.cjs and test-category-save.cjs; full MF-S4-05 real evidence is RPR-020.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-02); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-016 — Traverse shared header in resource-state fixture

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-019.
- **Original case IDs:** MF-S6-08, MF-S8-02.
- **Classification / severity / impact:** Confirmed testing-infrastructure defect; P2. Opaque header mock makes find(debt-pay-back) null; actual native Back absence not established.
- **Affected modules:** frontend/scripts/test-payment-resource-states.cjs and its existing test helper.
- **Narrow correction or evidence scope:** Use the existing shared-header node traversal contract; preserve loading/retry/journal and entity-identity guards.
- **Dependencies:** Explicit R6 test-only authorization; RPR-019 owns native fault/error evidence.
- **Acceptance criteria and stopping condition:** Existing resource-state assertions reach Back/retry without null.props and retain all no-mutation safeguards. Stop after the script once; record any genuine failure without repairing production automatically.
- **Tests to rerun:** test-payment-resource-states.cjs and directly affected header mock check; no navigation changes.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-02); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-017 — Disposition the fixed static-quality baseline

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-003.
- **Original case IDs:** MF-S1-08, MF-S8-02.
- **Classification / severity / impact:** Confirmed static-quality gate failure,not151 proven app bugs; P2. ESLint151 errors/86 warnings remain; TypeScript passed.
- **Affected modules:** Only the recorded ESLint diagnostics/configured frontend static gate.
- **Narrow correction or evidence scope:** Create one finite per-diagnostic functional-risk disposition at the frozen candidate; any actual code correction needs its own bounded approved scope. No blanket autofix,rule suppression,unrelated refactor or warning cleanup.
- **Dependencies:** Explicit R6 triage authorization; R2–R5 changes complete enough to distinguish their actual delta.
- **Acceptance criteria and stopping condition:** Every existing diagnostic is linked to an approved correction or explicit owner-reviewed residual disposition; no false clean-lint claim. Stop after this fixed list/delta,not repeated broad audits. Required functional defects cannot be waived by relabeling.
- **Tests to rerun:** TypeScript and ESLint without fix/cache; only regressions directly affected by an explicitly approved correction. No full historical-stage replay.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-02); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-018 — Enable only the missing approved integration fixtures

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** None — previously documented evidence gap; not a confirmed defect.
- **Original case IDs:** MF-S1-04, MF-S1-05.
- **Classification / severity / impact:** Missing isolation/fixture prerequisites,not a product defect; Critical evidence gate; no invented MFV severity. Recovered lab is empty and financial dispatch disabled; old claims/fixtures cannot safely be replayed.
- **Affected modules:** Existing docs/validation/stage2-lab controller/fixtures/adapters and approved test transport configuration.
- **Narrow correction or evidence scope:** Reuse existing architecture. Prepare a bounded manifest for missing original cases with exact new owned namespaces/collections,method allowlist,independent ledgers,network/write audit and cleanup rules; obtain explicit approval before preparation/writes. Never remove recovery guards or overwrite old state merely to run tests.
- **Dependencies:** Explicit R6 laboratory-only adaptation authorization plus target/fixture/data-lifetime approval. A distinct synthetic Android context/candidate-linked test APK or transport may need separately approved build/install; no current permission is implied. MFV-020 remains RESOLVED,not reopened.
- **Acceptance criteria and stopping condition:** Before financial execution verify restricted role/remote and foreign-DB negatives,provenance and authorized write/cleanup scope. Stop if any boundary cannot be verified; do not create a replacement lab or fall back to development data. Manifest readiness is not financial PASS.
- **Tests to rerun:** Only existing MF-S1-04/05 guards/fixture gate and per-case prerequisites. Subsequent financial executions belong to RPR-020/021/022/023 or RPR-001 final integration.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-03); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-019 — Complete missing native functional variants

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-007, MFV-019, MFV-021, MFV-023.
- **Original case IDs:** MF-S2-02, MF-S3-08, MF-S6-01, MF-S6-03, MF-S6-04, MF-S6-07, MF-S6-08, MF-S7-08.
- **Classification / severity / impact:** Missing Android evidence plus dependencies on known repaired UI defects; High evidence gate; do not infer new app defects. Account cancel,no-history Back,debt filter partition,Notes limits/mixed content/menu overflow,locale capability/error states and TalkBack remain partial.
- **Affected modules:** Existing Android test context,listed screens and existing mocks/capture tools only.
- **Narrow correction or evidence scope:** Execute only unverified variants already listed in these cases; no new form/navigation/feature work. Keep exact origin,entity and saved-content oracles.
- **Dependencies:** RPR-006/007/016 as relevant; explicit R6 Android authorization and verified synthetic context from RPR-018 for state-changing/fault tests. Hardware/manual participation may be required; unavailable variants remain BLOCKED.
- **Acceptance criteria and stopping condition:** Each missing listed variant gets actual device evidence or precise BLOCKED result; content/prefs preserved outside owned fixtures. Stop after one bounded attempt per variant; no data clear/reinstall or recursive investigations.
- **Tests to rerun:** Only listed missing portions of MF-S2-02,S3-08,S6-01/03/04/07/08,S7-08; retain accepted existing samples and distinguish mocks from Android.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#s7r2-20261019-230103); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-020 — Complete remaining financial-module integration variants

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-015, MFV-016, MFV-017, MFV-018.
- **Original case IDs:** MF-S4-01, MF-S4-02, MF-S4-03, MF-S4-04, MF-S4-05, MF-S4-07, MF-S4-08.
- **Classification / severity / impact:** Missing real financial-module evidence; known date/fixture dependencies; Critical evidence gate,not presumed ledger corruption. Bills,recurrence,budget,goals,categories,calendar and paged history lack required full replica/UI/oracle agreement.
- **Affected modules:** Existing bill/shared,creation-idempotency,goal,reference,calendar/history adapters and native consumers.
- **Narrow correction or evidence scope:** Supply only limited missing case adapters within the reused approved target,then execute original remaining variants. No production fixes or extra lifecycle combinations. Reports is RPR-023.
- **Dependencies:** RPR-018; RPR-002/003/014/015 where relevant. Candidate identity and explicit financial-write authorization required.
- **Acceptance criteria and stopping condition:** Exact original fixtures/statuses/counts/ledger and required UI agree,or record FAIL/BLOCKED with preserved evidence. Stop once each listed original case is classified after its missing variants; never change expectations to make a mismatch pass.
- **Tests to rerun:** Original remaining MF-S4-01/02/03/04/05/07/08 inputs and their allowlisted suites only; previously accepted assertions repeat only if changed code requires them.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s4-01); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-021 — Complete real integrity and two-user financial evidence

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-001, MFV-011, MFV-014.
- **Original case IDs:** MF-S3-04, MF-S3-05, MF-S5-01, MF-S5-02, MF-S5-03, MF-S5-04, MF-S5-05, MF-S5-08.
- **Classification / severity / impact:** Missing Mongo/ownership/fault evidence,not confirmed financial loss; Critical evidence gate. Mocks do not prove rollback,orphan prevention,concurrent keyed operations,unknown commit,ownership or snapshot totals.
- **Affected modules:** Existing ordinary/debt/payment/reference/shared/read/idempotency financial suites and approved test-only transport.
- **Narrow correction or evidence scope:** Adapt only required existing method/fixture bindings to the approved isolated target; run exact documented concurrency/write-boundary/identity variants. No new race inventory,real data or normal-service fault injection.
- **Dependencies:** RPR-018/012/013; RPR-005 before two-user ownership assertions can close. Test-only fault controls must be separately approved and safe; no new lab architecture.
- **Acceptance criteria and stopping condition:** Independent ledgers/pre-post snapshots show atomicity,rejected no-write,exactly-once and enforced principals; all original listed variants must execute before PASS. Stop affected operation on integrity risk; continue independent safe cases and record blockers once.
- **Tests to rerun:** Listed remaining MF-S3-04/05 and MF-S5-01/02/03/04/05/08 variants with explicit methods/audit; no legacy discovery or Stage1–5 restart.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-03); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-022 — Complete combined ledger and restart recovery evidence

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-007.
- **Original case IDs:** MF-S7-07, MF-S8-03, MF-S8-04, MF-S8-05.
- **Classification / severity / impact:** Missing combined financial/native evidence; Critical evidence gate. No verified combined ledger/display plus pending keyed-payment restart/recovery result; read-only outage is insufficient.
- **Affected modules:** Existing isolated financial API,account/transaction/debt/bill/goal/report consumers and native journal/storage fixtures.
- **Narrow correction or evidence scope:** Use the one original S8 fixed scenario and documented allocation/independent worksheet; then only original read/503,lost-response and restart variants. No new scenario or financial repair.
- **Dependencies:** RPR-018/020/021/023 and relevant harness fixes; explicit synthetic writes/fault/restart approval and candidate-linked Android context. No interruption of usual services without separate authorization.
- **Acceptance criteria and stopping condition:** All expected amounts/cardinalities/displays agree,no double count; committed records,pending intention,Note/locale/theme survive as required; same key reconciles without duplicate effect. Stop after the listed cases are classified; missing unsafe transport remains BLOCKED.
- **Tests to rerun:** MF-S8-03 exact approved regression batch,MF-S8-04 fixed scenario,MF-S8-05 restart; remaining MF-S7-07 original variants. Do not rerun all64 cases.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-04); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-023 — Verify Reports completeness and fixed volume matrix

- **Suggested phase / status:** R6 / PENDING.
- **Linked issues:** MFV-004, MFV-005, MFV-007, MFV-008.
- **Original case IDs:** MF-S4-06, MF-S7-04.
- **Classification / severity / impact:** Provisional Reports risk and missing scale evidence; Critical correctness evidence; no demonstrated total mismatch. Legacy500-reader cap may truncate totals; Android fixed large datasets/input response remain unverified.
- **Affected modules:** Reports/summary/history readers and existing synthetic fixture/capture tools.
- **Narrow correction or evidence scope:** Only frozen501/2001 report reconciliation and S7 exact account/debt/Notes/transaction sizes; compare to independent ledgers/IDs. Do not implement a reader/list redesign for an unproven consequence.
- **Dependencies:** RPR-018/011 and candidate-linked Android context; authorize exact synthetic population/cleanup. Missing safe local Notes fixture path must be documented,never replaced with storage clearing.
- **Acceptance criteria and stopping condition:** Complete qualifying report totals and exact pages/IDs,plus original <=200ms input criterion or honest FAIL/BLOCKED. Stop at this finite matrix. If wrong totals are demonstrated,link MFV-004 evidence/severity under owner review; do not auto-fix.
- **Tests to rerun:** Remaining MF-S4-06 and MF-S7-04 only; no arbitrary larger load,stress sweep or inference from mocked10001-row loops.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-04); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-024 — Prepare production Android artifact and provenance

- **Suggested phase / status:** R7 / PENDING.
- **Linked issues:** MFV-006, MFV-007.
- **Original case IDs:** MF-S1-07, MF-S7-02, MF-S8-06.
- **Classification / severity / impact:** Confirmed release-signing/destination blocker and provenance gap; P2 release blocker. Existing APK is debug-signed and points to LAN; source-to-build mapping is not attested.
- **Affected modules:** Existing Android/Expo release configuration,signing and artifact metadata.
- **Narrow correction or evidence scope:** Owner approves production signing/storage/distribution/destination choices; isolate production settings from development. Never version/read out private key material or overwrite debug.keystore. No publication as part of correction.
- **Dependencies:** Explicit R7 signing/config/build/install authorization,approved secured destination from RPR-005/025; stable corrected candidate and required R6 evidence.
- **Acceptance criteria and stopping condition:** Production artifact has approved non-debug signer,destination and exact source/worktree/dependency identity; no secrets packaged; applicable standalone evidence on that exact artifact. Stop at verified artifact evidence; upload/distribution needs separate authorization.
- **Tests to rerun:** Existing MF-S1-07/S7-02 artifact-related checks and MF-S8-06; rerun only changed-artifact startup/security variants,not unrelated screens.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-06); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-025 — Complete privacy,handling and deployment requirements

- **Suggested phase / status:** R7 / PENDING.
- **Linked issues:** MFV-001, MFV-006.
- **Original case IDs:** MF-S5-07, MF-S8-06, MF-S8-08.
- **Classification / severity / impact:** Unverified release/store requirements plus security dependencies; Mandatory release evidence; no invented legal/security defect. Privacy,retention/deletion,backup,transport,secret/exposure and store declarations are not verified.
- **Affected modules:** Existing deployment/configuration,data flows,backup/retention/transport and store/privacy documentation.
- **Narrow correction or evidence scope:** Owner supplies intended deployment/data-handling decisions; review only original release inputs and implement specifically approved necessary configuration/policy work. No unrelated account/security features,external probes or compliance claims from source alone.
- **Dependencies:** RPR-005 and approved production scope; explicit permission for external/store access or persistent configuration changes if required. Coordinate RPR-024 without circular approval: agree destination/security plan before building,verify artifact after.
- **Acceptance criteria and stopping condition:** Document actual collection/storage/sharing/retention/backup/deletion and accurate policy/store declarations; verify approved secret/transport/exposure safeguards or leave NOT VERIFIED. Stop after this fixed release checklist; no blanket assertion of legal/store approval.
- **Tests to rerun:** Remaining MF-S5-07 and release portions MF-S8-06/08; local pattern scans are not exhaustive deployed assurance.
- **Existing evidence:** [PROGRESS.md](PROGRESS.md#ev-mf-s8-06); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

### RPR-026 — Obtain missing iOS platform evidence

- **Suggested phase / status:** R7 / PENDING.
- **Linked issues:** None — previously documented evidence gap; not a confirmed defect.
- **Original case IDs:** MF-S8-06, MF-S8-08.
- **Classification / severity / impact:** Unverified Apple platform/store requirement,not an iOS defect; Mandatory platform evidence; no new severity. No iOS build/device evidence exists; Android cannot establish App Store readiness.
- **Affected modules:** Existing Expo iOS target/configuration and future explicitly authorized build/device artifact.
- **Narrow correction or evidence scope:** Record approved iOS candidate/signing/destination and use available authorized build/device facilities for relevant existing platform acceptance. No new feature,rewritten UI or additional65th case.
- **Dependencies:** Explicit R7 Apple credentials/build/device authorization,available tooling/hardware,RPR-005/025 and approved release configuration. R1 authorizes none of these actions.
- **Acceptance criteria and stopping condition:** Actual iOS build/device/provenance and applicable store/privacy evidence supplied; otherwise remain NOT VERIFIED and block Apple approval. Stop after the fixed platform evidence request,not an iOS debugging campaign.
- **Tests to rerun:** Applicable original MF-S8-06/08 platform/release inputs; no invented iOS PASS from static app.json.
- **Existing evidence:** [RELEASE_READINESS.md](RELEASE_READINESS.md#final-first-cycle-release-decision--s8-20261019-182837-cdt); linked MFV entry in [ISSUES.md](ISSUES.md) and original definition in [TEST_MATRIX.md](TEST_MATRIX.md).

## All30 blocked cases have one primary task

This table assigns planning accountability only; it does not change a test result. Dependencies may support several cases,while each blocked case has exactly one primary ticket. All unverified variants remain the original matrix variants,not new tests.

| Original BLOCKED case | Existing feature | Primary task | Supporting constraint |
|---|---|---|---|
| MF-S1-04 | Isolated integration target gate | RPR-018 | See task dependencies; no prerequisite bypass. |
| MF-S1-05 | Synthetic fixtures and independent oracle readiness | RPR-018 | See task dependencies; no prerequisite bypass. |
| MF-S2-02 | Account edits and derived current balance | RPR-019 | See task dependencies; no prerequisite bypass. |
| MF-S3-04 | Full settlement and invalid payments | RPR-013 | Fixture repair alone does not close real integration; RPR-018 and RPR-021 required. |
| MF-S3-05 | Payment cancellation and repeated cancellation | RPR-012 | Fixture repair alone does not close real integration; RPR-018 and RPR-021 required. |
| MF-S3-08 | Debt deletion, history and outstanding filters | RPR-019 | See task dependencies; no prerequisite bypass. |
| MF-S4-01 | Bills status, partial/full payments and filters | RPR-020 | See task dependencies; no prerequisite bypass. |
| MF-S4-03 | Budget limits, periods and creation replay | RPR-020 | See task dependencies; no prerequisite bypass. |
| MF-S4-04 | Savings goals and contributions | RPR-020 | See task dependencies; no prerequisite bypass. |
| MF-S4-05 | Categories, hierarchy and safe deletion | RPR-020 | See task dependencies; no prerequisite bypass. |
| MF-S4-06 | Monthly summary and Reports agreement | RPR-023 | See task dependencies; no prerequisite bypass. |
| MF-S4-07 | Calendar dates, refresh and period boundaries | RPR-020 | See task dependencies; no prerequisite bypass. |
| MF-S5-01 | MongoDB transaction atomicity and rollback | RPR-021 | See task dependencies; no prerequisite bypass. |
| MF-S5-02 | Referenced-parent concurrency and orphan prevention | RPR-021 | See task dependencies; no prerequisite bypass. |
| MF-S5-03 | Keyed concurrent requests and bounded retry | RPR-021 | See task dependencies; no prerequisite bypass. |
| MF-S5-04 | Ambiguous commit and network interruption | RPR-021 | See task dependencies; no prerequisite bypass. |
| MF-S5-05 | Ownership and financial destination identity | RPR-021 | RPR-005 approved authenticated principals before ownership closure. |
| MF-S5-07 | Sensitive data and network exposure | RPR-025 | See task dependencies; no prerequisite bypass. |
| MF-S5-08 | Read consistency, totals and fail-closed limits | RPR-021 | See task dependencies; no prerequisite bypass. |
| MF-S6-01 | Existing routes and Notes Back history | RPR-019 | See task dependencies; no prerequisite bypass. |
| MF-S6-07 | English/Spanish and Profile preferences | RPR-019 | See task dependencies; no prerequisite bypass. |
| MF-S6-08 | Empty, loading, error and unsupported-capability states | RPR-019 | See task dependencies; no prerequisite bypass. |
| MF-S7-01 | Expo Go startup and data readiness | RPR-009 | See task dependencies; no prerequisite bypass. |
| MF-S7-02 | Standalone release artifact startup | RPR-009 | See task dependencies; no prerequisite bypass. |
| MF-S7-03 | Navigation reliability and rapid interaction | RPR-009 | See task dependencies; no prerequisite bypass. |
| MF-S7-04 | Long lists and chart responsiveness | RPR-023 | See task dependencies; no prerequisite bypass. |
| MF-S7-07 | Offline, backend outage and app restart recovery | RPR-022 | See task dependencies; no prerequisite bypass. |
| MF-S8-03 | Approved backend financial regression batch | RPR-022 | See task dependencies; no prerequisite bypass. |
| MF-S8-04 | Cross-module ledger-to-display reconciliation | RPR-022 | See task dependencies; no prerequisite bypass. |
| MF-S8-05 | Restart and data preservation regression | RPR-022 | See task dependencies; no prerequisite bypass. |

The12 FAIL cases retain their current results. Direct correction paths: MF-S1-08→RPR-017; MF-S2-01→001; MF-S4-02→002; MF-S4-08→003; MF-S5-06→005; MF-S6-03/04→006 (one shared defect); MF-S7-05→008; MF-S7-08→007 plus remaining019 evidence. MF-S8-02 is the roll-up of004/011/014/015/016/017 and affected changed frontend checks; MF-S8-06 is005/024/025/026; MF-S8-07 is the R8 owner/blocker-disposition gate. These roll-ups are not additional product defects or repair tickets.

## Execution and closure controls for R2–R8

1. Authorize only the selected phase/tasks. Freeze that candidate/worktree and the relevant original test IDs; preserve experiments,secrets,local edits and financial documents. No current test counts change because this plan exists.
2. Begin with the documented reproduction and smallest correction. Production changes must stay inside approved modules/behavior. R1 supplies direction,not permission or a claim of fully diagnosed implementation internals.
3. Run only the task's relevant existing regressions and missing original variants. If a new genuine defect appears,record it and request scope rather than recursively fixing. Do not repeat all prior stages or arbitrary broad discovery. A phase-specific finite attempt limit is agreed at execution; expiration ends work except safe cleanup/reporting.
4. Financial writes,fault injection,target preparation,Android storage/build/install,signing/external services require their explicit operational authorization and verified boundaries. Reuse existing laboratory architecture; never erase old claims/remove recovery guards,reset app data,seed personal databases or repoint usual services as a shortcut.
5. Task implementation and case validation are distinct. Record code result versus unavailable integration/device evidence. Change an MFV status only on actual acceptance evidence; preserve historical results. Never infer PASS from a mock or expected-defect script exit0.
6. R8 refreshes exact candidate/artifact identity and only affected existing regressions/evidence inventories. MF-S8-01/07/08 decision reviews may recur for the changed candidate; this is not a ninth validation stage.22/12/30 remains the original cycle record,with later outcomes appended rather than rewritten as if they had always passed.
7. READY requires resolved public P0/P1,documented owner acceptance of permitted residual P2/P3,and complete mandatory financial/native/platform/release evidence. Debug signing,missing tenant security,unverified privacy/iOS or a required BLOCKED case cannot be waived into public approval. Owner sign-off is never impersonated.

## R1 exit and exact next action

R1 COMPLETE when this finite26-task inventory covers all20 non-resolved MFV entries and all30 BLOCKED cases,each task has scope/dependencies/acceptance/stop/reruns/phase/PENDING,and the existing64-case definitions/results and protected work remain unchanged. Verification is document structure/traceability and Git/file preservation only; no runtime test or financial write.

**R2 ready to begin: YES, for the explicit offline-first RPR-001–004 scope after owner authorization.** Their unavailable full real-DB/lifecycle/native portions stay assigned to R6 tasks; this is not a declaration that all R2 acceptance evidence already exists. The next instruction should authorize R2 only,its four issues,synthetic targeted regressions and no data migration/production-data change. Do not start R2 from this plan. R1 ends here; wait for the owner.


## R2 execution disposition

Explicit owner authorization supersedes the historical R1 wait-for-R2 text above. RPR-001–004 are COMPLETE at their stated offline-first stopping criteria: account request422/no-write and valid types/balances in extracted-route ASGI memory tests; local recurring day; calendar-day seven-day range; date-only long formatting with unchanged instant/currency behavior. All four MFV code defects010/017/018/024 are resolved by focused evidence,not by a full original-case rerun. Current backlog4 COMPLETE/22 PENDING; no other repair task began or changed status. Missing real account/lifecycle/history/Reports/device evidence stays with RPR-018/020/021/022/023/019 as already assigned; no guard removed or task silently passed.

R2 changes four production files and two focused regression files only,plus the five requested validation documents. Existing edits/experiments/keystore retained. No real Mongo financial write,new fixture/lab,dependency,signing/authentication/navigation/layout/animation change,APK build,commit or push. R3 readiness YES for its owner-approved design dependency after explicit authorization,not permission to implement R3 now. See current evidence and limits in PROGRESS.md.

## Owner-authorized R4 execution and R3 deferral

Owner explicitly deferred R3 authentication/session/multiuser implementation until later development and authorized only RPR-006/007 now. This supersedes the earlier sequential-start restriction for these two independent R4 tasks; it does not resolve MFV-001 or authorize public release. R3_SECURITY_DESIGN.md remains unchanged; RPR-005 remains PENDING/deferred. R4 bounded repairs are COMPLETE with focused automated and actual Samsung Expo Go evidence linked below. No R5/R6 work is started. Original64-case historical results remain22 PASS/12 FAIL/30 BLOCKED. RPR-019 retains the broader missing native variants.

See [R4 execution evidence](PROGRESS.md#r4-notes-and-name-keyboard-repairs).
