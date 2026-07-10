"""Water-balance engine (SPEC section 6, steps 1-7).

Pure calculation + planning: no valve is ever actuated from this module
(that is the executor's job). Everything works on the SQLAlchemy session
passed in, so it is fully testable offline.
"""
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from . import kc, soil

log = logging.getLogger(__name__)


def log_event(db: Session, level: str, message: str, meta: dict | None = None) -> None:
    db.add(models.EventLog(level=level, message=message, meta=meta))
    log.log(logging.WARNING if level == "warning" else logging.INFO, message)


def reconcile_interrupted_runs(db: Session) -> int:
    """Mark runs left 'running' by a killed session as aborted.

    A watering session sets a row to 'running' and back to 'done' when it
    finishes. If the add-on restarts (or is stopped) mid-run, the row would
    stay 'running' forever and linger in the dashboard — reconcile it here.
    """
    orphans = db.scalars(
        select(models.Schedule).where(models.Schedule.status == "running")
    ).all()
    for row in orphans:
        row.status = "aborted"
        row.skip_reason = "interrupted"
    if orphans:
        log_event(db, "warning",
                  f"{len(orphans)} interrupted run(s) marked aborted")
    db.flush()
    return len(orphans)


# ------------------------------------------------------------------ balance

def fill_balance(db: Session, daily_actuals: list[dict]) -> int:
    """Upsert et0/rain/kc_eff rows for every enabled zone (engine step 1)."""
    zones = db.scalars(select(models.Zone).where(models.Zone.enabled)).all()
    written = 0
    for zone in zones:
        for day in daily_actuals:
            month = int(day["date"][5:7])
            row = db.scalar(
                select(models.WaterBalance).where(
                    models.WaterBalance.zone_id == zone.id,
                    models.WaterBalance.date == day["date"],
                )
            )
            if row is None:
                row = models.WaterBalance(zone_id=zone.id, date=day["date"])
                db.add(row)
            row.et0 = day["et0"]
            row.rain_mm = day["rain_mm"]
            row.kc_eff = kc.kc_eff(zone, month)
            written += 1
    db.flush()
    return written


def update_deficits(db: Session, cfg: models.SystemConfig) -> None:
    """Recompute the deficit chain per zone (engine step 2).

    deficit = clamp(prev + ET0 x Kc_eff x intensity x et_mult
                    - effective_rain - irrigated, 0, TAW)

    Recomputed over the whole stored window each time — idempotent, and the
    clamp makes the series converge quickly even without infinite history.
    """
    zones = db.scalars(select(models.Zone)).all()
    for zone in zones:
        taw = soil.taw_mm(zone)
        infil = soil.infiltration_mmh(zone.soil_type)
        rows = db.scalars(
            select(models.WaterBalance)
            .where(models.WaterBalance.zone_id == zone.id)
            .order_by(models.WaterBalance.date)
        ).all()
        deficit = 0.0
        for row in rows:
            program = active_program(db, date.fromisoformat(row.date))
            et_mult = program.et_multiplier if program else 1.0
            et_loss = (row.et0 or 0.0) * (row.kc_eff or 0.0) * cfg.watering_intensity * et_mult
            # SPEC: effective rain = min(rain, infiltration capacity) x cover
            # factor (plastic film keeps most rainfall out of the root zone).
            eff_rain = min(row.rain_mm or 0.0, infil) * kc.cover_rain_factor(zone)
            deficit = max(0.0, min(taw, deficit + et_loss - eff_rain - (row.irrigated_mm or 0.0)))
            row.deficit_mm = round(deficit, 2)
    db.flush()


def current_deficit(db: Session, zone_id: int) -> float:
    row = db.scalar(
        select(models.WaterBalance)
        .where(models.WaterBalance.zone_id == zone_id)
        .order_by(models.WaterBalance.date.desc())
    )
    return row.deficit_mm or 0.0 if row else 0.0


def record_irrigation(db: Session, zone_id: int, mm: float, on_date: date | None = None) -> None:
    """Add applied irrigation to today's balance row (created if missing)."""
    d = (on_date or date.today()).isoformat()
    row = db.scalar(
        select(models.WaterBalance).where(
            models.WaterBalance.zone_id == zone_id, models.WaterBalance.date == d
        )
    )
    if row is None:
        row = models.WaterBalance(zone_id=zone_id, date=d)
        db.add(row)
    row.irrigated_mm = round((row.irrigated_mm or 0.0) + mm, 3)
    db.flush()


def merge_forecast_rain(daily: list[dict], ha_rain: list[dict],
                        today_iso: str) -> list[dict]:
    """Override FORECAST rain with the HA weather entity's values (SPEC 6.1).

    Past days keep Open-Meteo actuals; only dates >= today are replaced,
    and only where the entity actually provides that date.
    """
    by_date = {r["date"]: r["rain_mm"] for r in ha_rain}
    out = []
    for d in daily:
        if d["date"] >= today_iso and d["date"] in by_date:
            d = {**d, "rain_mm": by_date[d["date"]]}
        out.append(d)
    return out


