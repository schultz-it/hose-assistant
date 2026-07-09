"""Weather, sun and water-balance endpoints (SPEC sections 6, 9 — Milestone 3).

``GET /api/weather/summary``  — daily ET0/rain (past + forecast) + sun times.
``GET /api/balance``          — water-balance rows (weather side, per zone).
``POST /api/balance/refresh`` — pull actuals from Open-Meteo and upsert the
                                 balance table for every enabled zone.

Deficit computation and scheduling belong to the engine (Milestone 4); here
the balance rows are filled with the weather inputs (et0, rain, kc_eff).
"""
import os
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core import engine as eng
from ..core import ha as ha_client
from ..core import sun, weather
from ..db import get_db
from .config import ensure_config

router = APIRouter(prefix="/api", tags=["weather"])


def _require_location(cfg: models.SystemConfig) -> tuple[float, float]:
    if cfg.latitude is None or cfg.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Location not configured: set latitude/longitude via PUT /api/config",
        )
    return cfg.latitude, cfg.longitude


def _timezone(cfg: models.SystemConfig) -> str:
    return cfg.timezone or os.environ.get("TZ") or "UTC"


@router.get("/weather/summary")
async def weather_summary(db: Session = Depends(get_db)) -> dict:
    cfg = ensure_config(db)
    lat, lon = _require_location(cfg)
    try:
        daily = await weather.fetch_daily(lat, lon)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo unreachable: {exc}")
    today = date.today().isoformat()
    try:
        sun_today = sun.sun_times(lat, lon, _timezone(cfg))
    except Exception:
        sun_today = None  # e.g. polar day/night — weather data is still useful
    return {
        "latitude": lat,
        "longitude": lon,
        "elevation_m": cfg.elevation_m,
        "timezone": _timezone(cfg),
        "today": today,
        "sun": sun_today,
        "daily": [{**d, "is_forecast": d["date"] >= today} for d in daily],
    }


@router.get("/weather/entity_test")
async def weather_entity_test(db: Session = Depends(get_db)) -> dict:
    """Read the configured HA weather entity and show what the engine gets."""
    cfg = ensure_config(db)
    if not cfg.weather_entity:
        raise HTTPException(status_code=400, detail="No weather entity configured")
    try:
        state = await ha_client.get_state(cfg.weather_entity)
        if state is None:
            raise HTTPException(status_code=404,
                                detail=f"Entity {cfg.weather_entity} not found in HA")
        rain = await ha_client.get_weather_daily_rain(cfg.weather_entity)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"Could not read {cfg.weather_entity}: {exc!r}")
    return {
        "entity": cfg.weather_entity,
        "state": state.get("state"),
        "forecast_days": len(rain),
        "daily_rain_mm": rain,
        "note": "These values override the Open-Meteo FORECAST rain in the "
                "daily calculation (past actuals stay Open-Meteo).",
    }


@router.get("/balance")
def get_balance(days: int = 14, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(models.WaterBalance)
        .order_by(models.WaterBalance.date.desc(), models.WaterBalance.zone_id)
        .limit(days * 50)
    ).all()
    return [
        {
            "zone_id": r.zone_id,
            "date": r.date,
            "et0": r.et0,
            "kc_eff": r.kc_eff,
            "rain_mm": r.rain_mm,
            "irrigated_mm": r.irrigated_mm,
            "deficit_mm": r.deficit_mm,
        }
        for r in rows
    ]


@router.post("/balance/refresh")
async def refresh_balance(db: Session = Depends(get_db)) -> dict:
    """Fetch past-days actuals and upsert one balance row per zone per day."""
    cfg = ensure_config(db)
    lat, lon = _require_location(cfg)
    try:
        daily = await weather.fetch_daily(lat, lon)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo unreachable: {exc}")

    today = date.today().isoformat()
    actuals = [d for d in daily if d["date"] < today]
    zones = db.scalars(select(models.Zone).where(models.Zone.enabled)).all()
    written = eng.fill_balance(db, actuals)
    eng.update_deficits(db, cfg)
    db.commit()
    return {"zones": len(zones), "days": len(actuals), "rows_written": written}
