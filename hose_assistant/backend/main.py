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
from .api import config, programs, runs, weather, zones
from .core import scheduler as sched
from .core.executor import executor
from .db import Base, SessionLocal, engine

SUPERVISOR = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: tables, singleton config, scheduler, close-all clean slate."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.get(models.SystemConfig, 1) is None:
            db.add(models.SystemConfig(id=1))
            db.commit()
    sched.init()
    # SPEC failsafe: on add-on start, close all known valves ("clean slate").
    # Skipped outside HA (no SUPERVISOR_TOKEN) to keep local dev/tests quiet.
    if os.environ.get("SUPERVISOR_TOKEN"):
        await executor.close_everything("startup clean slate")
    yield
    await executor.stop_all()
    sched.shutdown()


app = FastAPI(title="Hose Assistant", lifespan=lifespan)

app.include_router(config.router)
app.include_router(zones.router)
app.include_router(programs.router)
app.include_router(weather.router)
app.include_router(runs.router)


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    # Temporary dev page — replaced by the real SPA in Milestone 5.
    return """<html><body style="font-family:sans-serif;max-width:40rem;margin:2rem auto">
<h1>🚿 Hose Assistant</h1>
<p>Add-on running. Milestones 1–4 OK.</p>
<h3>Location</h3>
<p>lat <input id="lat" size="9"> long <input id="lon" size="9">
<button onclick="saveLoc()">Save</button> <span id="locmsg"></span></p>
<h3>Data</h3>
<p><a href="api/config">config</a> · <a href="api/zones">zones</a> ·
<a href="api/programs">programs</a> · <a href="api/balance">balance</a> ·
<a href="api/weather/summary">weather summary</a> ·
<a href="api/ha/entities">HA entities</a></p>
<p><button onclick="refreshBal()">Refresh balance from Open-Meteo</button>
<span id="balmsg"></span></p>
<h3>Engine &amp; executor</h3>
<p><a href="api/schedule">schedule</a> · <a href="api/log">event log</a></p>
<p><button onclick="recalc()">Recalc plan now</button> <span id="recmsg"></span></p>
<p>Run zone id <input id="rzid" size="3" value="1"> for
<input id="rzmin" size="4" value="1"> min
<button onclick="runZone()">Run</button>
<button onclick="stopAll()" style="color:red">STOP ALL</button>
<span id="runmsg"></span></p>
<script>
function recalc(){
  recmsg.textContent='working…';
  fetch('api/engine/recalc',{method:'POST'}).then(r=>r.json())
  .then(j=>{recmsg.textContent=JSON.stringify(j);})
  .catch(e=>{recmsg.textContent='error: '+e;});
}
function runZone(){
  runmsg.textContent='starting…';
  fetch('api/run/zone/'+rzid.value+'?minutes='+rzmin.value,{method:'POST'})
  .then(r=>r.json()).then(j=>{runmsg.textContent=JSON.stringify(j);})
  .catch(e=>{runmsg.textContent='error: '+e;});
}
function stopAll(){
  fetch('api/stop_all',{method:'POST'}).then(r=>r.json())
  .then(j=>{runmsg.textContent=JSON.stringify(j);});
}
</script>
<script>
fetch('api/config').then(r=>r.json()).then(c=>{
  if(c.latitude!=null) document.getElementById('lat').value=c.latitude;
  if(c.longitude!=null) document.getElementById('lon').value=c.longitude;
});
function saveLoc(){
  fetch('api/config',{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({latitude:parseFloat(lat.value),longitude:parseFloat(lon.value)})})
  .then(r=>r.json()).then(c=>{
    locmsg.textContent='saved — elevation '+(c.elevation_m??'n/a')+' m';
  }).catch(e=>{locmsg.textContent='error: '+e;});
}
function refreshBal(){
  balmsg.textContent='fetching…';
  fetch('api/balance/refresh',{method:'POST'}).then(r=>r.json())
  .then(j=>{balmsg.textContent=JSON.stringify(j);})
  .catch(e=>{balmsg.textContent='error: '+e;});
}
</script></body></html>"""


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
