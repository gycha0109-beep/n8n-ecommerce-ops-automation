# E-commerce Order & Inventory Exception Automation

## Business Problem

Multi-channel commerce operations often receive the same business object in different schemas and delivery mechanisms. The operational risk is not the field mapping alone: duplicate deliveries, cancelled orders, unknown SKUs, low stock, transient APIs, and downstream notification failures can silently create incorrect state or force repetitive manual reconciliation.

## Existing Manual Workflow

A representative manual process would download marketplace files, rename columns, compare SKUs against a master, check warehouse quantities, remove cancellations and duplicates, then report rows that need human attention. Failures in external systems are typically handled by ad-hoc re-runs, which creates a second risk: duplicated orders or duplicated inventory reservations.

## Automation Architecture

The portfolio workflow accepts Shopify-like webhook payloads and rows derived from two marketplace CSV formats. n8n normalizes each source to one canonical order schema, validates it, performs an idempotency check, checks SKU/inventory state, calls a deterministic mock warehouse API, and commits successful orders through a PostgreSQL transaction function.

See `docs/architecture.md` for the diagram and boundary design.

## Key Reliability Features

- Source-specific normalization is explicit in the n8n Code node.
- `order_key` plus a PostgreSQL unique constraint provides idempotency defense in depth.
- Inventory reservation and order insert are in one database transaction with row locking.
- Permanent validation errors never enter the retry path.
- Temporary integration failures use bounded 1s → 2s → 4s backoff and a dead-letter route.
- Downstream notification failure is recorded without rolling back an already committed order.
- Exceptions contain structured codes, payload evidence, status, and resolution fields.
- A separate n8n Error Trigger workflow captures unexpected workflow execution failures.
- The daily summary queries database state instead of using hard-coded portfolio metrics.

## Failure Scenarios Tested

The synthetic corpus contains 42 deterministic order rows and includes normal orders, duplicated deliveries, cancellations, missing/unknown SKUs, invalid quantities, insufficient stock, malformed email, missing fields, invalid currency, malformed CSV numeric data, temporary API failures, exhausted retries, timeout behavior, and post-commit notification failure.

## Synthetic Demo Result

The current local contract smoke run produced:

| Metric | Result |
|---|---:|
| Fixture rows | 42 |
| Orders processed | 26 |
| Exceptions | 17 |
| Cancelled | 3 |
| Duplicates ignored | 2 |
| Retry recovered | 1 |
| Dead-letter jobs | 2 |

These numbers come from `generated/smoke-report.json`; they are not ROI or production claims.

## What I Implemented

- Three n8n workflow JSON exports: intake, error handler, daily summary.
- PostgreSQL/Supabase-compatible schema, constraints, indexes, and transaction functions.
- TypeScript mock integration API with deterministic failure modes.
- 42-row multi-source synthetic dataset.
- Windows/Linux smoke scripts and a deterministic contract harness.
- Workflow structural/security checks and database result verification.
- Architecture, failure catalog, README, demo script, and portfolio introduction.

## What This Demonstrates

This repository demonstrates how I structure a small automation delivery around failure handling and repeatability rather than only the happy path. It shows schema normalization, database safety, retry classification, dead-letter handling, auditability, and reproducible test scenarios.

It does **not** claim production experience with a specific merchant, marketplace, or accounting process. All customer, order, inventory, and result data is synthetic.

## Production Considerations

- Replace the mock warehouse endpoint with the customer's authenticated API.
- Configure n8n credentials in the credential store; never commit API keys or database passwords.
- Restrict incoming webhooks with authentication/signature verification and network controls.
- Add per-channel pagination/batch ingestion and source-event identifiers when available.
- Set retention policies for raw payloads and redact PII according to customer requirements.
- Use production observability, alert routing, backup/restore, and database monitoring.
- Tune retry limits and timeouts to the external provider's documented semantics.
- Treat settlement/accounting calculations as a separate, reviewed domain workflow rather than implying accounting correctness here.
