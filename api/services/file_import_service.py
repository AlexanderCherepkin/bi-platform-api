import hashlib
import io
import json
from datetime import date
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session


ALLOWED_TARGET_TABLES = {"fact_transactions", "fact_expenses"}


TRANSACTION_COLUMNS = {
    "transaction_date": ["transaction_date", "date", "дата", "дата транзакции"],
    "posting_date": ["posting_date", "posting", "дата проводки"],
    "account_id": ["account_id", "account", "счет id", "код счета"],
    "counterparty_id": ["counterparty_id", "counterparty", "контрагент id"],
    "department_id": ["department_id", "department", "отдел id"],
    "currency_id": ["currency_id", "currency", "валюта id"],
    "amount_original": ["amount_original", "amount", "сумма"],
    "description": ["description", "desc", "описание"],
}

TRANSACTION_REQUIRED = {"transaction_date", "amount_original", "account_id", "currency_id"}


EXPENSE_COLUMNS = {
    "expense_date": ["expense_date", "date", "дата", "дата расхода"],
    "account_id": ["account_id", "account", "счет id", "код счета"],
    "department_id": ["department_id", "department", "отдел id"],
    "expense_category": ["expense_category", "category", "категория"],
    "expense_item": ["expense_item", "item", "статья"],
    "currency_id": ["currency_id", "currency", "валюта id"],
    "amount_original": ["amount_original", "amount", "сумма"],
    "description": ["description", "desc", "описание"],
}

EXPENSE_REQUIRED = {"expense_date", "amount_original", "account_id", "currency_id", "expense_category", "expense_item"}


def _normalize_column_name(name: str) -> str:
    return name.strip().lower().replace("_", " ")


def _build_column_mapping(df_columns: list[str], target_table: str) -> dict[str, str]:
    spec = TRANSACTION_COLUMNS if target_table == "fact_transactions" else EXPENSE_COLUMNS
    normalized = {_normalize_column_name(c): c for c in df_columns}
    mapping: dict[str, str] = {}
    for canonical, aliases in spec.items():
        for alias in aliases:
            norm = _normalize_column_name(alias)
            if norm in normalized:
                mapping[canonical] = normalized[norm]
                break
    return mapping


def _parse_value(key: str, raw: Any) -> Any:
    if pd.isna(raw):
        return None
    if key in ("transaction_date", "posting_date", "expense_date"):
        if isinstance(raw, pd.Timestamp):
            return raw.date().isoformat()
        return str(raw)
    if key in ("account_id", "counterparty_id", "department_id", "currency_id"):
        try:
            return int(float(raw))
        except (ValueError, TypeError):
            return None
    if key == "amount_original":
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None
    return str(raw)


def _validate_row(mapped: dict[str, Any], target_table: str) -> list[str]:
    errors: list[str] = []
    if target_table == "fact_transactions":
        if not mapped.get("transaction_date"):
            errors.append("transaction_date is required")
        if mapped.get("amount_original") is None:
            errors.append("amount_original is required")
        elif mapped["amount_original"] <= 0:
            errors.append("amount_original must be positive")
        if mapped.get("account_id") is None:
            errors.append("account_id is required")
        if mapped.get("currency_id") is None:
            errors.append("currency_id is required")
    else:
        if not mapped.get("expense_date"):
            errors.append("expense_date is required")
        if mapped.get("amount_original") is None:
            errors.append("amount_original is required")
        elif mapped["amount_original"] <= 0:
            errors.append("amount_original must be positive")
        if not mapped.get("expense_category"):
            errors.append("expense_category is required")
        if not mapped.get("expense_item"):
            errors.append("expense_item is required")
        if mapped.get("account_id") is None:
            errors.append("account_id is required")
        if mapped.get("currency_id") is None:
            errors.append("currency_id is required")
    return errors


