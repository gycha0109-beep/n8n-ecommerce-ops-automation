#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INTAKE_ID='3e7b03e1-93af-4a51-8a16-819aff10b352'
ERROR_ID='e0f539bd-1abc-405c-a4f8-7e8861ac83bc'
SUMMARY_ID='83131f1e-3aba-4e04-a3b6-bc1946c30661'
WEBHOOK='http://localhost:5678/webhook/ecommerce-order-intake'

mkdir -p generated
rm -f generated/p13-*.txt generated/p13-*.log generated/p13-*.json

capture_evidence() {
  docker compose ps > generated/p13-compose-ps.txt 2>&1 || true
  docker compose logs --no-color > generated/p13-compose.log 2>&1 || true
  docker compose exec -T postgres psql -U ecommerce_ops -d ecommerce_ops -Atc 'SHOW server_version;' > generated/p13-postgres-version.txt 2>&1 || true
  docker compose exec -T n8n n8n --version > generated/p13-n8n-version.txt 2>&1 || true
  docker compose exec -T postgres psql -U ecommerce_ops -d ecommerce_ops -Atc \
    "SELECT (SELECT count(*) FROM orders)::int,(SELECT count(*) FROM exceptions)::int,(SELECT count(*) FROM exceptions WHERE error_code='ORDER_CANCELLED')::int,(SELECT count(*) FROM exceptions WHERE error_code='DUPLICATE_ORDER')::int,(SELECT count(*) FROM orders WHERE retry_recovered)::int,(SELECT count(*) FROM failed_jobs WHERE status='dead_letter')::int;" \
    > generated/p13-live-summary.txt 2>&1 || true
}

cleanup() {
  capture_evidence
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f .env
}
trap cleanup EXIT

umask 077
cat > .env <<EOF
POSTGRES_DB=ecommerce_ops
POSTGRES_USER=ecommerce_ops
POSTGRES_PASSWORD=$(openssl rand -hex 24)
N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)
N8N_HOST=localhost
N8N_PROTOCOL=http
WEBHOOK_URL=http://localhost:5678/
GENERIC_TIMEZONE=Asia/Seoul
TZ=Asia/Seoul
EOF

node scripts/verify-workflows.mjs
docker compose config >/dev/null
docker compose up -d --build

wait_http() {
  local url="$1"
  local attempts="${2:-90}"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}

wait_http http://localhost:3000/health 90
wait_http http://localhost:5678/healthz/readiness 90

pg_version="$(docker compose exec -T postgres postgres --version)"
n8n_version="$(docker compose exec -T n8n n8n --version | tail -n 1 | tr -d '\r')"
server_version="$(docker compose exec -T postgres psql -U ecommerce_ops -d ecommerce_ops -Atc 'SHOW server_version;' | tr -d '\r')"
[[ "$pg_version" == *'17.11'* ]]
[[ "$n8n_version" == '2.37.10' ]]
[[ "$server_version" == 17.11* ]]
echo "$pg_version"
echo "n8n $n8n_version"
echo "PostgreSQL server_version=$server_version"

docker compose exec -T postgres psql -U ecommerce_ops -d ecommerce_ops -Atc \
  "SELECT to_regclass('public.orders') IS NOT NULL AND to_regclass('public.exceptions') IS NOT NULL AND to_regclass('public.failed_jobs') IS NOT NULL;" \
  | grep -qx 't'

OWNER_PASSWORD="P13A$(openssl rand -hex 12)9"
export OWNER_PASSWORD
python - <<'PY'
import json, os
from pathlib import Path
Path('/tmp/p13-owner.json').write_text(json.dumps({
    'email': 'p13-owner@example.com',
    'firstName': 'P13',
    'lastName': 'Runner',
    'password': os.environ['OWNER_PASSWORD'],
}), encoding='utf-8')
PY
owner_status="$(curl -sS -o /tmp/p13-owner-response.json -w '%{http_code}' -X POST http://localhost:5678/rest/owner/setup -H 'content-type: application/json' --data-binary @/tmp/p13-owner.json)"
if [ "$owner_status" != '200' ] && [ "$owner_status" != '201' ]; then
  echo "owner setup failed: HTTP $owner_status"
  exit 1
fi
rm -f /tmp/p13-owner.json /tmp/p13-owner-response.json
unset OWNER_PASSWORD