# ------------------------------------------------------------------ programs

def _mmdd_in_range(d: date, start: str, end: str) -> bool:
    """True if date's MM-DD falls in [start, end], handling year wrap."""
    mmdd = d.strftime("%m-%d")
    if start <= end:
        return start <= mmdd <= end
    return mmdd >= start or mmdd <= end  # wraps over new year


def active_program(db: Session, on_date: date) -> models.Program | None:
    """Highest-priority budget/fixed program covering the date (SPEC 5.3)."""
    programs = db.scalars(select(models.Program)).all()
    candidates = [
        p for p in programs
        if not p.manual_only and p.date_start and p.date_end
        and _mmdd_in_range(on_date, p.date_start, p.date_end)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.priority, reverse=True)[0]


def _day_allowed(db: Session, program: models.Program, on_date: date) -> bool:
    rule = program.allowed_days or {}
    if "weekdays" in rule:
        return on_date.weekday() in rule["weekdays"]
    if "every_n_days" in rule:
        last = db.scalar(
            select(models.Schedule)
            .where(models.Schedule.program_id == program.id,
                   models.Schedule.status == "done")
            .order_by(models.Schedule.start.desc())
        )
        if last is None or last.start is None:
            return True
        return (on_date - last.start.date()).days >= int(rule["every_n_days"])
    return True  # no rule -> every day allowed


# ------------------------------------------------------------------ runtime

def runtime_minutes(zone: models.Zone, deficit_mm: float) -> float:
    """Minutes to replace the deficit at the zone's precipitation rate."""
    minutes = deficit_mm / zone.precipitation_rate_mmh * 60.0
    return round(min(minutes, float(zone.max_runtime_min)), 1)


def cycle_soak(zone: models.Zone, minutes: float) -> list[tuple[float, float]]:
    """Split a runtime into (run, soak) cycles to avoid runoff (engine step 6).

    Cycles are needed when the zone is steep or PR exceeds the soil's
    infiltration capacity. Zones run sequentially (interleaving other zones
    during soaks is a post-v1 optimisation).
    """
    infil = soil.infiltration_mmh(zone.soil_type)
    needs_cycles = zone.slope == "steep" or zone.precipitation_rate_mmh > infil
    if not needs_cycles or minutes <= 0:
        return [(minutes, 0.0)] if minutes > 0 else []
    # Max minutes per cycle before applied depth outruns infiltration.
    max_cycle = max(3.0, infil / zone.precipitation_rate_mmh * 60.0)
    if zone.slope == "steep":
        max_cycle = max(3.0, max_cycle / 2.0)
    cycles: list[tuple[float, float]] = []
    remaining = minutes
    while remaining > 0:
        run = round(min(max_cycle, remaining), 1)
        remaining = round(remaining - run, 1)
        soak = round(run, 1) if remaining > 0 else 0.0  # soak >= cycle length
        cycles.append((run, soak))
    return cycles


# ------------------------------------------------------------------ planning

