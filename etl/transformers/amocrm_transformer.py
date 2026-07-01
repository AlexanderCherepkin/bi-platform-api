from datetime import date, datetime
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text


def _ts_to_date(ts: int | None) -> date | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts).date()


def transform_amocrm(raw: dict[str, list[dict[str, Any]]], db: Session):
    counterparties = []
    employees = []
    leads = []
    deals = []

    currency_map = {r[0]: r[1] for r in db.execute(text("SELECT currency_code, currency_id FROM dim_currency")).fetchall()}

    for lead in raw.get("leads", []):
        created = _ts_to_date(lead.get("created_at"))
        converted = _ts_to_date(lead.get("updated_at")) if lead.get("lead_status") == "converted" else None
        contacts = lead.get("_embedded", {}).get("contacts", [])
        counterparty_id_src = contacts[0].get("id") if contacts else None
        if counterparty_id_src:
            counterparties.append({
                "source_system": "amoCRM",
                "source_id": str(counterparty_id_src),
                "counterparty_name": lead.get("name", "Неизвестно"),
                "counterparty_type": "customer",
            })
        employees.append({
            "source_system": "amoCRM",
            "source_id": str(lead.get("responsible_user_id")),
            "full_name": f"Менеджер {lead.get('responsible_user_id')}",
            "department_id": None,
        })
        leads.append({
            "source_system": "amoCRM",
            "source_id": str(lead.get("id")),
            "created_date": created,
            "converted_date": converted,
            "counterparty_id_src": counterparty_id_src,
            "employee_id_src": lead.get("responsible_user_id"),
            "pipeline_name": lead.get("pipeline_name", "Основная"),
            "source_channel": lead.get("source_channel", "unknown"),
            "lead_status": lead.get("lead_status", "new"),
            "utm_source": lead.get("utm_source", ""),
            "utm_medium": lead.get("utm_medium", ""),
        })

    for deal in raw.get("deals", []):
        created = _ts_to_date(deal.get("created_at"))
        closed = _ts_to_date(deal.get("closed_at"))
        currency = deal.get("currency", "RUB")
        amount = float(deal.get("price", 0))
        deals.append({
            "source_system": "amoCRM",
            "source_id": str(deal.get("id")),
            "deal_date": created or date.today(),
            "close_date": closed,
            "employee_id_src": deal.get("responsible_user_id"),
            "department_id": None,
            "stage_name": deal.get("stage_name", ""),
            "pipeline_name": deal.get("pipeline_name", ""),
            "deal_status": deal.get("deal_status", "open"),
            "amount_original": amount,
            "amount_rub": amount,
            "currency_id": currency_map.get(currency, 1),
            "margin_amount_rub": None,
            "cost_amount_rub": None,
            "probability_pct": deal.get("probability_pct", 0),
            "lead_time_days": (closed - created).days if closed and created else None,
            "description": deal.get("name", ""),
        })

    return {"counterparties": counterparties, "employees": employees, "leads": leads, "deals": deals}
