# Screenshot checklist

Add real screenshots after importing the workflows into n8n. Do not use mock UI images as if they were execution evidence.

Recommended captures:

1. `01-intake-overview.png` — full intake workflow with normalization, validation, idempotency, retry, dead-letter branches visible.
2. `02-retry-branch.png` — attempt 1/2/3 and 1s/2s/4s wait nodes.
3. `03-success-execution.png` — one processed synthetic order execution.
4. `04-exception-execution.png` — unknown SKU or insufficient-stock execution.
5. `05-dead-letter.png` — exhausted API retry path.
6. `06-daily-summary.png` — scheduled summary query/output.
7. `07-smoke-terminal.png` — A–I PASS output.

Before publishing, ensure no credential panel, API key, real email, or other customer data is visible.
