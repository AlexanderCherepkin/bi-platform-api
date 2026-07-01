from datetime import date, datetime
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text


def _parse_amount(value) -> float:
    if value is None:
        return 0.0
    s = str(value).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(value) -> date | None:
    if value is None:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def transform_gsheets(raw_rows: list[dict[str, Any]], db: Session):

    account_map = {r[0]: r[1] for r in db.execute(text("SELECT account_code, account_id FROM dim_account")).fetchall()}
    currency_map = {r[0]: r[1] for r in db.execute(text("SELECT currency_code, currency_id FROM dim_currency")).fetchall()}
    dept_map = {r[0]: r[1] for r in db.execute(text("SELECT department_code, department_id FROM dim_department")).fetchall()}

    staging = []
    expenses = []

    category_account = {
        "Канцелярия": "OPEX-005",
        "Маркетинг": "OPEX-003",
        "Аренда": "OPEX-002",
        "Логистика": "OPEX-006",
        "Связь": "OPEX-007",
        "ФОТ": "OPEX-001",
        "Закупки": "OPEX-004",
    }

    for idx, row in enumerate(raw_rows, start=2):
        amount = _parse_amount(row.get("amount_raw", "0"))
        expense_date = _parse_date(row.get("date_raw"))
        if not expense_date:
            continue
        currency_code = row.get("currency_raw", "RUB")
        category = row.get("category_raw", "Прочее")
        account_code = category_account.get(category, "OPEX-009")
        staging.append({
            "sheet_name": "expenses",
            "row_num": idx,
            "date_raw": row.get("date_raw"),
            "amount_raw": row.get("amount_raw"),
            "currency_raw": currency_code,
            "category_raw": category,
            "item_raw": row.get("item_raw", ""),
            "department_raw": row.get("department_raw", ""),
            "description_raw": row.get("description_raw", ""),
            "parsed_ok": True,
            "raw_row_json": row,
        })
        expenses.append({
            "expense_date": expense_date,
            "account_id": account_map.get(account_code, account_map.get("OPEX-009")),
            "department_id": dept_map.get(row.get("department_raw", "").upper()),
            "expense_category": category,
            "expense_item": row.get("item_raw", "Без названия"),
            "currency_id": currency_map.get(currency_code, 1),
            "amount_original": amount,
            "amount_rub": amount,
            "description": row.get("description_raw", ""),
            "source_system": "GoogleSheets",
            "is_manual_entry": False,
        })

    return {"staging": staging, "expenses": expenses}
