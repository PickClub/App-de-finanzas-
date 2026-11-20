# R3 delivery 2: detached authorization boundary

Status: incomplete for multiuser financial operations. The detached API is
available for offline composition only. It has no executable server entrypoint,
and the running development API does not mount it.

| Routes under /api | Disposition |
| --- | --- |
| GET /financial-context | Verified UUID and pinned environment; advertises no financial mutation capabilities |
| GET /accounts, /categories, /transactions, /transactions/{id}, /debts, /debts/{id} | Owner-scoped reads |
| GET/POST /notes, GET/PUT/DELETE /notes/{id} | Owner-scoped Notes; writes require an injected transaction fence |
| All other routes, including profile, histories, reports, totals, exports, seed, transfers and payment mutations | Fail closed; 401 without valid credentials, 404 with them |

The storage fence must match the principal's access digest against the current
family generation, check user status, expiration and revocation, and serialize
with rotation and revocation in the same MongoDB transaction as the mutation.
The context manager must only return after a confirmed commit and must roll
back if the mutation raises. A missing fence makes Notes writes unavailable.
The synthetic fence exercises denial and propagation, not MongoDB isolation.

Existing financial handlers and helpers still use fixed legacy ownership.
Mounting them behind bearer authentication would expose legacy data, so they
remain absent from the authenticated API. The legacy entrypoint explicitly
rejects production configuration. The local Android workflow is unchanged.
Neither entrypoint has been restarted or exposed by this delivery.

No cutover may occur until scoped financial writes, references, aggregates,
history, idempotency and session fencing are implemented and verified against
a real isolated replica, and the Android client can authenticate. No legacy
data claim, reassignment, or migration is included.

During offline verification the financial-context test double rejected the
existing Motor `session` argument. The double now accepts the same call
signature. The independent tests ran in the same batch.

## Financial ownership follow-up

The earlier route table describes the initial delivery. The detached API now
also enables POST /accounts, PUT/DELETE /accounts/{account_id},
POST /transactions for ordinary income, expense and transfer, and GET
/transactions/page. It shares the existing account balance computation, account
deletion guards, movement validation and history reader. The paginated reader
binds cursors to the authenticated UUID, environment and filters. Ordinary
movement creation rejects debt-linked movement types until their dedicated
operations are available.

The 72 legacy private method/path pairs now have 12 matches in the detached API
(including financial context) and 60 unmatched pairs. Five additional Notes
method/path pairs remain enabled. Legacy seed is deliberately excluded. Reports,
derived totals, profile, categories writes, ordinary movement edit/delete,
debt and loan writes, payment reconciliation and reversals, bills, recurring
payments, budgets, goals and export contracts remain blocked. No isolated
idempotent financial write was verified in this follow-up.

Before activation, finish owner propagation in these handlers and helpers, use
owner-scoped keys and receipts, and verify the matching-session transaction
fence in real MongoDB. In particular, test rotation or revocation against an
in-flight write, transfer rollback across both account updates, concurrent
reference creation versus deletion, and uncertain commit outcomes.

## Batch 2B: ordinary movements and receipts

The detached API adds PUT and DELETE /transactions/{tid} (14 of the 72
legacy private method/path pairs) and a new GET /transactions/{tid}/references
for owner-scoped accounts and categories. Linked obligation movements remain
under their dedicated, currently blocked operations. Ordinary edits retain
omitted fields and check the old and new references; edits and deletion
recompute all affected accounts using the shared balance function.

POST, PUT and DELETE accept an optional Idempotency-Key. The dedicated
movement_receipts collection uses a deterministic unique MongoDB _id derived
from owner and key. Each receipt stores the owner, operation/body fingerprint
and original response. A matching replay returns the receipt without touching
the movement or balances; mismatched operation, target or body returns 409.
Clients must reuse the same key on retries; unkeyed writes keep their existing
semantics. Receipts and effects commit together after the session fence. A
duplicate insert aborts the losing transaction and tells the caller to retry
with the same key against a fresh snapshot.

Replica acceptance remains pending: confirm the unique _id contract in the
deployment topology, same-key concurrent writes, rollback on receipt conflicts,
unknown commit results, and revocation/rotation versus financial writes. No
receipt index provisioning or deployment was performed. Receipt retention
must preserve the agreed retry window. The synthetic test double initially
lacked MongoDB's $ne filter behavior; the existing matcher now supplies it.

## Batch 2C: debts, loans and settlement

The detached API now matches 22 of the 72 legacy private method/path pairs.
New matches are POST /debts, PUT/DELETE /debts/{did}, GET
/debts/{did}/payments, POST /debt-payments, POST /debt-payments/reconcile,
DELETE /debt-payments/{pid}, and GET /summary. Existing PUT/DELETE
/transactions/{tid} also handle linked debt payments. The existing summary
contract supplies debt totals and the next payment without adding a calendar
route. Both entrypoints share debt calculations, linked payment operations
and summary math. The detached summary and reconciliation use the injected
fenced snapshot; they write no financial records.

