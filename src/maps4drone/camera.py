from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Camera:
    name: str
    sensor_w_mm: float
    sensor_h_mm: float
    focal_mm: float
    image_w: int
    image_h: int
    rolling_shutter_ms: float = 0.0  # 0 = unknown or mechanical shutter

    def gsd_m(self, altitude_m: float) -> float:
        return self.sensor_w_mm * altitude_m / (self.focal_mm * self.image_w)

    def footprint_m(self, distance_m: float) -> tuple[float, float]:
        """Ground (width, height) covered by one frame, landscape orientation."""
        return (
            self.sensor_w_mm * distance_m / self.focal_mm,
            self.sensor_h_mm * distance_m / self.focal_mm,
        )

    def line_spacing_m(self, altitude_m: float, side_overlap: float) -> float:
        return self.footprint_m(altitude_m)[0] * (1 - side_overlap)

    def shot_distance_m(self, altitude_m: float, front_overlap: float) -> float:
        return self.footprint_m(altitude_m)[1] * (1 - front_overlap)


@dataclass(frozen=True)
class Drone:
    id: str
    name: str
    cameras: dict[str, Camera]
    default_camera: str
    flight_minutes: float
    max_speed_ms: float
    max_height_m: float
    shoot_intervals_s: tuple[float, ...]
    export_format: str = "atom2"  # "atom2" or "dji"
    dji_enums: tuple[int, int] | None = None  # (drone, payload) enum values for the WPML

    def camera(self, name: str | None = None) -> Camera:
        key = name or self.default_camera
        try:
            return self.cameras[key]
        except KeyError:
            raise ValueError(
                f"{self.id}: unknown camera {key!r}, have {list(self.cameras)}"
            ) from None


def _parse(raw: dict[str, Any]) -> dict[str, Drone]:
    drones = {}
    for drone_id, d in raw.items():
        cameras = {k: Camera(name=k, **c) for k, c in d["cameras"].items()}
        dji = d.get("dji")
        drones[drone_id] = Drone(
            id=drone_id,
            name=d["name"],
            cameras=cameras,
            default_camera=d["default_camera"],
            flight_minutes=d["flight_minutes"],
            max_speed_ms=d["max_speed_ms"],
            max_height_m=d["max_height_m"],
            shoot_intervals_s=tuple(d["shoot_intervals_s"]),
            export_format=d.get("export_format", "atom2"),
            dji_enums=(dji["drone_enum"], dji["payload_enum"]) if dji else None,
        )
    return drones


def load_drones(path: Path | None = None) -> dict[str, Drone]:
    """Built-in catalog, or a user-supplied JSON file with the same layout."""
    if path is not None:
        return _parse(json.loads(path.read_text()))
    text = resources.files("maps4drone").joinpath("drones.json").read_text()
    return _parse(json.loads(text))
