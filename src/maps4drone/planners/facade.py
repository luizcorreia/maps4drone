import math

from ..camera import Camera, Drone
from ..geo import Projector, bearing_deg, wrap_180
from ..model import Mission, Waypoint
from .common import check_heights


def plan_facade(
    drone: Drone,
    camera: Camera,
    base_a: tuple[float, float],
    base_b: tuple[float, float],
    wall_height_m: float,
    standoff_m: float = 15.0,
    front_overlap: float = 0.75,
    side_overlap: float = 0.70,
    side: str = "left",
    speed_ms: float = 1.5,
) -> Mission:
    """Vertical grid in front of a wall running from base_a to base_b (lon, lat).

    The drone stands standoff_m away on the given side of the A->B direction, facing the
    wall with the gimbal level, and shoots a photo at every waypoint. Heights are relative
    to takeoff, so takeoff should be at wall-base level.
    """
    if side not in ("left", "right"):
        raise ValueError("side must be 'left' or 'right'")
    proj = Projector(*base_a)
    ax, ay = proj.forward(*base_a)
    bx, by = proj.forward(*base_b)
    length = math.hypot(bx - ax, by - ay)
    if length < 1:
        raise ValueError("wall must be at least 1 m long")
    ux, uy = (bx - ax) / length, (by - ay) / length
    nx, ny = (-uy, ux) if side == "left" else (uy, -ux)

    fw, fh = camera.footprint_m(standoff_m)
    hstep = fw * (1 - side_overlap)
    vstep = fh * (1 - front_overlap)
    cols = max(1, math.ceil((length - fw) / hstep) + 1) if length > fw else 1
    z_min, z_max = fh / 2, wall_height_m - fh / 2
    rows = max(1, math.ceil((z_max - z_min) / vstep) + 1) if z_max > z_min else 1
    z0 = z_min if rows > 1 else wall_height_m / 2
    z_step = (z_max - z_min) / (rows - 1) if rows > 1 else 0.0
    along0 = (length - hstep * (cols - 1)) / 2
    yaw = round(wrap_180(bearing_deg(-nx, -ny)))

    waypoints = []
    for r in range(rows):
        order = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
        for c in order:
            s = along0 + c * hstep
            lng, lat = proj.inverse(ax + ux * s + nx * standoff_m, ay + uy * s + ny * standoff_m)
            waypoints.append(
                Waypoint(
                    lat=lat,
                    lng=lng,
                    height=z0 + r * z_step,
                    gimbal_pitch=0.0,
                    yaw=yaw,
                    hover_time=1,
                    action="PHOTO",
                )
            )
    mission = Mission(
        drone=drone,
        waypoints=waypoints,
        speed_ms=min(speed_ms, drone.max_speed_ms),
        area_m2=length * wall_height_m,
    )
    mission.warnings.extend(check_heights(drone, waypoints))
    return mission
