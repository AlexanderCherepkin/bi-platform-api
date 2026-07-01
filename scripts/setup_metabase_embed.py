#!/usr/bin/env python3
"""
Bootstrap an embedded Metabase dashboard for the BI platform.

1. Log in to Metabase
2. Create a collection and cards based on DWH views (idempotent by card name)
3. Build a dashboard and add the cards
4. Enable public sharing and print/record the public embed URL

Environment variables:
  METABASE_URL (default http://localhost:3001)
  METABASE_ADMIN_EMAIL (default admin@company.local)
  METABASE_ADMIN_PASSWORD (default CorpB1_Pass2024!)
"""
import os
import sys
import time
import httpx

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3001")
ADMIN_EMAIL = os.getenv("METABASE_ADMIN_EMAIL", "admin@company.local")
ADMIN_PASSWORD = os.getenv("METABASE_ADMIN_PASSWORD", "CorpB1_Pass2024!")
DASHBOARD_NAME = "Executive Overview"
COLLECTION_NAME = "BI Dashboards"

CARD_DEFINITIONS = [
    (
        "P&L Waterfall",
        "table",
        "SELECT year, month, revenue, cogs, gross_profit, opex, operating_profit, net_profit, gross_margin_pct, operating_margin_pct, net_margin_pct FROM vw_pnl_waterfall WHERE revenue > 0 ORDER BY year DESC, month DESC LIMIT 50",
        {},
    ),
    (
        "Revenue Trend",
        "line",
        "SELECT year, month, revenue FROM vw_pnl_waterfall WHERE revenue > 0 ORDER BY year, month",
        {"graph.dimensions": ["year", "month"], "graph.metrics": ["revenue"]},
    ),
    (
        "Cashflow Overview",
        "bar",
        "SELECT year, month, month_name, inflows_revenue, outflows_total, net_cashflow FROM vw_cashflow_monthly WHERE net_cashflow != 0 ORDER BY year, month",
        {"graph.dimensions": ["month_name"], "graph.metrics": ["inflows_revenue", "outflows_total", "net_cashflow"]},
    ),
    (
        "Sales Funnel",
        "bar",
        "SELECT stage_name, SUM(deals_count) AS deals_count, SUM(amount_rub) AS amount_rub FROM vw_sales_funnel GROUP BY stage_name ORDER BY amount_rub DESC",
        {"graph.dimensions": ["stage_name"], "graph.metrics": ["deals_count", "amount_rub"]},
    ),
    (
        "Total Revenue",
        "scalar",
        "SELECT COALESCE(SUM(amount_rub),0) as total FROM fact_transactions WHERE account_id = 1",
        {},
    ),
    (
        "Total Expenses",
        "scalar",
        "SELECT COALESCE(SUM(amount_rub),0) as total FROM fact_expenses",
        {},
    ),
    (
        "Net Profit",
        "scalar",
        "SELECT COALESCE(SUM(CASE WHEN account_type = 'revenue' THEN amount_rub ELSE -amount_rub END),0) as profit FROM fact_transactions ft JOIN dim_account da ON ft.account_id = da.account_id",
        {},
    ),
    (
        "Margin Trend",
        "line",
        "SELECT year, month, gross_margin_pct, operating_margin_pct, net_margin_pct FROM vw_pnl_waterfall WHERE revenue > 0 ORDER BY year, month",
        {"graph.dimensions": ["year", "month"], "graph.metrics": ["gross_margin_pct", "operating_margin_pct", "net_margin_pct"]},
    ),
    (
        "Top Expenses by Category",
        "bar",
        "SELECT expense_category, SUM(amount_rub) as total FROM fact_expenses GROUP BY expense_category ORDER BY total DESC LIMIT 20",
        {"graph.dimensions": ["expense_category"], "graph.metrics": ["total"]},
    ),
    (
        "KPI Sales Managers",
        "table",
        "SELECT * FROM vw_kpi_sales_managers ORDER BY total_amount DESC LIMIT 50",
        {},
    ),
    (
        "Leads by Channel",
        "pie",
        "SELECT source_channel, COUNT(*) as leads FROM fact_crm_leads GROUP BY source_channel ORDER BY leads DESC",
        {"pie.dimension": "source_channel", "pie.metric": "leads"},
    ),
    (
        "Expenses Breakdown",
        "table",
        "SELECT * FROM vw_expenses_breakdown ORDER BY expense_date DESC LIMIT 50",
        {},
    ),
]

LAYOUTS = [
    {"col": 0, "row": 0, "size_x": 4, "size_y": 3},
    {"col": 4, "row": 0, "size_x": 4, "size_y": 3},
    {"col": 8, "row": 0, "size_x": 4, "size_y": 3},
    {"col": 12, "row": 0, "size_x": 4, "size_y": 3},
    {"col": 0, "row": 3, "size_x": 3, "size_y": 2},
    {"col": 3, "row": 3, "size_x": 3, "size_y": 2},
    {"col": 6, "row": 3, "size_x": 3, "size_y": 2},
    {"col": 9, "row": 3, "size_x": 3, "size_y": 2},
    {"col": 12, "row": 3, "size_x": 4, "size_y": 3},
    {"col": 0, "row": 5, "size_x": 6, "size_y": 3},
    {"col": 6, "row": 5, "size_x": 3, "size_y": 3},
    {"col": 9, "row": 5, "size_x": 4, "size_y": 3},
]


