"""Pydantic schemas: request validation and response serialization.

Mirrors the data model in SPEC section 5. Enum-like fields use ``Literal`` so
invalid values are rejected with a clear 422 error. Each entity has:
  * ``*Create`` — payload to create a row (required fields must be present),
  * ``*Update`` — all fields optional, for partial updates (PUT),
  * ``*Read``   — response model, includes ``id``.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# --- Enum-like value sets (SPEC section 5) ---
Units = Literal["metric", "imperial"]
IrrigationType = Literal[
    "spray", "rotor", "mp_rotator", "microspray", "drip", "subsurface_drip"
]
Cover = Literal["none", "organic_mulch", "plastic_mulch"]
SoilType = Literal["sandy", "loam", "clay"]
GrassType = Literal["cool_season", "warm_season", "shrubs_drip"]
Slope = Literal["flat", "gentle", "steep"]
ShadePreset = Literal["full_sun", "partial", "shade"]
ProgramMode = Literal["budget", "fixed"]
GeneratedBy = Literal["manual", "rules", "ai"]


# =========================== SystemConfig ===========================
class ConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation_m: Optional[float] = None
    timezone: Optional[str] = None
    units: Units = "metric"
    weather_entity: Optional[str] = None
    master_valve_entity: Optional[str] = None
    master_valve_pre_open_s: int = 5
    daily_calc_time: str = "03:00"
    watering_intensity: float = 1.0
    system_enabled: bool = True
    rain_delay_until: Optional[datetime] = None
    forecast_rain_skip_mm: float = 5.0
    wind_skip_kmh: Optional[float] = None
    language: str = "en"
    expose_entities: bool = False


class ConfigUpdate(BaseModel):
    """Partial update — only the provided fields are changed."""

    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    elevation_m: Optional[float] = None
    timezone: Optional[str] = None
    units: Optional[Units] = None
    weather_entity: Optional[str] = None
    master_valve_entity: Optional[str] = None
    master_valve_pre_open_s: Optional[int] = Field(default=None, ge=0)
    daily_calc_time: Optional[str] = None
    watering_intensity: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    system_enabled: Optional[bool] = None
    rain_delay_until: Optional[datetime] = None
    forecast_rain_skip_mm: Optional[float] = Field(default=None, ge=0)
    wind_skip_kmh: Optional[float] = None
    language: Optional[str] = None
    expose_entities: Optional[bool] = None


# =============================== Zone ===============================
class ZoneCreate(BaseModel):
    name: str
    valve_entity: str
    icon: str = "mdi:sprinkler"
    enabled: bool = True
    order: int = 0
    irrigation_type: IrrigationType = "spray"
    precipitation_rate_mmh: float = Field(35.0, gt=0)
    emitter_lh: Optional[float] = Field(default=None, gt=0)
    emitter_spacing_cm: Optional[float] = Field(default=None, gt=0)
    line_length_m: Optional[float] = Field(default=None, gt=0)
    cover: Cover = "none"
    soil_type: SoilType = "loam"
    grass_type: GrassType = "cool_season"
    root_depth_cm: float = Field(15.0, gt=0)
    area_m2: Optional[float] = Field(default=None, gt=0)
    slope: Slope = "flat"
    shade_preset: ShadePreset = "full_sun"
    shade_fine: int = Field(0, ge=0, le=100)
    shade_monthly: Optional[list[float]] = None
    moisture_entity: Optional[str] = None
    moisture_skip_pct: Optional[float] = Field(default=None, ge=0, le=100)
    rain_sensor_entity: Optional[str] = None
    max_runtime_min: int = Field(60, gt=0)


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    valve_entity: Optional[str] = None
    icon: Optional[str] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None
    irrigation_type: Optional[IrrigationType] = None
    precipitation_rate_mmh: Optional[float] = Field(default=None, gt=0)
    emitter_lh: Optional[float] = Field(default=None, gt=0)
    emitter_spacing_cm: Optional[float] = Field(default=None, gt=0)
    line_length_m: Optional[float] = Field(default=None, gt=0)
    cover: Optional[Cover] = None
    soil_type: Optional[SoilType] = None
    grass_type: Optional[GrassType] = None
    root_depth_cm: Optional[float] = Field(default=None, gt=0)
    area_m2: Optional[float] = Field(default=None, gt=0)
    slope: Optional[Slope] = None
    shade_preset: Optional[ShadePreset] = None
    shade_fine: Optional[int] = Field(default=None, ge=0, le=100)
    shade_monthly: Optional[list[float]] = None
    moisture_entity: Optional[str] = None
    moisture_skip_pct: Optional[float] = Field(default=None, ge=0, le=100)
    rain_sensor_entity: Optional[str] = None
    max_runtime_min: Optional[int] = Field(default=None, gt=0)


class ZoneRead(ZoneCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ============================= Program =============================
class ProgramCreate(BaseModel):
    name: str
    icon: str = "mdi:calendar-clock"
    color: str = "#4caf50"
    mode: ProgramMode = "budget"
    date_start: Optional[str] = None  # "MM-DD"
    date_end: Optional[str] = None  # "MM-DD"
    manual_only: bool = False
    priority: int = 0
    allowed_days: Optional[dict] = None
    window_start: str = "04:00"
    window_end: str = "08:00"
    mad_pct: float = Field(50.0, ge=0, le=100)
    et_multiplier: float = Field(1.0, gt=0)
    zone_overrides: Optional[dict] = None
    fixed_runs: Optional[list] = None
    generated_by: GeneratedBy = "manual"
    ai_explanation: Optional[str] = None


class ProgramUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    mode: Optional[ProgramMode] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    manual_only: Optional[bool] = None
    priority: Optional[int] = None
    allowed_days: Optional[dict] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    mad_pct: Optional[float] = Field(default=None, ge=0, le=100)
    et_multiplier: Optional[float] = Field(default=None, gt=0)
    zone_overrides: Optional[dict] = None
    fixed_runs: Optional[list] = None
    generated_by: Optional[GeneratedBy] = None
    ai_explanation: Optional[str] = None


class ProgramRead(ProgramCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
