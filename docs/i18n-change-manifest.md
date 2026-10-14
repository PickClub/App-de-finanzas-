# Internationalization change manifest

Initial branch: `conflict_280926_1750`. Initial HEAD: `223004f3d30c26a49205a90e1ec28f13cf57004f`.

This manifest lists changes made during the localization task, separately from pre-existing work.

## Created files

- `AGENTS.md`
- `docs/internationalization.md`
- `frontend/scripts/check-i18n.cjs`
- `frontend/scripts/i18n-test-support.cjs`
- `frontend/scripts/test-i18n.cjs`
- `frontend/src/i18n/errors.ts`

- `docs/i18n-change-manifest.md` (this file)

## Modified files

- `frontend/scripts/test-calendar-month-swipe.cjs`
- `frontend/scripts/test-home-calculator-visuals.cjs`
- `frontend/scripts/test-native-overscroll.cjs`
- `frontend/scripts/test-transaction-description-date-clear.cjs`
- `frontend/app/(tabs)/_layout.tsx`
- `frontend/app/(tabs)/index.tsx`
- `frontend/app/(tabs)/notes.tsx`
- `frontend/app/(tabs)/reports.tsx`
- `frontend/app/(tabs)/transactions.tsx`
- `frontend/app/accounts/[id].tsx`
- `frontend/app/accounts/new.tsx`
- `frontend/app/bills/[id].tsx`
- `frontend/app/bills/index.tsx`
- `frontend/app/bills/new.tsx`
- `frontend/app/bills/pay.tsx`
- `frontend/app/budgets/[id].tsx`
- `frontend/app/budgets/index.tsx`
- `frontend/app/budgets/new.tsx`
- `frontend/app/calendar/index.tsx`
- `frontend/app/categories/index.tsx`
- `frontend/app/categories/new.tsx`
- `frontend/app/debts/[id]/index.tsx`
- `frontend/app/debts/[id]/pay.tsx`
- `frontend/app/debts/index.tsx`
- `frontend/app/debts/new.tsx`
- `frontend/app/goals/contribute.tsx`
- `frontend/app/goals/new.tsx`
- `frontend/app/recurring/[id].tsx`
- `frontend/app/recurring/index.tsx`
- `frontend/app/recurring/new.tsx`
- `frontend/app/recurring/pay.tsx`
- `frontend/app/settings.tsx`
- `frontend/app/transactions/[id].tsx`
- `frontend/app/transactions/all.tsx`
- `frontend/app/transactions/new.tsx`
- `frontend/scripts/test-account-transactions.cjs`
- `frontend/scripts/test-calendar-bill-refresh.cjs`
- `frontend/scripts/test-category-initialization.cjs`
- `frontend/scripts/test-category-save.cjs`
- `frontend/scripts/test-debt-payment-idempotency.cjs`
- `frontend/scripts/test-deletion-lifecycle.cjs`
- `frontend/scripts/test-note-persistence.cjs`
- `frontend/scripts/test-obligation-payment-journal.cjs`
- `frontend/scripts/test-payment-flow-v2.cjs`
- `frontend/scripts/test-payment-journal-v2.cjs`
- `frontend/scripts/test-payment-resource-states.cjs`
- `frontend/scripts/test-r6-final-safety.cjs`
- `frontend/scripts/test-summary-totals.cjs`
- `frontend/scripts/test-transaction-direct-read.cjs`
- `frontend/scripts/test-transaction-history-page.cjs`
- `frontend/src/bills/shared.ts`
- `frontend/src/category-labels.ts`
- `frontend/src/components/date-range-sheet.tsx`
- `frontend/src/components/error-boundary.tsx`
- `frontend/src/debt-payments/view.ts`
- `frontend/src/format.ts`
- `frontend/src/i18n/index.tsx`
- `frontend/src/i18n/locales/en.json`
- `frontend/src/i18n/locales/es.json`
- `frontend/src/recurring/shared.tsx`
- `frontend/src/screens/TransactionsScreen.tsx`
- `frontend/src/use-resource-deletion.ts`

## Preservation

All other pre-existing file hashes match the task-start inventory. Backend, API contracts, financial journals, experiments/lab files, dependency manifests, lockfiles, and environment files were not changed by this task. No database access, commit, staging, or push was performed.
