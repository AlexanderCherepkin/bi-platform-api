import json
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Any


def _get_or_create_counterparty(db: Session, rows: list[dict[str, Any]]) -> dict[str, int]:
    mapping = {}
    for row in rows:
        src = row.get("source_system")
        sid = str(row.get("source_id")) if row.get("source_id") else None
        if not sid:
            continue
        key = f"{src}:{sid}"
        existing = db.execute(text("""
            SELECT counterparty_id FROM dim_counterparty
            WHERE source_system = :src AND source_id = :sid
            LIMIT 1
        """), {"src": src, "sid": sid}).fetchone()
        if existing:
            mapping[key] = existing[0]
            continue
        result = db.execute(text("""
            INSERT INTO dim_counterparty (
                source_system, source_id, counterparty_name, counterparty_type,
                inn, is_active, created_at, updated_at
            ) VALUES (
                :source_system, :source_id, :counterparty_name, :counterparty_type,
                :inn, TRUE, NOW(), NOW()
            )
            RETURNING counterparty_id
        """), {
            "source_system": src,
            "source_id": sid,
            "counterparty_name": row.get("counterparty_name", "Без названия"),
            "counterparty_type": row.get("counterparty_type", "other"),
            "inn": row.get("inn"),
        })
        mapping[key] = result.fetchone()[0]
    return mapping


def _get_or_create_employee(db: Session, rows: list[dict[str, Any]]) -> dict[str, int]:
    mapping = {}
    for row in rows:
        src = row.get("source_system")
        sid = str(row.get("source_id")) if row.get("source_id") else None
        if not sid:
            continue
        key = f"{src}:{sid}"
        existing = db.execute(text("""
            SELECT employee_id FROM dim_employee
            WHERE source_system = :src AND source_id = :sid
            LIMIT 1
        """), {"src": src, "sid": sid}).fetchone()
        if existing:
            mapping[key] = existing[0]
            continue
        result = db.execute(text("""
            INSERT INTO dim_employee (
                source_system, source_id, full_name, department_id,
                is_active, created_at
            ) VALUES (
                :source_system, :source_id, :full_name, :department_id,
                TRUE, NOW()
            )
            RETURNING employee_id
        """), {
            "source_system": src,
            "source_id": sid,
            "full_name": row.get("full_name", "Сотрудник"),
            "department_id": row.get("department_id"),
        })
        mapping[key] = result.fetchone()[0]
    return mapping


def load_1c(db: Session, data: dict[str, Any]) -> dict[str, int]:
    stats = {"staging": 0, "counterparties": 0, "transactions": 0}
    if not data.get("staging"):
        return stats

    for row in data["staging"]:
        db.execute(text("""
            INSERT INTO staging.stg_1c_transactions (
                doc_number, doc_date, doc_type, organization,
                counterparty_name, counterparty_inn,
                account_debit, account_credit, amount, currency_code,
                description, raw_json, loaded_at
            ) VALUES (
                :doc_number, :doc_date, :doc_type, :organization,
                :counterparty_name, :counterparty_inn,
                :account_debit, :account_credit, :amount, :currency_code,
                :description, :raw_json, NOW()
            )
        """), {
            **row,
            "raw_json": json.dumps(row.get("raw_json", {}), default=str) if isinstance(row.get("raw_json"), dict) else row.get("raw_json"),
        })
        stats["staging"] += 1

    cp_map = _get_or_create_counterparty(db, data.get("counterparties", []))
    stats["counterparties"] = len(cp_map)

    for tx in data.get("transactions", []):
        existing = db.execute(text("""
            SELECT transaction_id FROM fact_transactions
            WHERE source_system = :source_system AND source_id = :source_id
            LIMIT 1
        """), {
            "source_system": tx["source_system"],
            "source_id": tx["source_id"],
        }).fetchone()
        if existing:
            db.execute(text("""
                UPDATE fact_transactions SET
                    transaction_date = :transaction_date,
                    posting_date = :posting_date,
                    date_id = :transaction_date,
                    account_id = :account_id,
                    currency_id = :currency_id,
                    amount_original = :amount_original,
                    amount_rub = :amount_rub,
                    description = :description,
                    updated_at = NOW()
                WHERE transaction_id = :transaction_id
            """), {**tx, "transaction_id": existing[0]})
        else:
            db.execute(text("""
                INSERT INTO fact_transactions (
                    transaction_date, posting_date, date_id,
                    document_number, document_type, account_id, currency_id,
                    amount_original, amount_rub, description,
                    source_system, source_id, is_manual_entry, is_deleted,
                    created_at, updated_at
                ) VALUES (
                    :transaction_date, :posting_date, :transaction_date,
                    :document_number, :document_type, :account_id, :currency_id,
                    :amount_original, :amount_rub, :description,
                    :source_system, :source_id, FALSE, FALSE,
                    NOW(), NOW()
                )
            """), tx)
        stats["transactions"] += 1

    return stats


