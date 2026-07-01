from __future__ import annotations

from typing import List

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from deps import get_db, get_current_user, require_role
from models import AlertHistory, AlertRule, BiUser
from services.alerts_service import run_alert_checks

router = APIRouter()


class AlertRuleUpdate(BaseModel):
    is_active: bool | None = None
    threshold_value: float | None = None
    lookback_days: int | None = None
    severity: str | None = None


class AlertRuleOut(BaseModel):
    rule_id: int
    name: str
    metric_name: str
    condition: str
    threshold_value: float
    lookback_days: int
    severity: str
    schedule: str
    roles: List[str]
    is_active: bool
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AlertHistoryOut(BaseModel):
    alert_id: int
    rule_id: int | None
    metric_name: str | None
    metric_value: float | None
    threshold_value: float | None
    message: str
    severity: str | None
    channels: List[str]
    status: str
    acknowledged_by: str | None
    acknowledged_at: str | None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/rules", response_model=List[AlertRuleOut])
def list_rules(
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo")),
):
    rules = db.query(AlertRule).order_by(AlertRule.rule_id).all()
    return [
        AlertRuleOut(
            rule_id=r.rule_id,
            name=r.name,
            metric_name=r.metric_name,
            condition=r.condition,
            threshold_value=float(r.threshold_value),
            lookback_days=r.lookback_days,
            severity=r.severity,
            schedule=r.schedule,
            roles=list(r.roles or []),
            is_active=r.is_active,
            description=r.description,
        )
        for r in rules
    ]


@router.put("/rules/{rule_id}", response_model=AlertRuleOut)
def update_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "cfo")),
):
    rule = db.query(AlertRule).filter(AlertRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if payload.is_active is not None:
        rule.is_active = payload.is_active
    if payload.threshold_value is not None:
        rule.threshold_value = payload.threshold_value
    if payload.lookback_days is not None:
        rule.lookback_days = payload.lookback_days
    if payload.severity is not None:
        rule.severity = payload.severity
    db.commit()
    db.refresh(rule)
    return AlertRuleOut(
        rule_id=rule.rule_id,
        name=rule.name,
        metric_name=rule.metric_name,
        condition=rule.condition,
        threshold_value=float(rule.threshold_value),
        lookback_days=rule.lookback_days,
        severity=rule.severity,
        schedule=rule.schedule,
        roles=list(rule.roles or []),
        is_active=rule.is_active,
        description=rule.description,
    )


@router.get("/history", response_model=List[AlertHistoryOut])
def list_history(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo")),
):
    q = db.query(AlertHistory)
    if status:
        q = q.filter(AlertHistory.status == status)
    rows = q.order_by(AlertHistory.created_at.desc()).limit(limit).all()
    return [_history_out(r) for r in rows]


@router.post("/{alert_id}/ack", response_model=AlertHistoryOut)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "ceo", "cfo")),
):
    alert = db.query(AlertHistory).filter(AlertHistory.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = "acknowledged"
    alert.acknowledged_by = user.username
    alert.acknowledged_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return _history_out(alert)


@router.post("/run")
def run_alerts_now(
    schedule: str = "daily",
    db: Session = Depends(get_db),
    user: BiUser = Depends(require_role("admin", "cfo")),
):
    if schedule not in {"daily", "hourly"}:
        raise HTTPException(status_code=400, detail="schedule must be daily or hourly")
    import asyncio
    created = asyncio.run(run_alert_checks(schedule, db))
    return {"created": len(created)}


def _history_out(r: AlertHistory) -> AlertHistoryOut:
    return AlertHistoryOut(
        alert_id=r.alert_id,
        rule_id=r.rule_id,
        metric_name=r.metric_name,
        metric_value=float(r.metric_value) if r.metric_value is not None else None,
        threshold_value=float(r.threshold_value) if r.threshold_value is not None else None,
        message=r.message,
        severity=r.severity,
        channels=list(r.channels or []),
        status=r.status,
        acknowledged_by=r.acknowledged_by,
        acknowledged_at=r.acknowledged_at.isoformat() if r.acknowledged_at else None,
        created_at=r.created_at.isoformat() if r.created_at else None,
    )
