"""Open-Meteo client (SPEC section 6.1).

Open-Meteo is free and keyless. Two endpoints are used here:
  * Forecast API — daily FAO-56 ET0 (precomputed) and precipitation, both for
    the recent past (actuals) and the next days (forecast).
  * Elevation API — elevation from lat/long, used to prefill SystemConfig.

Only latitude/longitude are ever sent (privacy note in DOCS).
"""
import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

TIMEOUT = 15.0


async def fetch_elevation(lat: float, lon: float) -> float:
    """Return terrain elevation in metres for the given coordinates."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(ELEVATION_URL, params={"latitude": lat, "longitude": lon})
    resp.raise_for_status()
    return float(resp.json()["elevation"][0])


def fetch_elevation_sync(lat: float, lon: float) -> float:
    """Blocking variant, used from sync FastAPI routes (threadpool)."""
    resp = httpx.get(ELEVATION_URL, params={"latitude": lat, "longitude": lon},
                     timeout=TIMEOUT)
    resp.raise_for_status()
    return float(resp.json()["elevation"][0])


async def fetch_daily(lat: float, lon: float, *, past_days: int = 7,
                      forecast_days: int = 7) -> list[dict]:
    """Daily ET0 + precipitation, past actuals and forecast in one call.

    Returns a list of ``{date, et0, rain_mm}`` dicts, ordered by date.
    ``et0``/``rain_mm`` may be ``None`` when Open-Meteo has no value (rare).
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "et0_fao_evapotranspiration,precipitation_sum,windspeed_10m_max",
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(FORECAST_URL, params=params)
    resp.raise_for_status()
    daily = resp.json()["daily"]
    return [
        {"date": d, "et0": et0, "rain_mm": rain, "wind_kmh": wind}
        for d, et0, rain, wind in zip(
            daily["time"],
            daily["et0_fao_evapotranspiration"],
            daily["precipitation_sum"],
            daily["windspeed_10m_max"],
        )
    ]


async def fetch_current(lat: float, lon: float) -> dict:
    """Real-time-ish current conditions (Open-Meteo's model, refreshed hourly).

    This is the regional-fallback source for the Weather tab when no HA
    weather entity (e.g. a real local station) is configured.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,"
                   "weather_code,wind_speed_10m,is_day",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(FORECAST_URL, params=params)
    resp.raise_for_status()
    c = resp.json()["current"]
    return {
        "temperature_c": c.get("temperature_2m"),
        "humidity_pct": c.get("relative_humidity_2m"),
        "precipitation_mm": c.get("precipitation"),
        "wind_kmh": c.get("wind_speed_10m"),
        "weather_code": c.get("weather_code"),
        "is_day": c.get("is_day"),
        "time": c.get("time"),
    }


# WMO weather codes (https://open-meteo.com/en/docs) mapped onto the same
# condition vocabulary Home Assistant weather entities use, so the frontend
# needs only one icon/label lookup regardless of the data source.
_WMO_CONDITION = {
    0: "sunny", 1: "partlycloudy", 2: "partlycloudy", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "rainy", 53: "rainy", 55: "rainy", 56: "rainy", 57: "rainy",
    61: "rainy", 63: "rainy", 65: "pouring",
    66: "snowy-rainy", 67: "snowy-rainy",
    71: "snowy", 73: "snowy", 75: "snowy", 77: "snowy",
    80: "rainy", 81: "pouring", 82: "pouring",
    85: "snowy", 86: "snowy",
    95: "lightning-rainy", 96: "lightning-rainy", 99: "lightning-rainy",
}


def condition_from_wmo(code: int | None, is_day: int | None = 1) -> str:
    if code == 0 and not is_day:
        return "clear-night"
    return _WMO_CONDITION.get(code, "cloudy")
