# MoneyFlow development language and localization

- Use English for new code identifiers, comments, tests, technical documentation, and development messages.
- Default application locale is `en-US`. Spanish is `es`, with the `es-US` presentation policy. Never select a language from the device automatically.
- Use the centralized resources in `frontend/src/i18n/locales/` for every new system-generated UI label. Use descriptive English keys and interpolation/pluralization instead of concatenating translated fragments.
- Subscribe React components with `useTranslation()` from `@/src/i18n`. `tr()` is for display helpers that read the current locale; their owning component must subscribe. Avoid adding duplicate subscriptions.
- Language and currency are separate. Preserve existing monetary precision, rounding, storage, and currency rules.
- Never translate user-authored descriptions, account/category names, notes, or stored financial records automatically. Category display mapping requires verified system provenance; a matching name is not evidence.
- Preserve established API identifiers, database schemas, navigation routes, journals, and user data. Do not rename them for language consistency.
- Run `node frontend/scripts/check-i18n.cjs`, `node frontend/scripts/test-i18n.cjs`, TypeScript, and relevant regressions for localization changes. Report device and computed-label coverage limits honestly.
- Preserve uncommitted work and local experiments. Do not commit or push without explicit authorization.
