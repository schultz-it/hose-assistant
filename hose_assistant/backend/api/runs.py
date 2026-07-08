"""Run control + schedule + event log endpoints (SPEC 9 — Milestone 4)."""
from datetime import date, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core import engine as eng
from ..core import scheduler as sched
from ..core import soil, weather
from ..core.executor import executor
from ..db import get_db
from .config import ensure_config

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/status")
def get_status(db: Session = Depends(get_db)) -> dict:
    """One-call dashboard payload: system, executor, per-zone reservoir."""
    cfg = ensure_config(db)
    program = eng.active_program(db, date.today())
    mad_pct = program.mad_pct if program else 50.0
    zones = db.scalars(
        select(models.Zone).order_by(models.Zone.order, models.Zone.id)
    ).all()
    zone_status = []
    for z in zones:
        taw = soil.taw_mm(z)
        deficit = eng.current_deficit(db, z.id)
        zone_status.append({
            "id": z.id, "name": z.name, "icon": z.icon, "enabled": z.enabled,
            "deficit_mm": round(deficit, 1), "taw_mm": round(taw, 1),
            "trigger_mm": round(mad_pct / 100.0 * taw, 1),
        })
    upcoming = db.scalars(
        select(models.Schedule)
        .where(models.Schedule.status.in_(["planned", "running"]))
        .order_by(models.Schedule.start)
        .limit(20)
    ).all()
    return {
        "busy": executor.busy,
        "system_enabled": cfg.system_enabled,
        "watering_intensity": cfg.watering_intensity,
        "rain_delay_until": cfg.rain_delay_until.isoformat() if cfg.rain_delay_until else None,
        "active_program": {"id": program.id, "name": program.name} if program else None,
        "zones": zone_status,
        "upcoming": [
            {"id": r.id, "zone_id": r.zone_id, "start": r.start.isoformat() if r.start else None,
             "duration_min": r.duration_min, "status": r.status}
            for r in upcoming
        ],
    }


@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(models.Schedule).order_by(models.Schedule.start.desc()).limit(100)
    ).all()
    return [
        {
            "id": r.id, "program_id": r.program_id, "zone_id": r.zone_id,
            "start": r.start.isoformat() if r.start else None,
            "duration_min": r.duration_min, "status": r.status,
            "skip_reason": r.skip_reason,
        }
        for r in rows
    ]


@router.post("/schedule/{run_id}/skip")
def skip_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(models.Schedule, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if row.status != "planned":
        raise HTTPException(status_code=409, detail=f"Run is {row.status}, not planned")
    row.status = "skipped"
    row.skip_reason = "user"
    eng.log_event(db, "info", f"Run {run_id} skipped by user")
    db.commit()
    return {"id": run_id, "status": "skipped"}


@router.post("/run/zone/{zone_id}")
async def run_zone(zone_id: int, minutes: float = Query(gt=0, le=240),
                   db: Session = Depends(get_db)) -> dict:
    zone = db.get(models.Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    cfg = ensure_config(db)
    if not cfg.system_enabled:
        raise HTTPException(status_code=409, detail="System is OFF")
    minutes = min(minutes, float(zone.max_runtime_min))
    started = await executor.run_zone_now(zone_id, minutes)
    if not started:
        raise HTTPException(status_code=409, detail="Executor busy: a run is in progress")
    return {"zone_id": zone_id, "minutes": minutes, "status": "started"}


@router.post("/run/program/{program_id}")
async def run_program(program_id: int, db: Session = Depends(get_db)) -> dict:
    """Plan the program NOW (ignoring window/day rules) and execute it."""
    program = db.get(models.Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    cfg = ensure_config(db)
    if not cfg.system_enabled:
        raise HTTPException(status_code=409, detail="System is OFF")

    zones = db.scalars(
        select(models.Zone).where(models.Zone.enabled)
        .order_by(models.Zone.order, models.Zone.id)
    ).all()
    overrides = program.zone_overrides or {}
    rows: list[models.Schedule] = []
    start = datetime.now()
    for zone in zones:
        ov = overrides.get(str(zone.id), {})
        if not ov.get("enabled", True):
            continue
        deficit = eng.current_deficit(db, zone.id)
        minutes = eng.runtime_minutes(zone, deficit) * float(ov.get("multiplier", 1.0))
        if minutes <= 0:
            continue
        rows.append(models.Schedule(program_id=program.id, zone_id=zone.id,
                                    start=start, duration_min=minutes, status="planned"))
    if not rows:
        return {"program_id": program_id, "status": "nothing_to_run",
                "detail": "No zone above zero deficit"}
    db.add_all(rows)
    db.commit()
    started = await executor.run_schedule([r.id for r in rows])
    if not started:
        raise HTTPException(status_code=409, detail="Executor busy: a run is in progress")
    return {"program_id": program_id, "runs": len(rows), "status": "started"}


@router.post("/stop_all")
async def stop_all(db: Session = Depends(get_db)) -> dict:
    await executor.stop_all()
    return {"status": "stopped", "detail": "all valves closed"}


@router.post("/engine/recalc")
async def engine_recalc(db: Session = Depends(get_db)) -> dict:
    """Run the daily pipeline on demand (weather -> deficits -> plan)."""
    cfg = ensure_config(db)
    if cfg.latitude is None or cfg.longitude is None:
        raise HTTPException(status_code=400, detail="Location not configured")
    try:
        daily = await weather.fetch_daily(cfg.latitude, cfg.longitude)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo unreachable: {exc}")
    today_iso = date.today().isoformat()
    eng.fill_balance(db, [d for d in daily if d["date"] < today_iso])
    eng.update_deficits(db, cfg)
    for row in db.scalars(
        select(models.Schedule).where(models.Schedule.status == "planned")
    ).all():
        db.delete(row)
    created = eng.plan_today(db, cfg, daily)
    db.commit()
    if created and sched.scheduler is not None:
        run_ids = [r.id for r in created]
        first_start = min(r.start for r in created)
        sched.scheduler.add_job(
            sched.execute_plan, "date", run_date=max(first_start, datetime.now()),
            args=[run_ids], id="execute_plan", replace_existing=True,
            misfire_grace_time=3600,
        )
    return {
        "planned_runs": len(created),
        "runs": [{"zone_id": r.zone_id, "start": r.start.isoformat(),
                  "duration_min": r.duration_min} for r in created],
    }


@router.get("/log")
def get_log(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(models.EventLog).order_by(models.EventLog.ts.desc()).limit(limit)
    ).all()
    return [
        {"ts": r.ts.isoformat(), "level": r.level, "message": r.message, "meta": r.meta}
        for r in rows
    ]
