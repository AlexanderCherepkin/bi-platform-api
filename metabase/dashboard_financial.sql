-- =============================================================================
-- Metabase Questions / SQL Snippets for Financial Dashboard (MVP)
-- Paste these as "Native Query" questions in Metabase and add to a Dashboard
-- =============================================================================

-- ------------------------------------------------------------------------------
-- Q1: Executive P&L Waterfall (Year-to-Date)
-- ------------------------------------------------------------------------------
SELECT
    year,
    month,
    revenue,
    cogs,
    gross_profit,
    opex,
    operating_profit,
    tax,
    net_profit,
    gross_margin_pct,
    operating_margin_pct,
    net_margin_pct
FROM vw_pnl_waterfall
WHERE year = EXTRACT(YEAR FROM CURRENT_DATE)
ORDER BY month;

-- ------------------------------------------------------------------------------
-- Q2: Monthly Cashflow
-- ------------------------------------------------------------------------------
SELECT
    month,
    month_name,
    inflows_revenue,
    outflows_total,
    net_cashflow
FROM vw_cashflow_monthly
WHERE year = EXTRACT(YEAR FROM CURRENT_DATE)
ORDER BY month;

-- ------------------------------------------------------------------------------
-- Q3: Expense Breakdown by Category (Current Month)
-- ------------------------------------------------------------------------------
SELECT
    expense_category,
    SUM(amount_rub) AS total_rub,
    SUM(vat_amount) AS vat_rub,
    COUNT(*) AS entries
FROM vw_expenses_breakdown
WHERE year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND month = EXTRACT(MONTH FROM CURRENT_DATE)
GROUP BY expense_category
ORDER BY total_rub DESC;

-- ------------------------------------------------------------------------------
-- Q4: OPEX Trend by Department (Last 12 Months)
-- ------------------------------------------------------------------------------
SELECT
    year,
    month,
    department_name,
    SUM(amount_rub) AS total_rub
FROM vw_expenses_breakdown
WHERE date_id >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY year, month, department_name
ORDER BY year, month;

-- ------------------------------------------------------------------------------
-- Q5: Revenue vs Plan (manual plan table not yet created; placeholder)
-- ------------------------------------------------------------------------------
-- After sales data is imported from amoCRM / 1C, use fact_sales:
SELECT
    year,
    month,
    SUM(CASE WHEN deal_status = 'won' THEN amount_rub ELSE 0 END) AS revenue_won,
    SUM(amount_rub) AS revenue_total_pipeline
FROM vw_sales_funnel
WHERE deal_status = 'won'
GROUP BY year, month
ORDER BY year, month;

-- ------------------------------------------------------------------------------
-- Q6: Currency Exposure Summary
-- ------------------------------------------------------------------------------
SELECT
    currency_code,
    month,
    amount_original,
    amount_rub
FROM vw_currency_exposure
WHERE month >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '3 months'
ORDER BY month, currency_code;
