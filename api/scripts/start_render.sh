#!/bin/bash
set -e

if [ "$RUN_DB_INIT" = "1" ]; then
  echo "[render] Running remote DB initialization..."
  PYTHONPATH=/app python scripts/init_remote_db.py
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000
