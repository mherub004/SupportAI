#!/usr/bin/env bash
set -euo pipefail
cd /app
: "${DATABASE_URL:?A persistent PostgreSQL database is required}"
: "${OPERATOR_TOKEN:?An operator token is required}"
# Render supplies a standard PostgreSQL URI; SQLAlchemy uses the psycopg dialect.
export DATABASE_URL="$(python - <<'PY'
import os
url = os.environ['DATABASE_URL']
for prefix in ('postgres://', 'postgresql://'):
    if url.startswith(prefix):
        url = 'postgresql+psycopg://' + url[len(prefix):]
        break
if not url.startswith('postgresql+psycopg://'):
    raise SystemExit('Render deployment requires PostgreSQL; SQLite ephemeral storage is not supported')
print(url)
PY
)"
export API_URL=http://127.0.0.1:8000
export COOKIE_SECURE=true
if [[ -n "${PUBLIC_APP_URL:-}" ]]; then
  export DASHBOARD_ORIGIN="$PUBLIC_APP_URL"
elif [[ -z "${DASHBOARD_ORIGIN:-}" && -n "${RENDER_EXTERNAL_URL:-}" ]]; then
  export DASHBOARD_ORIGIN="$RENDER_EXTERNAL_URL"
fi
python -m app.cli init-db
if [[ "${CONNECTOR_MODE:-demo}" == demo ]]; then python -m app.cli seed-demo; fi
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 &
api_pid=$!
python -m app.worker &
worker_pid=$!
cd /app/dashboard
HOSTNAME=0.0.0.0 PORT="${PORT:-3000}" node server.js &
dashboard_pid=$!
cleanup() {
  kill "$api_pid" "$worker_pid" "$dashboard_pid" 2>/dev/null || true
  wait || true
}
trap cleanup EXIT INT TERM
# If any component dies, exit so the hosting platform restarts the whole service.
set +e
wait -n "$api_pid" "$worker_pid" "$dashboard_pid"
result=$?
set -e
if [[ "$result" == 0 ]]; then result=1; fi
exit "$result"
