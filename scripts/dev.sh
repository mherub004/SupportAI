#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/configure.py
set -a
source .env
set +a
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/supportflow-uv}"
export NEXT_TELEMETRY_DISABLED=1
root="$PWD"
cd "$root/backend"
uv sync --frozen
uv run python -m app.cli init-db
if [[ "${CONNECTOR_MODE:-demo}" == demo ]]; then uv run python -m app.cli seed-demo; fi
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 &
api_pid=$!
uv run python -m app.worker &
worker_pid=$!
cd "$root/dashboard"
npm ci --cache "${NPM_CONFIG_CACHE:-/tmp/supportflow-npm}" --no-audit --no-fund
npm run dev &
dashboard_pid=$!
trap 'kill "$api_pid" "$worker_pid" "$dashboard_pid" 2>/dev/null || true; wait || true' EXIT INT TERM
wait -n "$api_pid" "$worker_pid" "$dashboard_pid"
