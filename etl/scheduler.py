from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from etl.config import settings
from etl.runners.sync import run_sync
from etl.utils.telegram import send_telegram_message
import logging

scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)


def _safe_run_sync():
    try:
        run_sync()
    except Exception as exc:
        logger.exception("Scheduled ETL sync failed: %s", exc)
        send_telegram_message(
            f"🚨 <b>Scheduled ETL sync crashed</b>\n"
            f"Time: {datetime.now().isoformat()}\n"
            f"Error: {str(exc)[:500]}"
        )


def _run_alerts(schedule: str):
    from sqlalchemy.orm import Session
    from deps import engine
    from services.alerts_service import run_alert_checks

    db = Session(bind=engine)
    import asyncio
    try:
        asyncio.run(run_alert_checks(schedule, db))
    finally:
        db.close()


def _run_forecast():
    from sqlalchemy.orm import Session
    from deps import engine
    from services.forecast_service import run_forecast_job

    db = Session(bind=engine)
    try:
        return run_forecast_job(db)
    finally:
        db.close()


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            _safe_run_sync,
            trigger=IntervalTrigger(minutes=settings.etl_run_interval_minutes),
            id="etl_sync",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.add_job(
            lambda: _run_alerts("daily"),
            trigger=CronTrigger(hour=9, minute=0),
            id="alerts_daily",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.add_job(
            lambda: _run_alerts("hourly"),
            trigger=IntervalTrigger(hours=1),
            id="alerts_hourly",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.add_job(
            _run_forecast,
            trigger=CronTrigger(hour=3, minute=0),
            id="forecast_daily",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
