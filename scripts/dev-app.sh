#!/usr/bin/env bash
# Detect the LAN address each run; no dotenv changes or public secrets.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LAN_IP=$(python3 -B - <<'PY'
import ipaddress,json,subprocess
route=json.loads(subprocess.check_output(['ip','-j','route','get','1.1.1.1'],text=True))[0]
address=ipaddress.ip_address(route['prefsrc'])
if not address.is_private or address.is_loopback: raise SystemExit('No private LAN address detected.')
print(address)
PY
)
export EXPO_PUBLIC_BACKEND_URL="http://$LAN_IP:8001"
export REACT_NATIVE_PACKAGER_HOSTNAME="$LAN_IP"
python3 -B - <<'PY'
import json,os,urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(os.environ['EXPO_PUBLIC_BACKEND_URL']+'/api/',timeout=5) as response:
    assert json.load(response).get('message')=='MoneyFlow API'
PY
echo "Expo Go backend: $EXPO_PUBLIC_BACKEND_URL"
cd "$ROOT/frontend"
test -f node_modules/expo/bin/cli || { echo 'Existing Expo dependencies are required.' >&2; exit 1; }
exec node node_modules/expo/bin/cli start --go --lan --port 8081
