from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from deps import get_db, require_role

router = APIRouter()


def _list_dimension(db: Session, table: str, id_col: str, name_col: str, extra_where: str = ""):
    sql = f"""
        SELECT DISTINCT ON ({name_col}, {id_col}) {id_col} AS id, {name_col} AS name
        FROM {table}
        WHERE (is_active IS TRUE OR is_active IS NULL)
        {extra_where}
        ORDER BY {name_col}, {id_col}
    """
    rows = db.execute(text(sql)).fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


@router.get("/dimensions")
def list_dimensions(
    db: Session = Depends(get_db),
    user: Any = Depends(require_role("admin", "cfo", "sales_head", "manager"))
):
    return {
        "departments": _list_dimension(db, "dim_department", "department_id", "department_name"),
        "counterparties": _list_dimension(
            db, "dim_counterparty", "counterparty_id", "counterparty_name",
            "AND counterparty_type IN ('customer','supplier','partner')"
        ),
        "currencies": _list_dimension(db, "dim_currency", "currency_id", "currency_code"),
        "employees": _list_dimension(db, "dim_employee", "employee_id", "full_name"),
    }


@router.get("/tables")
def list_tables(
    db: Session = Depends(get_db),
    user: Any = Depends(require_role("admin", "cfo", "sales_head", "manager"))
):
    result = db.execute(text("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('public', 'staging', 'analytics')
        ORDER BY table_schema, table_name
    """))
    rows = result.mappings().all()
    return {"tables": [{"table_schema": r["table_schema"], "table_name": r["table_name"]} for r in rows]}


@router.post("/query")
def run_query(
    sql: str = Body(..., embed=True),
    params: dict = Body(None, embed=True),
    db: Session = Depends(get_db),
    user: Any = Depends(require_role("admin", "cfo", "sales_head", "manager"))
):
    forbidden = ["drop", "delete", "truncate", "alter", "create", "grant", "revoke"]
    lower = sql.lower()
    for word in forbidden:
        if word in lower:
            raise HTTPException(status_code=403, detail=f"Forbidden keyword: {word}")
    try:
        result = db.execute(text(sql), params or {})
        rows = result.mappings().all()
        if result.rowcount >= 0:
            db.commit()
        columns = list(rows[0].keys()) if rows else []
        return {"columns": columns, "rows": [dict(r) for r in rows], "rowCount": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
