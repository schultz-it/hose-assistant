"""Soil parameters (SPEC 5.2): available water capacity and infiltration."""

# soil_type -> (AWC mm/mm, infiltration capacity mm/h)
SOIL: dict[str, tuple[float, float]] = {
    "sandy": (0.06, 25.0),
    "loam": (0.12, 12.0),
    "clay": (0.17, 4.0),
}


def awc_mm_per_mm(soil_type: str) -> float:
    return SOIL[soil_type][0]


def infiltration_mmh(soil_type: str) -> float:
    return SOIL[soil_type][1]


def taw_mm(zone) -> float:
    """Total available water in the root zone (mm): AWC x root depth."""
    return awc_mm_per_mm(zone.soil_type) * zone.root_depth_cm * 10.0
