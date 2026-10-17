import math
from collections.abc import Sequence
from dataclasses import replace

from .elevation import Elevation, LonLat
from .geo import Projector
from .model import Waypoint


def _densify(waypoints: Sequence[Waypoint], step_m: float, proj: Projector) -> list[Waypoint]:
    out = [waypoints[0]]
    for a, b in zip(waypoints, waypoints[1:]):
        x0, y0 = proj.forward(a.lng, a.lat)
        x1, y1 = proj.forward(b.lng, b.lat)
        parts = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step_m))
        for k in range(1, parts):
            t = k / parts
            lng, lat = proj.inverse(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            out.append(replace(a, lat=lat, lng=lng))
        out.append(b)
    return out


def follow_terrain(
    waypoints: Sequence[Waypoint],
    altitude_m: float,
    takeoff: LonLat,
    elevation: Elevation,
    step_m: float = 30.0,
) -> list[Waypoint]:
    """Re-height the route so the drone keeps altitude_m above ground.

    Heights are relative to the takeoff point, which is how the drone measures them.
    Extra points inherit the attributes of the waypoint that starts their segment.
    """
    if not waypoints:
        return []
    proj = Projector(waypoints[0].lng, waypoints[0].lat)
    route = _densify(waypoints, step_m, proj)
    levels = elevation([takeoff, *((w.lng, w.lat) for w in route)])
    base = levels[0]
    if len(levels) != len(route) + 1:
        raise ValueError("elevation service returned an unexpected number of values")
    return [replace(w, height=altitude_m + ground - base) for w, ground in zip(route, levels[1:])]
