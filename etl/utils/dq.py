"""Lightweight data quality checks for ETL payloads before loading."""

from typing import Any

from etl.utils.telegram import send_telegram_message


class DqIssue:
    def __init__(self, source: str, rule: str, message: str, details: dict[str, Any] | None = None):
        self.source = source
        self.rule = rule
        self.message = message
        self.details = details or {}


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_transactions(rows: list[dict[str, Any]], source: str) -> list[DqIssue]:
    issues: list[DqIssue] = []
    for idx, row in enumerate(rows):
        ctx = {"row_index": idx, "source_id": row.get("source_id")}
        if _is_null(row.get("transaction_date")) and _is_null(row.get("expense_date")) and _is_null(row.get("deal_date")):
            issues.append(DqIssue(source, "missing_date", "Отсутствует дата транзакции", ctx))
        amount = _to_float(row.get("amount_original"))
        if amount is None:
            issues.append(DqIssue(source, "missing_amount", "Отсутствует сумма", ctx))
        elif amount < 0 and source in ("1c", "amocrm"):
            issues.append(DqIssue(source, "negative_revenue", f"Отрицательная сумма: {amount}", ctx))
    return issues


def _check_deals(rows: list[dict[str, Any]], source: str) -> list[DqIssue]:
    issues: list[DqIssue] = []
    for idx, row in enumerate(rows):
        ctx = {"row_index": idx, "source_id": row.get("source_id")}
        if _is_null(row.get("deal_date")) and _is_null(row.get("created_date")):
            issues.append(DqIssue(source, "missing_date", "Отсутствует дата сделки", ctx))
        amount = _to_float(row.get("amount_original"))
        if amount is None:
            issues.append(DqIssue(source, "missing_amount", "Отсутствует сумма сделки", ctx))
        elif amount < 0:
            issues.append(DqIssue(source, "negative_revenue", f"Отрицательная сумма сделки: {amount}", ctx))
    return issues


def _check_expenses(rows: list[dict[str, Any]], source: str) -> list[DqIssue]:
    issues: list[DqIssue] = []
    for idx, row in enumerate(rows):
        ctx = {"row_index": idx}
        if _is_null(row.get("expense_date")):
            issues.append(DqIssue(source, "missing_date", "Отсутствует дата расхода", ctx))
        amount = _to_float(row.get("amount_original"))
        if amount is None:
            issues.append(DqIssue(source, "missing_amount", "Отсутствует сумма расхода", ctx))
        elif amount < 0:
            issues.append(DqIssue(source, "negative_expense", f"Отрицательная сумма расхода: {amount}", ctx))
    return issues


def run_dq_checks(data: dict[str, Any]) -> list[DqIssue]:
    """Run checks on transformed payload before loading."""
    issues: list[DqIssue] = []
    if "transactions" in data:
        issues.extend(_check_transactions(data["transactions"], "1c"))
    if "deals" in data:
        issues.extend(_check_deals(data["deals"], "amocrm"))
    if "expenses" in data:
        issues.extend(_check_expenses(data["expenses"], "gsheets"))
    return issues


def format_dq_alert(issues: list[DqIssue]) -> str:
    lines = ["⚠️ <b>Data Quality anomalies detected</b>"]
    for issue in issues[:20]:
        lines.append(f"• {issue.source} / {issue.rule}: {issue.message}")
    if len(issues) > 20:
        lines.append(f"...и ещё {len(issues) - 20} аномалий")
    return "\n".join(lines)


def send_dq_telegram_alert(issues: list[DqIssue]) -> None:
    if issues:
        send_telegram_message(format_dq_alert(issues))
