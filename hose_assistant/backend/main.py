"""Hose Assistant — FastAPI application.

Milestone 1: Ingress hello page + Supervisor API entity listing.
Milestone 2: SQLite data layer + CRUD API for config, zones and programs.
Milestone 3: Open-Meteo weather + sun + balance filling.
Milestone 4: calculation engine + valve executor with failsafes.
Milestone 5: Preact SPA (served from frontend/dist; dev page moved to /dev).
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (import registers the ORM models on Base)
from .api import backup, config, programs, runs, weather, zones
from .core import engine as eng
from .core import ha as ha_client
from .core import scheduler as sched
from .core.executor import executor
from .db import Base, SessionLocal, apply_migrations, engine

SUPERVISOR = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: tables, singleton config, scheduler, close-all clean slate."""
    Base.metadata.create_all(bind=engine)
    apply_migrations()
    # Correct the process clock BEFORE the scheduler is created (its cron
    # jobs resolve "local time" at creation time). The run script already
    # sets TZ from bashio at container boot; this self-heals if that
    # silently failed, by asking HA Core directly for its real timezone —
    # the same Supervisor API path already proven to work elsewhere in the
    # app (weather entity reads, HA state queries).
    resolved_tz = await ha_client.sync_process_timezone()
    with SessionLocal() as db:
        cfg = db.get(models.SystemConfig, 1)
        if cfg is None:
            cfg = models.SystemConfig(id=1)
            db.add(cfg)
        tz = resolved_tz or os.environ.get("TZ")
        if tz:
            cfg.timezone = tz
        # Logged every boot so a wrong clock is diagnosable from the event
        # log alone, instead of only from user-reported symptoms.
        import datetime as _dt
        eng.log_event(
            db, "info",
            f"Startup timezone: {tz or 'unresolved (defaulting to container clock)'} "
            f"— process local time now reads {_dt.datetime.now().isoformat(timespec='seconds')} "
            f"(source: {'HA Core API' if resolved_tz else 'container TZ env var' if tz else 'none'})")
        # Runs left 'running' by a previous (killed) session must not linger.
        eng.reconcile_interrupted_runs(db)
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
app.include_router(backup.router)


@app.get("/dev", response_class=HTMLResponse)
async def dev_page() -> str:
    # Developer/debug page (the user-facing SPA is served at /).
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
<h3>Zones</h3>
<div id="zlist">loading…</div>
<p>name <input id="zname" size="12" placeholder="Front lawn">
valve <input id="zvalve" size="28" list="entities"
  placeholder="input_boolean.zona_1_test">
<datalist id="entities"></datalist>
<button onclick="addZone()">Add zone</button> <span id="zmsg"></span></p>
<script>
function loadZones(){
  fetch('api/zones').then(r=>r.json()).then(zs=>{
    zlist.innerHTML = zs.length ? zs.map(z=>
      '#'+z.id+' <b>'+z.name+'</b> → '+z.valve_entity+
      ' <button onclick="delZone('+z.id+')">✕</button>').join('<br>')
      : '<i>no zones yet</i>';
  });
}
function addZone(){
  zmsg.textContent='saving…';
  fetch('api/zones',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:zname.value,valve_entity:zvalve.value})})
  .then(r=>{if(!r.ok) throw r.status; return r.json();})
  .then(()=>{zmsg.textContent='ok';zname.value='';loadZones();})
  .catch(e=>{zmsg.textContent='error: '+e;});
}
function delZone(id){
  fetch('api/zones/'+id,{method:'DELETE'}).then(loadZones);
}
loadZones();
// entity autocomplete: mock valves first, then real switches
Promise.all([
  fetch('api/ha/entities?domain=input_boolean').then(r=>r.json()).catch(()=>({entities:[]})),
  fetch('api/ha/entities?domain=switch').then(r=>r.json()).catch(()=>({entities:[]})),
]).then(([a,b])=>{
  document.getElementById('entities').innerHTML =
    [...a.entities,...b.entities].map(e=>'<option value="'+e.entity_id+'">').join('');
});
</script>
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


# Serve the built SPA (Milestone 5). Mounted last so /api/* and /dev win.
# html=True serves index.html at "/" and for unknown paths (SPA routing).
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
