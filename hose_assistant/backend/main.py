"""Hose Assistant — Milestone 1 skeleton.

Serves a hello page through HA Ingress and proves Supervisor API access
by listing switch/valve entities at /api/ha/entities.
"""
import os

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

SUPERVISOR = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

app = FastAPI(title="Hose Assistant")


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return (
        "<html><body style='font-family:sans-serif;text-align:center;"
        "padding-top:4rem'><h1>🚿 Hose Assistant</h1>"
        "<p>Add-on skeleton is running. Milestone 1 OK.</p>"
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
