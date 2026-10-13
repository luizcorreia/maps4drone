import math

from ..camera import Drone
from ..geo import Projector, bearing_deg, wrap_180
from ..model import Mission, Waypoint
from .common import check_heights


def plan_orbit(
    drone: Drone,
    center: tuple[float, float],
    radius_m: float,
    height_m: float,
    points: int = 12,
    target_height_m: float = 0.0,
    speed_ms: float = 3.0,
    photo_each: bool = False,
) -> Mission:
    """Circle around a point of interest (lon, lat) with the camera locked on it.

    The gimbal tilt is computed so the camera looks at target_height_m above takeoff level.
    """
    if points < 3:
        raise ValueError("an orbit needs at least 3 points")
    proj = Projector(*center)
    cx, cy = proj.forward(*center)
    pitch = -math.degrees(math.atan2(height_m - target_height_m, radius_m))
    waypoints = []
    for k in range(points):
        a = 2 * math.pi * k / points
        dx, dy = radius_m * math.sin(a), radius_m * math.cos(a)
        lng, lat = proj.inverse(cx + dx, cy + dy)
        waypoints.append(
            Waypoint(
                lat=lat,
                lng=lng,
                height=height_m,
                gimbal_pitch=max(-90.0, min(20.0, pitch)),
                yaw=round(wrap_180(bearing_deg(-dx, -dy))),
                hover_time=1 if photo_each else 0,
                action="PHOTO" if photo_each else "NONE",
            )
        )
    mission = Mission(drone=drone, waypoints=waypoints, speed_ms=min(speed_ms, drone.max_speed_ms))
    mission.warnings.extend(check_heights(drone, waypoints))
    return mission
