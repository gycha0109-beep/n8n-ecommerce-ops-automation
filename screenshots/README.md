# Verified n8n screenshots

These are real screenshots captured from the local Docker Compose deployment of this synthetic portfolio project. They are execution evidence, not mockups.

| File | Evidence |
|---|---|
| `01-workflow-overview.png` | Full published intake workflow: normalization, validation, idempotency, inventory checks, retry branches, transaction, notification, and failure paths. |
| `02-retry-recovery-1.png` | Retry recovery execution, first half: attempt 1 failure, 1-second wait, and attempt 2. |
| `02-retry-recovery-2.png` | Retry recovery execution, second half: 2-second wait, attempt 3 success, `Mark Retry Recovered 3`, commit, notify, and success response. |
| `03-success-execution.png` | Normal synthetic order processed successfully through DB commit and notification. |
| `04-duplicate-idempotency.png` | Duplicate delivery detected and recorded without re-processing the order. |
| `05-dead-letter.png` | Exhausted temporary failure path: 1s → 2s → 4s bounded backoff, then dead-letter and controlled failure response. |
| `06-daily-summary.png` | Database-derived Asia/Seoul daily summary with successful, exception, duplicate, retry-recovered, and permanent-failure counts. |
| `07-n8n-overview.png` | All three portfolio workflows present and published in n8n. |

All visible orders, emails, SKUs, inventory values, and failures are synthetic demo data.

Before adding any future screenshots, verify that no credential panel, API key, password, `.env` value, or real customer data is visible.
