# Mock API

Credential-free deterministic integration simulator used by the portfolio workflow.

- `GET /health`
- `POST /api/reset`
- `POST /api/warehouse/reserve`
- `POST /api/notify`

`/api/warehouse/reserve` accepts `mode`:
- `normal`
- `fail_twice_then_success`
- `always_500`
- `timeout`
- `permanent_400`

Attempt counters are keyed by `order_key`, so retry behavior is deterministic within one server process.
