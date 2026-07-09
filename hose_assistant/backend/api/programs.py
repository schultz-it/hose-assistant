"""Program CRUD + generator endpoints (SPEC 5.3, 7.1, 9)."""
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..core import generator_rules
from ..db import get_db
from .config import ensure_config

router = APIRouter(prefix="/api/programs", tags=["programs"])


class GenerateRequest(BaseModel):
    engine: str = "rules"  # "ai" arrives with Milestone 9
    notes: str | None = None


@router.post("/generate")
async def generate_programs(req: GenerateRequest, db: Session = Depends(get_db)) -> dict:
    """Build a PROPOSAL of seasonal programs from the local climate.

    Nothing is persisted: the client previews the result and calls /apply.
    """
    if req.engine != "rules":
        raise HTTPException(status_code=400, detail="Only engine=rules is available (AI: M9)")
    cfg = ensure_config(db)
    if cfg.latitude is None or cfg.longitude is None:
        raise HTTPException(status_code=400, detail="Location not configured")
    try:
        return await generator_rules.generate(cfg.latitude, cfg.longitude)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo archive unreachable: {exc}")


@router.post("/apply")
def apply_programs(
    programs: list[schemas.ProgramCreate] = Body(embed=True),
    db: Session = Depends(get_db),
) -> list[schemas.ProgramRead]:
    """Persist an applied proposal: replaces previous rules-generated programs.

    Manually created/edited programs (generated_by != 'rules') are untouched.
    """
    for old in db.scalars(
        select(models.Program).where(models.Program.generated_by == "rules")
    ).all():
        db.delete(old)
    created = [models.Program(**p.model_dump()) for p in programs]
    db.add_all(created)
    db.commit()
    for c in created:
        db.refresh(c)
    return created


def _get_or_404(db: Session, program_id: int) -> models.Program:
    program = db.get(models.Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program


@router.get("", response_model=list[schemas.ProgramRead])
def list_programs(db: Session = Depends(get_db)):
    return db.scalars(
        select(models.Program).order_by(models.Program.priority, models.Program.id)
    ).all()


@router.post("", response_model=schemas.ProgramRead, status_code=201)
def create_program(payload: schemas.ProgramCreate, db: Session = Depends(get_db)):
    program = models.Program(**payload.model_dump())
    db.add(program)
    db.commit()
    db.refresh(program)
    return program


@router.get("/{program_id}", response_model=schemas.ProgramRead)
def get_program(program_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, program_id)


@router.put("/{program_id}", response_model=schemas.ProgramRead)
def update_program(
    program_id: int, payload: schemas.ProgramUpdate, db: Session = Depends(get_db)
):
    program = _get_or_404(db, program_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(program, field, value)
    db.commit()
    db.refresh(program)
    return program


@router.delete("/{program_id}", status_code=204)
def delete_program(program_id: int, db: Session = Depends(get_db)):
    program = _get_or_404(db, program_id)
    db.delete(program)
    db.commit()
