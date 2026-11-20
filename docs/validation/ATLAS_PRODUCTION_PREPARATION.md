# Pickwallet-prod Atlas connection preparation

Branch `conflict_280926_1750`. Inspected HEAD
`382edb64cc965c6db5ee419f3ff8fb5bbdea63ac`.

## Configuration

Motor 3.3.1 provides `AsyncIOMotorClient` for application operations. PyMongo
4.6.3 provides synchronous authentication transactions and startup validation.
Both versions are pinned in the backend and deployment requirements.

Development keeps `MONGO_URL` and `DB_NAME`, with the local development script
pointing to `development_local_finanzas` on port 27018. The isolated QA store
has its own fixed `r3_security_synthetic` target on port 27118. The legacy API
rejects production startup. The production entrypoint loads a separate
`PW_*` configuration from its process environment.

The production template in `deploy/production/mongo.env.example` selects
`APP_ENV=production`, `PW_MONGO_TARGET=Pickwallet-prod`, and Atlas allowlisted
networking. This profile pins the **proposed** database name `pickwallet_prod`.
Confirm that name before use. The existing beta profile remains separate.

Populate the exact three provider-issued member names and replica set ID from
the independently verified Atlas inventory for the correct project and cluster.
Use the standard seed-list connection format with explicit TLS, SCRAM-SHA-256,
and the Atlas SCRAM authentication database `admin`. The application database
is separate from the authentication database. The target validator requires the
URI database and members to match the explicit inventory and checks that seed
DNS addresses fit the network policy before opening a driver connection.
The display name `Pickwallet-prod` is a local profile label. It does not prove
the Atlas project's identity. At API startup the existing readiness gate also
checks the server-reported replica inventory, database environment UUID,
required indexes, and effective runtime grants.

Inject `PW_MONGO_URI` only into the future API process from an approved secret
store. Keep connection strings out of Git, frontend configuration, arguments,
logs and support transcripts. Keep the one-shot probe identity separate.
No values from local or QA configuration serve as a production fallback.

## Access requirements

- **Runtime identity.** Use a custom Atlas role scoped to the approved
  application database with `find`, `insert`, `update`, `remove`, and
  `listIndexes`, matching the existing startup gate. Scope the Atlas database
  user to the selected cluster. Use a separate authorized bootstrap identity
  for index and environment metadata provisioning.
- **Probe identity.** Use an expiring database user scoped to the same cluster
  with exactly `listIndexes` on `pickwallet_prod.moneyflow_metadata`. The
  probe checks effective privilege metadata and does not use the privilege to
  read documents or enumerate indexes. The probe and runtime identities use
  separate secret values.
- **Network.** Confirm the future server's fixed public IPv4 egress and place
  its exact `/32` in the Atlas project access list. The server needs DNS,
  outbound TLS to the three approved members on TCP 27017, and a CA trust
  store. The declared CIDR does not configure or verify the remote allowlist.
  This profile uses the restricted public endpoint. PrivateLink/SRV would
  require a separately reviewed configuration.

[Atlas database user configuration](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
· [Atlas network security](https://www.mongodb.com/docs/atlas/setup-cluster-security/)

## First authorized check

Confirm the project and cluster scope, the app database name, replica
inventory, environment UUID, server network access and effective probe role.
Set the environment from the protected configuration, inject only
`PW_ATLAS_PROBE_URI` into the probe process, and explicitly enable the one-shot
check with `PW_ATLAS_PROBE_ENABLED=1` and `python -m backend.atlas_probe --connect`.
Its disabled path exits before loading settings, resolving DNS or importing
the driver. The enabled path makes only `hello` and `connectionStatus` calls
and reports a sanitized stage on failure. It does not certify the environment
metadata or indexes. Those are separate runtime readiness requirements.
Never bypass a failed privilege or topology check by widening the probe role.

The probe is prepared and has not been run. Atlas authentication, live DNS,
allowlisting, and support for the returned effective privilege shape remain
unverified. Starting the production API is separate from the probe and needs
its own readiness and operational approval.
