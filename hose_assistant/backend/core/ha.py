"""Home Assistant Supervisor API client (SPEC 2, 6).

All valve actuation goes through here. Entities may be ``switch.*``,
``input_boolean.*`` (used as safe mocks while testing) or ``valve.*``.
The Supervisor proxy needs no user-provided token: ``SUPERVISOR_TOKEN`` is
injected by HA because the add-on declares ``homeassistant_api: true``.
"""
import os

import httpx

SUPERVISOR = "http://supervisor/core/api"
TIMEOUT = 10.0


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}"}


def _service_for(entity_id: str, turn_on: bool) -> tuple[str, str]:
    """Map an entity to its (domain, service) pair for on/off actuation."""
    domain = entity_id.split(".", 1)[0]
    if domain == "valve":
        return "valve", "open_valve" if turn_on else "close_valve"
    # switch, input_boolean, light, ... all use homeassistant.turn_on/off
    return "homeassistant", "turn_on" if turn_on else "turn_off"


async def get_state(entity_id: str) -> dict | None:
    """Return the state object for an entity, or None if missing."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{SUPERVISOR}/states/{entity_id}", headers=_headers())
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def call_on_off(entity_id: str, turn_on: bool) -> None:
    domain, service = _service_for(entity_id, turn_on)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{SUPERVISOR}/services/{domain}/{service}",
            headers=_headers(),
            json={"entity_id": entity_id},
        )
    resp.raise_for_status()


async def turn_on(entity_id: str) -> None:
    await call_on_off(entity_id, True)


async def turn_off(entity_id: str) -> None:
    await call_on_off(entity_id, False)


async def get_weather_daily_rain(entity_id: str) -> list[dict]:
    """Daily precipitation forecast from an HA ``weather.*`` entity.

    Uses the ``weather.get_forecasts`` service (with response) through the
    Supervisor proxy. Returns ``[{date, rain_mm}, ...]``.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{SUPERVISOR}/services/weather/get_forecasts?return_response",
            headers=_headers(),
            json={"entity_id": entity_id, "type": "daily"},
        )
    resp.raise_for_status()
    body = resp.json()
    forecast = (body.get("service_response", {}).get(entity_id, {}) or {}).get("forecast", [])
    out = []
    for f in forecast:
        day = (f.get("datetime") or "")[:10]
        if day:
            out.append({"date": day, "rain_mm": float(f.get("precipitation") or 0.0)})
    return out


def turn_off_sync(entity_id: str) -> None:
    """Blocking turn-off — used by persisted watchdog jobs (APScheduler)."""
    domain, service = _service_for(entity_id, False)
    resp = httpx.post(
        f"{SUPERVISOR}/services/{domain}/{service}",
        headers=_headers(),
        json={"entity_id": entity_id},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
