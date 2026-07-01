import argparse
import traceback
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import text

from etl.config import settings
from etl.db import get_db, close_db
from etl.extractors.onec import OneCExtractor
from etl.extractors.amocrm import AmoCRMExtractor
from etl.extractors.gsheets import GoogleSheetsExtractor
from etl.transformers.onec_transformer import transform_onec
from etl.transformers.amocrm_transformer import transform_amocrm
from etl.transformers.gsheets_transformer import transform_gsheets
from etl.loaders.fact_loader import load_1c, load_amocrm, load_gsheets
from etl.queue.lock import acquire_lock, release_lock
from etl.utils.cache import set_json, delete_key
from etl.utils.telegram import send_telegram_message
from etl.utils.dq import run_dq_checks, DqIssue, send_dq_telegram_alert


SOURCES = {
    "1c": (OneCExtractor, transform_onec, load_1c),
    "amocrm": (AmoCRMExtractor, transform_amocrm, load_amocrm),
    "gsheets": (GoogleSheetsExtractor, transform_gsheets, load_gsheets),
}


def run_sync(sources: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    if not acquire_lock():
        return {"status": "skipped", "reason": "Another ETL run is in progress"}

    started_at = datetime.now(timezone.utc).isoformat()
    run_record = {
        "started_at": started_at,
        "status": "running",
        "sources": sources or list(SOURCES.keys()),
        "records_processed": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "records_failed": 0,
        "error_message": None,
        "details": {},
    }
    _save_status(run_record)

    db = get_db()
    dq_issues: list[DqIssue] = []
    try:
        selected = sources if sources else list(SOURCES.keys())
        for src in selected:
            if src not in SOURCES:
                run_record["details"][src] = {"status": "unknown_source"}
                continue
            extractor_cls, transformer, loader = SOURCES[src]
            try:
                raw = extractor_cls().extract()
                transformed = transformer(raw, db)
                source_issues = run_dq_checks(transformed)
                dq_issues.extend(source_issues)
                if dry_run:
                    count = sum(len(v) for v in transformed.values() if isinstance(v, list))
                    run_record["details"][src] = {"status": "dry_run", "rows_transformed": count, "dq_issues": len(source_issues)}
                    continue
                stats = loader(db, transformed)
                db.commit()
                total = sum(stats.values())
                run_record["records_processed"] += total
                run_record["records_inserted"] += total
                run_record["details"][src] = {"status": "success", "stats": stats, "dq_issues": len(source_issues)}
            except Exception as e:
                db.rollback()
                run_record["records_failed"] += 1
                run_record["details"][src] = {
                    "status": "failed",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }

        details = run_record["details"].values()
        all_success = details and all(d.get("status") == "success" for d in details)
        run_record["status"] = "success" if all_success and not dq_issues else "partial" if all_success else "failed"
    except Exception as e:
        db.rollback()
        run_record["status"] = "failed"
        run_record["error_message"] = str(e)
    finally:
        close_db(db)
        run_record["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_status(run_record)
        run_id = _insert_run_record(run_record)
        if run_id and dq_issues:
            _insert_dq_logs(run_id, dq_issues)
            send_dq_telegram_alert(dq_issues)
        _notify_if_bad(run_record)
        release_lock()
        _invalidate_metrics_cache()

    return run_record


def _notify_if_bad(record: dict[str, Any]) -> None:
    status = record.get("status")
    if status not in ("failed", "partial"):
        return
    started = record.get("started_at", "unknown")
    finished = record.get("finished_at", "unknown")
    error = record.get("error_message") or ""
    details = record.get("details", {})
    failed_sources = [src for src, d in details.items() if d.get("status") == "failed"]
    source_info = f"Источники с ошибками: {', '.join(failed_sources)}" if failed_sources else ""
    message = (
        f"⚠️ <b>ETL run {status.upper()}</b>\n"
        f"Начало: {started}\n"
        f"Окончание: {finished}\n"
        f"Обработано: {record.get('records_processed', 0)} | "
        f"Ошибок: {record.get('records_failed', 0)}\n"
    )
    if source_info:
        message += f"{source_info}\n"
    if error:
        message += f"Ошибка: {error[:500]}"
    send_telegram_message(message)


def _save_status(record: dict[str, Any]) -> None:
    set_json("etl:last_run", record, ttl=86400)


def _insert_run_record(record: dict[str, Any]) -> int | None:
    db = get_db()
    try:
        result = db.execute(text("""
            INSERT INTO etl_runs (
                etl_name, started_at, finished_at, status,
                records_processed, records_inserted, records_updated,
                records_failed, error_message, log_output
            ) VALUES (
                :etl_name, :started_at, :finished_at, :status,
                :records_processed, :records_inserted, :records_updated,
                :records_failed, :error_message, :log_output
            ) RETURNING run_id
        """), {
            "etl_name": "sync",
            "started_at": record["started_at"],
            "finished_at": record["finished_at"],
            "status": record["status"],
            "records_processed": record["records_processed"],
            "records_inserted": record["records_inserted"],
            "records_updated": record["records_updated"],
            "records_failed": record["records_failed"],
            "error_message": record.get("error_message"),
            "log_output": str(record["details"])[:4000],
        })
        db.commit()
        row = result.fetchone()
        return row[0] if row else None
    except Exception:
        db.rollback()
        return None
    finally:
        close_db(db)


def _insert_dq_logs(run_id: int, issues: list[DqIssue]) -> None:
    db = get_db()
    try:
        for issue in issues:
            db.execute(text("""
                INSERT INTO etl_logs (run_id, log_type, source, metric_name, message, details)
                VALUES (:run_id, :log_type, :source, :metric_name, :message, :details)
            """), {
                "run_id": run_id,
                "log_type": "dq_anomaly",
                "source": issue.source,
                "metric_name": issue.rule,
                "message": issue.message,
                "details": issue.details,
            })
        db.commit()
    except Exception:
        db.rollback()
    finally:
        close_db(db)


def _invalidate_metrics_cache() -> None:
    delete_key("metrics:pnl")
    delete_key("metrics:cashflow")


def main():
    parser = argparse.ArgumentParser(description="BI Platform ETL sync runner")
    parser.add_argument(
        "--sources",
        type=lambda s: [x.strip() for x in s.split(",")],
        default=None,
        help="Comma-separated sources: 1c,amocrm,gsheets",
    )
    parser.add_argument("--dry-run", action="store_true", help="Transform without loading")
    args = parser.parse_args()
    result = run_sync(sources=args.sources, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
