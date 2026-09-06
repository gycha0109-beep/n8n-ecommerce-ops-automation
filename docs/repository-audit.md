# Repository Consistency Audit - P10 to P18

Date: 2026-09-07

## Corrections completed

- Removed deprecated n8n `.item` expression dependencies from generated exports and generator logic.
- Removed blocked `$env` workflow expressions in favor of Docker-service demo URLs.
- Replaced broken `??`/Unicode-sensitive workflow display names with ASCII-safe canonical names.
- Preserved stable top-level workflow IDs/version IDs through regeneration.
- Rejected UTF-8 BOMs in workflow verification and regenerated fixtures/workflows without BOM.
- Corrected shell execution portability so GitHub Actions can execute repository scripts.
- Removed Compose fallback demo secrets; required password/encryption values come from `.env`.
- Kept `.env` ignored and out of the committed Git tree.
- Upgraded/pinned runtime to n8n 2.37.10 and PostgreSQL 17.11 Alpine.
- Moved PostgreSQL 17 to `postgres17_data` rather than reusing a PostgreSQL 16 major-version data directory.
- Separated deterministic harness evidence, historical pre-upgrade live evidence, and current post-upgrade live evidence.
- Added an automated P13 Docker runtime regression and runtime evidence artifact upload.
- Fixed CI temp-file ownership/permissions so restrictive credential/workflow import files remain `0600` while readable by the n8n `node` user.
- Added README/docs to the runtime-regression path gate so verification claims trigger fresh runtime evidence.

## P13 post-upgrade runtime evidence

At commit `9105fb0faaf2dcd00ccec9e62dfb20f38bd2a03f`, GitHub Actions run `34064393045` completed the live Docker regression successfully using synthetic data only.

Verified runtime:

- n8n 2.37.10
- PostgreSQL 17.11
- workflow credential import
- all three workflow imports and publish/activation
- normal, duplicate, unknown-SKU, insufficient-stock, retry-recovery, 500-DLQ, permanent-400-DLQ, cancelled, and re-run-safety paths
- Daily Summary/database reconciliation: `2 / 7 / 1 / 2 / 1 / 2`
- Asia/Seoul summary date: 2026-09-07
- error-workflow binding
- no PostgreSQL incompatibility message matched by the regression log check
- runtime evidence artifact upload

The same commit's `portfolio-smoke` workflow also completed successfully.

## P18 current-state audit

### Runtime and workflow integrity

- Current Compose pins PostgreSQL 17.11 and n8n 2.37.10.
- Workflow verifier validates JSON parseability, IDs/version IDs, names, graph connections, reliability nodes, retry intervals, direct mock-service URLs, and Asia/Seoul summary semantics.
- P13 proves import/publish/activation and focused live behavior on an actual Docker Compose topology.

### Security / repository hygiene

- `.env` is ignored and is not present in the current Git tree.
- Workflow exports contain no credential binding IDs or committed runtime passwords/API keys by design.
- P13 credentials are random, temporary, restrictive-permission files and are removed during cleanup.
- All committed customer/order data is synthetic.

### Evidence and claims

- 42-fixture contract harness results remain distinct from the focused P13 live runtime totals.
- Historical pre-upgrade totals remain explicitly historical.
- No production ROI, real-client, accounting, settlement, or uptime claim is made.
- Real n8n UI screenshots are not fabricated; `screenshots/README.md` remains the capture checklist for a visual portfolio package.

### Non-blocking note

The n8n image logs a Python task-runner availability warning. This repository's verified Code nodes use JavaScript, so it did not affect P13. Python-runner capability is not claimed.

## Final acceptance state

The code/runtime evidence required for P10-P15 and P17-P18 is complete subject to the final documentation commit itself receiving green `portfolio-smoke` and `p13-runtime-regression` checks. P16's repository-side screenshot checklist is complete; actual UI screenshots remain a manual visual-portfolio capture because fabricated screenshots are intentionally prohibited.
