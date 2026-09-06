# Verification Results

Updated: 2026-09-07  
Dataset: synthetic demo data only  
No real customer or production data was used.

## Deterministic repository harness

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

First-run deterministic result:

- Fixture rows: **42**
- Orders processed: **26**
- Exceptions: **17**
- Cancelled: **3**
- Duplicates ignored: **2**
- Retry recovered: **1**
- Dead-letter jobs: **2**

Machine-readable evidence: `generated/smoke-report.json`.

## Live n8n/PostgreSQL pre-upgrade baseline

A real local n8n + PostgreSQL + mock-API run completed Tests A-I **9/9 PASS** before the P12 runtime upgrade. Representative runtime evidence included normal processing, duplicate suppression, validation failures, unknown SKU, insufficient inventory, retry recovery, exhausted retry dead-lettering, re-run safety, and database-to-daily-summary reconciliation.

Database-derived totals from that synthetic run:

- Successful orders: **5**
- Exceptions: **9**
- Cancelled: **1**
- Duplicates ignored: **2**
- Retry recovered: **1**
- Permanent failures: **4**

The daily summary returned the same six values. This baseline is historical evidence only; it must not be presented as post-upgrade verification.

## P10-P12 repository/static verification

The current repository is checked for:

- valid JSON and canonical top-level workflow `id` / `versionId` fields
- exact ASCII-safe workflow names
- no n8n `.item` paired-item references in exports or generator
- no blocked `$env` expressions in exports or generator
- no broken `??` name substitutions
- no committed `.env` or embedded credential/token patterns
- UTF-8 without BOM for repository-generated workflow/fixture files
- PostgreSQL 17.11 Compose target with a fresh `postgres17_data` volume key
- pinned n8n 2.37.10 image
- deterministic generator/export consistency

## Post-upgrade live verification status

P13 is still required after pulling these changes locally. The required live sequence is: stack start, workflow import/credential setup/publish, normal order, duplicate, retry recovery, always-500 dead letter, daily summary reconciliation, and re-run safety. Do not label the PostgreSQL 17.11 runtime PASS until those checks complete.