set -a
source .env
set +a
python - <<'PY'
import json, os
from pathlib import Path
Path('/tmp/p13-postgres-credential.json').write_text(json.dumps([{
    'id': 'p13-postgres-credential',
    'name': 'P13 Postgres',
    'type': 'postgres',
    'data': {
        'host': 'postgres', 'database': 'ecommerce_ops', 'user': 'ecommerce_ops',
        'password': os.environ['POSTGRES_PASSWORD'], 'port': 5432,
        'ssl': 'disable', 'allowUnauthorizedCerts': False, 'maxConnections': 10,
    },
}]), encoding='utf-8')
PY
n8n_cid="$(docker compose ps -q n8n)"
copy_for_n8n() {
  local source_path="$1"
  local container_path="$2"
  docker cp "$source_path" "$n8n_cid:$container_path"
  docker compose exec -T -u root n8n chown node:node "$container_path"
  docker compose exec -T -u root n8n chmod 600 "$container_path"
}
copy_for_n8n /tmp/p13-postgres-credential.json /tmp/p13-postgres-credential.json
docker compose exec -T n8n n8n import:credentials --input=/tmp/p13-postgres-credential.json
rm -f /tmp/p13-postgres-credential.json
docker compose exec -T -u root n8n rm -f /tmp/p13-postgres-credential.json

python - <<'PY'
import json
from pathlib import Path

target = Path('/tmp/p13-workflows')
target.mkdir(exist_ok=True)
for path in Path('workflows').glob('*.json'):
    workflow = json.loads(path.read_text(encoding='utf-8'))
    for node in workflow.get('nodes', []):
        if node.get('type') == 'n8n-nodes-base.postgres':
            node['credentials'] = {'postgres': {'id': 'p13-postgres-credential', 'name': 'P13 Postgres'}}
    if path.name == 'ecommerce-order-intake.json':
        workflow.setdefault('settings', {})['errorWorkflow'] = 'e0f539bd-1abc-405c-a4f8-7e8861ac83bc'
    (target / path.name).write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY

