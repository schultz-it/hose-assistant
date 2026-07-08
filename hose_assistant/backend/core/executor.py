"""Valve executor with hard failsafes (SPEC section 6, non-negotiable).

Safety model:
  * Before any valve opens, a persisted watchdog turn-off job is scheduled at
    ``duration + 2 min`` — it survives process restarts (SQLAlchemy job store)
    and fires even if this code crashes mid-run.
  * On add-on start: close every known valve ("clean slate").
  * Any HA API error mid-run: abort the session and close everything.
  * ``stop_all()`` (panic button): cancel the run task, close everything.

Zones run strictly one at a time; the optional master valve opens first and
closes at the end (SPEC 5.1).
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select

from .. import models
from ..db import SessionLocal
from . import engine as eng
from . import ha

log = logging.getLogger(__name__)

WATCHDOG_GRACE_MIN = 2.0

# Set by scheduler.init(); kept module-level so watchdog jobs are importable.
_scheduler = None


def set_scheduler(scheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def watchdog_turn_off(entity_id: str) -> None:
    """Persisted watchdog job body: force a valve closed (sync, standalone)."""
    try:
        ha.turn_off_sync(entity_id)
        log.warning("Watchdog fired: closed %s", entity_id)
    except Exception as exc:  # noqa: BLE001 — never raise from a watchdog
        log.error("Watchdog could not close %s: %s", entity_id, exc)


def _schedule_watchdog(entity_id: str, minutes: float) -> None:
    if _scheduler is None:
        return
    run_at = datetime.now() + timedelta(minutes=minutes + WATCHDOG_GRACE_MIN)
    _scheduler.add_job(
        watchdog_turn_off, "date", run_date=run_at, args=[entity_id],
        id=f"watchdog_{entity_id}", replace_existing=True,
        misfire_grace_time=24 * 3600,
    )


def _cancel_watchdog(entity_id: str) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(f"watchdog_{entity_id}")
    except Exception:  # job already fired or never existed
        pass


class Executor:
    """Sequential run queue. One irrigation session at a time."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._open_valves: set[str] = set()

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------- helpers

    async def _open(self, entity_id: str, minutes: float) -> None:
        _schedule_watchdog(entity_id, minutes)  # watchdog FIRST, then open
        await ha.turn_on(entity_id)
        self._open_valves.add(entity_id)

    async def _close(self, entity_id: str) -> None:
        await ha.turn_off(entity_id)
        self._open_valves.discard(entity_id)
        _cancel_watchdog(entity_id)

    async def close_everything(self, reason: str = "") -> None:
        """Close master + every zone valve, best-effort, never raises."""
        with SessionLocal() as db:
            cfg = db.get(models.SystemConfig, 1)
            entities = [z.valve_entity for z in db.scalars(select(models.Zone)).all()]
            if cfg and cfg.master_valve_entity:
                entities.append(cfg.master_valve_entity)
            for entity in entities:
                try:
                    await ha.turn_off(entity)
                except Exception as exc:  # noqa: BLE001
                    log.error("close_everything: %s failed: %s", entity, exc)
            self._open_valves.clear()
            if reason:
                eng.log_event(db, "warning", f"All valves closed: {reason}")
                db.commit()

    # ------------------------------------------------------------- running

    async def run_zone_now(self, zone_id: int, minutes: float) -> bool:
        """Manual single-zone run. Returns False if executor is busy."""
        if self.busy:
            return False
        self._task = asyncio.create_task(self._session([(zone_id, minutes)], None))
        return True

    async def run_schedule(self, run_ids: list[int]) -> bool:
        """Execute planned Schedule rows (already ordered)."""
        if self.busy:
            return False
        with SessionLocal() as db:
            rows = [db.get(models.Schedule, rid) for rid in run_ids]
            pairs = [(r.zone_id, r.duration_min) for r in rows if r and r.status == "planned"]
            ids = [r.id for r in rows if r and r.status == "planned"]
        self._task = asyncio.create_task(self._session(pairs, ids))
        return True

    async def stop_all(self) -> None:
        """Panic button: cancel the session and close everything."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self.close_everything("stop requested")

    async def _session(self, pairs: list[tuple[int, float]], run_ids: list[int] | None) -> None:
        """One irrigation session: master valve, zones in order, failsafes."""
        with SessionLocal() as db:
            cfg = db.get(models.SystemConfig, 1)
            master = cfg.master_valve_entity if cfg else None
            pre_open = cfg.master_valve_pre_open_s if cfg else 5
            total_min = sum(m for _, m in pairs)
            try:
                if master:
                    await self._open(master, total_min)
                    await asyncio.sleep(pre_open)

                for idx, (zone_id, minutes) in enumerate(pairs):
                    zone = db.get(models.Zone, zone_id)
                    if zone is None:
                        continue
                    run_id = run_ids[idx] if run_ids else None
                    if run_id:
                        row = db.get(models.Schedule, run_id)
                        row.status = "running"
                        db.commit()
                    eng.log_event(db, "info",
                                  f"Zone '{zone.name}' ON for {minutes:g} min")
                    db.commit()
                    for run_min, soak_min in eng.cycle_soak(zone, minutes):
                        await self._open(zone.valve_entity, run_min)
                        await asyncio.sleep(run_min * 60.0)
                        await self._close(zone.valve_entity)
                        if soak_min > 0:
                            await asyncio.sleep(soak_min * 60.0)
                    mm = minutes / 60.0 * zone.precipitation_rate_mmh
                    eng.record_irrigation(db, zone.id, mm, date.today())
                    if run_id:
                        row = db.get(models.Schedule, run_id)
                        row.status = "done"
                    eng.log_event(db, "info",
                                  f"Zone '{zone.name}' done ({mm:.1f} mm applied)")
                    db.commit()

                if master:
                    await self._close(master)
            except asyncio.CancelledError:
                raise  # stop_all() takes over the cleanup
            except Exception as exc:  # noqa: BLE001 — HA unreachable etc.
                eng.log_event(db, "error", f"Session aborted: {exc!r}")
                db.commit()
                await self.close_everything("session aborted on error")


# Singleton used by the API and scheduler.
executor = Executor()
