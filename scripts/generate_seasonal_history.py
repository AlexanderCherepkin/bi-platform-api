"""
Generate synthetic seasonal cashflow history for ML forecast demo.

Usage:
    docker compose exec api python scripts/generate_seasonal_history.py
"""
from __future__ import annotations

import os
import random
from datetime import date, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values

DB = os.getenv("DATABASE_URL", "postgresql://bi_admin:bi_secret@db:5432/bi_dwh")

def main():
    random.seed(42)
    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT account_id FROM dim_account WHERE account_type = 'revenue' AND account_code = 'REV-001'")
    rev_id = cur.fetchone()[0]
    cur.execute("SELECT account_id FROM dim_account WHERE account_type = 'cogs' AND account_code = 'COGS-001'")
    cogs_id = cur.fetchone()[0]
    cur.execute("SELECT account_id FROM dim_account WHERE account_type = 'opex' AND account_code = 'OPEX-001'")
    opex_id = cur.fetchone()[0]
    cur.execute("SELECT currency_id FROM dim_currency WHERE currency_code = 'RUB'")
    rub_id = cur.fetchone()[0]

    # Remove prior demo history for clean repeatable demo
    cur.execute("DELETE FROM fact_transactions WHERE source_system = 'seasonal_demo'")

    start = date(2024, 1, 1)
    end = date(2026, 6, 30)
    transactions = []

    d = start
    while d <= end:
        # deterministic seasonal pattern + noise
        month = d.month
        base_revenue = 400_000 + 120_000 * (1 if month in (3, 6, 9, 12) else 0.2 if month in (1, 2) else 0.6)
        base_cogs = base_revenue * 0.45
        base_opex = 120_000 + 20_000 * (1 if month in (1, 12) else 0)

        # split across ~4 days per month
        for _ in range(4):
            if random.random() < 0.8:
                amt = round(base_revenue / 4 * random.uniform(0.85, 1.15), 2)
                transactions.append((
                    d, d, d, f"demo-rev-{d.isoformat()}-{len(transactions)}", "invoice",
                    rev_id, None, None, None, None,
                    rub_id, amt, amt, round(amt * 0.2, 2) if random.random() < 0.5 else 0, 20,
                    None, None, "Продажа (сезонный демо)", "seasonal_demo", f"demo-{len(transactions)}", False
                ))
            if random.random() < 0.8:
                amt = round(base_cogs / 4 * random.uniform(0.85, 1.15), 2)
                transactions.append((
                    d, d, d, f"demo-cogs-{d.isoformat()}-{len(transactions)}", "delivery_note",
                    cogs_id, None, None, None, None,
                    rub_id, amt, amt, round(amt * 0.2, 2) if random.random() < 0.5 else 0, 20,
                    None, None, "Себестоимость (сезонный демо)", "seasonal_demo", f"demo-{len(transactions)}", False
                ))
            if random.random() < 0.9:
                amt = round(base_opex / 4 * random.uniform(0.9, 1.1), 2)
                transactions.append((
                    d, d, d, f"demo-opex-{d.isoformat()}-{len(transactions)}", "expense_report",
                    opex_id, None, None, None, None,
                    rub_id, amt, amt, round(amt * 0.2, 2) if random.random() < 0.5 else 0, 20,
                    None, None, "OPEX (сезонный демо)", "seasonal_demo", f"demo-{len(transactions)}", False
                ))
        d += timedelta(days=1)

    execute_values(cur, """
        INSERT INTO fact_transactions (
            transaction_date, posting_date, date_id, document_number, document_type,
            account_id, counterparty_id, department_id, product_id, employee_id,
            currency_id, amount_original, amount_rub, vat_amount, vat_rate,
            quantity, unit_price, description, source_system, source_id, is_manual_entry
        ) VALUES %s
    """, transactions)
    conn.commit()
    print(f"Inserted {len(transactions)} seasonal demo transactions from {start} to {end}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
