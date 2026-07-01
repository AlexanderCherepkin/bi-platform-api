-- Staging tables for self-service CSV/XLSX imports

CREATE TABLE IF NOT EXISTS staging_file_uploads (
    upload_id BIGSERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT,
    file_hash VARCHAR(64),
    target_table VARCHAR(50) NOT NULL CHECK (target_table IN ('fact_transactions', 'fact_expenses')),
    uploaded_by VARCHAR(255) NOT NULL,
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    total_rows INTEGER NOT NULL DEFAULT 0,
    valid_rows INTEGER NOT NULL DEFAULT 0,
    invalid_rows INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'validated', 'applied', 'rejected')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS staging_rows (
    staging_id BIGSERIAL PRIMARY KEY,
    upload_id BIGINT NOT NULL REFERENCES staging_file_uploads(upload_id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    target_table VARCHAR(50) NOT NULL,
    source_data JSONB NOT NULL,
    mapped_data JSONB,
    validation_errors JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'valid', 'invalid')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staging_uploads_status ON staging_file_uploads(status);
CREATE INDEX IF NOT EXISTS idx_staging_uploads_uploaded_by ON staging_file_uploads(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_staging_rows_upload_id ON staging_rows(upload_id);
CREATE INDEX IF NOT EXISTS idx_staging_rows_status ON staging_rows(status);
