import json
from datetime import date
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def transform_onec(raw_rows: list[dict[str, Any]], db: Session):
    """Преобразует сырые строки 1С в staging + целевые dim/fact записи."""
    staging = []
    counterparties = []
    transactions = []

    account_to_dim = {r[0]: r[1] for r in db.execute(text("SELECT account_code, account_id FROM dim_account")).fetchall()}
    currency_map = {r[0]: r[1] for r in db.execute(text("SELECT currency_code, currency_id FROM dim_currency")).fetchall()}

    for row in raw_rows:
        doc_date = _parse_date(row.get("doc_date"))
        if not doc_date:
            continue
        staging.append({
            "doc_number": row.get("doc_number"),
            "doc_date": doc_date,
            "doc_type": row.get("doc_type", "unknown"),
            "organization": row.get("organization", ""),
            "counterparty_name": row.get("counterparty_name", ""),
            "counterparty_inn": row.get("counterparty_inn", ""),
            "account_debit": row.get("account_debit", ""),
            "account_credit": row.get("account_credit", ""),
            "amount": row.get("amount", 0),
            "currency_code": row.get("currency_code", "RUB"),
            "description": row.get("description", ""),
            "raw_json": json.dumps(row, default=str),
        })

        if row.get("counterparty_name") and row.get("counterparty_inn"):
            counterparties.append({
                "source_system": "1C",
                "source_id": row.get("counterparty_inn"),
                "counterparty_name": row.get("counterparty_name"),
                "counterparty_type": "supplier",
                "inn": row.get("counterparty_inn"),
            })

        debit_account = row.get("account_debit", "")
        credit_account = row.get("account_credit", "")
        account_code = debit_account if debit_account.startswith("90") or debit_account.startswith("62") else credit_account
        account_id = account_to_dim.get(account_code)
        if not account_id:
            account_id = account_to_dim.get("OE-001")

        currency_id = currency_map.get(row.get("currency_code", "RUB"), 1)
        amount = float(row.get("amount", 0))

        transactions.append({
            "transaction_date": doc_date,
            "posting_date": doc_date,
            "document_number": row.get("doc_number"),
            "document_type": row.get("doc_type", "unknown"),
            "account_id": account_id,
            "currency_id": currency_id,
            "amount_original": amount,
            "amount_rub": amount,
            "description": row.get("description", ""),
            "source_system": "1C",
            "source_id": row.get("doc_number"),
            "is_manual_entry": False,
        })

    return {"staging": staging, "counterparties": counterparties, "transactions": transactions}
