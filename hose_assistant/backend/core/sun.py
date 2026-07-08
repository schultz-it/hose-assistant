"""Sunrise/sunset via astral (SPEC: sun data computed offline)."""
from datetime import date
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun as astral_sun


def sun_times(lat: float, lon: float, tz: str, day: date | None = None) -> dict:
    """Return sunrise/sunset/dawn/dusk ISO timestamps for a location."""
    tzinfo = ZoneInfo(tz)
    loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz)
    s = astral_sun(loc.observer, date=day or date.today(), tzinfo=tzinfo)
    return {
        "dawn": s["dawn"].isoformat(),
        "sunrise": s["sunrise"].isoformat(),
        "sunset": s["sunset"].isoformat(),
        "dusk": s["dusk"].isoformat(),
    }
