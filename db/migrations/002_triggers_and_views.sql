-- =============================================================================
-- BI DWH — Triggers, Audit, and Analytical Views
-- =============================================================================

-- ------------------------------------------------------------------------------
-- Helper: auto-update updated_at
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fact_transactions_updated
    BEFORE UPDATE ON fact_transactions
    FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();

CREATE TRIGGER trg_fact_sales_updated
    BEFORE UPDATE ON fact_sales
    FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();

CREATE TRIGGER trg_fact_expenses_updated
    BEFORE UPDATE ON fact_expenses
    FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();

CREATE TRIGGER trg_dim_counterparty_updated
    BEFORE UPDATE ON dim_counterparty
    FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();

CREATE TRIGGER trg_bi_users_updated
    BEFORE UPDATE ON bi_users
    FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();

-- ------------------------------------------------------------------------------
-- Audit trigger (generic — logs old/new values for UPDATE, full row for others)
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_audit_trigger()
RETURNS TRIGGER AS $$
DECLARE
    v_record_id BIGINT;
    v_old JSONB;
    v_new JSONB;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_record_id = OLD.transaction_id;
        v_old = to_jsonb(OLD);
        INSERT INTO audit_log (table_name, record_id, action, changed_by, old_values, new_values)
        VALUES (TG_TABLE_NAME, v_record_id, 'DELETE', COALESCE(current_setting('app.current_user', true), 'system'), v_old, NULL);
        RETURN OLD;
    ELSIF TG_OP = 'INSERT' THEN
        v_record_id = NEW.transaction_id;
        v_new = to_jsonb(NEW);
        INSERT INTO audit_log (table_name, record_id, action, changed_by, old_values, new_values)
        VALUES (TG_TABLE_NAME, v_record_id, 'INSERT', COALESCE(current_setting('app.current_user', true), 'system'), NULL, v_new);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        v_record_id = NEW.transaction_id;
        v_old = to_jsonb(OLD);
        v_new = to_jsonb(NEW);
        INSERT INTO audit_log (table_name, record_id, action, changed_by, old_values, new_values)
        VALUES (TG_TABLE_NAME, v_record_id, 'UPDATE', COALESCE(current_setting('app.current_user', true), 'system'), v_old, v_new);
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Apply audit only to mutable transactional tables where we need full audit trail
CREATE TRIGGER trg_audit_fact_transactions
    AFTER INSERT OR UPDATE OR DELETE ON fact_transactions
    FOR EACH ROW EXECUTE FUNCTION fn_audit_trigger();

-- ------------------------------------------------------------------------------
-- Analytical Views (for Metabase)
-- ------------------------------------------------------------------------------

-- P&L Summary by month
CREATE OR REPLACE VIEW vw_pnl_monthly AS
SELECT
    d.year,
    d.month,
    d.month_name,
    a.account_type,
    a.pnl_section,
    a.account_code,
    a.account_name,
    COALESCE(SUM(t.amount_rub), 0) AS amount_rub
FROM dim_date d
CROSS JOIN dim_account a
LEFT JOIN fact_transactions t ON t.date_id = d.date_id AND t.account_id = a.account_id AND NOT t.is_deleted
GROUP BY d.year, d.month, d.month_name, a.account_type, a.pnl_section, a.account_code, a.account_name;

