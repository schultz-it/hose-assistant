"""Hose Assistant — FastAPI application.

Milestone 1: Ingress hello page + Supervisor API entity listing.
Milestone 2: SQLite data layer + CRUD API for config, zones and programs.
"""
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import models  # noqa: F401  (import registers the ORM models on Base)
from .api import config, programs, zones
from .db import Base, SessionLocal, engine

SUPERVISOR = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and ensure the singleton config exists on startup."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.get(models.SystemConfig, 1) is None:
            db.add(models.SystemConfig(id=1))
            db.commit()
    yield


app = FastAPI(title="Hose Assistant", lifespan=lifespan)

app.include_router(config.router)
app.include_router(zones.router)
app.include_router(programs.router)


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return (
        "<html><body style='font-family:sans-serif;text-align:center;"
        "padding-top:4rem'><h1>🚿 Hose Assistant</h1>"
        "<p>Add-on running. Milestones 1–2 OK.</p>"
        "<p>Data layer:"
        " <a href='api/config'>config</a> ·"
        " <a href='api/zones'>zones</a> ·"
        " <a href='api/programs'>programs</a></p>"
        "<p><a href='api/ha/entities'>Test Supervisor API →</a></p>"
        "</body></html>"
    )


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/ha/entities")
async def ha_entities(domain: str = "switch") -> dict:
    """List HA entities of a domain via the Supervisor proxy."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPERVISOR}/states",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=10,
        )
    resp.raise_for_status()
    states = resp.json()
    entities = [
        {"entity_id": s["entity_id"], "state": s["state"],
         "name": s["attributes"].get("friendly_name", s["entity_id"])}
        for s in states
        if s["entity_id"].startswith(f"{domain}.")
    ]
    return {"domain": domain, "count": len(entities), "entities": entities}
