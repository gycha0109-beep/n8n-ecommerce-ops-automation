#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-order-intake.json
docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-error-handler.json
docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-daily-summary.json
echo "n8n workflow import: PASS"
