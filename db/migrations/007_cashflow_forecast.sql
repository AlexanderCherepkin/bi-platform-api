-- ML cashflow forecast storage

CREATE TABLE IF NOT EXISTS cashflow_forecasts (
    forecast_id SERIAL PRIMARY KEY,
    forecast_date DATE NOT NULL,
    metric_type VARCHAR(20) NOT NULL CHECK (metric_type IN ('inflow', 'outflow', 'net_cashflow')),
    predicted_value NUMERIC(18, 4) NOT NULL,
    lower_bound NUMERIC(18, 4) NOT NULL,
    upper_bound NUMERIC(18, 4) NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    is_forecast BOOLEAN NOT NULL DEFAULT TRUE,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (forecast_date, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_cashflow_forecasts_date ON cashflow_forecasts(forecast_date);
CREATE INDEX IF NOT EXISTS idx_cashflow_forecasts_type ON cashflow_forecasts(metric_type);
