"""Local climate normals from the Open-Meteo Archive API (SPEC 7.1).

Season boundaries are derived from the multi-year mean daily ET0 curve
(smoothed by day-of-year), not from fixed calendar dates:
  * Spring starts when the smoothed ET0 crosses ~2 mm/day going up,
  * Summer starts at ~4 mm/day,
  * Autumn starts when it falls back below 4 after the summer peak,
  * the watering season ends when it falls below 2 (winter).
"""
from datetime import date, timedelta

import httpx

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEOUT = 40.0

SPRING_ET0 = 2.0  # mm/day
SUMMER_ET0 = 4.0


async def fetch_climate_daily(lat: float, lon: float, years: int = 5) -> list[dict]:
    """Daily ET0 + rain for the last ``years`` full years (plus current)."""
    end = date.today() - timedelta(days=8)  # the archive lags a few days
    start = date(end.year - years, 1, 1)
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "et0_fao_evapotranspiration,precipitation_sum",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(ARCHIVE_URL, params=params)
    resp.raise_for_status()
    d = resp.json()["daily"]
    return [
        {"date": t, "et0": e, "rain_mm": r}
        for t, e, r in zip(d["time"], d["et0_fao_evapotranspiration"], d["precipitation_sum"])
        if e is not None
    ]


def smoothed_doy_et0(rows: list[dict], window: int = 7) -> list[float]:
    """366-entry mean ET0 by day-of-year, smoothed with a circular window."""
    sums = [0.0] * 366
    counts = [0] * 366
    for r in rows:
        y, m, d = (int(x) for x in r["date"].split("-"))
        doy = (date(2025, m, d) - date(2025, 1, 1)).days if (m, d) != (2, 29) else 59
        sums[doy] += r["et0"]
        counts[doy] += 1
    raw = [sums[i] / counts[i] if counts[i] else 0.0 for i in range(366)]
    n = 365  # ignore the leap slot for smoothing
    out = []
    for i in range(n):
        vals = [raw[(i + off) % n] for off in range(-window, window + 1)]
        out.append(sum(vals) / len(vals))
    return out


def _doy_to_mmdd(doy: int) -> str:
    return (date(2025, 1, 1) + timedelta(days=doy)).strftime("%m-%d")


def season_boundaries(sm: list[float]) -> dict:
    """Derive season start dates (MM-DD) from the smoothed ET0 curve."""
    n = len(sm)
    peak_doy = max(range(n), key=lambda i: sm[i])
    peak = sm[peak_doy]

    def first_cross(threshold: float, rng) -> int | None:
        for i in rng:
            if sm[i] >= threshold:
                return i
        return None

    spring = first_cross(SPRING_ET0, range(0, peak_doy)) if peak >= SPRING_ET0 else None
    summer = first_cross(SUMMER_ET0, range(0, peak_doy)) if peak >= SUMMER_ET0 else None
    autumn = None
    winter = None
    if summer is not None:
        autumn = next((i for i in range(peak_doy, n) if sm[i] < SUMMER_ET0), None)
    if spring is not None:
        winter = next((i for i in range(peak_doy, n) if sm[i] < SPRING_ET0), None)

    return {
        "peak_et0": round(peak, 2),
        "peak_date": _doy_to_mmdd(peak_doy),
        "spring_start": _doy_to_mmdd(spring) if spring is not None else None,
        "summer_start": _doy_to_mmdd(summer) if summer is not None else None,
        "autumn_start": _doy_to_mmdd(autumn) if autumn is not None else None,
        "winter_start": _doy_to_mmdd(winter) if winter is not None else None,
    }
