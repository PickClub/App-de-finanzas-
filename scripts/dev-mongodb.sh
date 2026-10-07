#!/usr/bin/env bash
# No dotenv loading, seed, application startup or volume deletion.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PROJECT=app-finanzas-local-development
COMPOSE=(podman compose -p "$PROJECT" -f "$ROOT/compose.dev.yml")
command -v podman >/dev/null || { echo 'Podman is required.' >&2; exit 1; }

status() {
  "${COMPOSE[@]}" exec -T mongodb-dev mongosh --quiet --host 127.0.0.1 --eval '
    const a=db.getSiblingDB("admin");
    const h=a.runCommand({hello:1}), s=a.runCommand({replSetGetStatus:1});
    const c=a.runCommand({replSetGetConfig:1}), f=a.runCommand({getParameter:1,featureCompatibilityVersion:1});
    if(h.setName!=="app_finanzas_dev_rs" || !h.isWritablePrimary || s.ok!==1 ||
       c.ok!==1 || c.config.members.length!==1 || c.config.members[0].host!=="mongodb-dev:27017" ||
       !h.logicalSessionTimeoutMinutes || f.ok!==1 || parseFloat(f.featureCompatibilityVersion.version)<4) {
      throw new Error("Development replica is not ready for transactions.");
    }
    print(JSON.stringify({replicaSet:h.setName,primary:h.isWritablePrimary,members:s.members.map(m=>({name:m.name,state:m.stateStr})),sessions:true,fcv:f.featureCompatibilityVersion.version,version:a.runCommand({buildInfo:1}).version,transactionsCompatible:true}));'
}

case "${1:-}" in
  start)
    "${COMPOSE[@]}" config >/dev/null
    "${COMPOSE[@]}" up -d mongodb-dev
    ready=false
    for ((i=0; i<60; i++)); do
      if "${COMPOSE[@]}" exec -T mongodb-dev mongosh --quiet --host 127.0.0.1 --eval 'quit(db.adminCommand({ping:1}).ok===1 ? 0 : 1)' >/dev/null 2>&1; then ready=true; break; fi
      sleep 1
    done
    "$ready" || { echo 'MongoDB startup timed out.' >&2; exit 1; }
    "${COMPOSE[@]}" exec -T mongodb-dev mongosh --quiet --host 127.0.0.1 --file /dev/stdin < "$ROOT/infra/mongodb/init-replica.js"
    status
    ;;
  status) status ;;
  stop) "${COMPOSE[@]}" stop mongodb-dev; echo 'Stopped; development data volume preserved.' ;;
  *) echo 'Usage: bash scripts/dev-mongodb.sh {start|status|stop}' >&2; exit 2 ;;
esac
