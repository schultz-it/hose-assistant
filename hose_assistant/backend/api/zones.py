"""Zone CRUD endpoints (SPEC 5.2, 9)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/api/zones", tags=["zones"])


def _get_or_404(db: Session, zone_id: int) -> models.Zone:
    zone = db.get(models.Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.get("", response_model=list[schemas.ZoneRead])
def list_zones(db: Session = Depends(get_db)):
    return db.scalars(select(models.Zone).order_by(models.Zone.order, models.Zone.id)).all()


@router.post("", response_model=schemas.ZoneRead, status_code=201)
def create_zone(payload: schemas.ZoneCreate, db: Session = Depends(get_db)):
    zone = models.Zone(**payload.model_dump())
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.get("/{zone_id}", response_model=schemas.ZoneRead)
def get_zone(zone_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, zone_id)


@router.put("/{zone_id}", response_model=schemas.ZoneRead)
def update_zone(zone_id: int, payload: schemas.ZoneUpdate, db: Session = Depends(get_db)):
    zone = _get_or_404(db, zone_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(zone, field, value)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=204)
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    zone = _get_or_404(db, zone_id)
    db.delete(zone)
    db.commit()