def plan_today(db: Session, cfg: models.SystemConfig, forecast: list[dict],
               today: date | None = None) -> list[models.Schedule]:
    """Build the next planned runs (engine steps 3-7). Returns created rows.

    The irrigation window is always honored: if it is called after today's
    window (or every fixed-mode run time) has already passed, planning
    rolls forward to the window's next occurrence (normally tomorrow)
    instead of ever starting a run "right now" outside the window — this
    matters because recalculation can be triggered any time of day (manual
    button, or automatically after saving a zone/program).

    ``forecast`` is the fetch_daily() output (needs today + tomorrow rows for
    the 24h rain-skip check and wind).
    """
    today = today or date.today()
    now = datetime.now()
    created: list[models.Schedule] = []

    if not cfg.system_enabled:
        log_event(db, "info", "Plan skipped: system is OFF")
        return created
    if cfg.rain_delay_until and cfg.rain_delay_until > now:
        log_event(db, "info", f"Plan skipped: rain delay until {cfg.rain_delay_until}")
        return created

    program = active_program(db, today)
    if program is None:
        log_event(db, "info", "No program covers today")
        return created
    if not _day_allowed(db, program, today):
        log_event(db, "info", f"'{program.name}': today not in allowed days")
        return created

    if program.mode == "fixed":
        fixed_runs = [
            r for r in (program.fixed_runs or [])
            if datetime.combine(today, time.fromisoformat(r["time"])) >= now
        ]
        plan_date = today
        if not fixed_runs and program.fixed_runs:
            # Every run time for today already passed: roll to tomorrow.
            plan_date = today + timedelta(days=1)
            next_program = active_program(db, plan_date)
            if next_program is None or not _day_allowed(db, next_program, plan_date):
                log_event(db, "info",
                          f"'{program.name}': today's run times already passed; "
                          f"no active program/allowed day tomorrow")
                return created
            program = next_program
            fixed_runs = program.fixed_runs or []

        next24 = [d for d in forecast if d["date"] >= plan_date.isoformat()][:2]
        rain_24h = sum(d["rain_mm"] or 0.0 for d in next24)
        if rain_24h >= cfg.forecast_rain_skip_mm:
            log_event(db, "info",
                      f"All runs skipped: {rain_24h:.1f} mm rain forecast in 24h "
                      f"(threshold {cfg.forecast_rain_skip_mm})")
            return created

        zones = db.scalars(
            select(models.Zone).where(models.Zone.enabled)
            .order_by(models.Zone.order, models.Zone.id)
        ).all()
        overrides = program.zone_overrides or {}
        for run in fixed_runs:
            t = time.fromisoformat(run["time"])
            start = datetime.combine(plan_date, t)
            for zone in zones:
                ov = overrides.get(str(zone.id), {})
                if not ov.get("enabled", True):
                    continue
                created.append(models.Schedule(
                    program_id=program.id, zone_id=zone.id, start=start,
                    duration_min=float(run["minutes_per_zone"]), status="planned"))
                start += timedelta(minutes=float(run["minutes_per_zone"]))
        db.add_all(created)
        db.flush()
        return created

    # budget mode
    window_start = datetime.combine(today, time.fromisoformat(program.window_start))
    window_end = datetime.combine(today, time.fromisoformat(program.window_end))
    if window_end <= window_start:
        window_end += timedelta(days=1)  # window crosses midnight

    if now >= window_end:
        # Today's window is already closed: roll to its next occurrence
        # instead of ever starting a run outside the configured window.
        next_date = today + timedelta(days=1)
        next_program = active_program(db, next_date)
        if next_program is None or not _day_allowed(db, next_program, next_date):
            log_event(db, "info",
                      f"'{program.name}': today's window already passed; "
                      f"no active program/allowed day tomorrow")
            return created
        program = next_program
        today = next_date
        window_start = datetime.combine(today, time.fromisoformat(program.window_start))
        window_end = datetime.combine(today, time.fromisoformat(program.window_end))
        if window_end <= window_start:
            window_end += timedelta(days=1)

    # Forecast rain in the next 24h from the planning day (today's remaining
    # + tomorrow forecast rows, or the rolled-forward day if we shifted).
    next24 = [d for d in forecast if d["date"] >= today.isoformat()][:2]
    rain_24h = sum(d["rain_mm"] or 0.0 for d in next24)
    wind_max = max((d.get("wind_kmh") or 0.0 for d in next24), default=0.0)
    if rain_24h >= cfg.forecast_rain_skip_mm:
        log_event(db, "info",
                  f"All runs skipped: {rain_24h:.1f} mm rain forecast in 24h "
                  f"(threshold {cfg.forecast_rain_skip_mm})")
        return created

    zones = db.scalars(
        select(models.Zone).where(models.Zone.enabled).order_by(models.Zone.order, models.Zone.id)
    ).all()
    overrides = program.zone_overrides or {}

    wanted: list[tuple[models.Zone, float]] = []
    for zone in zones:
        ov = overrides.get(str(zone.id), {})
        if not ov.get("enabled", True):
            continue
        if (cfg.wind_skip_kmh and zone.irrigation_type == "spray"
                and wind_max >= cfg.wind_skip_kmh):
            log_event(db, "info", f"Zone '{zone.name}' skipped: wind {wind_max:.0f} km/h")
            continue
        deficit = current_deficit(db, zone.id)
        threshold = program.mad_pct / 100.0 * soil.taw_mm(zone)
        if deficit < threshold:
            continue  # bucket not dry enough yet
        minutes = runtime_minutes(zone, deficit) * float(ov.get("multiplier", 1.0))
        if minutes > 0:
            wanted.append((zone, minutes))

    if not wanted:
        return created

    # Pack into the window, including soak pauses; proportional reduction if over.
    def total_span(pairs: list[tuple[models.Zone, float]]) -> float:
        span = 0.0
        for zone, minutes in pairs:
            span += sum(r + s for r, s in cycle_soak(zone, minutes))
        return span

    window_min = (window_end - window_start).total_seconds() / 60.0
    span = total_span(wanted)
    if span > window_min:
        factor = window_min / span
        wanted = [(z, round(m * factor, 1)) for z, m in wanted]
        log_event(db, "warning",
                  f"Plan exceeds window by {span - window_min:.0f} min: "
                  f"runtimes reduced to {factor * 100:.0f}%")

    cursor = window_start
    for zone, minutes in wanted:
        created.append(models.Schedule(
            program_id=program.id, zone_id=zone.id, start=cursor,
            duration_min=minutes, status="planned"))
        cursor += timedelta(minutes=sum(r + s for r, s in cycle_soak(zone, minutes)))
    db.add_all(created)
    db.flush()
    log_event(db, "info",
              f"Planned {len(created)} run(s) for '{program.name}' from "
              f"{window_start.strftime('%H:%M')}")
    return created
