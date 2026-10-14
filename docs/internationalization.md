# English-first internationalization

## Scope and baseline

The implementation started on `conflict_280926_1750`, at commit
`223004f3d30c26a49205a90e1ec28f13cf57004f` (`C3: complete paginated history and accurate home summary`).
The working tree already contained 39 modified tracked files and 61 untracked files. Their SHA-256 hashes were recorded before editing. Previous transaction, calendar, Bills, calculator, Home, and elastic-scroll changes must remain intact.

No database connection, financial operation, migration, seed execution, index, infrastructure change, package installation, commit, or push is part of this task.

## Architecture

The existing i18next/react-i18next implementation and bundled JSON dictionaries remain the foundation. One application instance is registered with `initReactI18next`. Locale identifiers are `en-US` and `es`. English is the default and fallback; the device language is never consulted.

Resources retain the existing domain organization (`common`, `home`, `accounts`, `transactions`, `debts`, `budgets`, `goals`, `calendar`, `bills`, `rp`, `reports`, `settings`, and other established domains). The new `ui` catalog centralizes previously inline labels. `notes`, `catalog`, validation/error domains, and pluralized keys are included. `en.json` is bound to the `en-US` locale; its filename remains compatible with existing repository references.

Use `useTranslation()` in components. `tr(key, options)` is a display-helper convenience using the current application instance. Module-level label definitions use getters so they do not freeze translations at import time. Their screen owns the reactive language subscription. No navigation keys are derived from translated labels.

New resources use descriptive English keys. Existing domain keys are preserved. Legacy persisted category names are compatibility aliases, not translation keys.

## Preference persistence

The established `app-language` key uses the existing storage wrapper. Explicit legacy `en` values normalize to `en-US`; `es` is preserved. Web startup accepts the earlier raw-string preference and the JSON-encoded representation. A missing or invalid preference selects English.

Hydration uses a revision guard so a late stored value cannot overwrite a fresh user selection. Writes are serialized; rapid choices end with the last selected language. A failed write rejects the choice, retains the current language, and shows the existing localized error dialog. Hydration does not rewrite saved preferences.

The Settings screen keeps its existing row and sheet. The English option is `English (United States)` and Spanish is `Español`. Switching changes language subscriptions without resetting navigation or form state. It does not modify the user record or its currency.

## Presentation policies

- English dates use `en-US`; Spanish dates use `es-US`, appropriate for a Spanish interface in the US market.
- Date-picker labels use Intl with the selected locale. Its existing Monday-first grid, date arithmetic, bounds, and selection rules remain unchanged.
- Currency keeps the existing USD conventions, comma grouping and whole-number rounding. Language changes do not convert currencies or rewrite amounts. The existing formatting rules, including negative signs, are unchanged.
- Confirmation, validation, empty/loading states, navigation labels, note tools, filters, report periods, and accessibility strings use resources.
- Display errors are localized separately from `ApiError` and financial guards. Known static public labels are matched to resource keys. Unknown messages use localized status/failure wording without exposing raw driver messages, credentials, response bodies, or user records. Unknown errors remain failures; no rollback or successful payment is inferred.
- Developer-only error-boundary details remain technical diagnostics.

## Data safeguards and limits

Stored account names, transaction descriptions, note bodies, category names, record IDs, references, enum values, API payload structures, and financial journals are not language identifiers and are not translated automatically.

New first-run sample notes use localized templates at creation, through the existing initialization path. Already stored notes are loaded verbatim and never relocalized. This task does not execute that initialization or rewrite notes. Historic sample notes and any user-written content may legitimately retain their original language.

The current category API has no reliable system-provenance marker. A name such as `Groceries` or `Alimentación` can also be user-created. Therefore category mapping is available only with an explicit verified-system indication; absent that evidence, the display preserves the stored name. This deliberately blocks blanket catalog relabeling. Full bilingual catalog coverage requires a separately reviewed provenance mechanism; no inference or migration is included here.

Unknown backend details receive safe localized wording. A future compatible server error-code catalog could make these messages more specific, but financial endpoints and error status contracts remain unchanged here.

## Validation

Run from the repository root:

```bash
node frontend/scripts/check-i18n.cjs
node frontend/scripts/test-i18n.cjs
```

Run TypeScript and lint from `frontend/`:

```bash
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint app src --no-cache
```

The static check verifies key parity, interpolation placeholders, literal translation-key references, JSX text, and display attributes. It does not prove computed labels, runtime responses, or device layout. Dynamic translation-key calls require explicit enum tests.

Localization tests use real i18next resources with simulated React/storage lifecycles. They cover English defaults, legacy/saved preferences, queued writes, hydration races, switching, fallback, missing keys, pluralization, dates, unchanged money formatting, custom content, HTTP errors, and actual Home rendering with cached mocked financial queries. Existing financial tests isolate presentation through shared fixtures while retaining payload, idempotency, journal, balance, and style assertions.

Do not equate these checks with 100% translation or Samsung verification. Review all tabs, internal screens, forms, sheets, errors, calendar/date controls, and both language choices in Expo Go. Check long strings at supported font scales. Document clipping rather than redesigning components.

Repository-wide lint also checks pre-existing React/Reanimated patterns. Report failures without disabling rules or expanding this language task into unrelated animation or financial refactors.

## Adding another language

1. Add a bundled dictionary matching every existing key and interpolation placeholder.
2. Add the locale to the `Lang` policy, supported list, normalization, resource registration, and Settings choices.
3. Define its date presentation policy without changing currency or financial date semantics.
4. Extend parity/default/persistence/fallback/switching tests and the static check.
5. Review translation fit on a device without changing typography or layout.

English remains the default development and fallback language. Never obtain translated strings by changing persisted financial identifiers or user-authored content.

## Results for this implementation

- Static resource check: 1,172 matching English/Spanish leaf keys across 79 frontend source files; no literal JSX text or display attributes found.
- Supported dynamic account, bill, budget, recurring, and calendar enum labels tested in both locales. The checker reports 42 dynamic call sites; this count is a review inventory, not a runtime completeness certificate.
- All 23 frontend test scripts passed, including payment/journal/idempotency/context guards, note persistence, direct transaction reading, description/date-filter handling, paginated history, Home totals and visual contracts, numeric animations, calendar gestures, and elastic scroll.
- TypeScript and `git diff --check` passed. Localization modules and catalog mapping lint without warnings or errors.
- Repository-wide lint remains failing: 132 errors and 44 warnings in React/Reanimated, hooks, unused imports, and related existing patterns. Rules were not suppressed and unrelated code was not refactored to silence them.
- Android/Expo Go device review remains pending. No claim of 100% translation or visual fit is made.
- No backend/database/financial journal/dependency/environment/experiment changes; no staging, commit, or push.