def load_amocrm(db: Session, data: dict[str, Any]) -> dict[str, int]:
    stats = {"counterparties": 0, "employees": 0, "leads": 0, "deals": 0}
    if not any(data.values()):
        return stats

    cp_map = _get_or_create_counterparty(db, data.get("counterparties", []))
    stats["counterparties"] = len(cp_map)
    emp_map = _get_or_create_employee(db, data.get("employees", []))
    stats["employees"] = len(emp_map)

    for lead in data.get("leads", []):
        cp_key = f"amoCRM:{lead.get('counterparty_id_src')}"
        emp_key = f"amoCRM:{lead.get('employee_id_src')}"
        existing = db.execute(text("""
            SELECT lead_id FROM fact_crm_leads
            WHERE source_system = :source_system AND source_id = :source_id
            LIMIT 1
        """), {
            "source_system": lead["source_system"],
            "source_id": lead["source_id"],
        }).fetchone()
        if existing:
            continue
        db.execute(text("""
            INSERT INTO fact_crm_leads (
                source_system, source_id, created_date, date_id,
                converted_date, counterparty_id, employee_id,
                pipeline_name, source_channel, lead_status,
                utm_source, utm_medium
            ) VALUES (
                :source_system, :source_id, :created_date, :created_date,
                :converted_date, :counterparty_id, :employee_id,
                :pipeline_name, :source_channel, :lead_status,
                :utm_source, :utm_medium
            )
        """), {
            **lead,
            "counterparty_id": cp_map.get(cp_key),
            "employee_id": emp_map.get(emp_key),
        })
        stats["leads"] += 1

    for deal in data.get("deals", []):
        emp_key = f"amoCRM:{deal.get('employee_id_src')}"
        existing = db.execute(text("""
            SELECT sale_id FROM fact_sales
            WHERE source_system = :source_system AND source_id = :source_id
            LIMIT 1
        """), {
            "source_system": deal["source_system"],
            "source_id": deal["source_id"],
        }).fetchone()
        if existing:
            db.execute(text("""
                UPDATE fact_sales SET
                    deal_date = :deal_date,
                    close_date = :close_date,
                    date_id = :deal_date,
                    employee_id = :employee_id,
                    deal_status = :deal_status,
                    amount_original = :amount_original,
                    amount_rub = :amount_rub,
                    probability_pct = :probability_pct,
                    lead_time_days = :lead_time_days,
                    updated_at = NOW()
                WHERE sale_id = :sale_id
            """), {**deal, "sale_id": existing[0], "employee_id": emp_map.get(emp_key)})
        else:
            db.execute(text("""
                INSERT INTO fact_sales (
                    source_system, source_id, deal_date, date_id,
                    close_date, employee_id, department_id,
                    stage_name, pipeline_name, deal_status,
                    amount_original, amount_rub, currency_id,
                    margin_amount_rub, cost_amount_rub,
                    probability_pct, lead_time_days, description,
                    is_deleted, created_at, updated_at
                ) VALUES (
                    :source_system, :source_id, :deal_date, :deal_date,
                    :close_date, :employee_id, :department_id,
                    :stage_name, :pipeline_name, :deal_status,
                    :amount_original, :amount_rub, :currency_id,
                    :margin_amount_rub, :cost_amount_rub,
                    :probability_pct, :lead_time_days, :description,
                    FALSE, NOW(), NOW()
                )
            """), {
                **deal,
                "employee_id": emp_map.get(emp_key),
            })
        stats["deals"] += 1

    return stats


def load_gsheets(db: Session, data: dict[str, Any]) -> dict[str, int]:
    stats = {"staging": 0, "expenses": 0}
    if not data.get("staging"):
        return stats

    for row in data["staging"]:
        db.execute(text("""
            INSERT INTO staging.stg_gsheets_expenses (
                sheet_name, row_num, date_raw, amount_raw, currency_raw,
                category_raw, item_raw, department_raw, description_raw,
                parsed_ok, raw_row_json, loaded_at
            ) VALUES (
                :sheet_name, :row_num, :date_raw, :amount_raw, :currency_raw,
                :category_raw, :item_raw, :department_raw, :description_raw,
                :parsed_ok, :raw_row_json, NOW()
            )
        """), {
            **row,
            "raw_row_json": json.dumps(row.get("raw_row_json", {}), default=str) if isinstance(row.get("raw_row_json"), dict) else row.get("raw_row_json"),
        })
        stats["staging"] += 1

    for expense in data.get("expenses", []):
        payload = {**expense, "employee_id": expense.get("employee_id")}
        db.execute(text("""
            INSERT INTO fact_expenses (
                expense_date, date_id, account_id, department_id,
                employee_id, expense_category, expense_item, currency_id,
                amount_original, amount_rub, description,
                source_system, is_manual_entry, is_deleted,
                created_at, updated_at
            ) VALUES (
                :expense_date, :expense_date, :account_id, :department_id,
                :employee_id, :expense_category, :expense_item, :currency_id,
                :amount_original, :amount_rub, :description,
                :source_system, FALSE, FALSE,
                NOW(), NOW()
            )
        """), payload)
        stats["expenses"] += 1

    return stats