def wait_for_ready(timeout: int = 120):
    print("Waiting for Metabase to be ready...")
    for _ in range(timeout):
        try:
            r = httpx.get(f"{METABASE_URL}/api/health", timeout=5.0)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print("Metabase is ready.")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("Timeout waiting for Metabase.")
    return False


def get_session_token():
    r = httpx.post(
        f"{METABASE_URL}/api/session",
        json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30.0,
    )
    if r.status_code != 200:
        print("Login failed:", r.status_code, r.text[:200])
        sys.exit(1)
    return r.json()["id"]


def get_db_id(session_id: str):
    headers = {"X-Metabase-Session": session_id}
    r = httpx.get(f"{METABASE_URL}/api/database", headers=headers, timeout=30.0)
    r.raise_for_status()
    for db in r.json().get("data", []):
        if db.get("name") == "BI DWH":
            return db["id"]
    print("BI DWH database not found in Metabase.")
    sys.exit(1)


def find_or_create_collection(session_id: str):
    headers = {"X-Metabase-Session": session_id}
    r = httpx.get(f"{METABASE_URL}/api/collection", headers=headers, timeout=30.0)
    r.raise_for_status()
    for coll in r.json():
        if coll.get("name") == COLLECTION_NAME:
            print(f"Collection exists: {coll['id']}")
            return coll["id"]
    r = httpx.post(
        f"{METABASE_URL}/api/collection",
        headers=headers,
        json={
            "name": COLLECTION_NAME,
            "color": "#509EE3",
            "description": "Корпоративные дашборды бизнес-аналитики",
        },
        timeout=30.0,
    )
    if r.status_code not in (200, 201, 202):
        print("Failed to create collection:", r.status_code, r.text[:200])
        sys.exit(1)
    cid = r.json()["id"]
    print(f"Created collection: {cid}")
    return cid


def list_cards(session_id: str, coll_id: int):
    headers = {"X-Metabase-Session": session_id}
    r = httpx.get(
        f"{METABASE_URL}/api/card?collection_id={coll_id}",
        headers=headers,
        timeout=30.0,
    )
    r.raise_for_status()
    return {c["name"]: c["id"] for c in r.json() if c.get("collection_id") == coll_id}


def create_or_update_card(session_id: str, db_id: int, coll_id: int, name: str, display: str, sql: str, viz_settings: dict):
    headers = {"X-Metabase-Session": session_id}
    existing = list_cards(session_id, coll_id)
    payload = {
        "name": name,
        "display": display,
        "dataset_query": {
            "type": "native",
            "native": {"query": sql, "template-tags": {}},
            "database": db_id,
        },
        "visualization_settings": viz_settings,
        "collection_id": coll_id,
    }
    if name in existing:
        card_id = existing[name]
        r = httpx.put(f"{METABASE_URL}/api/card/{card_id}", headers=headers, json=payload, timeout=30.0)
        if r.status_code not in (200, 201, 202):
            print(f"Card update '{name}' failed:", r.status_code, r.text[:200])
            return None
        print(f"Updated card '{name}' ID: {card_id}")
        return card_id
    r = httpx.post(f"{METABASE_URL}/api/card", headers=headers, json=payload, timeout=30.0)
    if r.status_code not in (200, 201, 202):
        print(f"Card '{name}' failed:", r.status_code, r.text[:200])
        return None
    cid = r.json().get("id")
    print(f"Created card '{name}' ID: {cid}")
    return cid


def find_or_create_dashboard(session_id: str, coll_id: int):
    headers = {"X-Metabase-Session": session_id}
    r = httpx.get(f"{METABASE_URL}/api/dashboard", headers=headers, timeout=30.0)
    r.raise_for_status()
    for d in r.json():
        if d.get("name") == DASHBOARD_NAME:
            dash_id = d["id"]
            print(f"Dashboard exists: {dash_id}")
            _ensure_dashboard_full_width(session_id, dash_id, d)
            return dash_id
    r = httpx.post(
        f"{METABASE_URL}/api/dashboard",
        headers=headers,
        json={
            "name": DASHBOARD_NAME,
            "description": "Главный дашборд для руководства: P&L, Cashflow, KPI, воронка",
            "collection_id": coll_id,
            "parameters": [],
            "width": "full",
        },
        timeout=30.0,
    )
    if r.status_code not in (200, 201, 202):
        print("Failed to create dashboard:", r.status_code, r.text[:200])
        sys.exit(1)
    did = r.json()["id"]
    print(f"Created dashboard: {did}")
    return did


