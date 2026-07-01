from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from deps import get_db, get_current_user, require_role
from models import BiUser
from schemas import PnlSummary, PnlWaterfallItem, BudgetVsActualItem
from etl.utils.cache import get_json, set_json
from etl.config import settings

router = APIRouter()


def _cached_or_compute(key: str, compute_fn):
    cached = get_json(key)
    if cached is not None:
        return cached
    result = compute_fn()
    set_json(key, result, ttl=settings.metrics_cache_ttl_seconds)
    return result


@router.get("/pnl", response_model=List[PnlSummary])
def get_pnl(
    year_from: int = None,
    year_to: int = None,
    month_from: int = None,
    month_to: int = None,
    department_id: int = None,
    counterparty_id: int = None,
    currency_id: int = None,
    employee_id: int = None,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo"))
):
    cache_key = (
        f"metrics:pnl:{year_from or 'all'}:{year_to or 'all'}:{month_from or 'all'}:{month_to or 'all'}"
        f":{department_id or 'all'}:{counterparty_id or 'all'}:{currency_id or 'all'}:{employee_id or 'all'}"
    )

    def _compute():
        sql = """
        SELECT
            d.year,
            d.month,
            COALESCE(SUM(CASE WHEN a.account_type = 'revenue' THEN t.amount_rub ELSE 0 END), 0) AS revenue,
            COALESCE(SUM(CASE WHEN a.account_type = 'cogs' THEN t.amount_rub ELSE 0 END), 0) AS cogs,
            COALESCE(SUM(CASE WHEN a.account_type = 'opex' THEN t.amount_rub ELSE 0 END), 0) AS opex,
            COALESCE(SUM(CASE WHEN a.account_type = 'tax' THEN t.amount_rub ELSE 0 END), 0) AS tax,
            COALESCE(SUM(CASE WHEN a.account_type = 'other_income' THEN t.amount_rub ELSE 0 END), 0) AS other_income,
            COALESCE(SUM(CASE WHEN a.account_type = 'other_expense' THEN t.amount_rub ELSE 0 END), 0) AS other_expense
        FROM dim_date d
        CROSS JOIN dim_account a
        LEFT JOIN fact_transactions t ON t.date_id = d.date_id
            AND t.account_id = a.account_id
            AND NOT t.is_deleted
        """
        params = {}
        filters = []
        if year_from:
            filters.append("d.year >= :yf")
            params["yf"] = year_from
        if year_to:
            filters.append("d.year <= :yt")
            params["yt"] = year_to
        if month_from:
            filters.append("d.month >= :mf")
            params["mf"] = month_from
        if month_to:
            filters.append("d.month <= :mt")
            params["mt"] = month_to
        if department_id:
            filters.append("t.department_id = :did")
            params["did"] = department_id
        if counterparty_id:
            filters.append("t.counterparty_id = :cid")
            params["cid"] = counterparty_id
        if currency_id:
            filters.append("t.currency_id = :curid")
            params["curid"] = currency_id
        if employee_id:
            filters.append("t.employee_id = :eid")
            params["eid"] = employee_id
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        sql += """
        GROUP BY d.year, d.month
        HAVING COALESCE(SUM(t.amount_rub), 0) != 0
        ORDER BY d.year DESC, d.month DESC
        """
        rows = db.execute(text(sql), params).fetchall()
        return [
            PnlSummary(
                year=r[0], month=r[1],
                revenue=r[2],
                cogs=r[3],
                gross_profit=r[2] - r[3],
                opex=r[4],
                operating_profit=r[2] - r[3] - r[4],
                tax=r[5],
                net_profit=r[2] - r[3] - r[4] - r[5] + r[6] - r[7],
                gross_margin_pct=round((r[2] - r[3]) / r[2] * 100, 2) if r[2] else 0,
                operating_margin_pct=round((r[2] - r[3] - r[4]) / r[2] * 100, 2) if r[2] else 0,
                net_margin_pct=round((r[2] - r[3] - r[4] - r[5] + r[6] - r[7]) / r[2] * 100, 2) if r[2] else 0,
            ).model_dump()
            for r in rows
        ]

    return _cached_or_compute(cache_key, _compute)


