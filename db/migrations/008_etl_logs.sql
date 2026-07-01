-- ETL execution logs for data quality anomalies and failures

CREATE TABLE IF NOT EXISTS etl_logs (
    log_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES etl_runs(run_id) ON DELETE SET NULL,
    log_type VARCHAR(50) NOT NULL CHECK (log_type IN ('info', 'warning', 'error', 'dq_anomaly')),
    source VARCHAR(50),
    metric_name VARCHAR(100),
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_etl_logs_run_id ON etl_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_etl_logs_type ON etl_logs(log_type);
CREATE INDEX IF NOT EXISTS idx_etl_logs_created_at ON etl_logs(created_at DESC);
