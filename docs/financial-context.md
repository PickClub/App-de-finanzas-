# Financial context — additive R6 stage 2

Nothing provisions on application startup. Financial context metadata was
explicitly provisioned and verified in the authorized local development environment;
the backend pin and local v2 payment flow are configured. Local payments verify the
expected environment and effective user before sending. Stage 3 provides the
read-only reconciliation API documented in
[debt-payment-reconciliation.md](debt-payment-reconciliation.md), integrated into
local recovery and verification.

The agreed R6 functional validation is approved, including isolated MongoDB
integration and physical Samsung checks. v2 is NOT activated in Emergent: publishing
the code does not provision or configure that environment. Activation requires its
own explicit provisioning, backend configuration, verified context and client
configuration. Legacy clients remain compatible without the new context headers.

## Context API and optional guard

`GET /api/financial-context` reads only `moneyflow_metadata/financial-context`.
It returns version 1, a canonical UUIDv4 `environment_id`, the server's effective
`user_id=default-user`, `mode=single_user` and available capabilities.
`debt_payment_reconciliation` is true with the Stage 3 route installed;
`cross_device_recovery` remains false.
This identity is not authentication. No new user/session system is introduced.

The server compares metadata against `MONEYFLOW_EXPECTED_ENVIRONMENT_ID`.
Absent/invalid metadata, an absent/invalid pin, a pin mismatch or an unavailable
database yields HTTP 503 on the context API, without creating metadata.

`POST /api/debt-payments` accepts optional `MoneyFlow-Environment-ID` and
`MoneyFlow-User-ID`. Neither header: unchanged legacy behavior, including on an
unprovisioned environment. One header: HTTP 422. Both: check the configured pin,
metadata and effective user inside the existing transaction before any financial
write or idempotent payment lookup. Mismatch: HTTP 409; unverifiable: HTTP 503.
The request body and success response remain unchanged. Headers do not select a
user or grant access. Old clients cannot claim protection against wrong-destination
routing because they do not supply this expected context.

## Explicit administration — requires separate human authorization

Do not execute the following against any persistent database until its exact
deployment/database has been authorized. No URI or UUID is hard-coded for local
Linux or Emergent. Do not copy a local UUID to Emergent.

1. Obtain the approved connection URI securely and assign it to
   `MONEYFLOW_PROVISION_MONGO_URL` in the administration process. This procedure
   does not load application .env files. Choose the approved database explicitly.
2. For an environment whose metadata is absent, run:

   ```bash
   python3 -B -m backend.provision_financial_context --mode create \
     --database APPROVED_DATABASE --confirm-database APPROVED_DATABASE
   ```

   This creates only one metadata document (`_id=financial-context`, version 1,
   environment_id UUIDv4, created_at UTC). The unique `_id` prevents competing
   creators from replacing it. Existing metadata is never overwritten; creation
   fails if already present. Creation requires write access only for metadata.
3. Store the emitted, non-secret UUID in that deployment's configuration as
   `MONEYFLOW_EXPECTED_ENVIRONMENT_ID`. Use the same pin for its replicas/aliases.
   Never place a MongoDB URI or credentials into frontend context responses.
4. Independently verify using the approved URI and explicit identity:

   ```bash
   python3 -B -m backend.provision_financial_context --mode verify \
     --database APPROVED_DATABASE --confirm-database APPROVED_DATABASE \
     --expected-id APPROVED_ENVIRONMENT_UUID
   ```

   Verification reads metadata only. It does not generate or repair identities.
5. Deploy the additive backend, verify the context response, then authorize client
   activation separately. Missing metadata never blocks the existing unguarded
   payment route; it blocks only the new context API/guarded requests.

## Lifecycle rules

- Restart/redeploy against the same complete financial dataset: retain metadata
  and pin; no new UUID is generated.
- Changed IP, proxy or URL alias serving the same dataset: retain identity/pin.
- Independent installations of Emergent: provision independently. Multiple
  backend replicas pointing to the same dataset must share identity/pin.
- Independent active clones/forks: omit financial-context metadata during the
  controlled clone procedure, then explicitly provision a new identity on the
  clone before activation. Do not replace the original environment's metadata.
  Never copy the original pin to a fork.
- Restore that rolls history back or loses idempotency records: quiesce traffic
  and treat it as a new context unless continuity has been explicitly verified.
  Do not let pending payments silently rebind to a restored dataset. Restoration
  and identity rotation require their own authorization; this script intentionally
  does not delete or rotate existing metadata.
- Copying both metadata and the pin to a divergent clone cannot be detected
  automatically. Identity is an operational invariant, not a clone detector.
  Metadata must remain immutable while requests are being served.

## v2 journal

v2 stores environment_id/user_id, the original key/payload and state/receipt.
Storage locations do not depend on URL. The context comes from a supplied verified
context reader; the library does not fabricate users, generate keys or send payments.
A pending journal belonging to another context blocks reassignment. Confirmed
journals can coexist between independent contexts. Clearing requires an explicitly
selected confirmed key. Store/network/corruption failures are not interpreted as
an empty journal. Same-runtime mutations are serialized across journal instances.

Any v1 record blocks v2 adoption conservatively, including confirmed legacy
records, because its original environment cannot be established from its URL alone.
It is neither migrated nor removed. A later authorized reconciliation stage must
resolve its provenance; "not found" will not by itself authorize a new key.

Validation includes 97 passing isolated backend tests, frontend in-memory tests and
12 passing integration scenarios with real MongoDB in an isolated temporary database.
On Samsung, recovery after a lost response and restarting Expo Go confirmed the
original payment without duplication; a second legitimate payment produced correct
balances and linked movements. The corrected "Verify register" action recovered
after a temporary consultation failure without creating a payment. The v2-to-v1
guard was also checked in the Samsung browser using the actual code with synthetic
in-memory pending/conflict records: zero payment requests and zero new keys, without
changing Expo Go storage or disabling its active v2 flow.

Only authorized local environments were provisioned. Emergent has not been
provisioned or activated by this work. The temporary Samsung database remains
separate and requires explicit authorization for cleanup.
