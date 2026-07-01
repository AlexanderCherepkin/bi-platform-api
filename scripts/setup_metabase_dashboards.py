import requests
import sys

METABASE_URL = "https://incidents-vegetation-obvious-copper.trycloudflare.com"
ADMIN_EMAIL = "admin@company.local"
ADMIN_PASSWORD = "CorpB1_Pass2024!"
DB_ID = 2

session = requests.Session()

# Login
r = session.post(f"{METABASE_URL}/api/session", json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
if r.status_code != 200:
    print("Login failed:", r.text)
    sys.exit(1)
token = r.json()["id"]
headers = {"X-Metabase-Session": token, "Content-Type": "application/json"}

# Create collection
coll = session.post(f"{METABASE_URL}/api/collection", headers=headers, json={
    "name": "BI Dashboards",
    "color": "#509EE3",
    "description": "Корпоративные дашборды бизнес-аналитики"
})
coll_id = coll.json().get("id")
print("Collection ID:", coll_id)

# Helper to create cards
cards = []

def create_card(name, display, sql, viz_settings=None):
    payload = {
        "name": name,
        "display": display,
        "dataset_query": {
            "type": "native",
            "native": {
                "query": sql,
                "template-tags": {}
            },
            "database": DB_ID
        },
        "visualization_settings": viz_settings or {},
        "collection_id": coll_id
    }
    r = session.post(f"{METABASE_URL}/api/card", headers=headers, json=payload)
    if r.status_code not in (200, 202):
        print(f"Card '{name}' failed:", r.status_code, r.text[:200])
        return None
    cid = r.json().get("id")
    print(f"Created card '{name}' ID:", cid)
    return cid

# 1. P&L Waterfall (table)
cards.append(create_card(
    "P&L Waterfall",
    "table",
    "SELECT year, month, revenue, cogs, gross_profit, opex, operating_profit, net_profit, gross_margin_pct, operating_margin_pct, net_margin_pct FROM vw_pnl_waterfall WHERE revenue > 0 ORDER BY year DESC, month DESC LIMIT 50"
))

# 2. Revenue Trend (line)
cards.append(create_card(
    "Revenue Trend",
    "line",
    "SELECT year, month, revenue FROM vw_pnl_waterfall WHERE revenue > 0 ORDER BY year, month",
    {"graph.dimensions": ["year", "month"], "graph.metrics": ["revenue"]}
))

# 3. Cashflow Overview (bar)
cards.append(create_card(
    "Cashflow Overview",
    "bar",
    "SELECT year, month, month_name, inflows_revenue, outflows_total, net_cashflow FROM vw_cashflow_monthly WHERE net_cashflow != 0 ORDER BY year, month",
    {"graph.dimensions": ["month_name"], "graph.metrics": ["inflows_revenue", "outflows_total", "net_cashflow"]}
))

# 4. Sales Funnel (funnel)
cards.append(create_card(
    "Sales Funnel",
    "funnel",
    "SELECT stage_name, SUM(deals_count) AS deals_count, SUM(amount_rub) AS amount_rub FROM vw_sales_funnel GROUP BY stage_name ORDER BY amount_rub DESC"
))

# 5. Top Expenses by Category (bar)
cards.append(create_card(
    "Top Expenses by Category",
    "bar",
    "SELECT expense_category, SUM(amount_rub) as total FROM fact_expenses GROUP BY expense_category ORDER BY total DESC LIMIT 20",
    {"graph.dimensions": ["expense_category"], "graph.metrics": ["total"]}
))

# 6. KPI Sales Managers (table)
cards.append(create_card(
    "KPI Sales Managers",
    "table",
    "SELECT * FROM vw_kpi_sales_managers ORDER BY total_amount DESC LIMIT 50"
))

# 7. Total Revenue (scalar)
cards.append(create_card(
    "Total Revenue",
    "scalar",
    "SELECT COALESCE(SUM(amount_rub),0) as total FROM fact_transactions WHERE account_id = 1"
))

# 8. Total Expenses (scalar)
cards.append(create_card(
    "Total Expenses",
    "scalar",
    "SELECT COALESCE(SUM(amount_rub),0) as total FROM fact_expenses"
))

# 9. Net Profit (scalar)
cards.append(create_card(
    "Net Profit",
    "scalar",
    "SELECT COALESCE(SUM(CASE WHEN account_type = 'revenue' THEN amount_rub ELSE -amount_rub END),0) as profit FROM fact_transactions ft JOIN dim_account da ON ft.account_id = da.account_id"
))

# 10. Monthly Margin Trend (line)
cards.append(create_card(
    "Margin Trend",
    "line",
    "SELECT year, month, gross_margin_pct, operating_margin_pct, net_margin_pct FROM vw_pnl_waterfall WHERE revenue > 0 ORDER BY year, month",
    {"graph.dimensions": ["year", "month"], "graph.metrics": ["gross_margin_pct", "operating_margin_pct", "net_margin_pct"]}
))

# 11. Leads by Channel (pie)
cards.append(create_card(
    "Leads by Channel",
    "pie",
    "SELECT source_channel, COUNT(*) as leads FROM fact_crm_leads GROUP BY source_channel ORDER BY leads DESC",
    {"pie.dimension": "source_channel", "pie.metric": "leads"}
))

# 12. Expenses Breakdown (table)
cards.append(create_card(
    "Expenses Breakdown",
    "table",
    "SELECT * FROM vw_expenses_breakdown ORDER BY expense_month DESC LIMIT 50"
))

card_ids = [c for c in cards if c is not None]
print(f"Created {len(card_ids)} cards")

# Create dashboard
dash = session.post(f"{METABASE_URL}/api/dashboard", headers=headers, json={
    "name": "Executive Overview",
    "description": "Главный дашборд для руководства: P&L, Cashflow, KPI, воронка",
    "collection_id": coll_id,
    "parameters": []
})
dash_id = dash.json().get("id")
print("Dashboard ID:", dash_id)

# Add cards to dashboard in a grid layout (4 columns, 3 rows)
# Layout: [x, y, width, height] in grid units (18x12 typically, but we use 4x4 cards)
# Metabase uses size_x, size_y, col, row
layouts = [
    {"col": 0, "row": 0, "sizeX": 4, "sizeY": 3},   # P&L Waterfall (big table)
    {"col": 4, "row": 0, "sizeX": 4, "sizeY": 3},   # Revenue Trend
    {"col": 8, "row": 0, "sizeX": 4, "sizeY": 3},  # Cashflow
    {"col": 12, "row": 0, "sizeX": 4, "sizeY": 3}, # Sales Funnel
    {"col": 0, "row": 3, "sizeX": 3, "sizeY": 2},  # Total Revenue scalar
    {"col": 3, "row": 3, "sizeX": 3, "sizeY": 2},  # Total Expenses scalar
    {"col": 6, "row": 3, "sizeX": 3, "sizeY": 2},  # Net Profit scalar
    {"col": 9, "row": 3, "sizeX": 3, "sizeY": 2},  # Margin Trend
    {"col": 12, "row": 3, "sizeX": 4, "sizeY": 3}, # Top Expenses
    {"col": 0, "row": 5, "sizeX": 6, "sizeY": 3},  # KPI Managers
    {"col": 6, "row": 5, "sizeX": 3, "sizeY": 3},  # Leads by Channel
    {"col": 9, "row": 5, "sizeX": 4, "sizeY": 3},  # Expenses Breakdown
]

for idx, card_id in enumerate(card_ids):
    if idx >= len(layouts):
        break
    l = layouts[idx]
    r = session.post(f"{METABASE_URL}/api/dashboard/{dash_id}/cards", headers=headers, json={
        "cardId": card_id,
        "col": l["col"],
        "row": l["row"],
        "sizeX": l["sizeX"],
        "sizeY": l["sizeY"],
        "series": [],
        "parameter_mappings": []
    })
    if r.status_code not in (200, 202):
        print(f"Failed to add card {card_id}:", r.status_code, r.text[:200])
    else:
        print(f"Added card {card_id} to dashboard")

print("Done! Dashboard URL:", f"{METABASE_URL}/dashboard/{dash_id}")
