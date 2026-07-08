"""Program CRUD endpoints (SPEC 5.3, 9).

Note: auto-generation of the 4 default seasonal programs is Milestone 6
(``POST /api/programs/generate``). Here we only expose plain CRUD.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/api/programs", tags=["programs"])


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
