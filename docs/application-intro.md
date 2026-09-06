I built a small n8n-based e-commerce operations demo focused on reliability rather than just happy-path automation.

It normalizes orders from multiple source schemas, detects duplicates and inventory exceptions, stores an audit trail, retries temporary integration failures, and routes exhausted failures to a dead-letter queue for review.

The repository uses only synthetic data and includes reproducible failure scenarios, PostgreSQL/Supabase-compatible schema, workflow JSON exports, and automated smoke checks.
