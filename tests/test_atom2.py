import json
from pathlib import Path

import pytest

from maps4drone import atom2 as writer
from maps4drone.model import Mission, Waypoint

FIXTURE = Path(__file__).parent / "fixtures" / "atom2_sample_mission.json"


def _mission(drone, **kw):
    wps = kw.pop("waypoints", [Waypoint(-23.1, -51.9, 100), Waypoint(-20.2, -51.8, 100.04)])
    return Mission(drone=drone, waypoints=wps, speed_ms=5.0, **kw)


def test_waypoint_keys_match_real_app_file(atom2):
    real = json.loads(FIXTURE.read_text())
    _, body = writer.mission_files(_mission(atom2))
    ours = json.loads(body)
    assert set(ours[0]) == set(real[0])
    assert {type(v) for v in ours[0].values()} <= {str, int, float}
    for key in ("gimbalType", "zoomType", "poiType", "poiHeight"):
        assert ours[0][key] == real[0][key]


def test_real_file_values_are_accepted_by_validation(atom2):
    for r in json.loads(FIXTURE.read_text()):
        w = Waypoint(
            r["lat"], r["lng"], r["height"], r["gimbalPitch"], None, r["hoverTime"], r["action"]
        )
        writer.mission_files(_mission(atom2, waypoints=[w]))


def test_global_json(atom2):
    g, _ = writer.mission_files(_mission(atom2))
    assert json.loads(g) == {
        "finishAction": "BACK",
        "globalHeight": 0,
        "globalHeightType": 0,
        "isOrder": True,
        "lostAction": "RETURN",
        "speed": 5.0,
    }


def test_yaw_and_speed_modes(atom2):
    wps = [Waypoint(-23.1, -51.9, 50, yaw=-171, speed=3.0), Waypoint(-20.2, -51.9, 50)]
    _, body = writer.mission_files(_mission(atom2, waypoints=wps))
    a, b = json.loads(body)
    assert (a["yawType"], a["yaw"], a["speedType"], a["speed"]) == ("HAND", -171, "DEFINE", 3.0)
    assert (b["yawType"], b["speedType"], b["speed"]) == ("TO_WAYPOINT", "GLOBAL", 5.0)


def test_legacy_poi_suffix(atom2):
    _, body = writer.mission_files(_mission(atom2), legacy_poi_list=True)
    assert body.endswith(";[]")
    assert json.loads(body.removesuffix(";[]"))


@pytest.mark.parametrize(
    "wp",
    [
        Waypoint(-20, -44, 50, gimbal_pitch=-91),
        Waypoint(-20, -44, 50, gimbal_pitch=21),
        Waypoint(-20, -44, 50, action="BOOM"),
        Waypoint(-91, -44, 50),
    ],
)
def test_validation_rejects_bad_waypoints(atom2, wp):
    with pytest.raises(ValueError):
        writer.mission_files(_mission(atom2, waypoints=[wp]))


def test_validation_rejects_bad_mission(atom2):
    with pytest.raises(ValueError, match="no waypoints"):
        writer.mission_files(_mission(atom2, waypoints=[]))
    with pytest.raises(ValueError, match="finish"):
        writer.mission_files(_mission(atom2, finish_action="EXPLODE"))
    m = _mission(atom2)
    m.speed_ms = 99
    with pytest.raises(ValueError, match="speed"):
        writer.mission_files(m)


def test_write_mission_layout(atom2, tmp_path):
    folder = writer.write_mission(_mission(atom2), tmp_path, mission_id=1770653566867)
    assert sorted(p.name for p in folder.iterdir()) == ["1770653566867.json", "global.json"]


def test_replace_keeps_dummy_names(atom2, tmp_path):
    dummy = tmp_path / "1790000000000"
    dummy.mkdir()
    (dummy / "global.json").write_text("{}")
    (dummy / "1790000000000.json").write_text("[]")
    (dummy / "task_1.jpg").write_bytes(b"jpg")
    writer.replace_mission(_mission(atom2), dummy)
    assert len(json.loads((dummy / "1790000000000.json").read_text())) == 2
    assert json.loads((dummy / "global.json").read_text())["speed"] == 5.0
    assert (dummy / "task_1.jpg").read_bytes() == b"jpg"


def test_replace_rejects_other_folders(atom2, tmp_path):
    with pytest.raises(ValueError, match="mission folder"):
        writer.replace_mission(_mission(atom2), tmp_path)
