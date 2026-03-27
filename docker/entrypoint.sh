#!/bin/sh
set -eu

MODE="${1:-api}"
if [ "$#" -gt 0 ]; then
  shift
fi

HOST="${UVICORN_HOST:-0.0.0.0}"
PORT="${UVICORN_PORT:-8000}"
LOG_DIR="${PULP_LOG_DIR:-/app/logs}"

mkdir -p "$LOG_DIR"

case "$MODE" in
  api)
    exec python -m uvicorn app.api.main:app --host "$HOST" --port "$PORT"
    ;;
  connector)
    export SOLVER_NAME="${SOLVER_NAME:-CBC}"
    exec python -m uvicorn app.connector_api.main:app --host "$HOST" --port "$PORT"
    ;;
  *)
    exec "$MODE" "$@"
    ;;
esac
