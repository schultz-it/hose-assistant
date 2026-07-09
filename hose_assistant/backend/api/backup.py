"""Backup & restore (settings + history) as a single JSON file.

The add-on's data already lives in ``/data`` (captured by Home Assistant
snapshots), but a manual export/import is a useful extra safety net and lets
you move a configuration between instances.
"""
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import DateTime, select
from sqlalchemy import inspect as sqla_inspect
from sqlalchemy.orm import Session

from .. import models
from ..core import engine as eng
from ..core import scheduler as sched
from ..core.executor import executor
from ..db import get_db

router = APIRouter(prefix="/api", tags=["backup"])

# All tables in a backup. Settings first, then history. No FKs are declared,
# so insert/delete order is not constrained.
BACKUP_MODELS = [
    models.SystemConfig, models.Zone, models.Program,
    models.WaterBalance, models.Schedule, models.EventLog,
]
BACKUP_VERSION = 1


def _row_to_dict(obj) -> dict:
    out = {}
    for col in sqla_inspect(obj.__class__).columns:
        v = getattr(obj, col.key)
        out[col.key] = v.isoformat() if isinstance(v, datetime) else v
    return out


def _coerce(model, d: dict) -> dict:
    """Keep only known columns and turn ISO strings back into datetimes."""
    out = {}
    for col in sqla_inspect(model).columns:
        if col.key not in d:
            continue
        v = d[col.key]
        if v is not None and isinstance(col.type, DateTime) and isinstance(v, str):
            v = datetime.fromisoformat(v)
        out[col.key] = v
    return out


@router.get("/backup")
def export_backup(db: Session = Depends(get_db)):
    data = {
        "app": "hose_assistant",
        "version": BACKUP_VERSION,
        "created": datetime.now().isoformat(),
        "tables": {
            m.__tablename__: [_row_to_dict(r) for r in db.scalars(select(m)).all()]
            for m in BACKUP_MODELS
        },
    }
    fname = f"hose_assistant_backup_{datetime.now():%Y%m%d_%H%M}.json"
    return JSONResponse(
        data, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/restore")
async def restore_backup(payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    if payload.get("app") != "hose_assistant":
        raise HTTPException(status_code=400, detail="Not a Hose Assistant backup file")
    if payload.get("version") != BACKUP_VERSION:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported backup version {payload.get('version')}")
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise HTTPException(status_code=400, detail="Malformed backup: no tables")

    # Safety: stop anything running before swapping the data underneath it.
    await executor.stop_all()

    counts = {}
    try:
        for model in reversed(BACKUP_MODELS):
            db.query(model).delete()
        db.flush()
        for model in BACKUP_MODELS:
            rows = tables.get(model.__tablename__, [])
            db.add_all(model(**_coerce(model, r)) for r in rows)
            counts[model.__tablename__] = len(rows)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Restore failed: {exc}")

    # Make sure a config row exists and re-arm the daily job with restored settings.
    if db.get(models.SystemConfig, 1) is None:
        db.add(models.SystemConfig(id=1))
        db.commit()
    sched.reschedule_daily_calc()
    eng.log_event(db, "info", f"Backup restored: {counts}")
    db.commit()
    return {"restored": counts}
