"""System configuration endpoints (SPEC 5.1, 9).

The configuration is a single row (``id == 1``). ``ensure_config`` creates it
with defaults the first time it is needed, so GET always returns something.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/api/config", tags=["config"])


def ensure_config(db: Session) -> models.SystemConfig:
    """Return the singleton config, creating it with defaults if missing."""
    cfg = db.get(models.SystemConfig, 1)
    if cfg is None:
        cfg = models.SystemConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("", response_model=schemas.ConfigRead)
def get_config(db: Session = Depends(get_db)):
    return ensure_config(db)


@router.put("", response_model=schemas.ConfigRead)
def update_config(payload: schemas.ConfigUpdate, db: Session = Depends(get_db)):
    cfg = ensure_config(db)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(cfg, field, value)

    # SPEC 5.1: elevation auto-fetched from Open-Meteo when location is set
    # and the user did not provide it explicitly. Best-effort: never fail the
    # config save because the elevation service is unreachable.
    location_changed = "latitude" in data or "longitude" in data
    if (location_changed and "elevation_m" not in data
            and cfg.latitude is not None and cfg.longitude is not None):
        try:
            from ..core.weather import fetch_elevation_sync

            cfg.elevation_m = fetch_elevation_sync(cfg.latitude, cfg.longitude)
        except Exception:
            pass

    db.commit()
    db.refresh(cfg)
    return cfg