def _read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    ext = filename.split(".")[-1].lower()
    try:
        if ext == "csv":
            return pd.read_csv(io.BytesIO(content))
        if ext in ("xlsx", "xls"):
            return pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to parse file: {exc}") from exc
    raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def import_file_to_staging(
    db: Session,
    file: UploadFile,
    target_table: str,
    uploaded_by: str,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    if target_table not in ALLOWED_TARGET_TABLES:
        raise HTTPException(status_code=400, detail=f"target_table must be one of {ALLOWED_TARGET_TABLES}")

    content = file.file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    df = _read_dataframe(content, file.filename or "unknown")
    column_mapping = _build_column_mapping(list(df.columns), target_table)
    required_keys = TRANSACTION_REQUIRED if target_table == "fact_transactions" else EXPENSE_REQUIRED
    missing = required_keys - set(column_mapping.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {sorted(missing)}")

    result = db.execute(text("""
        INSERT INTO staging_file_uploads (
            filename, file_size_bytes, file_hash, target_table, uploaded_by,
            total_rows, valid_rows, invalid_rows, status, notes
        ) VALUES (
            :filename, :file_size_bytes, :file_hash, :target_table, :uploaded_by,
            0, 0, 0, 'pending', :notes
        ) RETURNING upload_id
    """), {
        "filename": file.filename,
        "file_size_bytes": len(content),
        "file_hash": file_hash,
        "target_table": target_table,
        "uploaded_by": uploaded_by,
        "notes": notes,
    })
    upload_id = result.fetchone()[0]

    valid = 0
    invalid = 0
    for idx, row in enumerate(df.itertuples(index=False), start=2):
        source_data = {col: (None if pd.isna(row[i]) else row[i]) for i, col in enumerate(df.columns)}
        mapped = {canonical: _parse_value(canonical, source_data.get(src_col)) for canonical, src_col in column_mapping.items()}
        errors = _validate_row(mapped, target_table)
        status = "valid" if not errors else "invalid"
        if status == "valid":
            valid += 1
        else:
            invalid += 1

        db.execute(text("""
            INSERT INTO staging_rows (
                upload_id, row_number, target_table, source_data,
                mapped_data, validation_errors, status
            ) VALUES (
                :upload_id, :row_number, :target_table, :source_data,
                :mapped_data, :validation_errors, :status
            )
        """), {
            "upload_id": upload_id,
            "row_number": idx,
            "target_table": target_table,
            "source_data": json.dumps(source_data, default=_json_default),
            "mapped_data": json.dumps(mapped, default=_json_default),
            "validation_errors": json.dumps(errors),
            "status": status,
        })

    db.execute(text("""
        UPDATE staging_file_uploads
        SET total_rows = :total, valid_rows = :valid, invalid_rows = :invalid, status = 'validated'
        WHERE upload_id = :upload_id
    """), {
        "upload_id": upload_id,
        "total": valid + invalid,
        "valid": valid,
        "invalid": invalid,
    })
    db.commit()

    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "target_table": target_table,
        "total_rows": valid + invalid,
        "valid_rows": valid,
        "invalid_rows": invalid,
        "status": "validated",
    }


def list_uploads(db: Session, uploaded_by: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = "SELECT * FROM staging_file_uploads"
    params: dict[str, Any] = {}
    if uploaded_by:
        sql += " WHERE uploaded_by = :uploaded_by"
        params["uploaded_by"] = uploaded_by
    sql += " ORDER BY uploaded_at DESC LIMIT :limit"
    params["limit"] = limit
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def get_staging_rows(db: Session, upload_id: int, status: Optional[str] = None, limit: int = 1000) -> list[dict[str, Any]]:
    sql = "SELECT * FROM staging_rows WHERE upload_id = :upload_id"
    params: dict[str, Any] = {"upload_id": upload_id}
    if status:
        sql += " AND status = :status"
        params["status"] = status
    sql += " ORDER BY row_number LIMIT :limit"
    params["limit"] = limit
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]
