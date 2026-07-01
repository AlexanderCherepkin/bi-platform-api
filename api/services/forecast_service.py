from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sqlalchemy import text
from sqlalchemy.orm import Session

from models import CashflowForecast
from etl.config import settings as etl_settings
from etl.utils.cache import get_json, set_json

logger = logging.getLogger(__name__)

BASE_CURRENCY_ID = 1
FORECAST_MONTHS = 6
MIN_HISTORY_MONTHS = 3
OPTIMAL_HISTORY_MONTHS = 12


@dataclass
class ForecastPoint:
    forecast_date: date
    metric_type: str
    predicted_value: Decimal
    lower_bound: Decimal
    upper_bound: Decimal
    model_name: str
    is_forecast: bool


def run_forecast_job(db: Session) -> dict:
    """Entrypoint for APScheduler. Computes and stores cashflow forecasts."""
    logger.info("Starting cashflow forecast job")
    try:
        history = _load_monthly_history(db)
        if len(history) < MIN_HISTORY_MONTHS:
            logger.warning(
                "Insufficient history for ML forecast: %s months. Required: %s",
                len(history),
                MIN_HISTORY_MONTHS,
            )
            return {"status": "skipped", "reason": "insufficient_history"}

        forecasts = _build_forecasts(history)
        _persist_forecasts(forecasts, db)

        meta = {
            "history_months": len(history),
            "forecast_months": len(forecasts) // 3,
            "model": forecasts[0].model_name if forecasts else "none",
            "generated_at": datetime.utcnow().isoformat(),
        }
        set_json("forecast:last_run", meta, ttl=86400)
        logger.info("Cashflow forecast job completed: %s months forecasted", meta["forecast_months"])
        return {"status": "success", "forecasted_months": meta["forecast_months"]}
    except Exception as exc:
        logger.exception("Cashflow forecast job failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def _load_monthly_history(db: Session) -> pd.DataFrame:
    """Aggregate monthly inflow/outflow from fact_transactions and fact_expenses in base currency."""
    sql = """
    WITH monthly_transactions AS (
        SELECT
            DATE_TRUNC('month', t.transaction_date)::DATE AS month_date,
            SUM(CASE WHEN a.account_type IN ('revenue', 'other_income') THEN t.amount_rub ELSE 0 END) AS inflow,
            SUM(CASE WHEN a.account_type IN ('cogs', 'opex', 'tax', 'other_expense') THEN t.amount_rub ELSE 0 END) AS outflow
        FROM fact_transactions t
        JOIN dim_account a ON a.account_id = t.account_id
        WHERE NOT t.is_deleted
        GROUP BY DATE_TRUNC('month', t.transaction_date)
    ),
    monthly_expenses AS (
        SELECT
            DATE_TRUNC('month', e.expense_date)::DATE AS month_date,
            0 AS inflow,
            SUM(e.amount_rub) AS outflow
        FROM fact_expenses e
        WHERE NOT e.is_deleted
        GROUP BY DATE_TRUNC('month', e.expense_date)
    ),
    combined AS (
        SELECT month_date, inflow, outflow FROM monthly_transactions
        UNION ALL
        SELECT month_date, inflow, outflow FROM monthly_expenses
    )
    SELECT
        month_date,
        COALESCE(SUM(inflow), 0) AS inflow,
        COALESCE(SUM(outflow), 0) AS outflow
    FROM combined
    GROUP BY month_date
    ORDER BY month_date
    """
    rows = db.execute(text(sql)).fetchall()
    df = pd.DataFrame(rows, columns=["month_date", "inflow", "outflow"])
    if df.empty:
        return df
    df["month_date"] = pd.to_datetime(df["month_date"]).dt.date
    df["net_cashflow"] = df["inflow"] - df["outflow"]
    df["inflow"] = df["inflow"].astype(float)
    df["outflow"] = df["outflow"].astype(float)
    df["net_cashflow"] = df["net_cashflow"].astype(float)
    return df


def _build_forecasts(history: pd.DataFrame) -> List[ForecastPoint]:
    """Generate 3-6 months of inflow/outflow/net forecasts with confidence intervals."""
    last_date = history["month_date"].max()
    if not isinstance(last_date, date):
        last_date = last_date.date()

    horizon = FORECAST_MONTHS
    future_dates = [add_months(last_date, i) for i in range(1, horizon + 1)]

    model_name = "linear_regression_poly2" if len(history) >= OPTIMAL_HISTORY_MONTHS else "holt_winters_fallback"

    result: List[ForecastPoint] = []
    for metric in ("inflow", "outflow"):
        values, lower, upper = _predict_metric(history, metric, future_dates, model_name)
        for d, v, l, u in zip(future_dates, values, lower, upper):
            result.append(
                ForecastPoint(
                    forecast_date=d,
                    metric_type=metric,
                    predicted_value=Decimal(str(round(v, 2))),
                    lower_bound=Decimal(str(round(l, 2))),
                    upper_bound=Decimal(str(round(u, 2))),
                    model_name=model_name,
                    is_forecast=True,
                )
            )

    # Net cashflow derived deterministically from predicted inflow/outflow for matching month
    for d in future_dates:
        inf = next((r for r in result if r.forecast_date == d and r.metric_type == "inflow"), None)
        out = next((r for r in result if r.forecast_date == d and r.metric_type == "outflow"), None)
        if inf and out:
            net = inf.predicted_value - out.predicted_value
            result.append(
                ForecastPoint(
                    forecast_date=d,
                    metric_type="net_cashflow",
                    predicted_value=net,
                    lower_bound=inf.lower_bound - out.upper_bound,
                    upper_bound=inf.upper_bound - out.lower_bound,
                    model_name=model_name,
                    is_forecast=True,
                )
            )
    return result


def _predict_metric(
    history: pd.DataFrame,
    metric: str,
    future_dates: List[date],
    model_name: str,
) -> Tuple[List[float], List[float], List[float]]:
    """Return (predicted, lower_bound, upper_bound) for a metric."""
    n = len(history)
    if n < MIN_HISTORY_MONTHS:
        return _sma_fallback(history, metric, future_dates)

    # Feature: month index + month-of-year cyclical encoding
    X = np.arange(n).reshape(-1, 1)
    months = pd.to_datetime(history["month_date"]).dt.month.values
    month_sin = np.sin(2 * np.pi * months / 12).reshape(-1, 1)
    month_cos = np.cos(2 * np.pi * months / 12).reshape(-1, 1)
    X = np.hstack([X, month_sin, month_cos])

    y = history[metric].values

    if n >= OPTIMAL_HISTORY_MONTHS:
        poly = PolynomialFeatures(degree=2, include_bias=False)
        X_poly = poly.fit_transform(X)
        model = LinearRegression().fit(X_poly, y)
        future_X_base = np.arange(n, n + len(future_dates)).reshape(-1, 1)
        future_months = [d.month for d in future_dates]
        future_sin = np.sin(2 * np.pi * np.array(future_months) / 12).reshape(-1, 1)
        future_cos = np.cos(2 * np.pi * np.array(future_months) / 12).reshape(-1, 1)
        future_X = np.hstack([future_X_base, future_sin, future_cos])
        future_X_poly = poly.transform(future_X)
        preds = model.predict(future_X_poly)
    else:
        # Holt-Winters via statsmodels only if enough points; otherwise simple trend LR
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing

            series = pd.Series(y, index=pd.date_range(start=history["month_date"].min(), periods=n, freq="MS"))
            hw = ExponentialSmoothing(
                series,
                trend="add",
                seasonal="add",
                seasonal_periods=12 if n >= 24 else min(3, n),
            ).fit(optimized=True)
            future_index = pd.date_range(start=add_months(history["month_date"].max(), 1), periods=len(future_dates), freq="MS")
            preds = hw.forecast(len(future_dates)).reindex(future_index, fill_value=0).values
        except Exception:
            model = LinearRegression().fit(X, y)
            future_X_base = np.arange(n, n + len(future_dates)).reshape(-1, 1)
            future_months = [d.month for d in future_dates]
            future_sin = np.sin(2 * np.pi * np.array(future_months) / 12).reshape(-1, 1)
            future_cos = np.cos(2 * np.pi * np.array(future_months) / 12).reshape(-1, 1)
            future_X = np.hstack([future_X_base, future_sin, future_cos])
            preds = model.predict(future_X)

    preds = np.maximum(preds, 0)  # cashflow amounts non-negative in isolation
    residuals = y - _in_sample_predict(X, y, n >= OPTIMAL_HISTORY_MONTHS)
    mae = np.mean(np.abs(residuals)) if len(residuals) else 0
    std = np.std(residuals) if len(residuals) else mae
    margin = 1.96 * std + 0.1 * mae  # ~95% CI with small-sample safety
    lower = np.maximum(preds - margin, 0)
    upper = preds + margin
    return preds.tolist(), lower.tolist(), upper.tolist()


def _in_sample_predict(X: np.ndarray, y: np.ndarray, use_poly: bool) -> np.ndarray:
    if use_poly:
        from sklearn.preprocessing import PolynomialFeatures

        poly = PolynomialFeatures(degree=2, include_bias=False)
        X_poly = poly.fit_transform(X)
        model = LinearRegression().fit(X_poly, y)
        return model.predict(X_poly)
    model = LinearRegression().fit(X, y)
    return model.predict(X)


def _sma_fallback(history: pd.DataFrame, metric: str, future_dates: List[date]) -> Tuple[List[float], List[float], List[float]]:
    """Simple moving average fallback when history is below ML minimum."""
    window = min(3, len(history))
    mean_val = float(history[metric].tail(window).mean())
    std_val = float(history[metric].tail(window).std()) if len(history) > 1 else mean_val * 0.1
    preds = [mean_val] * len(future_dates)
    lower = [max(mean_val - std_val, 0)] * len(future_dates)
    upper = [mean_val + std_val] * len(future_dates)
    return preds, lower, upper


def _persist_forecasts(forecasts: List[ForecastPoint], db: Session) -> None:
    db.execute(text("DELETE FROM cashflow_forecasts"))
    for point in forecasts:
        db.execute(
            text("""
            INSERT INTO cashflow_forecasts
                (forecast_date, metric_type, predicted_value, lower_bound, upper_bound, model_name, is_forecast, generated_at)
            VALUES
                (:forecast_date, :metric_type, :predicted_value, :lower_bound, :upper_bound, :model_name, :is_forecast, NOW())
            ON CONFLICT (forecast_date, metric_type) DO UPDATE SET
                predicted_value = EXCLUDED.predicted_value,
                lower_bound = EXCLUDED.lower_bound,
                upper_bound = EXCLUDED.upper_bound,
                model_name = EXCLUDED.model_name,
                generated_at = NOW()
            """),
            {
                "forecast_date": point.forecast_date,
                "metric_type": point.metric_type,
                "predicted_value": point.predicted_value,
                "lower_bound": point.lower_bound,
                "upper_bound": point.upper_bound,
                "model_name": point.model_name,
                "is_forecast": point.is_forecast,
            },
        )
    db.commit()


def list_forecasts(db: Session) -> List[dict]:
    rows = db.execute(
        text("""
            SELECT forecast_date, metric_type, predicted_value, lower_bound, upper_bound, model_name, generated_at
            FROM cashflow_forecasts
            ORDER BY forecast_date, metric_type
        """)
    ).fetchall()
    return [
        {
            "forecast_date": r[0],
            "metric_type": r[1],
            "predicted_value": float(r[2] or 0),
            "lower_bound": float(r[3] or 0),
            "upper_bound": float(r[4] or 0),
            "model_name": r[5],
            "generated_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def get_forecast_meta() -> Optional[dict]:
    return get_json("forecast:last_run")


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)
