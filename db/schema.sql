CREATE SCHEMA IF NOT EXISTS n8n;

CREATE TABLE IF NOT EXISTS sku_master (
  sku text PRIMARY KEY,
  product_name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory (
  sku text PRIMARY KEY REFERENCES sku_master(sku),
  available_quantity integer NOT NULL CHECK (available_quantity >= 0),
  reserved_quantity integer NOT NULL DEFAULT 0 CHECK (reserved_quantity >= 0),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
  id bigserial PRIMARY KEY,
  order_key text NOT NULL UNIQUE,
  source text NOT NULL,
  external_order_id text NOT NULL,
  customer_email text NOT NULL,
  sku text NOT NULL REFERENCES sku_master(sku),
  quantity integer NOT NULL CHECK (quantity > 0),
  unit_price numeric(14,2) NOT NULL CHECK (unit_price >= 0),
  currency text NOT NULL,
  order_status text NOT NULL,
  retry_recovered boolean NOT NULL DEFAULT false,
  raw_payload jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  processed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orders_processed_at ON orders(processed_at);

CREATE TABLE IF NOT EXISTS exceptions (
  id bigserial PRIMARY KEY,
  idempotency_key text NOT NULL UNIQUE,
  source text,
  external_order_id text,
  order_key text,
  error_code text NOT NULL,
  error_message text NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','ignored')),
  resolution_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_exceptions_status_created ON exceptions(status, created_at);

CREATE TABLE IF NOT EXISTS processed_events (
  event_key text PRIMARY KEY,
  order_key text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  delivery_count integer NOT NULL DEFAULT 1 CHECK (delivery_count > 0)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  id uuid PRIMARY KEY,
  workflow_name text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status text NOT NULL CHECK (status IN ('running','success','partial_failure','failed')),
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS failed_jobs (
  id bigserial PRIMARY KEY,
  job_key text NOT NULL UNIQUE,
  order_key text,
  source text,
  external_order_id text,
  error_code text NOT NULL,
  error_message text NOT NULL,
  payload jsonb NOT NULL,
  attempts integer NOT NULL CHECK (attempts >= 1),
  status text NOT NULL DEFAULT 'dead_letter' CHECK (status IN ('dead_letter','requeued','resolved')),
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_failed_jobs_status_created ON failed_jobs(status, created_at);

CREATE OR REPLACE FUNCTION reserve_inventory_and_insert_order(
  p_order_key text,
  p_source text,
  p_external_order_id text,
  p_customer_email text,
  p_sku text,
  p_quantity integer,
  p_unit_price numeric,
  p_currency text,
  p_order_status text,
  p_retry_recovered boolean,
  p_raw_payload jsonb,
  p_created_at timestamptz
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
  current_available integer;
BEGIN
  IF EXISTS (SELECT 1 FROM orders WHERE order_key = p_order_key) THEN
    RETURN 'duplicate';
  END IF;

  SELECT available_quantity INTO current_available
  FROM inventory
  WHERE sku = p_sku
  FOR UPDATE;

  IF current_available IS NULL THEN
    RETURN 'unknown_sku';
  END IF;
  IF current_available < p_quantity THEN
    RETURN 'insufficient_stock';
  END IF;

  UPDATE inventory
  SET available_quantity = available_quantity - p_quantity,
      reserved_quantity = reserved_quantity + p_quantity,
      updated_at = now()
  WHERE sku = p_sku;

  INSERT INTO orders (
    order_key, source, external_order_id, customer_email, sku, quantity,
    unit_price, currency, order_status, retry_recovered, raw_payload, created_at
  ) VALUES (
    p_order_key, p_source, p_external_order_id, p_customer_email, p_sku, p_quantity,
    p_unit_price, p_currency, p_order_status, p_retry_recovered, p_raw_payload, p_created_at
  );

  RETURN 'processed';
EXCEPTION WHEN unique_violation THEN
  RETURN 'duplicate';
END;
$$;

CREATE OR REPLACE FUNCTION reserve_inventory_and_insert_order_b64(
  p_payload_b64 text,
  p_retry_recovered boolean
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
  p jsonb := convert_from(decode(p_payload_b64, 'base64'), 'UTF8')::jsonb;
BEGIN
  RETURN reserve_inventory_and_insert_order(
    p->>'order_key', p->>'source', p->>'external_order_id', p->>'customer_email', p->>'sku',
    (p->>'quantity')::integer, (p->>'unit_price')::numeric, p->>'currency', p->>'order_status',
    p_retry_recovered, COALESCE(p->'raw_payload', p), (p->>'created_at')::timestamptz
  );
END;
$$;

CREATE OR REPLACE FUNCTION record_exception_b64(
  p_payload_b64 text,
  p_error_code text,
  p_error_message text
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  p jsonb := convert_from(decode(p_payload_b64, 'base64'), 'UTF8')::jsonb;
  k text := COALESCE(p->>'order_key', p->>'source' || ':' || COALESCE(p->>'external_order_id','missing')) || ':' || p_error_code;
BEGIN
  INSERT INTO exceptions (idempotency_key, source, external_order_id, order_key, error_code, error_message, payload)
  VALUES (k, p->>'source', p->>'external_order_id', p->>'order_key', p_error_code, p_error_message, COALESCE(p->'raw_payload', p))
  ON CONFLICT (idempotency_key) DO UPDATE SET
    error_message = EXCLUDED.error_message,
    payload = EXCLUDED.payload;
END;
$$;

CREATE OR REPLACE FUNCTION record_failed_job_b64(
  p_payload_b64 text,
  p_error_code text,
  p_error_message text,
  p_attempts integer
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  p jsonb := convert_from(decode(p_payload_b64, 'base64'), 'UTF8')::jsonb;
  k text := COALESCE(p->>'order_key', p->>'source' || ':' || COALESCE(p->>'external_order_id','missing')) || ':' || p_error_code;
BEGIN
  INSERT INTO failed_jobs (job_key, order_key, source, external_order_id, error_code, error_message, payload, attempts)
  VALUES (k, p->>'order_key', p->>'source', p->>'external_order_id', p_error_code, p_error_message, COALESCE(p->'raw_payload', p), p_attempts)
  ON CONFLICT (job_key) DO UPDATE SET
    error_message = EXCLUDED.error_message,
    payload = EXCLUDED.payload,
    attempts = GREATEST(failed_jobs.attempts, EXCLUDED.attempts);
END;
$$;
