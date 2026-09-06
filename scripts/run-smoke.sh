#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
node --check mock-api/dist/server.js
node mock-api/dist/server.js > generated/mock-api.log 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT
for _ in {1..40}; do curl -fsS http://127.0.0.1:3000/health >/dev/null && break || sleep .1; done
python scripts/smoke_harness.py
python scripts/verify-results.py
node scripts/verify-workflows.mjs
