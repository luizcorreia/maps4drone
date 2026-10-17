from __future__ import annotations

from dataclasses import dataclass, field

from .camera import Drone


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lng: float
    height: float
    gimbal_pitch: float = -90.0
    yaw: float | None = None  # None: point the nose at the next waypoint
    hover_time: int = 0
    action: str = "NONE"
    speed: float | None = None  # None: use the mission speed


@dataclass
class Mission:
    drone: Drone
    waypoints: list[Waypoint]
    speed_ms: float
    finish_action: str = "BACK"
    shoot_interval_s: float | None = None
    area_m2: float | None = None
    warnings: list[str] = field(default_factory=list)
