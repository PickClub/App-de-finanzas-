# R3 delivery 1: authentication core

The isolated service implements Argon2id identity, operator invitation and
recovery, and opaque access/refresh sessions. Nothing imports it from the live
application. The operator authorizer and challenge delivery port are trusted
server-side dependencies. A future caller must derive operator authority from an
authenticated operator or an approved local command, never from request fields.

Run the offline suite with the backend dependencies available:

    python -B -m unittest -v backend.tests.test_auth_core

## Persistence and integration contract

The store must return only after a confirmed commit. Translate driver failures to
a generic StorageUnavailable without including credentials or driver payloads.
Never replay a service call whose commit result is unknown. A MongoDB adapter
must resolve ambiguous commits at the transaction level and retry write conflicts
with fresh state under a bounded policy. The in-memory double serializes all
transactions and does not model MongoDB snapshot isolation or commit uncertainty.

- Serialize account creation by normalized email with a unique index. Store
  credential identities separately from legacy profiles. At integration,
  provision the new UUID profile atomically with invitation acceptance.
- Serialize session creation, bulk revocation and password changes on an
  identity fence. Snapshot session counts alone cannot enforce the ten-family
  cap or prevent a new family slipping past a concurrent revoke-all. Index
  current access digests and refresh digests uniquely, and enforce uniqueness
  of family/generation on refresh records.
- Serialize rotation, replay revocation and logout on the same family document.
  Consume the old digest and save the next generation and new access digest in
  one transaction. Retain consumed digests through absolute family expiry.
  Commit a reuse revocation before returning an invalid-credentials error.
- Consume a challenge, compare credential version, change the password, and
  revoke families in one transaction. Credential version also invalidates other
  outstanding challenges once one succeeds. Check deadlines in code even when
  TTL cleanup is configured.
- Store challenges before calling delivery. If delivery fails or is ambiguous,
  the committed challenge remains bounded by its expiry and credential version.
  An operator can issue another challenge; the first successful consumption
  invalidates siblings. The adapter must redact payloads, links and tokens from
  logs and errors. There is no mail sender in this delivery.
- Before exposing routes, add shared throttling, operator authorization wiring,
  safe audit events, HTTPS delivery, and an async worker boundary for synchronous
  password work. Reuse a service instance per process for the hash concurrency
  bound. Implement the financial transaction authorization fence when protecting
  financial routes; the core principal is not itself a financial write permit.

MongoDB transaction behavior, collection/index provisioning, profile linkage,
HTTP error mapping, secure mail delivery and Android behavior are pending
integration. No real credentials, financial data, or live database are needed by
the offline suite.
