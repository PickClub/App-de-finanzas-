# R7 lot 3 — infrastructure preparation delivery

Date: 2026-11-05. Branch verified: `conflict_280926_1750`.

**R7 LOT 3 COMPLETED for offline infrastructure preparation. NO deployment/contracting
approval is implied; real infrastructure acceptance remains NOT RUN.**

Recommendation: Lightsail $12 Linux/2GB + exclusive attached static IPv4, same-host
Nginx HTTPS/authenticated API, Atlas M10 three-member replica, Resend Free and
Cloudflare DNS-only/at-cost domain. Owner must accept VM patching/operations duty.
Atlas access is TLS over a public endpoint restricted to one /32, **not** PrivateLink.
Private-only R7 configuration remains the default; the new explicitly selected Atlas
mode accepts only three Atlas member names, dedicated global /32 egress declarations,
TLS/SCRAM and Atlas `authSource=admin`, preserving strict effective DB-scoped privileges.

Costs including planning allowances: **$106.52 ordinary month; $117.52 annual domain
purchase/renewal month**, conditional on the advertised Atlas starting rate, region
quote, domain <=$12/year and low beta usage. These are not guaranteed invoices or
provider spending caps. Quotes/taxes/metered usage must fit the $120 cap before any
purchase. Render shared regional allowlisting can fit but is less narrowly isolated;
exclusive Render IPs or PrivateLink do not fit the selected margin. Exact comparisons,
sources and quote date are in R7_BETA_INFRASTRUCTURE.md.

## Files changed/created by this lot

- `backend/production_config.py` — explicit Atlas network/auth-source configuration;
  existing private/local environment behavior preserved.
- `backend/tests/test_beta_infrastructure.py` — focused new offline tests.
- `.dockerignore` — restricted backend image build context, no dotenv/data/legacy API.
- `deploy/beta/Dockerfile`, `requirements.txt`, `compose.yaml`, `start.sh` — candidate minimal
  unprivileged backend image and local-only listener deployment; no build/run performed.
- `deploy/beta/backend.env.example` — placeholder-only protected-secret-file contract.
- `deploy/beta/atlas-runtime-role.json` — scoped Atlas custom role, no inherited grants.
- `deploy/beta/plan.json`, `prepare.py` — budget/cash-flow policy, offline renderer,
  validation of actual Atlas access-list exports against the approved /32.
- `docs/validation/R7_BETA_INFRASTRUCTURE.md` — provider comparison, cited costs,
  security model and exact approval-dependent contracting/configuration sequence.
- `docs/validation/R7_BETA_OPERATIONS.md` — monitoring, backup/restore, failover,
  ambiguous-driver-commit, email, HTTPS, recovery and evidence procedures.
- This report, a scoped ISSUES entry and an R7 production-runbook cross-reference.

Existing R3/R7 changes were inspected and preserved. No financial module, Android,
MongoDB 27018/27118, data, service, cloud account or resource was modified. No commit,
push, AAB/APK, purchase, email delivery or public deployment occurred.

## Verification and limits

Final result: **35 passed / 0 failed / 0 skipped** (16 new infrastructure checks +
19 existing production checks). Final focused suite: `backend.tests.test_beta_infrastructure` plus
`backend.tests.test_production_backend`. The former covers Atlas/default-private
configuration, TLS/auth-source/hostname/egress rejection, private/public DNS contracts,
worst-month/upfront cost math, over-budget rejection, closed Atlas access-list exports,
backup-required policy, Nginx rendering and image/runtime role constraints. Existing
production tests cover authenticated routing, seed exclusion, trusted proxy spoofing,
secret redaction, SMTP simulation, recovery/revocation and storage failure behavior.
All external DNS/client actions in the tests are mocked; no live DB target is enabled.

The old temporary R3 Argon2 test directory no longer existed. The already-cached
Argon2 project dependency was extracted into a fresh temporary import path, without
package installation or changes to system/virtualenv dependencies. Tests use:

```bash
PYTHONPATH="$(cat /tmp/pickwallet-r7-test-deps-path)" APP_ENV=test \
  python3 -B -m unittest backend.tests.test_beta_infrastructure \
  backend.tests.test_production_backend -q
python3 -B deploy/beta/prepare.py --estimate-only
```

Additional checks passed: Python compilation, Black, shell syntax, JSON and Compose
YAML parsing, budget CLI and `git diff --check`. Runtime Python import closure is
explicitly allowlisted in the Docker context; no legacy server dependency is included.

The candidate image is not built; Python 3.12, full transitive dependency lock/hash,
base-image digest, dependency scan, Nginx syntax with real certificates and Compose's
actual host network/listener must be verified after authorization. Offline text/
configuration tests do not certify those runtime properties. Legacy FastAPI/Python
coroutine deprecation warnings are not new test failures.

## Real blockers and required decisions

- Approval of providers, actual regional quotes/taxes/domain, $120 budget interpretation
  (including release account/build fees if intended), region and VM technical owner.
  Metered services do not provide an aggregate hard financial cap here.
- Provider accounts/MFA, static IP, domain, scoped secrets, replica and backups do not
  exist yet. Their absence is intentional; placeholder config cannot start deployment.
- Actual Atlas allowlist/role/transaction behavior, live TLS/proxy checks, certificate
  renewal, email delivery, backup restore/PITR and failover remain NOT RUN.
- The ambiguous-commit test requires an approved precise fault harness; no proof is
  inferred from an ordinary disconnect or the older HTTP-response-loss test.
- Prior release gates remain: privacy/account deletion/Data Safety, signing/EAS,
  candidate artifact/16KB inspection and Samsung release acceptance. None is repaired
  or started as part of infrastructure preparation.

Next authorized actions are the numbered steps in R7_BETA_INFRASTRUCTURE.md, followed
by the evidence matrix in R7_BETA_OPERATIONS.md. No subsequent lot starts automatically.
