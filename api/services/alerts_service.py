from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from deps import engine
from models import AlertHistory, AlertRule, BiUser

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


@dataclass
class AlertCheckResult:
    rule_id: int
    metric_name: str
    metric_value: Decimal
    threshold_value: Decimal
    triggered: bool
    message: str
    severity: str


async def run_alert_checks(schedule: str, db: Session) -> List[AlertHistory]:
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.is_active == True, AlertRule.schedule == schedule)
        .all()
    )
    created: List[AlertHistory] = []
    for rule in rules:
        try:
            result = _evaluate_rule(rule, db)
        except Exception as exc:
            logger.warning("Alert rule %s evaluation failed: %s", rule.rule_id, exc)
            continue
        if not result.triggered:
            continue
        if _is_recently_alerted(rule.rule_id, db):
            logger.info("Rule %s recently alerted; skipping duplicate", rule.rule_id)
            continue
        history = _persist_alert(result, db)
        created.append(history)
        await _dispatch(history, rule, db)
    return created


def _evaluate_rule(rule: AlertRule, db: Session) -> AlertCheckResult:
    if rule.metric_name == "revenue":
        return _evaluate_revenue(rule, db)
    if rule.metric_name == "net_cashflow":
        return _evaluate_cashflow(rule, db)
    if rule.metric_name == "opex":
        return _evaluate_opex(rule, db)
    return AlertCheckResult(
        rule_id=rule.rule_id,
        metric_name=rule.metric_name,
        metric_value=Decimal("0"),
        threshold_value=Decimal(str(rule.threshold_value)),
        triggered=False,
        message="Unknown metric",
        severity=rule.severity,
    )


def _evaluate_revenue(rule: AlertRule, db: Session) -> AlertCheckResult:
    lookback = int(rule.lookback_days or 7)
    sql = """
    WITH periods AS (
        SELECT
            SUM(CASE WHEN transaction_date BETWEEN :current_start AND :current_end THEN amount_rub ELSE 0 END) AS current_period,
            SUM(CASE WHEN transaction_date BETWEEN :prev_start AND :prev_end THEN amount_rub ELSE 0 END) AS previous_period
        FROM fact_transactions t
        JOIN dim_account a ON a.account_id = t.account_id
        WHERE a.account_type = 'revenue'
          AND NOT t.is_deleted
    )
    SELECT current_period, previous_period FROM periods
    """
    today = date.today()
    current_end = today
    current_start = today - timedelta(days=lookback - 1)
    prev_end = current_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=lookback - 1)
    params = {
        "current_start": current_start,
        "current_end": current_end,
        "prev_start": prev_start,
        "prev_end": prev_end,
    }
    row = db.execute(text(sql), params).fetchone()
    current = Decimal(row[0] or 0)
    previous = Decimal(row[1] or 0)
    threshold = Decimal(str(rule.threshold_value))
    triggered = False
    message = "Выручка в норме"
    if previous > 0:
        drop_pct = (previous - current) / previous * 100
        triggered = drop_pct > threshold
        if triggered:
            message = (
                f"⚠️ Падение выручки: {drop_pct:.1f}% за {lookback} дней "
                f"(текущий период {current:,.0f} ₽ vs прошлый {previous:,.0f} ₽). "
                f"Порог: {threshold:.0f}%"
            )
    return AlertCheckResult(
        rule_id=rule.rule_id,
        metric_name=rule.metric_name,
        metric_value=current,
        threshold_value=threshold,
        triggered=triggered,
        message=message,
        severity=rule.severity,
    )


def _evaluate_cashflow(rule: AlertRule, db: Session) -> AlertCheckResult:
    lookback = int(rule.lookback_days or 1)
    sql = """
    WITH tx_flow AS (
        SELECT
            a.account_type,
            t.amount_rub
        FROM fact_transactions t
        JOIN dim_account a ON a.account_id = t.account_id
        WHERE t.transaction_date BETWEEN :start AND :end
          AND NOT t.is_deleted
    ),
    expense_flow AS (
        SELECT
            a.account_type,
            e.amount_rub
        FROM fact_expenses e
        JOIN dim_account a ON a.account_id = e.account_id
        WHERE e.expense_date BETWEEN :start AND :end
          AND NOT e.is_deleted
    ),
    all_flow AS (
        SELECT * FROM tx_flow
        UNION ALL
        SELECT * FROM expense_flow
    )
    SELECT
        COALESCE(SUM(CASE WHEN account_type IN ('revenue', 'other_income') THEN amount_rub ELSE 0 END), 0)
        - COALESCE(SUM(CASE WHEN account_type IN ('cogs', 'opex', 'tax', 'other_expense') THEN amount_rub ELSE 0 END), 0)
    FROM all_flow
    """
    today = date.today()
    start = today - timedelta(days=lookback - 1)
    params = {"start": start, "end": today}
    row = db.execute(text(sql), params).fetchone()
    value = Decimal(row[0] or 0)
    threshold = Decimal(str(rule.threshold_value))
    triggered = value < threshold
    message = (
        f"🚨 Отрицательный cashflow за {lookback} дн.: {value:,.0f} ₽. "
        f"Порог: < {threshold:,.0f} ₽"
        if triggered
        else f"Cashflow в норме: {value:,.0f} ₽"
    )
    return AlertCheckResult(
        rule_id=rule.rule_id,
        metric_name=rule.metric_name,
        metric_value=value,
        threshold_value=threshold,
        triggered=triggered,
        message=message,
        severity=rule.severity,
    )