for file in /tmp/p13-workflows/*.json; do
  base="$(basename "$file")"
  copy_for_n8n "$file" "/tmp/$base"
  docker compose exec -T n8n n8n import:workflow --input="/tmp/$base"
  docker compose exec -T -u root n8n rm -f "/tmp/$base"
done

docker compose exec -T n8n n8n list:workflow > /tmp/p13-workflows.txt
grep -F "$INTAKE_ID|E-commerce Order Intake - Reliability Demo" /tmp/p13-workflows.txt
grep -F "$ERROR_ID|E-commerce Ops - Global Error Handler" /tmp/p13-workflows.txt
grep -F "$SUMMARY_ID|E-commerce Daily Summary" /tmp/p13-workflows.txt

docker compose exec -T n8n n8n publish:workflow --id="$ERROR_ID"
docker compose exec -T n8n n8n publish:workflow --id="$SUMMARY_ID"
docker compose exec -T n8n n8n publish:workflow --id="$INTAKE_ID"
docker compose restart n8n

activated=0
for _ in $(seq 1 60); do
  logs="$(docker compose logs --no-color n8n 2>&1 || true)"
  if curl -fsS http://localhost:5678/healthz/readiness >/dev/null 2>&1 \
    && grep -Fq 'Activated workflow "E-commerce Order Intake - Reliability Demo"' <<<"$logs" \
    && grep -Fq 'Activated workflow "E-commerce Daily Summary"' <<<"$logs" \
    && grep -Fq 'Activated workflow "E-commerce Ops - Global Error Handler"' <<<"$logs"; then
    activated=1
    break
  fi
  sleep 2
done
test "$activated" -eq 1

post_order() {
  local label="$1" expected_code="$2" expected_status="$3" payload="$4"
  local body="/tmp/p13-${label}.json"
  local code
  code="$(curl -sS -o "$body" -w '%{http_code}' -X POST "$WEBHOOK" -H 'content-type: application/json' --data-binary "$payload")"
  echo "$label -> HTTP $code $(cat "$body")"
  test "$code" = "$expected_code"
  python - "$body" "$expected_status" <<'PY'
import json, sys
body = json.load(open(sys.argv[1], encoding='utf-8'))
assert body.get('status') == sys.argv[2], body
PY
}

psqlq() {
  docker compose exec -T postgres psql -U ecommerce_ops -d ecommerce_ops -Atc "$1" | tr -d '\r'
}

normal='{"source":"shopify","payload":{"id":"P13-NORMAL","email":"p13-normal@example.com","financial_status":"paid","created_at":"2026-09-07T00:00:00+09:00","currency":"KRW","line_items":[{"sku":"SKU-RED-001","quantity":2,"price":10100}],"integration_mode":"normal","notification_mode":"normal"}}'
retry='{"source":"shopify","payload":{"id":"P13-RETRY","email":"p13-retry@example.com","financial_status":"paid","created_at":"2026-09-07T00:01:00+09:00","currency":"KRW","line_items":[{"sku":"SKU-BLU-002","quantity":1,"price":15000}],"integration_mode":"fail_twice_then_success","notification_mode":"normal"}}'
unknown='{"source":"shopify","payload":{"id":"P13-UNKNOWN","email":"p13-unknown@example.com","financial_status":"paid","created_at":"2026-09-07T00:02:00+09:00","currency":"KRW","line_items":[{"sku":"SKU-NOT-FOUND","quantity":1,"price":11000}],"integration_mode":"normal","notification_mode":"normal"}}'
lowstock='{"source":"shopify","payload":{"id":"P13-LOW-STOCK","email":"p13-stock@example.com","financial_status":"paid","created_at":"2026-09-07T00:03:00+09:00","currency":"KRW","line_items":[{"sku":"SKU-LTD-006","quantity":5,"price":11000}],"integration_mode":"normal","notification_mode":"normal"}}'
always500='{"source":"shopify","payload":{"id":"P13-ALWAYS-500","email":"p13-500@example.com","financial_status":"paid","created_at":"2026-09-07T00:04:00+09:00","currency":"KRW","line_items":[{"sku":"SKU-GRN-003","quantity":1,"price":15000}],"integration_mode":"always_500","notification_mode":"normal"}}'
permanent400='{"source":"shopify","payload":{"id":"P13-PERM-400","email":"p13-400@example.com","financial_status":"paid","created_at":"2026-09-07T00:05:00+09:00","currency":"KRW","line_items":[{"sku":"SKU-BLK-004","quantity":1,"price":15000}],"integration_mode":"permanent_400","notification_mode":"normal"}}'
cancelled='{"source":"shopify","payload":{"id":"P13-CANCELLED","email":"p13-cancel@example.com","financial_status":"cancelled","created_at":"2026-09-07T00:06:00+09:00","currency":"KRW","line_items":[{"sku":"SKU-WHT-005","quantity":1,"price":12000}],"integration_mode":"normal","notification_mode":"normal"}}'

post_order normal 200 processed "$normal"
post_order duplicate 202 exception "$normal"
post_order unknown 202 exception "$unknown"
post_order lowstock 202 exception "$lowstock"
post_order retry 200 processed "$retry"
post_order always500 202 dead_letter "$always500"
post_order permanent400 202 dead_letter "$permanent400"
post_order cancelled 202 exception "$cancelled"

test "$(psqlq "SELECT count(*) FROM orders WHERE order_key='shopify:P13-NORMAL';")" = '1'
test "$(psqlq "SELECT count(*) FROM exceptions WHERE order_key='shopify:P13-NORMAL' AND error_code='DUPLICATE_ORDER';")" = '1'
test "$(psqlq "SELECT count(*) FROM exceptions WHERE order_key='shopify:P13-UNKNOWN' AND error_code='UNKNOWN_SKU';")" = '1'
test "$(psqlq "SELECT count(*) FROM exceptions WHERE order_key='shopify:P13-LOW-STOCK' AND error_code='INSUFFICIENT_STOCK';")" = '1'
test "$(psqlq "SELECT count(*) FROM orders WHERE order_key='shopify:P13-RETRY' AND retry_recovered=true;")" = '1'
test "$(psqlq "SELECT count(*) FROM failed_jobs WHERE order_key='shopify:P13-ALWAYS-500' AND error_code='API_TEMPORARY_FAILURE' AND attempts=3 AND status='dead_letter';")" = '1'
test "$(psqlq "SELECT count(*) FROM failed_jobs WHERE order_key='shopify:P13-PERM-400' AND error_code='API_PERMANENT_FAILURE' AND attempts=1 AND status='dead_letter';")" = '1'
test "$(psqlq "SELECT count(*) FROM exceptions WHERE order_key='shopify:P13-CANCELLED' AND error_code='ORDER_CANCELLED';")" = '1'
test "$(psqlq "SELECT count(*) FROM orders WHERE order_key='shopify:P13-CANCELLED';")" = '0'
test "$(psqlq 'SELECT min(available_quantity) >= 0 FROM inventory;')" = 't'

orders_before="$(psqlq 'SELECT count(*) FROM orders;')"
inventory_before="$(psqlq "SELECT string_agg(sku||':'||available_quantity||':'||reserved_quantity, ',' ORDER BY sku) FROM inventory;")"
post_order rerun_normal 202 exception "$normal"
post_order rerun_retry 202 exception "$retry"
test "$orders_before" = "$(psqlq 'SELECT count(*) FROM orders;')"
test "$inventory_before" = "$(psqlq "SELECT string_agg(sku||':'||available_quantity||':'||reserved_quantity, ',' ORDER BY sku) FROM inventory;")"
echo 'Live webhook regression: PASS'

kst_start="(date_trunc('day', now() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul')"
kst_end="((date_trunc('day', now() AT TIME ZONE 'Asia/Seoul') + interval '1 day') AT TIME ZONE 'Asia/Seoul')"
successful="$(psqlq "SELECT count(*) FROM orders WHERE processed_at >= $kst_start AND processed_at < $kst_end;")"
exceptions="$(psqlq "SELECT count(*) FROM exceptions WHERE created_at >= $kst_start AND created_at < $kst_end;")"
cancelled_count="$(psqlq "SELECT count(*) FROM exceptions WHERE created_at >= $kst_start AND created_at < $kst_end AND error_code='ORDER_CANCELLED';")"
duplicates="$(psqlq "SELECT count(*) FROM exceptions WHERE created_at >= $kst_start AND created_at < $kst_end AND error_code='DUPLICATE_ORDER';")"
recovered="$(psqlq "SELECT count(*) FROM orders WHERE processed_at >= $kst_start AND processed_at < $kst_end AND retry_recovered;")"
failures="$(psqlq "SELECT count(*) FROM failed_jobs WHERE created_at >= $kst_start AND created_at < $kst_end AND status='dead_letter';")"

# This P13 scenario set is deterministic; explicit totals catch accidental test drift.
test "$successful" = '2'
test "$exceptions" = '7'
test "$cancelled_count" = '1'
test "$duplicates" = '2'
test "$recovered" = '1'
test "$failures" = '2'

docker compose stop n8n
set +e
docker compose run --rm -T n8n execute --id="$SUMMARY_ID" --rawOutput > generated/p13-daily-output.txt 2>&1
execute_code=$?
set -e
cat generated/p13-daily-output.txt
if [ "$execute_code" -ne 0 ]; then
  echo "Daily summary CLI execution failed with exit code $execute_code"
  exit "$execute_code"
fi

python - generated/p13-daily-output.txt "$successful" "$exceptions" "$cancelled_count" "$duplicates" "$recovered" "$failures" <<'PY'
import json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

text = Path(sys.argv[1]).read_text(encoding='utf-8')
decoder = json.JSONDecoder()
execution = None
for index, char in enumerate(text):
    if char != '{':
        continue
    try:
        value, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    if isinstance(value, dict) and value.get('mode') == 'cli' and isinstance(value.get('data'), dict) and 'resultData' in value['data']:
        execution = value
        break
if execution is None:
    raise SystemExit('Could not parse n8n execute JSON output')

summaries = []
def walk(value):
    if isinstance(value, dict):
        if value.get('event') == 'daily_summary':
            summaries.append(value)
        for child in value.values():
            walk(child)
    elif isinstance(value, list):
        for child in value:
            walk(child)
walk(execution)
if not summaries:
    raise SystemExit('daily_summary payload not found')

summary = summaries[-1]
expected = {
    'successful': int(sys.argv[2]),
    'exceptions': int(sys.argv[3]),
    'cancelled': int(sys.argv[4]),
    'duplicates_ignored': int(sys.argv[5]),
    'retry_recovered': int(sys.argv[6]),
    'permanent_failures': int(sys.argv[7]),
}
for key, value in expected.items():
    assert int(summary[key]) == value, (key, summary[key], value)
expected_date = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
assert summary['date'] == expected_date, (summary['date'], expected_date)

Path('generated/p13-runtime-summary.json').write_text(json.dumps({
    'dataset': 'synthetic demo data only',
    'runtime': {'n8n': '2.37.10', 'postgresql': '17.11'},
    'live_webhook_regression': 'PASS',
    'daily_summary_reconciliation': 'PASS',
    'daily_summary_timezone': 'Asia/Seoul',
    'date': expected_date,
    'metrics': expected,
}, indent=2) + '\n', encoding='utf-8')
print('Daily summary reconciliation: PASS', expected)
print('Asia/Seoul summary date: PASS', expected_date)
PY

docker compose start n8n
wait_http http://localhost:5678/healthz/readiness 60

binding="$(docker compose exec -T postgres psql -U ecommerce_ops -d ecommerce_ops -Atc "SELECT settings::jsonb->>'errorWorkflow' FROM n8n.workflow_entity WHERE id='$INTAKE_ID';" | tr -d '\r')"
test "$binding" = "$ERROR_ID"

docker compose logs --no-color n8n > generated/p13-n8n.log
if grep -Eiq '(unsupported|not supported|incompatible).{0,80}postgres|postgres.{0,80}(unsupported|not supported|incompatible)' generated/p13-n8n.log; then
  echo 'PostgreSQL compatibility error detected in n8n log.'
  exit 1
fi

echo 'Error workflow binding: PASS'
echo 'PostgreSQL compatibility log check: PASS'
echo 'P13 live runtime regression: PASS'