Payment creation uses the existing owner-derived payment ID, original request
fingerprint and unique _id. Cancellation retains keyed tombstones, rejects
late recreation, and can also store a separate operation receipt via the 2B
mechanism. Payment editing preserves the original fingerprint. Financial
context headers are destination checks only and never authenticate a caller.

Initial offline regressions exposed a shadowed module alias and test seams
that still patched the old summary or debt recomputation location. The alias
and test seams were corrected while retaining the original assertions, fault
injection and fixed calendar clock. Track real replica evidence under MFV-001:
same-key concurrency, ambiguous commits, receipt and ledger rollback, and
revocation races. No database was provisioned or contacted.

## Batch 2D: bills and recurring payments

The detached API adds 23 legacy method/path pairs, bringing coverage to 45
of 72. It covers bills, summaries, bill payment history, recurring schedules,
occurrences, link candidates, lifecycle changes, payment records, reversals
and reconciliation. Configuration-only /recurring templates are a separate
module and remain blocked. The detached factory leaves R4 managed writes
disabled; managed records cannot fall back to the unmanaged payment path.

Bill and recurring calculations share the existing schedule, occurrence and
status helpers with the legacy API. Owner-scoped operations reuse the
reference coordination, account balance, shared read and reconciliation
services. Writes require the injected transaction fence. The detached
unmanaged path directs settlement of a linked period through its bill; a bill
cannot charge a period that already has an independent expense or a receipt
belonging to another bill. Both paths coordinate on the same recurrence
document before deciding. Partial bill payments keep one movement per payment
and use a linked recurring tracking record. Parent deletion preserves real
expenses; explicit eligible payment reversal restores the balance.

Creation and payment IDs and original request fingerprints retain the
existing owner-scoped namespaces. Payment reversal retains tombstones and
late keyed replays cannot recreate the movement. Real MongoDB verification
remains pending for simultaneous settlement from both routes, receipt
uniqueness, next-period generation races, ambiguous commits, reversals and
the session fence. No real data was accessed or changed.

The regression batch found unresolved owner names in three legacy model
defaults carried over from the 2C extraction. They were restored to the
legacy constant in the legacy server only. The synthetic store was also
corrected to implement the existing unset behavior on linked receipts.

## Batch 2E: budgets, savings goals and financial calendar

The detached API adds 17 existing method/path pairs, bringing coverage to
62 of 72. Budget list, detail and overview scope their category catalog,
expense rows and time windows to the owner. Goal reads and contribution
history use the same verified UUID as writes. Goal deposits and withdrawals
reuse the existing direction and account-balance rules. Deleting a goal
retires contributions and removes the goal links while retaining transfers
that already moved money. There is no legacy contribution reversal endpoint;
this batch introduces none. The existing withdrawal operation can move
money back to an owned account.

Calendar events, monthly totals and upcoming commitments share the legacy
projection and date rules. Real expense and debt-payment movements are
counted once, including bill expenses with recurring tracking records.
Budget, goal and contribution creates preserve their owner-scoped keyed IDs
and fingerprints. All mutations require the existing session fence.
Replica verification remains pending for concurrent keyed contributions,
both account updates, aggregate refresh and transaction rollback, budget
overlap races, revocation, and commit uncertainty. No MongoDB was used.

The remaining ten legacy pairs are profile (two), category mutations and
initialization (four), recurring templates (three), and the disabled demo
seed (one).

## Batch 2F: functional route coverage closure

The detached API covers 71 of the 72 legacy private pairs. The demo seed is
intentionally excluded; the anonymous boundary rejects it and an authenticated
request receives 404. See [route coverage](R3_ROUTE_COVERAGE.md) for the full
pair-by-pair inventory.

Profile reads use the verified UUID and project only existing public profile
fields. Writes accept name, currency and profile photo. A missing profile
returns 404 without provisioning; the eventual identity/profile provisioning
transaction must be verified separately. Profile writes never touch credentials.

Category initialization materializes the shared static catalog within the
verified owner's scope. It does not read or copy legacy private categories.
New catalog documents have deterministic owner/type/role/name IDs backed by
the built-in unique _id index. Repeat initialization is additive. Conflicting
concurrent attempts must abort and retry a fresh transaction. Category deletion
checks active references and hierarchy before deleting. Parent paths require
owned nodes and cannot introduce a cycle.

Recurring templates remain configuration-only. They verify the source
movement, account, destination and category against the owner, keep the
existing date contract and do not create an expense or a recurring payment
record. Optional Idempotency-Key uses the existing owner receipt service.

Replica certification is still pending for simultaneous catalog
initialization, category deletion versus reference creation, template receipt
races, profile provisioning, and session fencing. The detached API was not
activated. No MongoDB access, Android changes, or next delivery occurred.
