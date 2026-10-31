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
uv run python -m app.cli init-db --personal-test
if [[ "${CONNECTOR_MODE:-demo}" == demo ]]; then uv run python -m app.cli seed-demo; fi
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 &
api_pid=$!
uv run python -m app.worker &
worker_pid=$!
uv run uvicorn app.main:create_test_app --factory --host 127.0.0.1 --port 8001 &
test_api_pid=$!
uv run python -m app.worker --personal-test &
test_worker_pid=$!
export TEST_API_URL=http://127.0.0.1:8001
cd "$root/dashboard"
npm ci --cache "${NPM_CONFIG_CACHE:-/tmp/supportflow-npm}" --no-audit --no-fund
npm run dev &
dashboard_pid=$!
trap 'kill "$api_pid" "$worker_pid" "$test_api_pid" "$test_worker_pid" "$dashboard_pid" 2>/dev/null || true; wait || true' EXIT INT TERM
wait -n "$api_pid" "$worker_pid" "$dashboard_pid"
