"""Home Assistant Supervisor API client (SPEC 2, 6).

All valve actuation goes through here. Entities may be ``switch.*``,
``input_boolean.*`` (used as safe mocks while testing) or ``valve.*``.
The Supervisor proxy needs no user-provided token: ``SUPERVISOR_TOKEN`` is
injected by HA because the add-on declares ``homeassistant_api: true``.
"""
import os
import time

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


async def get_rain_today_mm(entity_id: str) -> float | None:
    """Read a daily-rain sensor (mm fallen today) from a local station.

    Returns None when the entity is missing/unknown/unavailable or not
    numeric. Inches are converted to mm via the unit_of_measurement
    attribute; anything else is assumed to already be mm.
    """
    state = await get_state(entity_id)
    if state is None or state.get("state") in (None, "unknown", "unavailable"):
        return None
    try:
        value = float(state["state"])
    except (TypeError, ValueError):
        return None
    unit = (state.get("attributes", {}).get("unit_of_measurement") or "").lower()
    if unit in ("in", "inch", "inches", "in/d"):
        value *= 25.4
    return round(value, 2)


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


async def get_ha_timezone() -> str | None:
    """HA Core's configured time_zone (e.g. "Europe/Rome"), or None.

    Uses ``GET /api/config`` — a standard, always-available Core endpoint —
    rather than relying on the shell TZ export at container boot, which may
    silently fail (wrong bashio call, permission quirk, empty result).
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{SUPERVISOR}/config", headers=_headers())
    resp.raise_for_status()
    return resp.json().get("time_zone")


async def sync_process_timezone() -> str | None:
    """Best-effort: make the process clock match HA's real timezone.

    Never raises — if unreachable (e.g. no SUPERVISOR_TOKEN in local dev),
    the caller falls back to whatever TZ the container already has.
    """
    try:
        tz = await get_ha_timezone()
    except Exception:  # noqa: BLE001
        return None
    if tz and tz != os.environ.get("TZ"):
        os.environ["TZ"] = tz
        time.tzset()  # re-read TZ so datetime.now() reflects it immediately
    return tz


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
