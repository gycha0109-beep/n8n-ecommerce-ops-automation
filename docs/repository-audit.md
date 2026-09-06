# Repository Consistency Audit - P10 to P12

Date: 2026-09-07

## Findings corrected

- Workflow exports were fixed previously, but `scripts/generate_workflows.py` still regenerated deprecated `.item.json` references and blocked `$env` expressions.
- Three workflow display names contained broken `??` substitutions; the generator still used Unicode em dashes.
- The workflow generator omitted top-level workflow IDs, so regeneration could recreate CLI-import-invalid exports.
- Four generated CSV fixtures contained UTF-8 BOMs.
- Linux shell scripts were stored without executable mode, causing GitHub Actions `Permission denied`.
- Current documentation still described n8n 2.37.7 / PostgreSQL 16 and mixed deterministic harness evidence with the real local demo baseline.
- Compose embedded fallback demo secrets for the PostgreSQL password and n8n encryption key.
- Compose still targeted PostgreSQL 16 and reused the PostgreSQL 16 volume path/key, which is unsafe for a direct major-version container swap.
- Mock integration environment variables remained in Compose although the verified workflow exports use Docker-service URLs directly.

## Corrections

- Generator and exports now use `.first().json` and direct `http://mock-api:3000/...` demo endpoints.
- Names are ASCII-safe: `E-commerce Order Intake - Reliability Demo`, `E-commerce Ops - Global Error Handler`, and `E-commerce Daily Summary`.
- Stable top-level workflow IDs/version IDs are preserved by the generator.
- Generated fixtures/workflows are UTF-8 without BOM.
- Shell scripts are committed executable.
- Compose pins n8n 2.37.10 and PostgreSQL 17.11 Alpine.
- Required password/encryption values must come from `.env`; `.env` remains ignored.
- PostgreSQL 17 uses `postgres17_data`, leaving the old PostgreSQL 16 volume untouched.
- Documentation separates deterministic harness results from the historical live n8n baseline and explicitly marks P13 post-upgrade regression as pending.
