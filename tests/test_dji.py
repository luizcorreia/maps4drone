import io
import zipfile
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from tests.test_web import AREA

from maps4drone import dji
from maps4drone.camera import load_drones
from maps4drone.model import Mission, Waypoint
from maps4drone.planners.survey import SurveyParams, plan_survey
from maps4drone.web.app import app, get_elevation

WPML = "{http://www.dji.com/wpmz/1.0.6}"
DJI_IDS = ["litox1", "mini4pro", "mini3pro", "mini3", "mini5pro", "mavic3e", "air3s"]


@pytest.fixture(scope="module")
def drones():
    return load_drones()


@pytest.fixture
def mission(drones, square):
    drone = drones["mini4pro"]
    return plan_survey(square, drone, drone.camera(), SurveyParams(heading_deg=0, interval_s=2))


def test_catalog_has_dji_drones_with_enums(drones):
    for drone_id in DJI_IDS:
        drone = drones[drone_id]
        assert drone.export_format == "dji" and drone.dji_enums is not None
        assert drone.camera().gsd_m(100) > 0
    assert drones["atom2"].export_format == "atom2" and drones["atom2"].dji_enums is None
    assert drones["mini5pro"].dji_enums == (343, 0)
    assert set(drones["mini5pro"].cameras) == {"50mp-4x3", "12mp-4x3", "12mp-16x9"}


def test_survey_is_densified_at_the_shot_distance(mission):
    wps = dji.photo_waypoints(mission)
    assert len(wps) > len(mission.waypoints)
    assert all(w.action == "PHOTO" for w in wps)
    for got, want in ((wps[0], mission.waypoints[0]), (wps[-1], mission.waypoints[-1])):
        assert (got.lat, got.lng) == pytest.approx((want.lat, want.lng), abs=1e-9)


def test_photo_waypoints_keep_explicit_actions(drones):
    wps = [Waypoint(-23.0, -51.0, 30.0, action="PHOTO"), Waypoint(-23.0, -51.001, 30.0)]
    m = Mission(drone=drones["mini4pro"], waypoints=wps, speed_ms=5)
    assert [w.action for w in dji.photo_waypoints(m)] == ["PHOTO", "NONE"]


def test_split_shares_the_seam_waypoint():
    wps = [Waypoint(0.0, i * 1e-5, 50.0) for i in range(450)]
    chunks = dji.split_with_overlap(wps, 195)
    assert all(len(c) <= 195 for c in chunks)
    assert [c[0] for c in chunks[1:]] == [c[-1] for c in chunks[:-1]]
    assert chunks[0][0] == wps[0] and chunks[-1][-1] == wps[-1]
    assert dji.split_with_overlap(wps[:195], 195) == [wps[:195]]


def test_kmz_is_well_formed_and_carries_the_drone_enums(mission):
    [data] = dji.mission_kmz(mission)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert sorted(z.namelist()) == ["wpmz/template.kml", "wpmz/waylines.wpml"]
        wayline = ET.fromstring(z.read("wpmz/waylines.wpml"))
        template = ET.fromstring(z.read("wpmz/template.kml"))
    assert wayline.find(f".//{WPML}droneEnumValue").text == "67"
    assert wayline.find(f".//{WPML}payloadEnumValue").text == "53"
    assert template.find(f".//{WPML}droneEnumValue").text == "67"
    placemarks = wayline.findall(".//{*}Placemark")
    assert len(placemarks) == len(dji.photo_waypoints(mission))
    photos = [f for f in wayline.iter(f"{WPML}actionActuatorFunc") if f.text == "takePhoto"]
    assert len(photos) == len(placemarks)
    heights = {float(p.find(f"{WPML}executeHeight").text) for p in placemarks}
    assert heights == {100.0}


def test_gimbal_is_set_only_when_the_pitch_changes(drones):
    wps = [Waypoint(0.0, i * 1e-4, 40.0, gimbal_pitch=-90.0) for i in range(3)]
    wps.append(Waypoint(0.0, 4e-4, 40.0, gimbal_pitch=-45.0))
    m = Mission(drone=drones["mini4pro"], waypoints=wps, speed_ms=5)
    root = ET.fromstring(dji.waylines_wpml(m, dji.photo_waypoints(m)))
    rotations = [float(a.text) for a in root.iter(f"{WPML}gimbalPitchRotateAngle")]
    assert rotations == [-90.0, -45.0]


def test_atom2_drone_is_refused(drones, square):
    drone = drones["atom2"]
    m = plan_survey(square, drone, drone.camera(), SurveyParams(heading_deg=0))
    with pytest.raises(ValueError, match="DJI enum"):
        dji.mission_kmz(m)


@pytest.fixture
def client():
    app.dependency_overrides[get_elevation] = lambda: lambda pts: [0.0] * len(pts)
    yield TestClient(app)
    app.dependency_overrides.clear()


def export(client, **params):
    body = {"mode": "grid", "geometry": AREA, "params": {"interval": 2, **params}}
    return client.post("/api/export", json=body)


def test_export_dji_returns_a_kmz(client):
    r = export(client, drone="mini4pro", altitude=100)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.google-earth.kmz"
    assert r.headers["content-disposition"].endswith('.kmz"')
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert "wpmz/waylines.wpml" in z.namelist()


def test_export_dji_splits_long_routes_into_a_zip_of_kmz(client):
    r = export(client, drone="mini4pro", altitude=30, front=90, side=90)
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
        assert len(names) > 1 and all(n.endswith(".kmz") for n in names)
        for name in names:
            with zipfile.ZipFile(io.BytesIO(z.read(name))) as kmz:
                wayline = ET.fromstring(kmz.read("wpmz/waylines.wpml"))
            assert len(wayline.findall(".//{*}Placemark")) <= dji.MAX_WAYPOINTS


def test_export_atom2_is_unchanged(client):
    r = export(client, drone="atom2")
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert "global.json" in z.namelist()


def test_plan_validates_dji_missions_with_the_dji_writer(client, monkeypatch):
    def refuse(_mission):
        raise ValueError("recusado pelo escritor DJI")

    monkeypatch.setattr(dji, "mission_kmz", refuse)
    body = {"mode": "grid", "geometry": AREA, "params": {"interval": 2}}
    dji_plan = client.post(
        "/api/plan", json={**body, "params": {**body["params"], "drone": "mini4pro"}}
    )
    assert dji_plan.status_code == 422
    assert dji_plan.json()["detail"] == "recusado pelo escritor DJI"
    assert client.post("/api/plan", json=body).status_code == 200  # atom2 does not use it
