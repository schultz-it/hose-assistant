"""APScheduler wiring (SPEC 2, 6): persisted jobs + the daily calc pipeline.

Job store lives in ``/data/scheduler.db`` so watchdog turn-offs survive
restarts (they fire on startup if their time passed while we were down).

Jobs:
  * ``daily_calc``  — cron at cfg.daily_calc_time: refresh weather, update
    deficits, plan today, arm today's execution.
  * ``execute_plan``— date job at the program window start.
  * ``watchdog_*``  — per-valve forced turn-off (see executor).
"""
import logging
from datetime import date, datetime

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..db import DATA_DIR, SessionLocal
from . import engine as eng
from . import executor as ex
from . import ha, weather

log = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


def init() -> AsyncIOScheduler:
    """Create + start the scheduler and arm the daily job. Idempotent."""
    global scheduler
    if scheduler is not None:
        return scheduler
    scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{DATA_DIR}/scheduler.db")}
    )
    ex.set_scheduler(scheduler)
    scheduler.start()
    reschedule_daily_calc()
    # Keep the displayed deficit/reservoir fresh between the nightly calc and
    # any user action (save, manual recalc) — otherwise it only reflects
    # whatever was last computed, however many hours ago that was.
    scheduler.add_job(periodic_recalc, "interval", hours=1,
                      id="periodic_recalc", replace_existing=True,
                      misfire_grace_time=1800)
    # SPEC 11: entity exposure tick (no-op unless enabled in Setup).
    from . import expose

    scheduler.add_job(expose.refresh_job, "interval", seconds=60,
                      id="expose_refresh", replace_existing=True)
    return scheduler


async def periodic_recalc() -> None:
    """Hourly tick: same best-effort pipeline as after a zone/program save."""
    with SessionLocal() as db:
        await try_recalc(db, "periodic refresh")


def shutdown() -> None:
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        ex.set_scheduler(None)


def reschedule_daily_calc() -> None:
    """(Re)arm the daily calc cron from the configured time."""
    if scheduler is None:
        return
    with SessionLocal() as db:
        cfg = db.get(models.SystemConfig, 1)
        calc_time = (cfg.daily_calc_time if cfg else None) or "03:00"
    hour, minute = (int(x) for x in calc_time.split(":")[:2])
    scheduler.add_job(
        daily_calc, "cron", hour=hour, minute=minute,
        id="daily_calc", replace_existing=True, misfire_grace_time=3600,
    )
    log.info("Daily calc scheduled at %s", calc_time)


async def run_recalc(db: Session, cfg: models.SystemConfig) -> list[models.Schedule]:
    """The shared engine pipeline: weather -> balance -> deficits -> plan -> arm.

    Used by the nightly cron, the manual "Recalculate plan" button, and the
    auto-recalc triggered after saving a zone or program. Raises on weather
    fetch failure (callers decide how to surface that); the optional HA
    weather-entity override degrades to a logged warning instead.
    """
    daily = await weather.fetch_daily(cfg.latitude, cfg.longitude)  # may raise
    today_iso = date.today().isoformat()
    # SPEC 6.1: an HA weather entity, if set, overrides the FORECAST rain.
    if cfg.weather_entity:
        try:
            ha_rain = await ha.get_weather_daily_rain(cfg.weather_entity)
            daily = eng.merge_forecast_rain(daily, ha_rain, today_iso)
            eng.log_event(db, "info",
                          f"Forecast rain from {cfg.weather_entity} "
                          f"({len(ha_rain)} days)")
        except Exception as exc:  # noqa: BLE001
            eng.log_event(db, "warning",
                          f"Weather entity {cfg.weather_entity} unreadable "
                          f"({exc!r}); using Open-Meteo forecast")
    balance_days = [d for d in daily if d["date"] < today_iso]
    # Today gets a PARTIAL row — rain actually fallen and ET0 accumulated so
    # far (hourly sums) — so the reservoir reflects rain as it happens.
    # Recomputed on every recalc; tomorrow the full-day actual replaces it.
    # Best-effort: without it the balance is simply as of yesterday (the
    # pre-1.3.1 behaviour), which planning already tolerates.
    try:
        so_far = await weather.fetch_today_so_far(cfg.latitude, cfg.longitude)
        balance_days.append({"date": today_iso, **so_far})
    except Exception as exc:  # noqa: BLE001
        eng.log_event(db, "warning",
                      f"Today's partial rain/ET0 unavailable ({exc}); "
                      f"balance is as of yesterday")
    eng.fill_balance(db, balance_days)
    eng.update_deficits(db, cfg)
    # Drop stale planned rows, then re-plan from scratch.
    for row in db.scalars(
        select(models.Schedule).where(models.Schedule.status == "planned")
    ).all():
        db.delete(row)
    created = eng.plan_today(db, cfg, daily)
    db.commit()
    if created and scheduler is not None:
        first_start = min(r.start for r in created)
        run_ids = [r.id for r in created]
        scheduler.add_job(
            execute_plan, "date",
            run_date=max(first_start, datetime.now()),
            args=[run_ids], id="execute_plan", replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info("Execution armed at %s for %d run(s)", first_start, len(created))
    return created


async def try_recalc(db: Session, reason: str) -> None:
    """Best-effort recalc after a zone/program save — never raises.

    Silently skipped if the location isn't set yet (e.g. still in the
    first-run wizard); any weather/API failure is logged, not propagated,
    so a save action never fails because of it.
    """
    cfg = db.get(models.SystemConfig, 1)
    if cfg is None or cfg.latitude is None or cfg.longitude is None:
        return
    try:
        await run_recalc(db, cfg)
    except Exception as exc:  # noqa: BLE001
        eng.log_event(db, "warning", f"Auto-recalc after {reason} failed: {exc!r}")
        db.commit()


async def daily_calc() -> None:
    """Cron entry point: same pipeline as run_recalc, tolerant of no location."""
    with SessionLocal() as db:
        cfg = db.get(models.SystemConfig, 1)
        if cfg is None or cfg.latitude is None or cfg.longitude is None:
            eng.log_event(db, "warning", "Daily calc skipped: location not set")
            db.commit()
            return
        try:
            await run_recalc(db, cfg)
        except Exception as exc:  # noqa: BLE001
            eng.log_event(db, "error", f"Daily calc: weather fetch failed: {exc}")
            db.commit()


async def execute_plan(run_ids: list[int]) -> None:
    started = await ex.executor.run_schedule(run_ids)
    if not started:
        with SessionLocal() as db:
            eng.log_event(db, "warning", "Planned run not started: executor busy")
            db.commit()
