# R6 stage 3 — read-only debt payment reconciliation

`POST /api/debt-payments/reconcile` accepts the existing `DebtPaymentCreate` body
and a required `Idempotency-Key` header. POST is used to supply the complete original
body, not to execute a payment. No balances, payments, accounts or movements are
inserted, updated or deleted. It never provisions metadata or loads demo data.

It derives the payment ID from effective server user and key exactly as creation
does, and compares SHA-256 of the same Pydantic-normalized `model_dump` and Python
JSON serialization retained by creation. Equal amounts or nearby dates are never
used to infer identity. Omitted/null fields normalize through the existing model.

Optional `MoneyFlow-Environment-ID` and `MoneyFlow-User-ID` have the same policy as
creation. One header fails with 422. Both are verified against metadata/configuration
and the effective user, before financial reads, inside the read-only snapshot.
A different context/user fails with 409. Unavailable context/consistent snapshot
returns `unverifiable`, not `not_found`. Headers do not authenticate a user.

Reads use the existing bounded transaction runner with snapshot read concern,
primary read preference and majority commit policy; no fallback to mixed reads.
Concurrent creation/deletion may be visible before or after its atomic commit,
but the query does not combine two different snapshots. These are read transactions,
not financial writes. No existing financial calculation/creation route is changed.

Response statuses:

- `matched`: stored original request fingerprint matches. The current live payment
  and linked movement have a verifiable relationship. This identifies the original
  intention; it does NOT assert that the payment has never been edited.
- `discrepancy`: the key identifies a different original normalized request.
- `cancelled`: a matching original request has an annulment tombstone and no linked
  movement remains. Never resurrect it or retry it as a new intention.
- `not_found`: no matching keyed record was visible in that snapshot. This does not
  prove that a concurrent or delayed creation will not subsequently commit, nor
  exclude older unkeyed payments. Never allocate another key to escape this state.
- `unverifiable`: missing/corrupt original fingerprint, inconsistent current links,
  invalid current data, failed connectivity or inability to complete the snapshot.
  Preserve the local original intention; do not treat this as successful payment.

`changed_fields` reports observable changes to debt, amount, account, notes and an
explicit original date. `current_payment` describes current values, not reconstructed
original values. Neither internal `_id` nor the stored request fingerprint is exposed.

When the submitted original date was null, its fingerprint proves that original
null request value. The original server-generated effective date is NOT separately
retained. `generated_date_history_verifiable=false` makes that limitation explicit;
`current_submission_matches=null` when other fields match. Do not infer absence of
later date edits from an empty changed_fields list. No stored document structure was
modified or historical dates guessed.

Every result states `retry_requires_original_key_and_payload=true`. That is a
constraint, not blanket permission to retry: cancelled/discrepant/unverifiable
results require appropriate resolution. A permissible retry after verification still
uses the original creation route, original key and exact original body. The query
itself never changes or clears any journal and never sends a creation request.

The frontend API helper and payment screen are integrated with the locally activated
v2 flow. Recovery never sends a payment automatically; explicit verification only
recovers and reconciles the original intention. A retry retains the original key
and payload. Original clients and payment endpoints keep working. No automatic v1
migration or cross-device recovery is implemented.

The agreed R6 functional validation is approved. Automated memory/HTTP tests cover
snapshot outcomes, original hash matching after payment edits, tombstones, response
loss and context failures. The reviewed backend suite passed 97 tests; frontend
tests, TypeScript and diff checks also passed. Twelve real MongoDB integration
scenarios passed in a temporary isolated database, including concurrent same-key
requests without duplicate payments or movements.

Physical Samsung checks completed: losing the server response, restarting Expo Go
and recovering confirmed the original fictitious $100 payment without a second
discount. A separate legitimate $150 payment resulted in exactly two payments and
two linked movements, a $750 account balance and $250 remaining debt from initial
values of $1000 and $500. "Verify register" recovered after a temporary consultation
failure without creating payments. A separate Samsung browser check of the actual
v2-to-v1 guard with in-memory records blocked pending/conflict cases with zero
payment requests and zero new keys; it did not alter Expo Go's stored operations.

v2 activation in Emergent is NOT performed. It requires independent explicit
configuration and verification of its own financial context; publishing these
changes does not activate it or copy any local identity. The temporary Samsung
database is retained pending explicit cleanup authorization. These completed tests
do not extend the scope to multiuser authentication, cross-device synchronization
or recovery after uninstalling the app.