@router.get("/cashflow")
def get_cashflow(
    year_from: int = None,
    year_to: int = None,
    month_from: int = None,
    month_to: int = None,
    department_id: int = None,
    counterparty_id: int = None,
    currency_id: int = None,
    employee_id: int = None,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo"))
):
    cache_key = (
        f"metrics:cashflow:{year_from or 'all'}:{year_to or 'all'}:{month_from or 'all'}:{month_to or 'all'}"
        f":{department_id or 'all'}:{counterparty_id or 'all'}:{currency_id or 'all'}:{employee_id or 'all'}"
    )

    def _compute():
        sql = """
        SELECT
            d.year,
            d.month,
            COALESCE(SUM(CASE WHEN a.account_type IN ('revenue', 'other_income') THEN t.amount_rub ELSE 0 END), 0) AS inflows_revenue,
            COALESCE(SUM(CASE WHEN a.account_type IN ('cogs','opex','tax','other_expense') THEN t.amount_rub ELSE 0 END), 0) AS outflows_total
        FROM dim_date d
        LEFT JOIN fact_transactions t ON t.date_id = d.date_id AND NOT t.is_deleted
        LEFT JOIN dim_account a ON a.account_id = t.account_id
        """
        params = {}
        filters = []
        if year_from:
            filters.append("d.year >= :yf")
            params["yf"] = year_from
        if year_to:
            filters.append("d.year <= :yt")
            params["yt"] = year_to
        if month_from:
            filters.append("d.month >= :mf")
            params["mf"] = month_from
        if month_to:
            filters.append("d.month <= :mt")
            params["mt"] = month_to
        if department_id:
            filters.append("t.department_id = :did")
            params["did"] = department_id
        if counterparty_id:
            filters.append("t.counterparty_id = :cid")
            params["cid"] = counterparty_id
        if currency_id:
            filters.append("t.currency_id = :curid")
            params["curid"] = currency_id
        if employee_id:
            filters.append("t.employee_id = :eid")
            params["eid"] = employee_id
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        sql += """
        GROUP BY d.year, d.month
        HAVING COALESCE(SUM(t.amount_rub), 0) != 0
        ORDER BY d.year DESC, d.month DESC
        """
        rows = db.execute(text(sql), params).fetchall()
        return [
            {
                "year": r[0], "month": r[1],
                "cash_inflow": r[2],
                "cash_outflow": r[3],
                "net_cashflow": r[2] - r[3]
            }
            for r in rows
        ]

    return _cached_or_compute(cache_key, _compute)


@router.get("/sales-funnel")
def get_sales_funnel(
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "sales_head"))
):
    sql = """
    SELECT year, month, pipeline_name, stage_name, deal_status,
        deals_count, amount_rub, won_amount, lost_amount
    FROM vw_sales_funnel
    WHERE 1=1
    """
    params = {}
    if year:
        sql += " AND year = :y"; params["y"] = year
    if month:
        sql += " AND month = :m"; params["m"] = month
    sql += " ORDER BY year DESC, month DESC, pipeline_name, stage_name"
    rows = db.execute(text(sql), params).fetchall()
    return [
        {
            "year": r[0], "month": r[1], "pipeline": r[2], "stage": r[3], "status": r[4],
            "deals_count": r[5], "amount_rub": r[6], "won_amount": r[7], "lost_amount": r[8]
        }
        for r in rows
    ]


