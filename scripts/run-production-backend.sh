#!/usr/bin/env bash
# Explicit production entrypoint; secrets must already be injected by the supervisor.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# The trusted proxy must be on this host. Never enable Uvicorn's forwarded-header rewriting.
exec python3 -m uvicorn backend.production_api:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log --log-level warning
