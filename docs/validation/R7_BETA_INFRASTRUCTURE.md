# PickWallet R7 lot 3 — closed-beta infrastructure

Price review: **2026-11-05**. Currency USD. Required branch:
`conflict_280926_1750`. Status: **PREPARATION ONLY — no resources created or deployed**.
This supersedes only the network/provider assumptions of the R7 lot 1 runbook;
financial, owner, session-fence and idempotency contracts remain unchanged.

## Recommended architecture and decision

Use one AWS Lightsail Linux **2 GB / $12 monthly IPv4 bundle**, a reserved attached
static IPv4, same-host Nginx TLS termination and the authenticated FastAPI container.
Use **Atlas Core M10, three voting data-bearing members**, in the matching AWS region;
Resend Free SMTP for controlled account email; Cloudflare Free DNS and a non-premium
at-cost domain. Owner must approve region, domain, providers and operating responsibility.
No price assumes promotional credits or a free production database.

```text
Samsung release -> HTTPS:443 -> Nginx on Lightsail -> 127.0.0.1:8000 authenticated API
                                          |
                         TLS:27017 -> Atlas M10 (three-member replica)
                         source restricted to the attached static IPv4 /32
                         TLS:465 -> Resend verified sender
Cloudflare: DNS-only API A record; no HTTP proxy or extra forwarded-header hop
```

This is **TLS over a restricted public Atlas endpoint**, not PrivateLink or a private
IP database. Atlas rejects sources outside the exclusive application /32, and the app
independently verifies certificates, exact Atlas host inventory, replica/environment
identity and least-privilege grants. No `0.0.0.0/0`, IPv6 `::/0`, developer home range or
shared Render region range is part of the recommended configuration. Runtime secrets
are separate from infrastructure operator credentials. The API never hosts MongoDB.

The tradeoff is explicit: Lightsail is not managed application hosting. Someone must
own OS/Docker/Nginx updates, certificate renewal and alerts; one API VM has no
availability-zone failover. A managed Atlas replica protects database availability,
not API uptime or regional disasters. If nobody will operate the VM, do not deploy
this recommendation; reassess the managed-hosting tradeoff rather than silently
leaving patches unattended. A single API instance is acceptable only for an approved
small beta downtime target, not a promise of high availability.

### Render and alternatives

| Option | Cost/fit | Security and operational assessment |
| --- | --- | --- |
| Lightsail + M10 + attached static IP | Proposed $106.52 ordinary month, $117.52 annual domain-payment month, including allowances | Exclusive /32 egress without NAT gateway/PrivateLink fees; narrow Atlas access; VM maintenance required |
| Render Hobby paid compute + M10 + shared regional outbound CIDRs | Can fit $120: 2 GB compute $25 + M10 worst-month starting base $59.52 = $84.52 before backup/domain/usage/tax | Technically supports TLS + IP allowlisting without any-IP access. CIDRs are shared by other Render tenants; not an exclusive workload identity. More managed operations, weaker network isolation than the selected /32. This is not the prepared configuration and would require an explicit policy change. |
| Render Pro + dedicated egress + M10 | At least $25 workspace + $100 IP set + compute + $59.52 Atlas; exceeds $120 | Strong dedicated egress but financially unsuitable |
| Render Pro + AWS PrivateLink + M10 | $25 workspace + $30 link + even $7 compute + $59.52 Atlas = $121.52, **before** backups/domain/AWS endpoint or transfer charges | Private connectivity, but no safe budget margin; 2 GB compute increases this further |
| Self-host MongoDB on the API VM | Cheap base bill, rejected | Shares a failure domain and turns database patching, replica quorum and backup correctness into owner responsibilities; one-node replica transactions do not provide production availability |

Render's shared range configuration must not be described as unrestricted internet
access: it can use a real allowlist and strong credentials. Conversely, shared CIDRs
must not be represented as exclusive static IPs. No shared-range exception was added
to the code. Render Free is unsuitable for this API's operational requirement:
free services block SMTP 465/587, and it is not the always-on paid service assumed here.
Atlas Free/Flex are not selected because M10 supports the managed failover rehearsal,
custom operational controls and dedicated-cluster backup features this release needs.

