from __future__ import annotations

from collections.abc import Sequence

from ..camera import Drone
from ..elevation import Elevation, LonLat
from ..geo import Projector
from ..model import Mission, Waypoint
from ..terrain import follow_terrain

MIN_HEIGHT_M = 5.0


class EmptyRouteError(ValueError):
    """No flight line fits the area (it is smaller than the line spacing)."""


def shoot_interval(drone: Drone, requested: float) -> float:
    if requested not in drone.shoot_intervals_s:
        raise ValueError(f"{drone.name}: interval must be one of {list(drone.shoot_intervals_s)} s")
    return requested


def finish(
    mission: Mission,
    altitude_m: float,
    elevation: Elevation | None,
    takeoff: LonLat | None,
    terrain_step_m: float,
) -> Mission:
    """Apply terrain following (if asked) and collect safety warnings."""
    if elevation is not None:
        if takeoff is None:
            raise ValueError("terrain following needs a takeoff point")
        mission.waypoints = follow_terrain(
            mission.waypoints, altitude_m, takeoff, elevation, terrain_step_m
        )
    agl = altitude_m if elevation is not None else None
    mission.warnings.extend(check_heights(mission.drone, mission.waypoints, agl))
    return mission


def check_heights(
    drone: Drone, waypoints: Sequence[Waypoint], agl_m: float | None = None
) -> list[str]:
    """Warn about heights outside safe limits.

    With terrain following the legal limit applies to agl_m (height above ground), since
    waypoint heights are relative to takeoff and can legitimately be higher.
    """
    heights = [w.height for w in waypoints]
    top = agl_m if agl_m is not None else max(heights)
    warnings = []
    if top > drone.max_height_m:
        warnings.append(f"height {top:.0f} m is above the {drone.max_height_m:.0f} m legal limit")
    if agl_m is None and min(heights) < MIN_HEIGHT_M:
        warnings.append(f"min height {min(heights):.1f} m is below {MIN_HEIGHT_M:.0f} m")
    return warnings


def to_waypoints(
    points_xy: Sequence[tuple[float, float]], proj: Projector, height: float, pitch: float
) -> list[Waypoint]:
    out = []
    for x, y in points_xy:
        lng, lat = proj.inverse(x, y)
        out.append(Waypoint(lat=lat, lng=lng, height=height, gimbal_pitch=pitch))
    return out
