import math
from dataclasses import dataclass

from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from ..camera import Camera, Drone
from ..elevation import Elevation, LonLat
from ..geo import Projector
from ..model import Mission
from ..routing import closest_end_first, serpentine
from .common import finish, shoot_interval, to_waypoints

XY = tuple[float, float]


@dataclass(frozen=True)
class SurveyParams:
    altitude_m: float = 100.0
    front_overlap: float = 0.80
    side_overlap: float = 0.70
    heading_deg: float = 0.0  # compass bearing of the flight lines, 0 = north
    interval_s: float = 3.0
    gimbal_pitch: float = -90.0
    margin_m: float = 0.0
    double: bool = False
    terrain_step_m: float = 30.0


def _segments(geom: BaseGeometry) -> list[LineString]:
    if isinstance(geom, LineString):
        return [geom] if geom.length > 1e-6 else []
    return [s for g in getattr(geom, "geoms", []) for s in _segments(g)]


def _flight_lines(area: BaseGeometry, spacing: float, heading: float) -> list[list[XY]]:
    """Parallel lines at the given compass heading, covering area, as ordered point lists."""
    pivot = area.centroid
    rotated = affinity.rotate(area, heading, origin=pivot)
    minx, miny, maxx, maxy = rotated.bounds
    lines: list[list[XY]] = []
    x = minx + spacing / 2
    while x < maxx:
        cut = rotated.intersection(LineString([(x, miny - 1), (x, maxy + 1)]))
        pieces = sorted(
            (sorted(s.coords, key=lambda c: c[1]) for s in _segments(cut)),
            key=lambda c: c[0][1],
        )
        line: list[XY] = []
        for piece in pieces:
            line.extend((piece[0], piece[-1]))
        if line:
            lines.append(line)
        x += spacing
    back = []
    for line in lines:
        pts = affinity.rotate(LineString(line), -heading, origin=pivot)
        back.append([(float(px), float(py)) for px, py in pts.coords])
    return back


def plan_survey(
    area_lonlat: Polygon | MultiPolygon,
    drone: Drone,
    camera: Camera,
    params: SurveyParams,
    elevation: Elevation | None = None,
    takeoff: LonLat | None = None,
) -> Mission:
    """Lawn-mower (or double, cross-hatched) survey over a polygon."""
    interval = shoot_interval(drone, params.interval_s)
    c = area_lonlat.centroid
    proj = Projector(c.x, c.y)
    area = _project(area_lonlat, proj)
    if params.margin_m:
        area = area.buffer(params.margin_m, join_style="mitre")
    spacing = camera.line_spacing_m(params.altitude_m, params.side_overlap)
    shot = camera.shot_distance_m(params.altitude_m, params.front_overlap)

    headings = (
        [params.heading_deg, params.heading_deg + 90] if params.double else [params.heading_deg]
    )
    route: list[XY] = []
    for heading in headings:
        pass_pts = serpentine(_flight_lines(area, spacing, heading))
        if route:
            pass_pts = closest_end_first(pass_pts, route[-1])
        route.extend(pass_pts)

    mission = Mission(
        drone=drone,
        waypoints=to_waypoints(route, proj, params.altitude_m, params.gimbal_pitch),
        speed_ms=min(math.floor(shot / interval * 10) / 10, drone.max_speed_ms),
        shoot_interval_s=interval,
        area_m2=float(area.area),
    )
    if shot / interval > drone.max_speed_ms:
        mission.warnings.append(
            f"overlap needs {shot / interval:.1f} m/s at a {interval:g} s interval; "
            f"capped at {drone.max_speed_ms:g} m/s, real front overlap will be lower"
        )
    return finish(mission, params.altitude_m, elevation, takeoff, params.terrain_step_m)


def _project(geom: Polygon | MultiPolygon, proj: Projector) -> BaseGeometry:
    def ring(coords: object) -> list[XY]:
        return [proj.forward(x, y) for x, y, *_ in coords]  # type: ignore[attr-defined]

    polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    out = [Polygon(ring(p.exterior.coords), [ring(h.coords) for h in p.interiors]) for p in polys]
    return out[0] if len(out) == 1 else MultiPolygon(out)