-- P&L Waterfall (Revenue → Gross Profit → Operating Profit → Net Profit)
CREATE OR REPLACE VIEW vw_pnl_waterfall AS
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        a.account_type,
        SUM(CASE WHEN t.amount_rub IS NOT NULL THEN t.amount_rub ELSE 0 END) AS amount_rub
    FROM dim_date d
    CROSS JOIN dim_account a
    LEFT JOIN fact_transactions t ON t.date_id = d.date_id AND t.account_id = a.account_id AND NOT t.is_deleted
    GROUP BY d.year, d.month, a.account_type
),
rollup AS (
    SELECT
        year,
        month,
        COALESCE(SUM(CASE WHEN account_type = 'revenue' THEN amount_rub END), 0) AS revenue,
        COALESCE(SUM(CASE WHEN account_type = 'cogs' THEN amount_rub END), 0) AS cogs,
        COALESCE(SUM(CASE WHEN account_type = 'opex' THEN amount_rub END), 0) AS opex,
        COALESCE(SUM(CASE WHEN account_type = 'tax' THEN amount_rub END), 0) AS tax,
        COALESCE(SUM(CASE WHEN account_type = 'other_income' THEN amount_rub END), 0) AS other_income,
        COALESCE(SUM(CASE WHEN account_type = 'other_expense' THEN amount_rub END), 0) AS other_expense
    FROM monthly
    GROUP BY year, month
)
SELECT
    year,
    month,
    revenue,
    cogs,
    revenue - cogs AS gross_profit,
    opex,
    revenue - cogs - opex AS operating_profit,
    tax,
    other_income,
    other_expense,
    revenue - cogs - opex - tax + other_income - other_expense AS net_profit,
    CASE WHEN revenue != 0 THEN ROUND((revenue - cogs) / revenue * 100, 2) ELSE 0 END AS gross_margin_pct,
    CASE WHEN revenue != 0 THEN ROUND((revenue - cogs - opex) / revenue * 100, 2) ELSE 0 END AS operating_margin_pct,
    CASE WHEN revenue != 0 THEN ROUND((revenue - cogs - opex - tax + other_income - other_expense) / revenue * 100, 2) ELSE 0 END AS net_margin_pct
FROM rollup;

-- Cashflow by month (simplified — accrual-based approximation)
CREATE OR REPLACE VIEW vw_cashflow_monthly AS
SELECT
    d.year,
    d.month,
    d.month_name,
    COALESCE(SUM(CASE WHEN a.account_type = 'revenue' THEN t.amount_rub ELSE 0 END), 0) AS inflows_revenue,
    COALESCE(SUM(CASE WHEN a.account_type IN ('cogs','opex','tax','other_expense') THEN t.amount_rub ELSE 0 END), 0) AS outflows_total,
    COALESCE(SUM(CASE WHEN a.account_type = 'other_income' THEN t.amount_rub ELSE 0 END), 0) AS inflows_other,
    COALESCE(SUM(CASE WHEN a.account_type IN ('revenue','other_income') THEN t.amount_rub ELSE 0 END), 0)
        - COALESCE(SUM(CASE WHEN a.account_type IN ('cogs','opex','tax','other_expense') THEN t.amount_rub ELSE 0 END), 0) AS net_cashflow
FROM dim_date d
LEFT JOIN fact_transactions t ON t.date_id = d.date_id AND NOT t.is_deleted
LEFT JOIN dim_account a ON a.account_id = t.account_id
GROUP BY d.year, d.month, d.month_name;

-- Expenses breakdown by category and department
CREATE OR REPLACE VIEW vw_expenses_breakdown AS
SELECT
    e.expense_date,
    d.year,
    d.month,
    dep.department_name,
    a.account_name,
    e.expense_category,
    e.expense_item,
    e.amount_rub,
    e.vat_amount,
    e.amount_rub - e.vat_amount AS amount_without_vat,
    e.source_system,
    e.is_manual_entry
FROM fact_expenses e
JOIN dim_date d ON d.date_id = e.date_id
LEFT JOIN dim_department dep ON dep.department_id = e.department_id
LEFT JOIN dim_account a ON a.account_id = e.account_id
WHERE NOT e.is_deleted;

-- Sales funnel ( amoCRM stages)
CREATE OR REPLACE VIEW vw_sales_funnel AS
SELECT
    s.deal_date,
    d.year,
    d.month,
    s.pipeline_name,
    s.stage_name,
    s.deal_status,
    COUNT(*) AS deals_count,
    SUM(s.amount_rub) AS amount_rub,
    AVG(s.amount_rub) AS avg_deal_size,
    SUM(CASE WHEN s.deal_status = 'won' THEN s.amount_rub ELSE 0 END) AS won_amount,
    SUM(CASE WHEN s.deal_status = 'lost' THEN s.amount_rub ELSE 0 END) AS lost_amount
