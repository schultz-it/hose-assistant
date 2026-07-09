"""Rule-based program generator (SPEC 7.1) — always available, offline logic.

Takes the local climate season boundaries and proposes the 4 default
programs. Output is a PROPOSAL: nothing is persisted until the user applies
it (POST /api/programs/apply).

Zone-type differentiation note (Andrea's requirement): frequency and depth
per zone emerge from the water-balance physics — drip beds have deeper
roots (bigger bucket) and mulched zones lose less water (lower Kc_eff), so
budget mode waters them less often automatically. The programs set the
shared knobs: windows (pre-dawn in summer), MAD and priority.
"""
from datetime import date, timedelta

from . import climate


def _day_before(mmdd: str) -> str:
    d = date(2025, int(mmdd[:2]), int(mmdd[3:5])) - timedelta(days=1)
    return d.strftime("%m-%d")


def build_proposal(bounds: dict) -> dict:
    """Program dicts from season boundaries. Returns {programs, explanation}."""
    programs: list[dict] = []
    notes: list[str] = []

    spring, summer = bounds["spring_start"], bounds["summer_start"]
    autumn, winter = bounds["autumn_start"], bounds["winter_start"]

    # Lawn Start: fixed short frequent runs, manual activation (seeding time).
    programs.append({
        "name": "Lawn Start", "icon": "mdi:sprout", "color": "#8bc34a",
        "mode": "fixed", "manual_only": True, "priority": 10,
        "window_start": "07:00", "window_end": "18:00",
        "mad_pct": 0.0, "et_multiplier": 1.0,
        "fixed_runs": [
            {"time": "07:00", "minutes_per_zone": 5},
            {"time": "12:00", "minutes_per_zone": 5},
            {"time": "17:00", "minutes_per_zone": 5},
        ],
        "generated_by": "rules",
        "ai_explanation": "Enable manually after seeding/overseeding; disable "
                          "once the lawn is established (4-6 weeks).",
    })

    if spring is None:
        notes.append("Mean ET0 never reaches 2 mm/day: climate too cold/wet for "
                     "scheduled irrigation — only Lawn Start proposed.")
        return {"programs": programs, "explanation": " ".join(notes)}

    if summer:
        programs.append({
            "name": "Spring", "icon": "mdi:flower", "color": "#4caf50",
            "mode": "budget", "date_start": spring, "date_end": _day_before(summer),
            "priority": 1, "window_start": "06:00", "window_end": "09:00",
            "mad_pct": 50.0, "et_multiplier": 1.0, "generated_by": "rules",
        })
        programs.append({
            "name": "Summer", "icon": "mdi:white-balance-sunny", "color": "#ff9800",
            "mode": "budget", "date_start": summer,
            "date_end": _day_before(autumn) if autumn else "09-15",
            "priority": 2, "window_start": "04:00", "window_end": "08:00",
            "mad_pct": 40.0, "et_multiplier": 1.0, "generated_by": "rules",
        })
        if autumn and winter:
            programs.append({
                "name": "Autumn", "icon": "mdi:leaf", "color": "#795548",
                "mode": "budget", "date_start": autumn, "date_end": winter,
                "priority": 1, "window_start": "06:00", "window_end": "09:00",
                "mad_pct": 50.0, "et_multiplier": 1.0, "generated_by": "rules",
            })
        notes.append(
            f"Local ET0 peaks at {bounds['peak_et0']} mm/day around {bounds['peak_date']}. "
            f"Season boundaries from the 5-year ET0 curve: spring {spring}, summer {summer}"
            + (f", autumn {autumn}" if autumn else "")
            + (f", season end {winter}" if winter else "") + ".")
        notes.append("Summer waters pre-dawn (04:00-08:00) with MAD 40%; "
                     "Spring/Autumn in the morning with MAD 50%.")
    else:
        programs.append({
            "name": "Season", "icon": "mdi:flower", "color": "#4caf50",
            "mode": "budget", "date_start": spring, "date_end": winter or "10-15",
            "priority": 1, "window_start": "06:00", "window_end": "09:00",
            "mad_pct": 50.0, "et_multiplier": 1.0, "generated_by": "rules",
        })
        notes.append("Mild climate (ET0 never reaches 4 mm/day): one growing-season "
                     "program instead of separate Spring/Summer/Autumn.")

    notes.append("Drip beds and mulched zones water less often automatically: "
                 "deeper roots and lower evaporation slow their deficit.")
    return {"programs": programs, "explanation": " ".join(notes)}


async def generate(lat: float, lon: float) -> dict:
    """Fetch climate normals and build the proposal."""
    rows = await climate.fetch_climate_daily(lat, lon)
    sm = climate.smoothed_doy_et0(rows)
    bounds = climate.season_boundaries(sm)
    out = build_proposal(bounds)
    out["climate"] = bounds
    return out
