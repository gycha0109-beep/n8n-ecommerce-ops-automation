#!/usr/bin/env bash
set -euo pipefail
URL="${1:-http://localhost:5678/webhook/ecommerce-order-intake}"
curl -fsS -X POST "$URL" -H 'content-type: application/json' \
  --data @<(python - <<'PY'
import json
p=json.load(open('fixtures/shopify_orders.json',encoding='utf-8'))[0]
print(json.dumps({'source':'shopify','payload':p}))
PY
)
