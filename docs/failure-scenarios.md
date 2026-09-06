# Failure Scenarios

All fixtures are synthetic/demo data.

| Code | Retry? | Route | Demonstrated by fixture |
|---|---:|---|---|
| `DUPLICATE_ORDER` | No | Ignore duplicate + audit exception | duplicate Shopify webhook / Amazon CSV order |
| `ORDER_CANCELLED` | No | Exception/manual review | 3 cancelled orders |
| `MISSING_FIELD` | No | Exception | missing SKU / missing order ID |
| `MALFORMED_EMAIL` | No | Exception | invalid email format |
| `MALFORMED_INPUT` | No | Exception | non-numeric CSV quantity |
| `UNKNOWN_SKU` | No | Exception | SKU not in master |
| `INVALID_QUANTITY` | No | Exception | zero / negative quantity |
| `INSUFFICIENT_STOCK` | No | Exception | limited SKU request > stock |
| `INVALID_CURRENCY` | No | Exception | unsupported synthetic currency |
| `API_TEMPORARY_FAILURE` | Yes, max 3 attempts | recover or dead-letter | fail twice then success, always-500, timeout |
| `API_PERMANENT_FAILURE` | No after 4xx | dead-letter | supported by mock API mode `permanent_400` |
| `NOTIFICATION_FAILURE` | No order rollback | exception/manual retry | post-commit notification failure |
| `WORKFLOW_EXECUTION_FAILURE` | n/a | global n8n error workflow → failed_jobs | unexpected workflow execution error |

## Backoff policy

The n8n intake workflow exposes the retry chain as separate nodes:

```text
attempt 1
  ↓ 5xx/timeout
wait 1s
  ↓
attempt 2
  ↓ 5xx/timeout
wait 2s
  ↓
attempt 3
  ↓ exhausted
wait 4s
  ↓
failed_jobs + exception + alert
```

Validation errors and 4xx-style permanent integration failures are not retried.

## Re-run behavior

`order_key = source + ':' + external_order_id` is the business idempotency key. A pre-check provides a clean operator path, while the database unique constraint remains authoritative. Inventory is decremented only inside the same transaction that inserts the order, preventing a re-run from reserving stock twice.
