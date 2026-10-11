#!/usr/bin/env bash
# Local development only; process variables override the real dotenv.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export MONEYFLOW_LOCAL_MODE=1
export APP_ENV="${APP_ENV-development}"
export MONGO_URL="${MONGO_URL-mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true}"
export DB_NAME="${DB_NAME-development_local_finanzas}"
export CORS_ORIGINS='http://localhost:8081'
export LOG_LEVEL=INFO
cd "$ROOT"
python3 -B - <<'PY'
from backend.config import load_settings
load_settings()
PY
bash "$ROOT/scripts/dev-mongodb.sh" status
python3 -B - <<'PY'
import os, subprocess
from pymongo import MongoClient
assert subprocess.check_output(['podman','port','app-finanzas-local-development_mongodb-dev_1'],text=True).strip()=='27017/tcp -> 127.0.0.1:27018'
with MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000) as client:
    h=client.admin.command('hello')
    assert h.get('setName')=='app_finanzas_dev_rs' and h.get('isWritablePrimary')
print('APP_ENV=development; database=development_local_finanzas; API port=8001')
PY
export PYTHONDONTWRITEBYTECODE=1
exec python3 -B -m uvicorn backend.server:app --host 0.0.0.0 --port 8001
