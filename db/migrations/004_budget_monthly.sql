-- Budget vs Actual — monthly budget table and comparison view

CREATE TABLE IF NOT EXISTS budget_monthly (
    budget_id         BIGSERIAL PRIMARY KEY,
    year              SMALLINT NOT NULL,
    month             SMALLINT NOT NULL,
    account_id        INT NOT NULL REFERENCES dim_account(account_id),
    department_id     INT REFERENCES dim_department(department_id),
    budget_amount_rub NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (year, month, account_id, department_id)
);

CREATE INDEX IF NOT EXISTS idx_budget_monthly_period ON budget_monthly(year, month);
CREATE INDEX IF NOT EXISTS idx_budget_monthly_account ON budget_monthly(account_id);

COMMENT ON TABLE budget_monthly IS 'Monthly budget by account and optional department';

-- View: Budget vs Actual by account/month
CREATE OR REPLACE VIEW vw_budget_vs_actual AS
WITH actual AS (
    SELECT
        d.year,
        d.month,
        a.account_id,
        a.account_code,
        a.account_name,
        a.account_type,
        COALESCE(SUM(t.amount_rub), 0) AS actual_amount_rub
    FROM dim_date d
    CROSS JOIN dim_account a
    LEFT JOIN fact_transactions t ON t.date_id = d.date_id
        AND t.account_id = a.account_id
        AND NOT t.is_deleted
    GROUP BY d.year, d.month, a.account_id, a.account_code, a.account_name, a.account_type
),
budget AS (
    SELECT
        b.year,
        b.month,
        b.account_id,
        COALESCE(SUM(b.budget_amount_rub), 0) AS budget_amount_rub
    FROM budget_monthly b
    GROUP BY b.year, b.month, b.account_id
)
SELECT
    a.year,
    a.month,
    a.account_id,
    a.account_code,
    a.account_name,
    a.account_type,
    a.actual_amount_rub,
    COALESCE(b.budget_amount_rub, 0) AS budget_amount_rub,
    COALESCE(b.budget_amount_rub, 0) - a.actual_amount_rub AS variance_amount_rub,
    CASE
        WHEN COALESCE(b.budget_amount_rub, 0) = 0 THEN NULL
        ELSE ROUND((a.actual_amount_rub - COALESCE(b.budget_amount_rub, 0)) / b.budget_amount_rub * 100, 2)
    END AS variance_pct
FROM actual a
LEFT JOIN budget b ON b.year = a.year AND b.month = a.month AND b.account_id = a.account_id;

-- Seed demo budgets for revenue and opex accounts (monthly averages, 2026)
INSERT INTO budget_monthly (year, month, account_id, department_id, budget_amount_rub)
SELECT
    2026 AS year,
    month,
    account_id,
    NULL AS department_id,
    CASE
        WHEN account_type = 'revenue' THEN 600000
        WHEN account_type = 'cogs' THEN 250000
        WHEN account_type = 'opex' THEN 120000
        WHEN account_type = 'tax' THEN 30000
        WHEN account_type = 'other_income' THEN 10000
        WHEN account_type = 'other_expense' THEN 5000
        ELSE 0
    END AS budget_amount_rub
FROM dim_account,
    generate_series(1, 12) AS month
WHERE is_active = TRUE
ON CONFLICT (year, month, account_id, department_id) DO UPDATE
SET budget_amount_rub = EXCLUDED.budget_amount_rub,
    updated_at = NOW();
