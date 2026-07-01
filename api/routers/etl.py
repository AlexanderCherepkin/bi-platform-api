from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from deps import get_db, require_role
from etl.runners.sync import run_sync, SOURCES
from etl.scheduler import start_scheduler, shutdown_scheduler
from etl.utils.cache import get_json
from models import EtlRun

router = APIRouter()


class SyncRequest(BaseModel):
    sources: list[str] | None = None
    dry_run: bool = False


@router.post("/sync", response_model=dict[str, Any])
def trigger_sync(
    payload: SyncRequest,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "cfo"))
):
    sources = payload.sources
    valid = sources is None or all(s in SOURCES for s in sources)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Unknown source. Allowed: {list(SOURCES.keys())}")
    result = run_sync(sources=sources, dry_run=payload.dry_run)
    return result


@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    user=Depends(require_role("admin", "cfo", "ceo", "sales_head", "manager"))
):
    last = get_json("etl:last_run")
    runs = db.query(EtlRun).order_by(EtlRun.started_at.desc()).limit(10).all()
    return {
        "last_run": last,
        "recent_runs": [
            {
                "run_id": r.run_id,
                "etl_name": r.etl_name,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "status": r.status,
                "records_processed": r.records_processed,
                "records_inserted": r.records_inserted,
                "records_updated": r.records_updated,
                "records_failed": r.records_failed,
            }
            for r in runs
        ],
    }


@router.post("/scheduler/start")
def start_etl_scheduler(user=Depends(require_role("admin"))):
    start_scheduler()
    return {"status": "scheduler_started"}


@router.post("/scheduler/stop")
def stop_etl_scheduler(user=Depends(require_role("admin"))):
    shutdown_scheduler()
    return {"status": "scheduler_stopped"}