Sources: [Render pricing](https://render.com/pricing),
[dedicated IP pricing and eligibility](https://render.com/blog/dedicated-ips-for-your-services-on-render),
[shared outbound ranges](https://render.com/docs/outbound-ip-addresses),
[PrivateLink pricing](https://render.com/docs/private-link),
[free SMTP restriction](https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports),
[Atlas private endpoint tier limits](https://www.mongodb.com/docs/atlas/security-private-endpoint/).
Render's dynamic pricing page was cross-checked against its official docs/blog. The
$7 and $25 compute entries are provider list prices, not a quote for this application.

## Monthly estimate and purchasing gate

Worst recurring month uses **744 hours** for the advertised M10 starting rate. Its
website's $56.94 monthly starting illustration is not treated as a fixed $56.94 cap.
Actual regional quotes must replace the starting rate before purchase.

| Item | Monthly USD | Meaning |
| --- | ---: | --- |
| Lightsail Linux 2 GB, IPv4, 60 GB SSD | 12.00 | Listed bundle; 2 burstable vCPUs, not two dedicated sustained cores |
| Attached static IPv4 | 0.00 | Included while attached; unused addresses can incur charges |
| Atlas M10 starting base, $0.08 × 744h | 59.52 | Advertised minimum, region/provider/storage configuration can increase it |
| Atlas snapshots + PITR | 8.00 | **Allowance**, not an included/free or fixed-price backup product |
| VM incremental snapshots | 3.00 | Allowance; not a database backup |
| Domain | 1.00 | Amortized **$12 annual purchase/renewal ceiling**, actual TLD quote pending |
| Resend Free | 0.00 | Within 3,000/month and 100/day; verified domain, no automatic paid upgrade |
| Cloudflare DNS-only/free | 0.00 | No paid proxy/WAF/registrar add-on assumed |
| Data transfer and other metered usage | 5.00 | Allowance, primarily Atlas egress; co-region does not prove it is free |
| Temporary restore/fault drill cluster | 3.00 | Allowance; at starting rate ~37.5 extra M10 hours, delete only after evidence approval |
| Tax/currency allowance | 15.00 | Not a jurisdiction-specific tax quote |
| **Ordinary recurring month** | **106.52** | **$13.48 below $120**, with the above assumptions |
| **Domain purchase or renewal month** | **117.52** | Replaces $1 amortization with actual $12 upfront payment; **$2.48 remaining** |

A cost of $18/year for a selected domain would exceed the current first-month envelope.
Choose a suitable domain quoted at or below $12/year, use an already-owned approved
domain, or rebalance **before** authorizing purchases. Domain availability, TLD, tax
and renewal pricing were not guessed. A Resend Pro upgrade ($20/month), M10 regional
premium or a larger backup footprint requires a new approved budget, not auto-upgrade.

Pricing references: [Lightsail bundles/snapshot pricing](https://aws.amazon.com/lightsail/pricing/),
[attached static-IP charging](https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html),
[Atlas advertised base](https://www.mongodb.com/pricing),
[Atlas backup and transfer billing](https://www.mongodb.com/docs/atlas/billing/cluster-configuration-costs/),
[Resend limits and paid tier](https://resend.com/pricing),
[Cloudflare at-cost registration/DNS](https://www.cloudflare.com/domains/).

Extra charges to check: first/renewal annual domain cash payment, VAT/sales tax and
foreign-exchange fees, Atlas snapshot/oplog size and restore transfer, cross-region
traffic, endpoint or NAT fees if architecture changes, detached static IPs, VM snapshot
retention, extra disk, temporary second clusters, registry/build/storage overages,
paid monitoring/support, email overages and optional Google Play/EAS account/build
costs. No paid registry/CI/support plan is assumed. Google Play/EAS costs belong in the
overall release budget if the $120 includes them; they are not purchased here.

**A calculator or billing alert is not a hard provider spending cap.** These files do
not guarantee an invoice ceiling under arbitrary usage. Before purchasing, record
all actual checkout quotes, taxes and first-month cash totals; reject a combined
projection over $120. Require approval for scaling, new clusters or paid email plans.
Set provider alerts and a daily combined cost ledger, with intervention at $90/$105/
$115 total forecast; stop new invitations/load tests early. Never silently drop backups,
disable TLS or delete financial records to reduce cost. If $120 is an inviolable
technical cap regardless of traffic, this metered managed stack cannot certify it;
retain the no-deploy gate until a provider-enforced/capped commercial arrangement or
approved service-suspension policy exists. No automatic financial-service shutdown
or destructive budget action is prepared.

## Files and offline tools

- `backend/production_config.py`: new explicit `PW_MONGO_NETWORK_MODE=atlas_allowlisted`
  and dedicated `PW_MONGO_EGRESS_CIDRS`; old private mode remains default. Atlas mode
  requires three exact `.mongodb.net:27017` hosts and `authSource=admin`, TLS/SCRAM;
  public DNS is accepted only in that explicit mode. No certificate bypass, wildcard
  access-list mode or local database destination is added.
- `deploy/beta/backend.env.example`: placeholders only; filled secrets belong outside
  the checkout. The username's authentication DB `admin` does **not** confer admin
  authorization; grants remain restricted to `pickwallet_beta` and checked at startup.
- `deploy/beta/atlas-runtime-role.json`: Atlas custom role with only FIND/INSERT/UPDATE/
  REMOVE/LIST_INDEXES on that database, no inherited/admin/DDL roles. Create it through
  the Atlas control plane, restrict the runtime user to the one beta cluster, and
  inspect effective privileges with the runtime startup check. Never weaken that
  verifier if Atlas's observed privilege output differs; diagnose before deployment.
- `deploy/beta/Dockerfile`, `requirements.txt`, root `.dockerignore`: candidate Python
  3.12 image, nonroot authenticated factory only, minimal runtime dependencies and
  build context excluding legacy entrypoints, dotenv, tests and data directories.
  Pin the approved base image digest, resolve/hash transitive dependencies and scan
  the clean image before deployment; the image was **not built or certified** here.
  The dependency file selects existing declared/local versions, not a framework upgrade.
- `deploy/beta/compose.yaml` and `start.sh`: approved image digest required, read-only filesystem,
  capped logs/memory/PIDs, no capabilities, no-new-privileges, host networking solely
  to preserve same-host Nginx's actual loopback peer. Uvicorn binds **127.0.0.1**, never
  public 8000; no forwarded-header rewriting or access logs. TCP health is liveness,
  not proof of database readiness. No database container/volume is defined. The launcher
  requires an explicit authorized-host flag, host marker/external secret file and a
  SHA-256 image digest, and never pulls/builds an image implicitly.
- `deploy/beta/plan.json`, `prepare.py`: no secrets, sockets, cloud SDK or subprocess
  calls. Estimate, validate IP/budget/backup policy and render Nginx plus approved
  inventory into a new directory. Unfilled placeholders fail closed. Existing files
  are not overwritten. The renderer preserves the R7 TLS template, overwrites proxy
  headers from the socket peer and adds rejection of an unexpected public Host.

Offline commands (safe now; no cloud action):

```bash
python3 -B deploy/beta/prepare.py --estimate-only
python3 -B deploy/beta/prepare.py --plan /PROTECTED/approved-plan.json --output /NEW/output
python3 -B deploy/beta/prepare.py --plan /PROTECTED/approved-plan.json \
  --check-atlas-access-list /PROTECTED/atlas-actual-access-list.json
```

The last command validates a **fresh actual Atlas GET project accessList export**
against the exact planned /32; additional entries, any-IP and expired/temporary policy
entries are rejected. Its offline success proves only that supplied export matches;
an authorized operator must verify provenance/freshness and the effective network
behavior. Declaring an egress IP in environment variables does not configure Atlas's
control plane or prove a VM's actual outbound address.

Network and role references: [Atlas SCRAM authentication database and user scopes](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/),
[Atlas custom role API](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2/2025-02-19/operation/operation-creategroupcustomdbrolerole),
[Resend verified SMTP TLS settings](https://resend.com/docs/send-with-smtp).

## Exact contracting/configuration sequence — only after authorization

1. Owner approves provider accounts, region, domain, billing/tax address, technical
   operator/backup contact and the actual total quotes. Enable MFA/passkeys, recovery
   contacts and billing alerts on AWS/Atlas/Resend/Cloudflare. No root/API account
   credentials go into Git, chat, CLI history or screenshots. Use separate operator
   roles; runtime has no cloud API privileges.
2. In Lightsail choose the quoted $12 Linux IPv4 bundle and an approved maintained OS
   in the same region as the quoted Atlas M10. Allocate and **attach** a reserved
   static IPv4. Allow inbound **443 only**, plus SSH from the operator's exact /32;
   do not open 8000, MongoDB or Docker daemon ports. Do not publish an IPv6 AAAA record
   or enable an unreviewed alternate ingress/egress path. Verify the actual egress IP
   with an approved external observer before allowlisting it. Never run these steps
   against the development Nobara machine.
3. In Atlas create a **separate beta project**, AWS-region M10 three-member replica,
   dedicated database `pickwallet_beta`, no demo/sample financial data or development
   migration. Do not silently choose M0/Flex or add global access. Add only the VM's
   static /32. Export/validate actual accessList. Separate a narrowly scoped temporary
   admin/bootstrap identity from runtime; limit operator network access to explicit
   temporary /32 entries during provisioning, remove them, and revalidate before
   traffic. Final policy contains only the app's /32.
4. Create the custom runtime role/user in Atlas, scope user to that cluster. Set a
   high-entropy URL-encoded password, select SCRAM-SHA-256, capture provider-issued
   standard seed-list hosts and replica name (three members), set `authSource=admin`.
   Do not paste a default SRV string into the strict standard seed-list setting or
   append relaxed TLS/directConnection options. Atlas host replacement requires
   reviewed inventory updates; do not trust arbitrary discovery targets by widening
   this application inventory. Generate a fresh UUID4 for financial-context metadata.
5. With the bootstrap identity on the **new beta DB only**, pre-create all collections,
   apply `backend.production_services.index_plan()` and financial-context metadata
   described in R7_PRODUCTION_RUNBOOK. Use a protected driver configuration, never a
   password-bearing command line. Runtime startup is read-only readiness validation;
   it does not bootstrap collections/indexes or import `default-user`. Revoke bootstrap
   credentials/network entries afterward. Stop on privilege mismatch; no runtime DDL.
6. Enable Atlas Cloud Backup and continuous backup/PITR before any tester data. Propose
   daily snapshots retained 7 days and weekly retained 4 weeks, with a >=24h PITR
   window; confirm provider-supported configuration and actual quote. Proposed beta
   **RPO <=15 minutes, RTO <=4 hours** need owner approval and measured restore evidence.
   Bound compute/storage expansion to approved sizes; monitor disk early and pause
   new enrollment before capacity is exhausted. Never automate deleting data/backups
   or turn off recovery controls to stay under budget.
7. Purchase/attach the approved domain only if its actual annual charge fits the
   first-month/renewal envelope. Configure Cloudflare nameservers, DNSSEC and DNS-only
   API A record to the static IP. Do not enable Cloudflare HTTP proxy/Flexible TLS:
   it changes the verified proxy/client-IP contract. Obtain a publicly trusted Let's
   Encrypt certificate using a narrowly scoped Cloudflare DNS-01 token held outside
   source in a root-readable credentials file. Configure renewal and reload hooks;
   test renewal without logging DNS tokens/private keys. No port 80 is required by
   this DNS-01 design. Inspect the real Nginx config with `nginx -t` after certificates
   exist; install/reload only on the approved new VM.
8. Verify a sending subdomain in Resend, publish its actual SPF/DKIM records and a
   reviewed DMARC policy. Do not overwrite an existing domain's SPF with a second
   conflicting record. Disable tracking; choose a domain-scoped send-only key. Use
   `smtp.resend.com:465`, username `resend`, API key as password, verified From address.
   Define a monitored beta operator/support contact; Resend sending alone is not an
   inbound support mailbox. Provider email dashboards may retain message bodies,
   including short-lived codes: disclose this processor, restrict dashboard access
   and retention. No email was sent here.
9. Build the minimal image only after build authorization in isolated CI, use a
   reviewed base digest, dependency lock/SBOM and vulnerability scan, smoke/import and
   production tests; publish to an approved free/capped registry using an immutable
   image digest. No live secrets in build args/layers. Install maintained Docker,
   Compose and Nginx on the new host; operator controls patches and reboots. Filled
   `/etc/pickwallet/backend.env` is root-owned mode 0600 and outside the checkout.
   Docker access is privileged: restrict it. Inject secrets through a secret manager
   or protected file; Docker administrators can inspect environment variables.
10. Fill a protected copy of `plan.json`, recalculate both month types, render Nginx,
    configure `PW_RELEASE_IMAGE` to the approved digest, provision the non-secret
    `/etc/pickwallet/beta-host-approved` marker on that new VM only, and invoke
    `bash deploy/beta/start.sh --authorized-beta-host` on the new
    VM. The one container has host networking but only a loopback listener; trust
    exactly `127.0.0.1/32`. Nginx terminates real TLS, replaces forwarded headers with
    its observed peer/IP, rejects wrong Host, and never retries financial writes.
    Run the live acceptance matrix below with disposable synthetic accounts/data.
11. Keep enrollment closed until evidence is reviewed. Then provide Android EAS with
    the approved HTTPS origin and the **same** environment UUID. Candidate AAB/build
    and Google Play upload remain separate explicit authorizations. Privacy/deletion/
    Data Safety/signing and Samsung release gates from R7 lot 2 remain open.

No `terraform apply`, cloud CLI create, remote SSH, DNS mutation, resource purchase,
Docker build/pull/start, local database connection or deployment was executed here.
