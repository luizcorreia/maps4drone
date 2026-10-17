"""Writer for the Potensic Atom 2 waypoint mission files (Potensic Eve app).

Layout on the phone: /sdcard/Android/data/com.ipotensic.atom/files/Waypoint/<id>/
  global.json    mission-wide settings
  <id>.json      the waypoints

The app keeps an index of missions elsewhere, so a folder dropped in from outside is
deleted on launch. The workaround is to create a dummy mission in the app and overwrite
its two files, keeping the names. `replace_mission` does exactly that.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .model import Mission, Waypoint

ACTIONS = {"NONE", "PHOTO", "START_RECORD", "STOP_RECORD"}
FINISH_ACTIONS = {"BACK", "LAND", "HOVER", "RETURN"}
PITCH_RANGE = (-90.0, 20.0)
_MISSION_FILE = re.compile(r"^\d+\.json$")


def _dumps(obj: object) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _waypoint(w: Waypoint, mission_speed: float) -> dict[str, object]:
    if w.action not in ACTIONS:
        raise ValueError(f"unknown action {w.action!r}")
    if not PITCH_RANGE[0] <= w.gimbal_pitch <= PITCH_RANGE[1]:
        raise ValueError(f"gimbal pitch {w.gimbal_pitch} outside {PITCH_RANGE}")
    if not (-90 <= w.lat <= 90 and -180 <= w.lng <= 180):
        raise ValueError(f"bad coordinates {w.lat}, {w.lng}")
    own_speed = w.speed is not None
    return {
        "action": w.action,
        "gimbalPitch": round(w.gimbal_pitch),
        "gimbalType": "DEFINE",
        "height": round(w.height, 1),
        "hoverTime": int(w.hover_time),
        "lat": round(w.lat, 8),
        "lng": round(w.lng, 8),
        "poiHeight": 50.0,
        "poiLat": 0.0,
        "poiLng": 0.0,
        "poiType": 0,
        "speed": float(w.speed if w.speed is not None else mission_speed),
        "speedType": "DEFINE" if own_speed else "GLOBAL",
        "yaw": 0 if w.yaw is None else round(w.yaw),
        "yawType": "TO_WAYPOINT" if w.yaw is None else "HAND",
        "zoomRatio": 1.0,
        "zoomType": "HAND",
    }


def mission_files(mission: Mission, legacy_poi_list: bool = False) -> tuple[str, str]:
    """Return (global.json, <id>.json) contents.

    legacy_poi_list appends the ";[]" POI array that older firmware is reported to use.
    """
    if not mission.waypoints:
        raise ValueError("mission has no waypoints")
    if mission.finish_action not in FINISH_ACTIONS:
        raise ValueError(f"unknown finish action {mission.finish_action!r}")
    if not 0 < mission.speed_ms <= mission.drone.max_speed_ms:
        raise ValueError(f"speed must be in (0, {mission.drone.max_speed_ms}] m/s")
    global_json = _dumps(
        {
            "finishAction": mission.finish_action,
            "globalHeight": 0,
            "globalHeightType": 0,
            "isOrder": True,
            "lostAction": "RETURN",
            "speed": float(mission.speed_ms),
        }
    )
    body = _dumps([_waypoint(w, mission.speed_ms) for w in mission.waypoints])
    return global_json, body + (";[]" if legacy_poi_list else "")


def write_mission(
    mission: Mission, out_dir: Path, mission_id: int | None = None, legacy_poi_list: bool = False
) -> Path:
    """Write a new mission folder named after a millisecond timestamp."""
    mission_id = mission_id or int(time.time() * 1000)
    global_json, body = mission_files(mission, legacy_poi_list)
    folder = out_dir / str(mission_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "global.json").write_text(global_json)
    (folder / f"{mission_id}.json").write_text(body)
    return folder


def replace_mission(mission: Mission, existing: Path, legacy_poi_list: bool = False) -> Path:
    """Overwrite the two files of a mission folder the app created, keeping their names."""
    candidates = [p for p in existing.iterdir() if _MISSION_FILE.match(p.name)]
    if len(candidates) != 1 or not (existing / "global.json").exists():
        raise ValueError(f"{existing} does not look like an Atom 2 mission folder")
    global_json, body = mission_files(mission, legacy_poi_list)
    (existing / "global.json").write_text(global_json)
    candidates[0].write_text(body)
    return existing
