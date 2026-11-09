-- 004: queue resilience for Make.com handoffs
ALTER TABLE relay_queue ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE relay_queue ADD COLUMN IF NOT EXISTS claimed BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS relay_errors (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  component TEXT NOT NULL,
  reel_id TEXT,
  message TEXT NOT NULL,
  payload JSONB
);
CREATE INDEX IF NOT EXISTS relay_errors_ts_idx ON relay_errors (ts DESC);