def _ensure_dashboard_full_width(session_id: str, dash_id: int, dash: dict):
    if dash.get("width") == "full":
        return
    headers = {"X-Metabase-Session": session_id}
    payload = {
        "name": dash["name"],
        "description": dash.get("description"),
        "collection_id": dash.get("collection_id"),
        "parameters": dash.get("parameters", []),
        "width": "full",
    }
    r = httpx.put(f"{METABASE_URL}/api/dashboard/{dash_id}", headers=headers, json=payload, timeout=30.0)
    if r.status_code in (200, 201, 202):
        print("Set dashboard width to full")
    else:
        print("Failed to set full width:", r.status_code, r.text[:200])


def add_cards_to_dashboard(session_id: str, dash_id: int, card_ids: list[int]):
    headers = {"X-Metabase-Session": session_id}
    cards_payload = []
    for idx, card_id in enumerate(card_ids):
        if idx >= len(LAYOUTS):
            break
        l = LAYOUTS[idx]
        cards_payload.append(
            {
                "id": -(idx + 1),  # new dashcard placeholder
                "card_id": card_id,
                "col": l["col"],
                "row": l["row"],
                "size_x": l["size_x"],
                "size_y": l["size_y"],
                "parameter_mappings": [],
                "series": [],
            }
        )
    r = httpx.put(
        f"{METABASE_URL}/api/dashboard/{dash_id}/cards",
        headers=headers,
        json={"cards": cards_payload},
        timeout=60.0,
    )
    if r.status_code not in (200, 201, 202):
        print("Failed to add cards to dashboard:", r.status_code, r.text[:200])
    else:
        returned = r.json().get("cards", [])
        print(f"Added {len(returned)} cards to dashboard")


def clear_dashboard_cards(session_id: str, dash_id: int):
    headers = {"X-Metabase-Session": session_id}
    r = httpx.get(f"{METABASE_URL}/api/dashboard/{dash_id}", headers=headers, timeout=30.0)
    r.raise_for_status()
    dash = r.json()
    existing = dash.get("dashcards", [])
    if not existing:
        return
    payload = {"cards": []}
    r = httpx.put(
        f"{METABASE_URL}/api/dashboard/{dash_id}/cards",
        headers=headers,
        json=payload,
        timeout=60.0,
    )
    if r.status_code in (200, 201, 202):
        print(f"Cleared {len(existing)} existing dashcards")
    else:
        print("Failed to clear dashcards:", r.status_code, r.text[:200])


def enable_public_dashboard(session_id: str, dash_id: int):
    headers = {"X-Metabase-Session": session_id}
    r = httpx.get(f"{METABASE_URL}/api/dashboard/{dash_id}", headers=headers, timeout=30.0)
    r.raise_for_status()
    existing = r.json().get("public_uuid")
    if existing:
        print(f"Dashboard already public: {existing}")
        return existing
    r = httpx.post(
        f"{METABASE_URL}/api/dashboard/{dash_id}/public_link",
        headers=headers,
        timeout=30.0,
    )
    if r.status_code not in (200, 201, 202):
        print("Failed to enable public sharing:", r.status_code, r.text[:200])
        sys.exit(1)
    uuid = r.json().get("uuid")
    print(f"Enabled public sharing: {uuid}")
    return uuid


def write_env_file(dashboard_uuid: str):
    """Write the public Metabase URL to the Next.js env file for local dev."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "vercel-app", ".env.local")
    env_path = os.path.abspath(env_path)
    public_url = f"{METABASE_URL}/public/dashboard/{dashboard_uuid}"
    lines = [
        "# Auto-generated by scripts/setup_metabase_embed.py",
        f"NEXT_PUBLIC_METABASE_URL={METABASE_URL}",
        f"NEXT_PUBLIC_METABASE_DASHBOARD_UUID={dashboard_uuid}",
        f"NEXT_PUBLIC_METABASE_DASHBOARD_URL={public_url}",
        "",
    ]
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote embed config to {env_path}")
    print(f"Public dashboard URL: {public_url}")


def main():
    if not wait_for_ready():
        sys.exit(1)
    session_id = get_session_token()
    db_id = get_db_id(session_id)
    coll_id = find_or_create_collection(session_id)

    card_ids = []
    for name, display, sql, viz in CARD_DEFINITIONS:
        cid = create_or_update_card(session_id, db_id, coll_id, name, display, sql, viz)
        if cid:
            card_ids.append(cid)

    print(f"Prepared {len(card_ids)} cards")

    dash_id = find_or_create_dashboard(session_id, coll_id)
    clear_dashboard_cards(session_id, dash_id)
    add_cards_to_dashboard(session_id, dash_id, card_ids)

    uuid = enable_public_dashboard(session_id, dash_id)
    write_env_file(uuid)
    print("Metabase embed setup complete.")


if __name__ == "__main__":
    main()
