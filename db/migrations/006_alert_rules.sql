-- Alert rules and history tables

CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    condition VARCHAR(50) NOT NULL CHECK (condition IN ('drop_pct', 'rise_pct', 'below', 'above')),
    threshold_value NUMERIC(18, 4) NOT NULL,
    lookback_days INTEGER DEFAULT 7,
    severity VARCHAR(20) DEFAULT 'warning' CHECK (severity IN ('info', 'warning', 'critical')),
    schedule VARCHAR(20) DEFAULT 'daily' CHECK (schedule IN ('hourly', 'daily')),
    roles VARCHAR(50)[] DEFAULT ARRAY['admin', 'cfo'],
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts_history (
    alert_id SERIAL PRIMARY KEY,
    rule_id INTEGER REFERENCES alert_rules(rule_id) ON DELETE SET NULL,
    metric_name VARCHAR(100),
    metric_value NUMERIC(18, 4),
    threshold_value NUMERIC(18, 4),
    message TEXT NOT NULL,
    severity VARCHAR(20),
    channels VARCHAR(20)[] DEFAULT ARRAY['ui'],
    status VARCHAR(20) DEFAULT 'new' CHECK (status IN ('new', 'acknowledged', 'resolved')),
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_history_status ON alerts_history(status);
CREATE INDEX IF NOT EXISTS idx_alerts_history_created_at ON alerts_history(created_at DESC);

INSERT INTO alert_rules (name, metric_name, condition, threshold_value, lookback_days, severity, schedule, roles, description)
VALUES
    ('Падение выручки >20% (WoW)', 'revenue', 'drop_pct', 20.0, 7, 'critical', 'daily', ARRAY['admin', 'ceo', 'cfo'], 'Выручка за последние 7 дней упала более чем на 20% по сравнению с аналогичным 7-дневным периодом неделей ранее'),
    ('Отрицательный cashflow', 'net_cashflow', 'below', 0.0, 1, 'critical', 'hourly', ARRAY['admin', 'cfo'], 'Чистый cashflow за последние сутки отрицательный — угроза кассового разрыва'),
    ('Рост OPEX (MoM)', 'opex', 'rise_pct', 15.0, 30, 'warning', 'daily', ARRAY['admin', 'cfo'], 'OPEX за последние 30 дней вырос более чем на 15% по сравнению с предыдущим 30-дневным периодом')
ON CONFLICT DO NOTHING;
