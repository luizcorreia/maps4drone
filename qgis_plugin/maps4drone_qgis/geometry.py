"""QGIS-independent helpers: plain coordinates in, core objects and attribute rows out."""

from collections.abc import Sequence
from typing import Any

from shapely.geometry import MultiPolygon, Polygon

XY = tuple[float, float]
Ring = Sequence[XY]

# (name, kind) with kind in {"int", "double", "string"}; the algorithms map kinds to QGIS types
WAYPOINT_FIELDS = [
    ("idx", "int"),
    ("lat", "double"),
    ("lng", "double"),
    ("height", "double"),
    ("speed", "double"),
    ("pitch", "double"),
    ("yaw", "double"),
    ("action", "string"),
    ("hover_s", "int"),
]
ROUTE_FIELDS = [
    ("waypoints", "int"),
    ("distance_m", "double"),
    ("duration_s", "double"),
    ("speed_ms", "double"),
    ("batteries", "int"),
    ("area_ha", "double"),
]


def polygons_from_rings(polygons: Sequence[Sequence[Ring]]) -> Polygon | MultiPolygon:
    """Build a (multi)polygon from [polygon][ring][(lon, lat)]; the first ring is the shell."""
    built = [
        Polygon(rings[0], list(rings[1:]))
        for rings in polygons
        if rings and len(rings[0]) >= 4  # closed ring: 3 corners + closing point
    ]
    if not built:
        raise ValueError("the input has no polygon with an area")
    return built[0] if len(built) == 1 else MultiPolygon(built)


def first_line(parts: Sequence[Sequence[XY]]) -> list[XY]:
    """First line part with at least two points, as [(lon, lat)]."""
    for part in parts:
        if len(part) >= 2:
            return [(float(x), float(y)) for x, y in part]
    raise ValueError("the input has no line with two or more points")


def waypoint_rows(mission: Any) -> list[tuple[Any, ...]]:
    return [
        (
            i,
            w.lat,
            w.lng,
            w.height,
            w.speed or mission.speed_ms,
            w.gimbal_pitch,
            w.yaw,
            w.action,
            w.hover_time,
        )
        for i, w in enumerate(mission.waypoints, start=1)
    ]


def route_coords(mission: Any) -> list[XY]:
    return [(w.lng, w.lat) for w in mission.waypoints]


def route_row(mission: Any, stats: Any) -> tuple[Any, ...]:
    return (
        stats.waypoints,
        stats.distance_m,
        stats.duration_s,
        mission.speed_ms,
        stats.batteries,
        stats.area_ha,
    )


def summary_text(mission: Any, stats: Any) -> str:
    minutes, seconds = divmod(round(stats.duration_s), 60)
    lines = [
        f"waypoints : {stats.waypoints}",
        f"distance  : {stats.distance_m / 1000:.2f} km at {mission.speed_ms:.1f} m/s",
        f"duration  : ~{minutes}min {seconds:02d}s ({stats.batteries} battery)",
        "images    : " + ", ".join(f"~{n} @ {i:g}s" for i, n in stats.images.items()),
    ]
    if stats.area_ha is not None:
        lines.append(f"area      : {stats.area_ha:.2f} ha")
    if mission.shoot_interval_s:
        lines.append(
            f"IMPORTANT : set the app camera timer to {mission.shoot_interval_s:g} s before flying"
        )
    lines.extend(f"WARNING   : {w}" for w in mission.warnings)
    return "\n".join(lines)
