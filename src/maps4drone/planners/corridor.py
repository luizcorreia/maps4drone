from __future__ import annotations

import math

from shapely.geometry import LineString

from ..camera import Camera, Drone
from ..elevation import Elevation, LonLat
from ..geo import Projector
from ..model import Mission
from ..routing import serpentine
from .common import finish, shoot_interval, to_waypoints
from .survey import XY, SurveyParams


def plan_corridor(
    centerline_lonlat: list[LonLat],
    drone: Drone,
    camera: Camera,
    params: SurveyParams,
    lines: int = 3,
    elevation: Elevation | None = None,
    takeoff: LonLat | None = None,
) -> Mission:
    """Parallel passes along a road/rail/river axis: one on the axis plus pairs on both sides."""
    if lines < 1 or lines % 2 == 0:
        raise ValueError("lines must be odd (1 on the axis + 1 per side per pair)")
    interval = shoot_interval(drone, params.interval_s)
    proj = Projector(*centerline_lonlat[0])
    axis = LineString([proj.forward(x, y) for x, y in centerline_lonlat])
    spacing = camera.line_spacing_m(params.altitude_m, params.side_overlap)
    shot = camera.shot_distance_m(params.altitude_m, params.front_overlap)

    offsets = [k * spacing for k in range(-(lines // 2), lines // 2 + 1)]
    passes: list[list[XY]] = []
    for offset in offsets:
        track = axis if offset == 0 else axis.offset_curve(offset, join_style="mitre")
        if track.geom_type != "LineString":
            raise ValueError("centerline bends too sharply for this line spacing")
        passes.append([(float(x), float(y)) for x, y in track.coords])

    mission = Mission(
        drone=drone,
        waypoints=to_waypoints(serpentine(passes), proj, params.altitude_m, params.gimbal_pitch),
        speed_ms=min(math.floor(shot / interval * 10) / 10, drone.max_speed_ms),
        shoot_interval_s=interval,
        area_m2=float(axis.length * spacing * lines),
    )
    return finish(mission, params.altitude_m, elevation, takeoff, params.terrain_step_m)
