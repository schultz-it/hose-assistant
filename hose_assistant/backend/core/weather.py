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
        "daily": "et0_fao_evapotranspiration,precipitation_sum",
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(FORECAST_URL, params=params)
    resp.raise_for_status()
    daily = resp.json()["daily"]
    return [
        {"date": d, "et0": et0, "rain_mm": rain}
        for d, et0, rain in zip(
            daily["time"],
            daily["et0_fao_evapotranspiration"],
            daily["precipitation_sum"],
        )
    ]
