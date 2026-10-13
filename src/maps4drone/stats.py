import math
from dataclasses import dataclass

from .geo import Projector
from .model import Mission

BATTERY_USABLE = 0.75  # keep a reserve for return and wind


@dataclass(frozen=True)
class Stats:
    waypoints: int
    distance_m: float
    duration_s: float
    batteries: int
    images: dict[float, int]
    area_ha: float | None


def estimate(mission: Mission, intervals: tuple[float, ...] = (3.0, 5.0)) -> Stats:
    wps = mission.waypoints
    proj = Projector(wps[0].lng, wps[0].lat)
    pts = [(*proj.forward(w.lng, w.lat), w.height) for w in wps]
    distance = 0.0
    duration = float(sum(w.hover_time for w in wps))
    for (a, b, c), (d, e, f), w in zip(pts, pts[1:], wps[1:], strict=False):
        leg = math.dist((a, b, c), (d, e, f))
        distance += leg
        duration += leg / (w.speed or mission.speed_ms)
    usable_s = mission.drone.flight_minutes * 60 * BATTERY_USABLE
    return Stats(
        waypoints=len(wps),
        distance_m=distance,
        duration_s=duration,
        batteries=max(1, math.ceil(duration / usable_s)),
        images={i: round(duration / i) for i in intervals},
        area_ha=None if mission.area_m2 is None else mission.area_m2 / 10_000,
    )


def format_duration(seconds: float) -> str:
    m, s = divmod(round(seconds), 60)
    return f"{m}min {s:02d}s"


__all__ = ["Stats", "estimate", "format_duration"]
