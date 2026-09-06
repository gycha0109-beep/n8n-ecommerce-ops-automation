# 2-minute demo video script

**0:00–0:15 — Problem**
“This is a synthetic e-commerce operations demo built around reliability. Three channel schemas enter one intake workflow, but the interesting part is what happens when orders are duplicated, invalid, out of stock, or an API fails.”

**0:15–0:35 — Workflow overview**
Show `ecommerce-order-intake.json` in n8n. Point to Normalize → Validate → Idempotency → Inventory. Then pan to the three warehouse attempts and the 1s/2s/4s wait nodes.

**0:35–0:55 — Database safety**
Open `db/schema.sql`. Show `orders.order_key UNIQUE` and the inventory transaction function. Explain that the workflow checks duplicates for clean routing, but the database constraint is still authoritative.

**0:55–1:20 — Failure simulation**
Open `mock-api/src/server.ts`. Show `fail_twice_then_success`, `always_500`, and `timeout`. Run `scripts/run-smoke.ps1` or `.sh` and show Tests A–I passing.

**1:20–1:40 — Results**
Open `generated/smoke-report.json`. Show processed orders, exceptions, retry recovery, dead-letter jobs, and confirm inventory never goes negative.

**1:40–1:55 — Re-run safety + audit**
Explain that the harness replays the full dataset against a cloned DB and asserts that order count and inventory remain unchanged. Show `exceptions` / `failed_jobs` schema fields.

**1:55–2:00 — Close**
“The repository is fully synthetic and designed as a reproducible portfolio sample. A real delivery would swap in the customer's credentials, API contracts, and channel-specific rules.”
