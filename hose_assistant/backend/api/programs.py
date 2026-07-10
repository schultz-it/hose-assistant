"""Program CRUD + generator endpoints (SPEC 5.3, 7.1, 9)."""
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..core import generator_ai, generator_rules
from ..core import scheduler as sched
from ..db import get_db
from .config import ensure_config

router = APIRouter(prefix="/api/programs", tags=["programs"])


class GenerateRequest(BaseModel):
    engine: str = "rules"  # or "ai"
    notes: str | None = None


@router.get("/ai_info")
def ai_info() -> dict:
    """Which AI provider (if any) is configured in the add-on options."""
    return generator_ai.provider_info()


@router.post("/generate")
async def generate_programs(req: GenerateRequest, db: Session = Depends(get_db)) -> dict:
    """Build a PROPOSAL of seasonal programs (rules or AI).

    Nothing is persisted: the client previews the result and calls /apply.
    AI failures fall back to the rule-based proposal with a clear message
    (SPEC 7.2). AI never actuates anything.
    """
    if req.engine not in ("rules", "ai"):
        raise HTTPException(status_code=400, detail="engine must be 'rules' or 'ai'")
    cfg = ensure_config(db)
    if cfg.latitude is None or cfg.longitude is None:
        raise HTTPException(status_code=400, detail="Location not configured")
    try:
        rules_out = await generator_rules.generate(cfg.latitude, cfg.longitude)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo archive unreachable: {exc}")
    if req.engine == "rules":
        return {**rules_out, "engine_used": "rules"}
    try:
        ai_out = await generator_ai.generate(db, cfg, rules_out, req.notes)
        return {**ai_out, "climate": rules_out.get("climate")}
    except Exception as exc:  # noqa: BLE001 — any AI failure -> rules fallback
        return {
            **rules_out,
            "engine_used": "rules_fallback",
            "explanation": f"AI generation failed ({exc}). Showing the "
                           f"rule-based proposal instead. {rules_out['explanation']}",
        }


@router.post("/review")
async def review_programs(req: GenerateRequest, db: Session = Depends(get_db)) -> dict:
    """'Ask AI to review' current programs vs config and balance history."""
    cfg = ensure_config(db)
    if cfg.latitude is None or cfg.longitude is None:
        raise HTTPException(status_code=400, detail="Location not configured")
    if not generator_ai.provider_info()["available"]:
        raise HTTPException(status_code=400, detail="No AI provider configured")
    try:
        rules_out = await generator_rules.generate(cfg.latitude, cfg.longitude)
        text = await generator_ai.review(db, cfg, rules_out, req.notes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AI review failed: {exc}")
    return {"review": text}


@router.post("/apply")
async def apply_programs(
    programs: list[schemas.ProgramCreate] = Body(embed=True),
    db: Session = Depends(get_db),
) -> list[schemas.ProgramRead]:
    """Persist an applied proposal: replaces previously generated programs.

    Manually created/edited programs (generated_by == 'manual') are untouched.
    """
    for old in db.scalars(
        select(models.Program).where(models.Program.generated_by.in_(["rules", "ai"]))
    ).all():
        db.delete(old)
    created = [models.Program(**p.model_dump()) for p in programs]
    db.add_all(created)
    db.commit()
    for c in created:
        db.refresh(c)
    # Auto-recalc: the active program may have changed -> replan today.
    await sched.try_recalc(db, "programs applied")
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
async def update_program(
    program_id: int, payload: schemas.ProgramUpdate, db: Session = Depends(get_db)
):
    program = _get_or_404(db, program_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(program, field, value)
    db.commit()
    db.refresh(program)
    await sched.try_recalc(db, "program updated")
    return program


@router.delete("/{program_id}", status_code=204)
async def delete_program(program_id: int, db: Session = Depends(get_db)):
    program = _get_or_404(db, program_id)
    db.delete(program)
    db.commit()
    await sched.try_recalc(db, "program deleted")
