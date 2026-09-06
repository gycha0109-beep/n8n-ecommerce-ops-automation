# E-commerce Order & Inventory Exception Automation

A production-oriented **n8n e-commerce operations portfolio** built around failure handling, idempotency, inventory safety, and auditability rather than only happy-path node chaining.

It normalizes Shopify-like webhook payloads and two marketplace CSV schemas, rejects permanent business errors, protects against duplicate processing, checks stock, retries temporary warehouse failures, dead-letters exhausted jobs, records exceptions, and sends a database-derived daily summary.

> **Synthetic data only.** Every order, email, SKU, inventory value, failure, and result in this repository is fabricated for demonstration. This repository makes no production ROI, accounting, tax, or real-client claims.

## Problem

Multi-channel order operations commonly fail in ways that basic automations hide:

- different source columns and payload shapes
- duplicate webhooks / duplicate CSV rows
- cancelled orders mixed into paid orders
- missing or unknown SKUs
- invalid quantities and currencies
- insufficient warehouse stock
- temporary API 500 / timeout failures
- retries that accidentally create duplicate state
- successful DB writes followed by notification failure
- no exception queue or dead-letter trail
- summary reports that do not reconcile to stored data

This demo treats those as first-class workflow states.

## Architecture

```mermaid
flowchart TD
    SH[Shopify-like webhook] --> N[n8n intake]
    AM[Amazon-like CSV] --> N
    MP[Marketplace CSV] --> N
    N --> C[Normalize to canonical schema]
    C --> V{Validate}
    V -->|invalid/cancelled| E[(exceptions)]
    V -->|valid| I{Idempotency}
    I -->|duplicate| E
    I -->|new| S{SKU + stock}
    S -->|exception| E
    S --> R1[Warehouse attempt 1]
    R1 -->|5xx/timeout| W1[1s]
    W1 --> R2[attempt 2]
    R2 -->|5xx/timeout| W2[2s]
    W2 --> R3[attempt 3]
    R3 -->|exhausted| W4[4s]
    W4 --> DLQ[(failed_jobs)]
    R1 -->|success| TX[PostgreSQL transaction]
    R2 -->|success| TX
    R3 -->|success| TX
    TX --> O[(orders)]
    TX --> INV[(inventory)]
    O --> ALERT[notification webhook]
    ALERT -->|fails| E
    SCH[Daily schedule] --> Q[DB aggregate]
    Q --> ALERT
```

Detailed design: [`docs/architecture.md`](docs/architecture.md)

## Reliability features

- **Canonical schema** with explicit per-source mapping inside n8n.
- **Idempotency key:** `source + ':' + external_order_id`.
- **Defense in depth:** workflow pre-check plus `orders.order_key UNIQUE`.
- **Transactional inventory:** `SELECT ... FOR UPDATE`, inventory decrement, and order insert are one PostgreSQL function transaction.
- **Permanent vs temporary failure classification:** validation/4xx are not retried; 5xx/timeouts are.
- **Bounded retry chain:** attempt 1 → wait 1s → attempt 2 → wait 2s → attempt 3 → wait 4s → dead-letter.
- **Post-commit notification isolation:** a notification failure records `NOTIFICATION_FAILURE` instead of rolling back a valid order.
- **Audit trail:** `exceptions`, `failed_jobs`, `processed_events`, `workflow_runs`.
- **Global workflow error handler:** unexpected n8n execution errors route to a separate failure workflow.
- **Database-derived daily summary:** no hard-coded demo totals.

## Canonical order schema

```json
{
  "source": "shopify",
  "external_order_id": "SHOP-10001",
  "order_key": "shopify:SHOP-10001",
  "customer_email": "demo01@example.com",
  "sku": "SKU-RED-001",
  "quantity": 2,
  "unit_price": 10100,
  "currency": "KRW",
  "order_status": "paid",
  "created_at": "2026-09-01T09:00:00+09:00"
}
```

## Tech stack

- n8n **2.37.10** pinned Docker image
- PostgreSQL **17.11** pinned Alpine image / Supabase-compatible SQL
- Node.js 22 mock API
- TypeScript source with dependency-free prebuilt JS runtime
- Python 3 standard-library deterministic smoke harness
- Docker Compose for reproducible local topology
- GitHub Actions for deterministic contract and live container regression

