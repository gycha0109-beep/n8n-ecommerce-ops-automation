# Architecture

All business and customer data in this repository is synthetic.

```mermaid
flowchart TD
    S[Shopify-like webhook JSON] --> N[n8n intake]
    A[Amazon-like CSV rows] --> N
    M[Marketplace CSV rows] --> N
    N --> C[Canonical normalization]
    C --> V{Validation}
    V -->|Permanent validation error| E[(exceptions)]
    V -->|Valid| I{Idempotency check}
    I -->|Already processed| E
    I -->|New| K{SKU + stock check}
    K -->|Unknown SKU / insufficient stock| E
    K -->|Valid| R1[Warehouse API attempt 1]
    R1 -->|5xx / timeout| W1[Wait 1s]
    W1 --> R2[Attempt 2]
    R2 -->|5xx / timeout| W2[Wait 2s]
    W2 --> R3[Attempt 3]
    R3 -->|still failing| W4[Wait 4s]
    W4 --> D[(failed_jobs / dead letter)]
    R1 -->|2xx| T[PostgreSQL transaction]
    R2 -->|2xx| T
    R3 -->|2xx| T
    T --> O[(orders)]
    T --> INV[(inventory)]
    O --> AL[notification webhook]
    AL -->|notification failure| E
    SCH[Daily schedule] --> Q[Aggregate DB query]
    Q --> SUM[Summary webhook]
    ERR[n8n Error Trigger] --> D
```

## Reliability boundaries

1. **Normalization boundary** — source-specific payloads become one canonical order contract.
2. **Validation boundary** — non-retryable business errors are rejected before integrations.
3. **Idempotency boundary** — application-level lookup plus `orders.order_key UNIQUE` protects against duplicate deliveries and concurrent races.
4. **Inventory boundary** — `reserve_inventory_and_insert_order*()` locks inventory and updates stock + order atomically.
5. **Integration boundary** — retryable warehouse failures use bounded exponential backoff; exhausted retries go to `failed_jobs`.
6. **Notification boundary** — downstream alert failure does not roll back a successfully committed order; it creates `NOTIFICATION_FAILURE` for manual follow-up.
7. **Audit boundary** — `exceptions`, `failed_jobs`, `processed_events`, and `workflow_runs` retain operational evidence.

## Production mapping

The local Docker topology uses PostgreSQL 16. The schema is intentionally Supabase-compatible because Supabase exposes PostgreSQL. In a real delivery, the n8n Postgres credential should point to the customer's Supabase/PostgreSQL instance rather than hard-coding connection data in the workflow JSON.