def _evaluate_opex(rule: AlertRule, db: Session) -> AlertCheckResult:
    lookback = int(rule.lookback_days or 30)
    sql = """
    WITH periods AS (
        SELECT
            SUM(CASE WHEN transaction_date BETWEEN :current_start AND :current_end AND a.account_type = 'opex' THEN t.amount_rub ELSE 0 END) AS current_period,
            SUM(CASE WHEN transaction_date BETWEEN :prev_start AND :prev_end AND a.account_type = 'opex' THEN t.amount_rub ELSE 0 END) AS previous_period
        FROM fact_transactions t
        JOIN dim_account a ON a.account_id = t.account_id
        WHERE NOT t.is_deleted
    )
    SELECT current_period, previous_period FROM periods
    """
    today = date.today()
    current_end = today
    current_start = today - timedelta(days=lookback - 1)
    prev_end = current_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=lookback - 1)
    params = {
        "current_start": current_start,
        "current_end": current_end,
        "prev_start": prev_start,
        "prev_end": prev_end,
    }
    row = db.execute(text(sql), params).fetchone()
    current = Decimal(row[0] or 0)
    previous = Decimal(row[1] or 0)
    threshold = Decimal(str(rule.threshold_value))
    triggered = False
    message = "OPEX в норме"
    if previous > 0:
        rise_pct = (current - previous) / previous * 100
        triggered = rise_pct > threshold
        if triggered:
            message = (
                f"⚠️ Рост OPEX: {rise_pct:.1f}% за {lookback} дней "
                f"(текущий период {current:,.0f} ₽ vs прошлый {previous:,.0f} ₽). "
                f"Порог: {threshold:.0f}%"
            )
    return AlertCheckResult(
        rule_id=rule.rule_id,
        metric_name=rule.metric_name,
        metric_value=current,
        threshold_value=threshold,
        triggered=triggered,
        message=message,
        severity=rule.severity,
    )


def _is_recently_alerted(rule_id: int, db: Session, hours: int = 4) -> bool:
    since = datetime.utcnow() - timedelta(hours=hours)
    row = db.execute(
        text("""
            SELECT 1 FROM alerts_history
            WHERE rule_id = :rid AND created_at > :since
            LIMIT 1
        """),
        {"rid": rule_id, "since": since},
    ).fetchone()
    return row is not None


def _persist_alert(result: AlertCheckResult, db: Session) -> AlertHistory:
    history = AlertHistory(
        rule_id=result.rule_id,
        metric_name=result.metric_name,
        metric_value=result.metric_value,
        threshold_value=result.threshold_value,
        message=result.message,
        severity=result.severity,
        channels=["ui"],
        status="new",
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


async def _dispatch(history: AlertHistory, rule: AlertRule, db: Session) -> None:
    await _send_telegram(history)
    await _broadcast_sse(history)


async def _send_telegram(history: AlertHistory) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    text_msg = (
        f"*{history.severity.upper()}* alert\\n\n"
        f"{history.message}\n\n"
        f"Metric: `{history.metric_name}`\n"
        f"Value: `{float(history.metric_value or 0):,.2f}`\n"
        f"Threshold: `{float(history.threshold_value or 0):,.2f}`\n"
        f"Time: {history.created_at.isoformat()}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text_msg,
        "parse_mode": "MarkdownV2",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
        logger.info("Telegram alert sent for alert_id=%s", history.alert_id)
    except Exception as exc:
        logger.warning("Telegram send failed for alert_id=%s: %s", history.alert_id, exc)


async def _broadcast_sse(history: AlertHistory) -> None:
    try:
        from realtime import _notify_all

        _notify_all(
            {
                "type": "alert",
                "payload": {
                    "alert_id": history.alert_id,
                    "rule_id": history.rule_id,
                    "metric_name": history.metric_name,
                    "message": history.message,
                    "severity": history.severity,
                    "created_at": history.created_at.isoformat() if history.created_at else None,
                },
            }
        )
    except Exception as exc:
        logger.warning("SSE broadcast failed for alert_id=%s: %s", history.alert_id, exc)


def get_recipients(rule: AlertRule, db: Session) -> List[BiUser]:
    roles = rule.roles or ["admin", "cfo"]
    return (
        db.query(BiUser)
        .filter(BiUser.role.in_(roles), BiUser.is_active == True)
        .all()
    )