## Quick start — deterministic smoke test

This test does **not** require Docker, external SaaS, Google, Slack, or npm packages.

### Windows PowerShell

```powershell
cd n8n-ecommerce-ops-automation
.\scripts\run-smoke.ps1
```

If Windows PowerShell 5.1 blocks local scripts, enable them only for the current shell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Repository JSON/workflow files are UTF-8 **without BOM**. On Windows PowerShell 5.1, avoid rewriting JSON with `Set-Content -Encoding UTF8`, which adds a BOM; use a BOM-less UTF-8 writer instead.

### macOS / Linux / Git Bash

```bash
cd n8n-ecommerce-ops-automation
./scripts/run-smoke.sh
```

Expected checks:

```text
Test A — Normal order: PASS
Test B — Duplicate webhook: PASS
Test C — Unknown SKU: PASS
Test D — Insufficient inventory: PASS
Test E — Temporary API failure: PASS
Test F — Permanent/exhausted API failure: PASS
Test G — Cancelled order: PASS
Test H — Re-run safety: PASS
Test I — Daily summary reconciliation: PASS
```

The machine-readable report is written to `generated/smoke-report.json`. Full verification notes: [`docs/test-results.md`](docs/test-results.md).

## Full n8n + PostgreSQL setup

1. Copy environment values:

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Change at least `N8N_ENCRYPTION_KEY` and `POSTGRES_PASSWORD` in `.env`.

3. Start the stack:

```bash
docker compose up -d
```

The n8n UI is available at `http://localhost:5678/` after the service is ready.

### PostgreSQL 16 → 17 local demo reset

The PostgreSQL 17 upgrade intentionally uses a new Compose volume key, `postgres17_data`. This avoids trying to open a PostgreSQL 16 data directory with PostgreSQL 17. Because this repository contains synthetic demo data, the new PostgreSQL 17 volume is initialized from `db/schema.sql` and `db/seed.sql`. A previous PostgreSQL 16 volume is not migrated automatically.

4. Import the workflows:

```bash
docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-order-intake.json
docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-error-handler.json
docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-daily-summary.json
```

5. In n8n, create one **Postgres** credential pointing to the `ecommerce_ops` database and attach it to all Postgres nodes. Workflow JSON intentionally contains no credential ID, password, or API key.

6. Set `E-commerce Ops - Global Error Handler` as the error workflow for the intake workflow, then publish/activate the required workflows.

7. Send one fixture:

```powershell
.\scripts\send-webhook.ps1
```

Or send all 42 synthetic rows after the intake webhook is active:

```bash
python scripts/send-all-fixtures.py
```

## Synthetic fixture coverage

The corpus contains **42 deterministic rows** across three source schemas, including normal orders, duplicates, cancellations, missing/unknown SKUs, invalid quantities, insufficient stock, malformed email/input, invalid currency, temporary failures, permanent failures, timeout behavior, and post-commit notification failure.

See [`docs/failure-scenarios.md`](docs/failure-scenarios.md).

## Verified synthetic results

### Deterministic repository harness

Generated from the 42 repository fixtures:

| Metric | Result |
|---|---:|
| Fixture rows | 42 |
| Orders processed | 26 |
| Exceptions | 17 |
| Cancelled | 3 |
| Duplicates ignored | 2 |
| Retry recovered | 1 |
| Dead-letter jobs | 2 |

All Tests **A-I pass** in the deterministic contract harness. The harness replays the complete dataset against a cloned database and verifies that order count and inventory remain unchanged.

### Post-upgrade live n8n/PostgreSQL regression

A GitHub-hosted Ubuntu runner executed the real Docker Compose topology at commit `9105fb0faaf2dcd00ccec9e62dfb20f38bd2a03f` in Actions run **34064393045**. The run used synthetic data only and completed successfully against **n8n 2.37.10** and **PostgreSQL 17.11**.

Verified paths:

- workflow structural/security verification
- credential import and all three workflow imports
- exact workflow names/IDs
- workflow publish/activation
- normal order processing
- duplicate suppression
- unknown SKU exception
- insufficient-stock exception
- temporary failure recovery after retry
- exhausted 500 failure → dead letter after 3 attempts
- permanent 400 failure → dead letter without retry
- cancelled-order exception
- re-run safety with unchanged order count and inventory
- database-derived Daily Summary reconciliation
- Asia/Seoul calendar-date reconciliation
- error-workflow binding
- PostgreSQL compatibility log check