FROM fact_sales s
JOIN dim_date d ON d.date_id = s.date_id
WHERE NOT s.is_deleted
GROUP BY s.deal_date, d.year, d.month, s.pipeline_name, s.stage_name, s.deal_status;

-- KPI: sales managers
CREATE OR REPLACE VIEW vw_kpi_sales_managers AS
SELECT
    d.year,
    d.month,
    emp.full_name AS manager_name,
    dep.department_name,
    COUNT(*) AS deals_count,
    SUM(CASE WHEN s.deal_status = 'won' THEN 1 ELSE 0 END) AS won_deals,
    SUM(CASE WHEN s.deal_status = 'lost' THEN 1 ELSE 0 END) AS lost_deals,
    SUM(s.amount_rub) AS total_amount,
    SUM(CASE WHEN s.deal_status = 'won' THEN s.amount_rub ELSE 0 END) AS won_amount,
    AVG(s.amount_rub) AS avg_deal_size,
    CASE WHEN COUNT(*) > 0 THEN ROUND(SUM(CASE WHEN s.deal_status = 'won' THEN 1 ELSE 0 END)::NUMERIC / COUNT(*) * 100, 2) ELSE 0 END AS win_rate_pct,
    SUM(s.margin_amount_rub) AS total_margin,
    CASE WHEN SUM(s.amount_rub) > 0 THEN ROUND(SUM(s.margin_amount_rub) / SUM(s.amount_rub) * 100, 2) ELSE 0 END AS avg_margin_pct
FROM fact_sales s
JOIN dim_date d ON d.date_id = s.date_id
LEFT JOIN dim_employee emp ON emp.employee_id = s.employee_id
LEFT JOIN dim_department dep ON dep.department_id = s.department_id
WHERE NOT s.is_deleted
GROUP BY d.year, d.month, emp.full_name, dep.department_name;

-- Currency exposure summary
CREATE OR REPLACE VIEW vw_currency_exposure AS
SELECT
    c.currency_code,
    c.currency_name,
    DATE_TRUNC('month', t.transaction_date) AS month,
    SUM(t.amount_original) AS amount_original,
    SUM(t.amount_rub) AS amount_rub,
    AVG(er.rate_value) AS avg_rate_for_month,
    SUM(t.amount_original * er.rate_value) AS implied_amount_rub
FROM fact_transactions t
JOIN dim_currency c ON c.currency_id = t.currency_id
LEFT JOIN fact_exchange_rates er ON er.date_id = t.date_id AND er.currency_from = c.currency_code AND er.currency_to = 'RUB'
WHERE NOT t.is_deleted
GROUP BY c.currency_code, c.currency_name, DATE_TRUNC('month', t.transaction_date);

-- ------------------------------------------------------------------------------
-- Comments for Metabase discovery
-- ------------------------------------------------------------------------------
COMMENT ON TABLE dim_date IS 'Calendar dimension — pre-generated date spine';
COMMENT ON TABLE dim_currency IS 'Currency reference (RUB, USD, CNY, EUR)';
COMMENT ON TABLE dim_counterparty IS 'Customers, suppliers, partners — deduplicated master data';
COMMENT ON TABLE dim_account IS 'Chart of accounts aligned with P&L structure';
COMMENT ON TABLE fact_transactions IS 'General ledger transactions from 1C + manual entries + integrations';
COMMENT ON TABLE fact_sales IS 'Deals pipeline from amoCRM and 1C invoices';
COMMENT ON TABLE fact_expenses IS 'Expenses from Google Sheets + manual input + 1C';
COMMENT ON TABLE audit_log IS 'Full audit trail for transactional tables';
COMMENT ON VIEW vw_pnl_monthly IS 'Monthly P&L detail by account — connect in Metabase as Question';
COMMENT ON VIEW vw_pnl_waterfall IS 'High-level P&L waterfall with margins — primary executive dashboard';
COMMENT ON VIEW vw_cashflow_monthly IS 'Monthly cashflow approximation — inflows, outflows, net';
COMMENT ON VIEW vw_sales_funnel IS 'Sales pipeline stages and conversion amounts';
COMMENT ON VIEW vw_kpi_sales_managers IS 'Manager-level sales KPIs — use with Row-Level Security in Metabase';
