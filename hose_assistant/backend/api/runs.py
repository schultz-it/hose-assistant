"""Run control + schedule + event log endpoints (SPEC 9 — Milestone 4)."""
from datetime import date, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..core import engine as eng
from ..core import kc, soil
from ..core import scheduler as sched
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


@router.post("/zones/{zone_id}/reset_reservoir")
def reset_reservoir(zone_id: int,
                    state: str = Query("full", pattern="^(full|empty)$"),
                    db: Session = Depends(get_db)) -> dict:
    """Set a zone's soil reservoir to FULL (deficit 0) or EMPTY (deficit TAW).

    Recorded as a manual adjustment on today's balance row (positive mm for
    "just watered", negative for "actually bone dry"), so the balance chain
    stays consistent across recomputes — a raw overwrite would be undone by
    the next daily calculation.
    """
    zone = db.get(models.Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    cfg = ensure_config(db)
    target = 0.0 if state == "full" else soil.taw_mm(zone)
    delta = round(eng.current_deficit(db, zone_id) - target, 3)
    if abs(delta) > 1e-9:
        eng.record_irrigation(db, zone_id, delta)
        eng.update_deficits(db, cfg)
    eng.log_event(db, "info",
                  f"Reservoir set {state} for '{zone.name}' "
                  f"({delta:+.1f} mm manual adjustment)")
    db.commit()
    return {"zone_id": zone_id, "state": state,
            "deficit_mm": eng.current_deficit(db, zone_id)}


@router.get("/zones/{zone_id}/reservoir_detail")
def reservoir_detail(zone_id: int, db: Session = Depends(get_db)) -> dict:
    """Breakdown of the latest balance row behind the dashboard's mm figure.

    Same terms as engine.update_deficits, surfaced read-only for the
    dashboard's "how is this calculated" info popup.
    """
    zone = db.get(models.Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    cfg = ensure_config(db)
    taw = soil.taw_mm(zone)
    infil = soil.infiltration_mmh(zone.soil_type)
    row = db.scalar(
        select(models.WaterBalance)
        .where(models.WaterBalance.zone_id == zone_id)
        .order_by(models.WaterBalance.date.desc())
    )
    if row is None:
        return {"zone_id": zone_id, "date": None, "taw_mm": round(taw, 1)}
    program = eng.active_program(db, date.today())
    et_mult = program.et_multiplier if program else 1.0
    et0 = row.et0 or 0.0
    kc_eff = row.kc_eff or 0.0
    rain_mm = row.rain_mm or 0.0
    irrigated_mm = row.irrigated_mm or 0.0
    cover_factor = kc.cover_rain_factor(zone)
    eff_rain = round(min(rain_mm, infil) * cover_factor, 2)
    et_loss = round(et0 * kc_eff * cfg.watering_intensity * et_mult, 2)
    return {
        "zone_id": zone_id, "date": row.date, "taw_mm": round(taw, 1),
        "deficit_mm": round(row.deficit_mm or 0.0, 1),
        "et0": round(et0, 2), "kc_eff": round(kc_eff, 3),
        "watering_intensity": cfg.watering_intensity, "et_multiplier": et_mult,
        "et_loss_mm": et_loss,
        "rain_mm": round(rain_mm, 1), "cover_rain_factor": cover_factor,
        "infiltration_cap_mmh": infil, "effective_rain_mm": eff_rain,
        "irrigated_mm": round(irrigated_mm, 2),
    }


@router.get("/history")
def get_history(limit: int = 30, db: Session = Depends(get_db)) -> dict:
    """Irrigation runs + rain days, most recent first (dashboard history list)."""
    zone_names = {z.id: z.name for z in db.scalars(select(models.Zone)).all()}
    runs = db.scalars(
        select(models.Schedule)
        .where(models.Schedule.status.in_(["done", "aborted", "skipped"]))
        .order_by(models.Schedule.start.desc())
        .limit(limit)
    ).all()
    rain_rows = db.execute(
        select(models.WaterBalance.date, func.max(models.WaterBalance.rain_mm))
        .group_by(models.WaterBalance.date)
        .order_by(models.WaterBalance.date.desc())
        .limit(limit)
    ).all()
    return {
        "irrigations": [
            {"id": r.id, "zone_id": r.zone_id,
             "zone_name": zone_names.get(r.zone_id, f"#{r.zone_id}"),
             "start": r.start.isoformat() if r.start else None,
             "duration_min": r.duration_min, "status": r.status,
             "skip_reason": r.skip_reason}
            for r in runs
        ],
        "rain": [
            {"date": d, "rain_mm": round(mm, 1)} for d, mm in rain_rows if mm and mm > 0
        ],
    }


@router.post("/stop_all")
async def stop_all(db: Session = Depends(get_db)) -> dict:
    await executor.stop_all()
    return {"status": "stopped", "detail": "all valves closed"}


@router.post("/system/on")
def system_on(db: Session = Depends(get_db)) -> dict:
    cfg = ensure_config(db)
    cfg.system_enabled = True
    eng.log_event(db, "info", "System switched ON")
    db.commit()
    return {"system_enabled": True}


@router.post("/system/off")
async def system_off(db: Session = Depends(get_db)) -> dict:
    """Master OFF: also stops any run in progress (SPEC dashboard controls)."""
    cfg = ensure_config(db)
    cfg.system_enabled = False
    eng.log_event(db, "info", "System switched OFF")
    db.commit()
    await executor.stop_all()
    return {"system_enabled": False}


@router.post("/system/rain_delay")
def rain_delay(hours: int = Query(ge=0, le=168), db: Session = Depends(get_db)) -> dict:
    """Pause planning for N hours (0 cancels the delay)."""
    from datetime import timedelta

    cfg = ensure_config(db)
    cfg.rain_delay_until = (datetime.now() + timedelta(hours=hours)) if hours else None
    eng.log_event(db, "info",
                  f"Rain delay {'set: ' + str(hours) + 'h' if hours else 'cancelled'}")
    db.commit()
    return {"rain_delay_until": cfg.rain_delay_until.isoformat() if cfg.rain_delay_until else None}


@router.post("/schedule/{run_id}/override")
def override_run(run_id: int, minutes: float = Query(gt=0, le=240),
                 db: Session = Depends(get_db)) -> dict:
    """Override the duration of a planned run (SPEC: per-run edit)."""
    row = db.get(models.Schedule, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if row.status != "planned":
        raise HTTPException(status_code=409, detail=f"Run is {row.status}, not planned")
    zone = db.get(models.Zone, row.zone_id)
    minutes = min(minutes, float(zone.max_runtime_min)) if zone else minutes
    row.duration_min = minutes
    eng.log_event(db, "info", f"Run {run_id} duration overridden to {minutes:g} min")
    db.commit()
    return {"id": run_id, "duration_min": minutes}


@router.post("/engine/recalc")
async def engine_recalc(db: Session = Depends(get_db)) -> dict:
    """Run the daily pipeline on demand (weather -> deficits -> plan)."""
    cfg = ensure_config(db)
    if cfg.latitude is None or cfg.longitude is None:
        raise HTTPException(status_code=400, detail="Location not configured")
    try:
        created = await sched.run_recalc(db, cfg)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo unreachable: {exc}")
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
