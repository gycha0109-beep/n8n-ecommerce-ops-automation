# Verification Results

Updated: 2026-09-07  
Dataset: **synthetic demo data only**  
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

Machine-readable repository evidence: `generated/smoke-report.json`.

## Post-upgrade P13 live runtime regression

**Result: PASS**

- Verified commit: `9105fb0faaf2dcd00ccec9e62dfb20f38bd2a03f`
- GitHub Actions workflow: `p13-runtime-regression`
- Run ID: `34064393045`
- Runtime: n8n **2.37.10**, PostgreSQL **17.11**
- Runner: GitHub-hosted Ubuntu 24.04
- Summary timezone contract: **Asia/Seoul**
- Summary date verified: **2026-09-07**
- Dataset: synthetic demo data only

### Runtime assertions

| Assertion | Result |
|---|---|
| Workflow structural/security verification | PASS |
| PostgreSQL 17.11 startup/version check | PASS |
| n8n 2.37.10 startup/version check | PASS |
| PostgreSQL credential import | PASS |
| Intake / error / daily-summary workflow import | PASS |
| Exact workflow IDs and ASCII-safe names | PASS |
| Workflow publish/activation | PASS |
| Normal order | PASS |
| Duplicate suppression | PASS |
| Unknown SKU exception | PASS |
| Insufficient-stock exception | PASS |
| Temporary API retry recovery | PASS |
| Always-500 exhausted retry → DLQ | PASS |
| Permanent-400 no-retry → DLQ | PASS |
| Cancelled order | PASS |
| Re-run safety | PASS |
| Daily Summary reconciliation | PASS |
| Asia/Seoul calendar date | PASS |
| Error workflow binding | PASS |
| PostgreSQL compatibility log check | PASS |

### Focused P13 database / Daily Summary totals

| Metric | Result |
|---|---:|
| Successful | 2 |
| Exceptions | 7 |
| Cancelled | 1 |
| Duplicates ignored | 2 |
| Retry recovered | 1 |
| Permanent failures / dead-letter jobs | 2 |

The Daily Summary returned the same six values. The job uploaded **8 runtime-evidence files** as the `p13-runtime-evidence` artifact.

The P13 script also asserted that re-sending the successful normal/retry orders did not change successful-order count or inventory state.

## Historical pre-upgrade live baseline

A prior local n8n + PostgreSQL + mock-API run completed Tests A-I **9/9 PASS** before the runtime upgrade. Its synthetic database-derived totals were:

- Successful orders: **5**
- Exceptions: **9**
- Cancelled: **1**
- Duplicates ignored: **2**
- Retry recovered: **1**
- Permanent failures: **4**

This baseline is retained only for history and must not be confused with the current P13 result above.

## Repository/static verification

Current automated/static checks cover:

- valid JSON and canonical top-level workflow `id` / `versionId`
- exact ASCII-safe workflow names
- no n8n `.item` paired-item expressions in workflow exports
- no blocked `$env` expressions in workflow exports
- no broken `??` workflow/node names
- workflow UTF-8 BOM rejection
- possible embedded workflow-secret pattern rejection
- required reliability nodes and bounded 1s → 2s → 4s retry chain
- Docker-service mock URLs
- Asia/Seoul daily-summary date contract
- deterministic generator/export consistency in CI
- PostgreSQL 17.11 Compose target with `postgres17_data`
- pinned n8n 2.37.10 image
- `.env` ignored and absent from the Git tree

## CI status and evidence policy

`portfolio-smoke` runs on pushes and pull requests. `p13-runtime-regression` runs when runtime-sensitive code **or runtime-verification documentation** changes, so a documentation claim cannot become the final `main` HEAD without also causing a fresh live regression run.

The runtime workflow creates temporary random database/encryption credentials at execution time; no production/customer credential is required for the synthetic regression.

## Observed non-blocking runtime note

The n8n container logs report that a Python task runner is unavailable in the image. The verified workflows use JavaScript Code nodes, and all P13 assertions completed successfully. This is not treated as evidence for Python-runner support; a deployment needing Python task execution should configure the appropriate production runner topology.

## Evidence boundary

PASS here means the stated synthetic checks passed on the stated repository/runtime configuration. It does **not** mean the project has been operated against a real merchant, real marketplace account, production traffic, production settlement/accounting, or measured ROI.
