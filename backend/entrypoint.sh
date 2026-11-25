#!/bin/sh
# Runs as root only to fix ownership of the mounted /data volume, then drops to the app user.
set -e
mkdir -p /data
chown -R app:app /data 2>/dev/null || true
exec runuser -u app -- uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
