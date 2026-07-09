"""SQLAlchemy ORM models — the persistent data layer (SPEC section 5).

All quantities are metric internally. Enum-like fields are stored as plain
strings; their allowed values are validated by the Pydantic schemas in
``schemas.py``. Lists and maps are stored as JSON columns.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class SystemConfig(Base):
    """Singleton row (``id == 1``): global system configuration (SPEC 5.1)."""

    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    units: Mapped[str] = mapped_column(String, default="metric")
    weather_entity: Mapped[str | None] = mapped_column(String, nullable=True)
    master_valve_entity: Mapped[str | None] = mapped_column(String, nullable=True)
    master_valve_pre_open_s: Mapped[int] = mapped_column(Integer, default=5)
    daily_calc_time: Mapped[str] = mapped_column(String, default="03:00")
    watering_intensity: Mapped[float] = mapped_column(Float, default=1.0)
    system_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rain_delay_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    forecast_rain_skip_mm: Mapped[float] = mapped_column(Float, default=5.0)
    wind_skip_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str] = mapped_column(String, default="en")
    # SPEC 11: opt-in exposure of sensors/switch/number back into HA
    expose_entities: Mapped[bool] = mapped_column(Boolean, default=False)


class Zone(Base):
    """An irrigation zone: one valve + its physical characteristics (SPEC 5.2)."""

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    icon: Mapped[str] = mapped_column(String, default="mdi:sprinkler")
    valve_entity: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    irrigation_type: Mapped[str] = mapped_column(String, default="spray")
    precipitation_rate_mmh: Mapped[float] = mapped_column(Float, default=35.0)
    # Drip calculator inputs (optional; drip/subsurface types only)
    emitter_lh: Mapped[float | None] = mapped_column(Float, nullable=True)
    emitter_spacing_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    line_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Soil cover over the root zone: affects evaporation AND effective rain
    cover: Mapped[str] = mapped_column(String, default="none")
    soil_type: Mapped[str] = mapped_column(String, default="loam")
    grass_type: Mapped[str] = mapped_column(String, default="cool_season")
    root_depth_cm: Mapped[float] = mapped_column(Float, default=15.0)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    slope: Mapped[str] = mapped_column(String, default="flat")
    shade_preset: Mapped[str] = mapped_column(String, default="full_sun")
    # 0-100 slider mapped onto shade factor 1.0 -> 0.5; 0 == full sun (see core/kc.py)
    shade_fine: Mapped[int] = mapped_column(Integer, default=0)
    shade_monthly: Mapped[list | None] = mapped_column(JSON, nullable=True)
    moisture_entity: Mapped[str | None] = mapped_column(String, nullable=True)
    moisture_skip_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_sensor_entity: Mapped[str | None] = mapped_column(String, nullable=True)
    max_runtime_min: Mapped[int] = mapped_column(Integer, default=60)


class Program(Base):
    """A watering program / seasonal mode (SPEC 5.3)."""

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    icon: Mapped[str] = mapped_column(String, default="mdi:calendar-clock")
    color: Mapped[str] = mapped_column(String, default="#4caf50")
    mode: Mapped[str] = mapped_column(String, default="budget")
    date_start: Mapped[str | None] = mapped_column(String, nullable=True)  # "MM-DD"
    date_end: Mapped[str | None] = mapped_column(String, nullable=True)  # "MM-DD"
    manual_only: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    allowed_days: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    window_start: Mapped[str] = mapped_column(String, default="04:00")
    window_end: Mapped[str] = mapped_column(String, default="08:00")
    mad_pct: Mapped[float] = mapped_column(Float, default=50.0)
    et_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    zone_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fixed_runs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    generated_by: Mapped[str] = mapped_column(String, default="manual")
    ai_explanation: Mapped[str | None] = mapped_column(String, nullable=True)


# --- Runtime tables (SPEC 5.4): schema is defined now so it exists, but these
# are written by the engine/executor in later milestones. No CRUD endpoints. ---


class WaterBalance(Base):
    """Per-zone daily water-balance bucket."""

    __tablename__ = "water_balance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[str] = mapped_column(String, index=True)  # ISO date "YYYY-MM-DD"
    et0: Mapped[float | None] = mapped_column(Float, nullable=True)
    kc_eff: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    irrigated_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    deficit_mm: Mapped[float | None] = mapped_column(Float, nullable=True)


class Schedule(Base):
    """A planned / running / done irrigation run."""

    __tablename__ = "schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zone_id: Mapped[int] = mapped_column(Integer, index=True)
    start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="planned")
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)


class EventLog(Base):
    """Append-only event log surfaced in the dashboard."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    level: Mapped[str] = mapped_column(String, default="info")
    message: Mapped[str] = mapped_column(String)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
