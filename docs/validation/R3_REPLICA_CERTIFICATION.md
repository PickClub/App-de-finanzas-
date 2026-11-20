# R3 isolated replica certification

Final run: 10 tests passed, including nine scenarios against MongoDB 8.0.32
and one offline destination guard. No failures or skips in the final run.

The only MongoDB destination was 127.0.0.1:27118, database
r3_security_synthetic, single primary r3_security_test_rs. The disposable
Podman container published only the authorized loopback port and used a
fresh temporary data directory. The runner rejected any URI differing from
the explicit allowlist before constructing a client, then verified the set,
single member and writable primary. The authenticated FastAPI app ran in
process through ASGITransport with the isolated database and auth store.
No legacy routes or network HTTP listener were started for this test.
The container was stopped after verification; its files were retained.

| Scenario | Verified on replica |
| --- | --- |
| A/B isolation | Foreign writes and note reads rejected; owner profiles, catalogs, history and totals; synthetic legacy row unchanged |
| Transfers and keys | Concurrent writes across distinct session families; one effect per owner/key; independent keys and ledger reconciliation |
| Response loss | Dropped ASGI response after the ledger commit; same-key replay returned the original ID and receipt |
| Rollback | Failure after both balance writes and receipt insertion rolled back all three effects and movement |
| Debt, bills and goals | Partial debt payment, cancellation and tombstone; concurrent linked bill settlement and one next period; recurrence did not charge twice; goal deposit and withdrawal reconciled |
| Sessions | Concurrent refresh emits one generation and reuse revokes it; expiry; recovery revokes target sessions; closed auth driver fails closed |
| Revocation race | Revocation before the fence blocks transfer and payment with zero financial effects; already fenced transfer commits once before revocation and subsequent requests fail |
| Resource races | Concurrent catalog initialization, account deletion versus reference creation and invitation consumption/profile provisioning preserve invariants |

The first refresh probe allowed a transient conflict to return a storage
error and used a separate replay to observe revocation. The final executor
retries only MongoDB-labeled transient transaction aborts with a fresh
snapshot, then verifies the losing refresh revokes the winner without a
third submission. Unknown commit results are never retried at the service
body boundary. The adapter and fence are integration-only code, not wired to
a deployed backend.

This run does not certify primary failover, a MongoDB commit result lost
between MongoDB and the driver, production adapter deployment, or Android.
The observed response-loss case occurs after MongoDB confirmed commit.
Production session orchestration must preserve the tested retry and fence
contract. No data or service at development port 27018 was used.
