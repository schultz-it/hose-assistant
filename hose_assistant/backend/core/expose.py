"""HA entity exposure (SPEC section 11) — opt-in via Setup.

Primary path: MQTT Discovery when a broker is available (auto-detected via
the Supervisor services API). Publishes, grouped under one "Hose Assistant"
device:
  * per zone: ``sensor..._zone_<id>_deficit`` (mm), ``..._next_run``
  * global:   ``sensor..._active_zone``, ``sensor..._next_program``
  * bidirectional: ``switch..._system_enabled``, ``number..._intensity``
    (commands from HA update the add-on and vice versa).

Fallback: REST states via the Supervisor proxy — read-only sensors only,
not registry-persistent (documented limitation).
"""
import asyncio
import json
import logging
import os
from datetime import datetime

import httpx
from sqlalchemy import select

from .. import models
from ..db import SessionLocal
from . import engine as eng

log = logging.getLogger(__name__)

PREFIX = "hose_assistant"
DISCOVERY = "homeassistant"
SUPERVISOR = "http://supervisor"

_exposer = None  # singleton, managed by refresh_job()


# --------------------------------------------------------------- state model

def gather_state(db) -> dict:
    """Everything we expose, as {object_id: {state, config-extras}}."""
    from .executor import executor

    cfg = db.get(models.SystemConfig, 1)
    zones = db.scalars(select(models.Zone).order_by(models.Zone.id)).all()
    upcoming = db.scalars(
        select(models.Schedule).where(models.Schedule.status.in_(["planned", "running"]))
        .order_by(models.Schedule.start)
    ).all()
    next_by_zone = {}
    for r in upcoming:
        next_by_zone.setdefault(r.zone_id, r.start.isoformat() if r.start else None)

    active_zone = "none"
    if executor.busy:
        running = [r for r in upcoming if r.status == "running"]
        if running:
            z = db.get(models.Zone, running[0].zone_id)
            active_zone = z.name if z else str(running[0].zone_id)
    program = eng.active_program(db, datetime.now().date())

    ents: dict[str, dict] = {}
    for z in zones:
        deficit = eng.current_deficit(db, z.id)
        ents[f"zone_{z.id}_deficit"] = {
            "component": "sensor", "name": f"{z.name} deficit",
            "state": round(deficit, 1), "unit_of_measurement": "mm",
            "icon": "mdi:water-minus",
        }
        ents[f"zone_{z.id}_next_run"] = {
            "component": "sensor", "name": f"{z.name} next run",
            "state": next_by_zone.get(z.id) or "none", "icon": "mdi:clock-outline",
        }
    ents["active_zone"] = {
        "component": "sensor", "name": "Active zone", "state": active_zone,
        "icon": "mdi:sprinkler-variant",
    }
    ents["next_program"] = {
        "component": "sensor", "name": "Active program",
        "state": program.name if program else "none", "icon": "mdi:calendar-clock",
    }
    ents["system_enabled"] = {
        "component": "switch", "name": "System enabled",
        "state": "ON" if (cfg and cfg.system_enabled) else "OFF",
        "icon": "mdi:power",
    }
    ents["intensity"] = {
        "component": "number", "name": "Watering intensity",
        "state": cfg.watering_intensity if cfg else 1.0,
        "min": 0.5, "max": 2.0, "step": 0.05, "icon": "mdi:water-percent",
    }
    return ents


# --------------------------------------------------------------- MQTT path