@router.get("/kpi/managers")
def get_manager_kpi(
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "sales_head"))
):
    sql = """
    SELECT year, month, manager_name, department_name,
        deals_count, won_deals, lost_deals, total_amount, won_amount,
        win_rate_pct, total_margin, avg_margin_pct
    FROM vw_kpi_sales_managers
    WHERE 1=1
    """
    params = {}
    if year:
        sql += " AND year = :y"; params["y"] = year
    if month:
        sql += " AND month = :m"; params["m"] = month
    sql += " ORDER BY year DESC, month DESC, total_amount DESC"
    rows = db.execute(text(sql), params).fetchall()
    return [
        {
            "year": r[0], "month": r[1], "manager": r[2], "department": r[3],
            "deals": r[4], "won": r[5], "lost": r[6], "total_amount": r[7],
            "won_amount": r[8], "win_rate_pct": r[9], "margin": r[10], "margin_pct": r[11]
        }
        for r in rows
    ]


@router.get("/pnl-waterfall", response_model=List[PnlWaterfallItem])
def get_pnl_waterfall(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo"))
):
    cache_key = f"metrics:pnl-waterfall:{year}:{month}"

    def _compute():
        sql = """
        SELECT
            revenue,
            cogs,
            gross_profit,
            opex,
            operating_profit,
            tax,
            net_profit,
            other_income,
            other_expense
        FROM vw_pnl_waterfall
        WHERE year = :y AND month = :m
        LIMIT 1
        """
        row = db.execute(text(sql), {"y": year, "m": month}).fetchone()
        if row is None:
            return []
        r = row._mapping
        items = [
            {"label": "Выручка", "value": float(r["revenue"]), "is_total": True, "is_negative": False},
            {"label": "COGS", "value": float(r["cogs"]), "is_total": False, "is_negative": True},
            {"label": "Вал. прибыль", "value": float(r["gross_profit"]), "is_total": True, "is_negative": False},
            {"label": "OPEX", "value": float(r["opex"]), "is_total": False, "is_negative": True},
            {"label": "Оп. прибыль", "value": float(r["operating_profit"]), "is_total": True, "is_negative": False},
        ]
        other_income = float(r["other_income"] or 0)
        other_expense = float(r["other_expense"] or 0)
        tax = float(r["tax"] or 0)
        if other_income:
            items.append({"label": "Прочие доходы", "value": other_income, "is_total": False, "is_negative": False})
        if other_expense:
            items.append({"label": "Прочие расходы", "value": other_expense, "is_total": False, "is_negative": True})
        if tax:
            items.append({"label": "Налог", "value": tax, "is_total": False, "is_negative": True})
        items.append({"label": "Чистая прибыль", "value": float(r["net_profit"]), "is_total": True, "is_negative": False})
        return items

    return _cached_or_compute(cache_key, _compute)


@router.get("/budget-vs-actual", response_model=List[BudgetVsActualItem])
def get_budget_vs_actual(
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo"))
):
    cache_key = f"metrics:budget-vs-actual:{year or 'all'}:{month or 'all'}"

    def _compute():
        sql = """
        SELECT
            year, month, account_id, account_code, account_name, account_type,
            actual_amount_rub, budget_amount_rub, variance_amount_rub, variance_pct
        FROM vw_budget_vs_actual
        WHERE actual_amount_rub != 0 OR budget_amount_rub != 0
        """
        params = {}
        filters = []
        if year:
            filters.append("year = :y")
            params["y"] = year
        if month:
            filters.append("month = :m")
            params["m"] = month
        if filters:
            sql += " AND " + " AND ".join(filters)
        sql += " ORDER BY year DESC, month DESC, account_code"
        rows = db.execute(text(sql), params).fetchall()
        return [
            {
                "year": r[0], "month": r[1], "account_id": r[2], "account_code": r[3],
                "account_name": r[4], "account_type": r[5],
                "actual_amount_rub": r[6], "budget_amount_rub": r[7],
                "variance_amount_rub": r[8], "variance_pct": r[9]
            }
            for r in rows
        ]

    return _cached_or_compute(cache_key, _compute)
