"""Crop coefficient (Kc) and shade factor (SPEC 5.2).

``Kc_eff = Kc_month(grass) x shade_factor(month)``

Monthly Kc tables are Northern-Hemisphere calendars (peak in summer), with the
peaks mandated by the SPEC: cool-season turf 0.95, warm-season 0.75. Shade:
the fine slider (0-100) maps linearly onto factor 1.0 -> 0.5; the preset only
positions the slider default (full_sun=0, partial=40, shade=80). An optional
12-value monthly curve overrides both.
"""

KC_MONTHLY: dict[str, list[float]] = {
    #               Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep   Oct   Nov   Dec
    "cool_season": [0.75, 0.80, 0.85, 0.90, 0.95, 0.95, 0.95, 0.95, 0.90, 0.85, 0.80, 0.75],
    "warm_season": [0.55, 0.55, 0.60, 0.65, 0.70, 0.75, 0.75, 0.75, 0.70, 0.65, 0.60, 0.55],
    "shrubs_drip": [0.50] * 12,
}

# Default slider position implied by each shade preset.
PRESET_FINE: dict[str, int] = {"full_sun": 0, "partial": 40, "shade": 80}

# Soil cover: mulch reduces evaporation (Kc factor); plastic film also keeps
# most rainfall out of the root zone (rain factor, used by the engine).
COVER_KC: dict[str, float] = {"none": 1.0, "organic_mulch": 0.85, "plastic_mulch": 0.75}
COVER_RAIN: dict[str, float] = {"none": 1.0, "organic_mulch": 1.0, "plastic_mulch": 0.3}


def cover_kc_factor(zone) -> float:
    return COVER_KC.get(getattr(zone, "cover", "none") or "none", 1.0)


def cover_rain_factor(zone) -> float:
    return COVER_RAIN.get(getattr(zone, "cover", "none") or "none", 1.0)


def shade_factor(zone, month: int) -> float:
    """Shade factor in [0.5, 1.0] for a zone in a given month (1-12)."""
    if zone.shade_monthly and len(zone.shade_monthly) == 12:
        return float(zone.shade_monthly[month - 1])
    return 1.0 - 0.005 * zone.shade_fine


def kc_eff(zone, month: int) -> float:
    """Effective crop coefficient for a zone in a given month (1-12)."""
    kc = KC_MONTHLY[zone.grass_type][month - 1]
    return round(kc * shade_factor(zone, month) * cover_kc_factor(zone), 3)
