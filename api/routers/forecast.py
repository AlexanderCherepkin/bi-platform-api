from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from deps import get_db, require_role
from models import BiUser
from services.forecast_service import list_forecasts, get_forecast_meta, run_forecast_job

router = APIRouter()


class ForecastPointOut(BaseModel):
    forecast_date: str
    metric_type: str
    predicted_value: float
    lower_bound: float
    upper_bound: float
    model_name: str
    generated_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/cashflow", response_model=List[ForecastPointOut])
def get_cashflow_forecasts(
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo")),
):
    rows = list_forecasts(db)
    return [
        ForecastPointOut(
            forecast_date=str(r["forecast_date"]),
            metric_type=r["metric_type"],
            predicted_value=r["predicted_value"],
            lower_bound=r["lower_bound"],
            upper_bound=r["upper_bound"],
            model_name=r["model_name"],
            generated_at=r["generated_at"],
        )
        for r in rows
    ]


@router.post("/cashflow/run")
def run_forecast_now(
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "cfo")),
):
    result = run_forecast_job(db)
    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result.get("error", "Forecast failed"))
    return result


@router.get("/cashflow/meta")
def get_forecast_status(
    user: BiUser = Depends(require_role("admin", "ceo", "cfo")),
):
    return get_forecast_meta() or {"status": "unknown"}
