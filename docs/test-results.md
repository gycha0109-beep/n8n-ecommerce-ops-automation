# Verification Results

Date: 2026-09-03
Dataset: 42 synthetic orders
No real customer or production data was used.

## Executed in the artifact environment

| Test | Assertion | Result |
|---|---|---|
| A | Normal order stored exactly once | PASS |
| B | Duplicate delivery does not create a second order | PASS |
| C | Unknown SKU becomes an exception | PASS |
| D | Insufficient stock becomes an exception and inventory never goes below zero | PASS |
| E | `fail_twice_then_success` recovers on retry | PASS |
| F | Exhausted 500/timeout failures are written to `failed_jobs` | PASS |
| G | Cancelled orders are not stored as successful orders | PASS |
| H | Full dataset re-run leaves order count and inventory unchanged | PASS |
| I | Summary metrics reconcile to database queries | PASS |

## First-run synthetic result

- Fixture rows: **42**
- Orders processed: **26**
- Exceptions: **17**
- Cancelled: **3**
- Duplicates ignored: **2**
- Retry recovered: **1**
- Dead-letter jobs: **2**

Machine-readable evidence: `generated/smoke-report.json`.

## Workflow checks

`node scripts/verify-workflows.mjs` passed and verifies:

- all three workflow JSON files parse
- all connection targets exist
- intake workflow contains Webhook, Code, Postgres, HTTP Request, and Wait nodes
- explicit 1s / 2s / 4s retry waits exist
- duplicate, inventory exception, dead-letter, transaction, and notification-failure nodes exist
- daily workflow includes a Schedule Trigger
- no obvious hard-coded API token/password pattern exists in workflow JSON

## Environment-dependent check not executed here

A live **n8n 2.37.7 CLI import** was not executed in this artifact sandbox because Docker is unavailable and outbound npm registry access timed out. This is intentionally not reported as PASS.

On a Docker-enabled machine, run:

```bash
docker compose up -d
./scripts/import-workflows.sh
```

or on PowerShell:

```powershell
docker compose up -d
.\scripts\import-workflows.ps1
```

A portfolio screenshot should only be captured after this live import and execution succeeds.