Database/Daily Summary totals for this focused P13 scenario set:

| Metric | Result |
|---|---:|
| Successful | 2 |
| Exceptions | 7 |
| Cancelled | 1 |
| Duplicates ignored | 2 |
| Retry recovered | 1 |
| Permanent failures / dead-letter jobs | 2 |

The Daily Summary produced the same six values for **2026-09-07 Asia/Seoul**. Runtime evidence was uploaded by the workflow as the `p13-runtime-evidence` artifact.

### Historical pre-upgrade baseline

A prior local synthetic run before the PostgreSQL 17.11 / n8n 2.37.10 upgrade produced 5 successful orders, 9 exceptions, 1 cancellation, 2 ignored duplicates, 1 retry recovery, and 4 permanent failures. It is retained only as historical evidence and is not used as the upgraded-runtime result.

## Verification scope

- **Repository harness:** deterministic contract behavior over all 42 synthetic fixtures.
- **Current live runtime:** actual n8n 2.37.10 + PostgreSQL 17.11 + mock API Docker topology in GitHub Actions.
- **Evidence boundary:** these tests establish reproducible demo behavior; they do not establish customer-specific production performance, uptime, ROI, settlement correctness, or accounting correctness.

## Exception codes

| Code | Meaning | Retry |
|---|---|---:|
| `DUPLICATE_ORDER` | already processed idempotency key | No |
| `ORDER_CANCELLED` | cancelled/canceled order | No |
| `MISSING_FIELD` | required canonical field absent | No |
| `MALFORMED_EMAIL` | invalid email shape | No |
| `MALFORMED_INPUT` | malformed numeric/input row | No |
| `UNKNOWN_SKU` | SKU not in master | No |
| `INVALID_QUANTITY` | quantity <= 0 | No |
| `INSUFFICIENT_STOCK` | stock lower than requested quantity | No |
| `INVALID_CURRENCY` | unsupported currency | No |
| `API_TEMPORARY_FAILURE` | 5xx/timeout exhausted | Yes, bounded |
| `API_PERMANENT_FAILURE` | non-retryable integration response | No |
| `NOTIFICATION_FAILURE` | downstream alert failed after DB commit | Separate follow-up |
| `WORKFLOW_EXECUTION_FAILURE` | unexpected n8n execution error | Error workflow |

## Screenshots

The repository intentionally does not fabricate n8n execution screenshots. [`screenshots/README.md`](screenshots/README.md) is the capture checklist for real UI evidence. GitHub Actions runtime logs/artifacts are automated evidence, not substitutes for screenshots in a visual portfolio presentation.

## Security notes

- No credential IDs, tokens, API keys, or customer data are intended to be committed.
- `.env` is ignored; `.env.example` contains placeholders only.
- CI creates temporary random database/encryption credentials and removes the local `.env` during cleanup.
- SQL business inputs use query parameters.
- Webhook authentication/signature verification is a **production requirement** and intentionally documented rather than faked in the local mock.
- Raw payload retention and PII redaction must be adjusted to customer requirements.

## Limitations

- The mock warehouse API is deterministic and local; it does not model every vendor-specific timeout or rate-limit behavior.
- CSV ingestion is row-based in the demo; a client delivery would usually ingest/download files inside n8n or from object storage/SFTP according to the source contract.
- Manual review UI is represented by structured exception records/status fields; a customer-specific admin UI is outside this portfolio scope.
- The current n8n container emits a Python task-runner availability warning. This demo executes JavaScript Code nodes and the verified P13 paths completed successfully; deployments that require Python task runners should configure the appropriate production runner topology.
- The repository does not claim production merchant experience, production uptime, accounting/tax correctness, or financial ROI.

## Portfolio materials

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/failure-scenarios.md`](docs/failure-scenarios.md)
- [`docs/test-results.md`](docs/test-results.md)
- [`docs/repository-audit.md`](docs/repository-audit.md)
- [`docs/portfolio-case-study.md`](docs/portfolio-case-study.md)
- [`docs/demo-video-script.md`](docs/demo-video-script.md)
- [`docs/application-intro.md`](docs/application-intro.md)
