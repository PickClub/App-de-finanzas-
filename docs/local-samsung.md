# Samsung with local DEVELOPMENT services

After authorizing service startup, run these commands from the repository root,
each server in its own terminal:

```bash
bash scripts/dev-mongodb.sh start
bash scripts/dev-backend.sh
bash scripts/dev-app.sh
```

The backend uses APP_ENV=development, database development_local_finanzas,
127.0.0.1:27018, replica set app_finanzas_dev_rs and directConnection=true.
Only FastAPI (8001) and Expo (8081) are exposed to the LAN. MongoDB remains
loopback-only. The local backend/.env uses the same destination and explicitly
sets MONEYFLOW_LOCAL_MODE=1. Process variables take priority, but local mode
rejects any other host, port, database, replica set or connection options before
constructing a MongoDB client. Port 27017 on the PC is never used by this mode.
The script forces local mode and rejects conflicting external APP_ENV,
MONGO_URL or DB_NAME values instead of silently replacing them.

MONEYFLOW_LOCAL_MODE is an opt-in local safeguard. Do not enable it in Emergent
or production; without it, their existing configuration behavior is unchanged.
The local .env is ignored by Git and must not be copied to those environments.
No command loads demo data or runs seed. MongoDB startup may initialize the
development replica set; backend startup ensures application indexes.

Configuration-only validation (no services or MongoDB connection):

```bash
python3 -B -c 'from backend.config import load_settings; load_settings(); print("Configuration valid")'
bash -n scripts/dev-backend.sh
```

Once MongoDB is running, inspect its replica set without writing data:

```bash
bash scripts/dev-mongodb.sh status
```

Connect Samsung and PC to the same trusted Wi-Fi. Scan the terminal QR in
Expo Go. The app script detects the PC LAN address on each start; if it changes,
restart Expo and scan its new QR. localhost on the phone refers to the phone.

Use synthetic data only. Check an empty account list, create an account with
1000, create an i_owe debt with 500, pay 100 from the account and verify account
900 and debt pending 400. Use the existing available UI; report errors before
changing any code. Never press the demo restore button for this workflow.

Ctrl+C stops each foreground server. MongoDB can stay running; to stop it without
deleting data, run bash scripts/dev-mongodb.sh stop.

The Nobara firewall currently allows TCP 1025-65535 in FedoraWorkstation.
These scripts do not change firewall rules. Use a trusted network; the API has
no authentication yet. A different firewall must permit LAN clients to access
8001 and 8081. Expo Go must support this project's Expo SDK/native modules;
if it reports incompatibility, diagnose before installing or changing packages.