async def detect_mqtt() -> dict | None:
    """Broker credentials from the Supervisor services API, or None."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SUPERVISOR}/services/mqtt",
                                    headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {})
        return {"host": data["host"], "port": data.get("port", 1883),
                "username": data.get("username"), "password": data.get("password")}
    except Exception:  # noqa: BLE001
        return None


class MqttExposer:
    """Paho client wrapper: discovery + states out, commands in."""

    def __init__(self, creds: dict, loop: asyncio.AbstractEventLoop):
        import paho.mqtt.client as mqtt

        self._loop = loop
        self._discovered: set[str] = set()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="hose_assistant")
        if creds.get("username"):
            self.client.username_pw_set(creds["username"], creds.get("password"))
        self.client.will_set(f"{PREFIX}/availability", "offline", retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(creds["host"], creds["port"], keepalive=60)
        self.client.loop_start()

    def close(self) -> None:
        try:
            self.client.publish(f"{PREFIX}/availability", "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    # ---- paho callbacks (MQTT thread) ----

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        client.publish(f"{PREFIX}/availability", "online", retain=True)
        client.subscribe(f"{PREFIX}/system_enabled/set")
        client.subscribe(f"{PREFIX}/intensity/set")
        self._discovered.clear()  # republish discovery after (re)connect

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode().strip()
        asyncio.run_coroutine_threadsafe(self._handle_command(msg.topic, payload),
                                         self._loop)

    async def _handle_command(self, topic: str, payload: str) -> None:
        """Bidirectional part: HA -> add-on. Runs on the main loop."""
        from .executor import executor

        with SessionLocal() as db:
            cfg = db.get(models.SystemConfig, 1)
            if cfg is None:
                return
            if topic.endswith("system_enabled/set"):
                enable = payload.upper() == "ON"
                cfg.system_enabled = enable
                eng.log_event(db, "info", f"System switched {'ON' if enable else 'OFF'} via MQTT")
                db.commit()
                if not enable:
                    await executor.stop_all()
            elif topic.endswith("intensity/set"):
                try:
                    cfg.watering_intensity = min(2.0, max(0.5, float(payload)))
                    db.commit()
                except ValueError:
                    return
            self.publish(gather_state(db))

    # ---- publishing (any thread; paho is thread-safe) ----

    def publish(self, ents: dict) -> None:
        device = {"identifiers": [PREFIX], "name": "Hose Assistant",
                  "manufacturer": "hose-assistant", "model": "HA add-on"}
        for oid, e in ents.items():
            if oid not in self._discovered:
                conf = {
                    "name": e["name"], "unique_id": f"{PREFIX}_{oid}",
                    "state_topic": f"{PREFIX}/{oid}/state",
                    "availability_topic": f"{PREFIX}/availability",
                    "icon": e.get("icon"), "device": device,
                }
                if e.get("unit_of_measurement"):
                    conf["unit_of_measurement"] = e["unit_of_measurement"]
                if e["component"] in ("switch", "number"):
                    conf["command_topic"] = f"{PREFIX}/{oid}/set"
                if e["component"] == "number":
                    conf.update(min=e["min"], max=e["max"], step=e["step"])
                self.client.publish(
                    f"{DISCOVERY}/{e['component']}/{PREFIX}/{oid}/config",
                    json.dumps({k: v for k, v in conf.items() if v is not None}),
                    retain=True)
                self._discovered.add(oid)
            self.client.publish(f"{PREFIX}/{oid}/state", str(e["state"]), retain=True)


class RestExposer:
    """Fallback: read-only sensors via Supervisor REST states."""

    async def publish(self, ents: dict) -> None:
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            for oid, e in ents.items():
                if e["component"] != "sensor":
                    continue  # REST path cannot receive commands
                body = {"state": str(e["state"]),
                        "attributes": {"friendly_name": f"Hose Assistant {e['name']}",
                                       "icon": e.get("icon")}}
                if e.get("unit_of_measurement"):
                    body["attributes"]["unit_of_measurement"] = e["unit_of_measurement"]
                try:
                    await client.post(f"{SUPERVISOR}/core/api/states/sensor.{PREFIX}_{oid}",
                                      headers={"Authorization": f"Bearer {token}"}, json=body)
                except Exception as exc:  # noqa: BLE001
                    log.debug("REST expose failed for %s: %s", oid, exc)
                    return


# --------------------------------------------------------------- refresh job

async def refresh_job() -> None:
    """Periodic tick: honor the toggle, lazily create/tear down the exposer."""
    global _exposer
    with SessionLocal() as db:
        cfg = db.get(models.SystemConfig, 1)
        enabled = bool(cfg and cfg.expose_entities)
        ents = gather_state(db) if enabled else None

    if not enabled:
        if isinstance(_exposer, MqttExposer):
            _exposer.close()
        _exposer = None
        return

    if _exposer is None:
        creds = await detect_mqtt()
        if creds:
            try:
                _exposer = MqttExposer(creds, asyncio.get_running_loop())
                log.info("Entity exposure via MQTT discovery (%s)", creds["host"])
            except Exception as exc:  # noqa: BLE001
                log.warning("MQTT connect failed (%s); using REST fallback", exc)
                _exposer = RestExposer()
        else:
            _exposer = RestExposer()
            log.info("Entity exposure via REST states (no MQTT broker)")

    if isinstance(_exposer, MqttExposer):
        _exposer.publish(ents)
    else:
        await _exposer.publish(ents)
