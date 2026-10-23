#!/bin/sh
# Container entrypoint: `api` (default), `worker`, `migrate`, or any command.
set -eu

wait_for_db() {
  python - <<'PY'
import os, sys, time
import psycopg
url = (os.environ.get("MIGRATION_DATABASE_URL") or os.environ["DATABASE_URL"]).replace("postgresql+psycopg://", "postgresql://")
for attempt in range(60):
    try:
        psycopg.connect(url, connect_timeout=3).close()
        sys.exit(0)
    except psycopg.OperationalError:
        time.sleep(2)
print("database not reachable", file=sys.stderr)
sys.exit(1)
PY
}

case "${1:-api}" in
  api)
    wait_for_db
    # Several uvicorn workers: aggregate their Prometheus samples (multiprocess mode).
    export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus-api}"
    rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      --workers "${API_WORKERS:-2}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
    ;;
  worker)
    wait_for_db
    # Prometheus multiprocess mode: pool processes write samples here; start clean.
    export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
    rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    exec celery -A app.workers.celery_app worker \
      --loglevel="${LOG_LEVEL:-INFO}" --concurrency="${WORKER_CONCURRENCY:-2}" \
      -Q ingestion,evaluation,celery
    ;;
  migrate)
    wait_for_db
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
