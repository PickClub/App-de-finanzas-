# R7 lot 4A — account and data deletion

## Account flow

Profile shows **Delete account** for authenticated sessions. The EN/ES Montserrat
sheet describes permanent deletion, distinguishes backup expiry, and requires
the current password plus explicit confirmation.

`POST /api/auth/account/delete` accepts only a password and uses the verified
bearer principal. Production applies per-principal and existing per-IP limits.
The service rechecks the active session, identity and password version after
password verification. Validation and failure responses redact credentials.
`204` follows a confirmed MongoDB commit. A storage failure returns `503`.
If the connection drops or commit confirmation is lost, the app shows an
unconfirmed result. A repeat with a bearer removed by the first commit receives
`401`. A retry after a confirmed rollback requires a valid session and password.
There is no automatic destructive request replay or permanent deletion receipt.

The app clears its session, secure refresh key and query cache after `204`.
Payment and obligation journals are removed by the deleted account's exact
environment/owner namespace. Local writes and cleanup share a queue, and a
session-generation check rejects late writes. A scoped marker retries journal
cleanup on the next launch if its initial device write succeeded. The signed-out
screen distinguishes confirmed active-database deletion from a device cleanup
failure. A device crash before marker persistence, storage failure that prevents
marker creation, other offline devices, and unattributable legacy storage can
leave local remnants. The app cannot remotely wipe those devices.

## Ownership inventory

| Stored scope | Collections or data |
| --- | --- |
| Financial documents and associations, matched by `user_id` | accounts, transactions, categories, debts, debt_payments, bills, bill_payments, recurring_payments, recurring_payment_records, recurring_templates, budgets, saving_goals, goal_contributions |
| Other owned data, matched by `user_id` | notes, shared_obligations, shared_tracking_intents, movement_receipts |
| Profile and auth identity | users matched by `id`, auth_users matched by `_id` |
| Credentials | auth_sessions and auth_challenges matched by `user_id`, auth_refresh matched by family IDs taken from that user's sessions |
| Derived data | Calendar and summaries are computed from owned records. Their local query caches are invalidated. |
| Shared metadata and safety counters | moneyflow_metadata belongs to the environment. auth_rate_limits contains keyed digest buckets with TTL. These are outside the account-row cascade. |

The Mongo transaction uses snapshot reads and majority acknowledgement. Identity
and session-family writes contend with login, password changes and the financial
session fence. Challenge issuance also touches the current identity revision so
it cannot create an orphan from a stale snapshot. Other owners and `default-user`
are outside every deletion predicate. A fresh operator invitation for the same
email can create a distinct identity. Old credentials and tokens do not grant
access to that identity.

The single transaction keeps partial failure recoverable through rollback. An
account large enough to hit MongoDB transaction or resource limits requires a
reviewed operational resolution before retry. Provision the updated owner indexes
through the R7 DBA index plan before activating a production candidate. A live
Atlas runtime and realistic largest-account test remain release checks.

## Retention and restore policy

- Active database rows in the inventory are erased on commit. Pseudonymous
  abuse-control buckets contain an HMAC key, count and expiry. Keep them for
  abuse prevention until TTL cleanup. A deletion bucket expires after 30 minutes
  plus MongoDB TTL processing time. Other buckets follow their configured windows.
- Backups and PITR may hold prior versions of the account. Disclose the actual
  configured snapshot/PITR expiry before publication. The R7 proposal retains
  daily snapshots for seven days and weekly snapshots for four weeks, with the
  exact provider configuration and expiry evidence pending. A database `204`
  does not certify expiration of every backup or processor copy.
- A restored database must stay isolated. Before reconnecting it to clients,
  reconcile deletions made after its recovery point, repeat owned-data erasure
  for the affected IDs, and invalidate restored sessions and challenges. Require
  an independently durable, access-controlled deletion ledger or equivalent
  evidenced mechanism covering every retained recovery point before opening the
  beta. The ledger and restore reconciliation are pending. Until then, block
  cutover to backups containing erased accounts. Restrict retained deletion
  evidence to the minimum needed for restoration and expire it after relevant
  backups become unrecoverable.
- Review processor retention and deletion requests, including invitation/recovery
  email data. Document actual security or legal exceptions, their duration and
  access restrictions. Publish only periods and actions the operator can verify.

## Offline public page draft

**EN — Delete your PickWallet account and data.** You can request deletion here
without installing PickWallet. We verify that the account belongs to you before
processing your request. Deletion permanently removes the account and associated
data from our active service. Backup copies expire separately. The privacy policy
explains retention, verification and how to follow up.

**ES — Eliminar tu cuenta y datos de PickWallet.** Puedes solicitar la eliminación
aquí sin instalar PickWallet. Verificamos que la cuenta te pertenece antes de
procesar la solicitud. La eliminación borra permanentemente la cuenta y sus datos
asociados del servicio activo. Las copias de seguridad caducan por separado.
La política de privacidad explica la retención, la verificación y el seguimiento.

Place a visible request action beneath this copy on the approved HTTPS domain.
The future browser flow can use first-party reauthentication and the same deletion
endpoint, with an exact allowed origin and credentials kept in memory. Provide
an accessible recovery/contact path for people who cannot sign in. A support
request must verify control of the account without asking for a password over
email, avoid confirming whether an address is registered and distinguish request
receipt from completed deletion. Publish the processing time once established.
The page draft has no live request action. Implement and test that action and
recovery support, publish the working URL, link the privacy policy and complete
the Google Play Data safety deletion answers before submission.

[Google Play account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en)

## Verification

Six integration cases used freshly generated database names on a disposable
MongoDB 8.0.32 replica. They exercised actual transaction rollback, complete
inventory erasure, owner isolation, access/refresh/recovery rejection, retry,
a simulated lost success acknowledgement, and races with a financial write and
recovery issuance. The lost acknowledgement was injected at the service boundary.
It does not certify ambiguous commit behavior on Atlas.

The combined backend run passed 50 tests. Frontend checks exercised EN/ES Profile
and auth gate, HTTPS request shape, exact `204` confirmation, scoped cleanup,
stale writes, local cleanup failure and restart retry. Localization, Profile
motion and TypeScript checks cover the changed source. Native device behavior
and production restoration remain release checks.

## Files changed

- Backend — `backend/auth_core.py`, `backend/auth_mongodb.py`,
  `backend/production_api.py`, `backend/r3_local_api.py`,
  `backend/production_services.py`.
- App — `frontend/app/settings.tsx`, `frontend/src/auth-session.ts`,
  `frontend/src/private-journal.ts`, `frontend/src/components/auth-gate.tsx`,
  `frontend/src/i18n/locales/en.json`, `frontend/src/i18n/locales/es.json`.
- Tests — `backend/tests/test_account_deletion_isolated.py`,
  `frontend/scripts/test-auth-session.cjs`,
  `frontend/scripts/test-account-forms.cjs`,
  `frontend/scripts/test-profile-settings.cjs`.
- Documentation — this delivery record, including the public page draft.

The disposable replica ran on a dynamically assigned loopback port and was
removed after testing. Existing MongoDB instances on 27018 and 27118 were
outside the test targets.
