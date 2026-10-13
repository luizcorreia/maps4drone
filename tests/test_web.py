import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maps4drone.web.app import app, get_elevation

FIXTURE = Path(__file__).parent / "fixtures" / "atom2_sample_mission.json"
AREA = {
    "type": "Polygon",
    "coordinates": [
        [
            [-51.9, -23.15],
            [-51.8964, -23.15],
            [-51.8964, -23.1473],
            [-51.9, -23.1473],
            [-51.9, -23.15],
        ]
    ],
}
LINE = {
    "type": "LineString",
    "coordinates": [[-51.9, -23.15], [-51.899, -23.149], [-51.897, -23.149]],
}
KML = (
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon><outerBoundaryIs>'
    "<LinearRing><coordinates>-51.9,-23.15 -51.8964,-23.15 -51.8964,-23.1473 -51.9,-23.15"
    "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>"
)


@pytest.fixture
def client():
    calls = []

    def fake(points):
        calls.append(len(points))
        return [700 + 0.01 * i for i, _ in enumerate(points)]

    app.dependency_overrides[get_elevation] = lambda: fake
    c = TestClient(app)
    c.elevation_calls = calls  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()


def post(client, mode, geometry, **params):
    return client.post("/api/plan", json={"mode": mode, "geometry": geometry, "params": params})


@pytest.mark.parametrize(
    ("mode", "geometry", "params"),
    [
        ("grid", AREA, {}),
        ("double_grid", AREA, {"angle": 35}),
        ("corridor", LINE, {"lines": 3}),
        (
            "orbit",
            {"type": "Point", "coordinates": [-51.9, -23.15]},
            {"altitude": 40, "radius": 30},
        ),
        (
            "facade",
            {"type": "LineString", "coordinates": [[-51.9, -23.15], [-51.8995, -23.15]]},
            {"wall_height": 15},
        ),
        (
            "waypoints",
            {"type": "MultiPoint", "coordinates": [[-51.9, -23.15], [-51.899, -23.15]]},
            {},
        ),
    ],
)
def test_plan_every_mode(client, mode, geometry, params):
    r = post(client, mode, geometry, **params)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["stats"]["waypoints"] == len(data["geojson"]["features"]) - 1
    assert data["geojson"]["features"][0]["geometry"]["type"] == "LineString"
    assert set(data["stats"]["images"]) == {"3", "5"}
    assert data["speed"] > 0


def test_grid_interval_and_warnings(client):
    data = post(client, "grid", AREA, interval=2, altitude=130).json()
    assert data["interval"] == 2
    assert any("legal limit" in w for w in data["warnings"])


def test_terrain_uses_mocked_elevation(client):
    r = post(client, "grid", AREA, terrain=True, takeoff=[-51.9, -23.15])
    assert r.status_code == 200
    assert client.elevation_calls  # type: ignore[attr-defined]


def test_error_mapping(client):
    assert post(client, "grid", AREA, terrain=True).status_code == 422  # no takeoff
    assert "decolagem" in post(client, "grid", AREA, terrain=True).json()["detail"]
    assert post(client, "grid", None).status_code == 422
    assert post(client, "grid", LINE).status_code == 422
    assert post(client, "grid", AREA, interval=1).status_code == 422
    assert post(client, "grid", AREA, drone="nope").status_code == 422
    assert post(client, "grid", AREA, front=120).status_code == 422  # pydantic validation
    assert post(client, "corridor", LINE, lines=2).status_code == 422
    assert post(client, "orbit", AREA).status_code == 422
    assert post(client, "facade", LINE, terrain=True, takeoff=[0, 0]).status_code == 422
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    assert "invalido" in post(client, "grid", bowtie).json()["detail"]


def test_elevation_failure_is_502(client):
    def broken(points):
        raise OSError("offline")

    app.dependency_overrides[get_elevation] = lambda: broken
    r = post(client, "grid", AREA, terrain=True, takeoff=[-51.9, -23.15])
    assert r.status_code == 502


def test_export_zip(client):
    r = client.post("/api/export", json={"mode": "grid", "geometry": AREA, "params": {}})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = sorted(z.namelist())
    assert "global.json" in names and "README.txt" in names
    (mission_name,) = [n for n in names if n[0].isdigit()]
    assert mission_name.endswith(".json") and len(mission_name) == len("1791892508550.json")
    waypoints = json.loads(z.read(mission_name))
    real = json.loads(FIXTURE.read_text())
    assert set(waypoints[0]) == set(real[0])
    assert json.loads(z.read("global.json"))["lostAction"] == "RETURN"


def test_export_rejects_invalid(client):
    r = client.post("/api/export", json={"mode": "grid", "geometry": None, "params": {}})
    assert r.status_code == 422


def test_drones_and_camera(client):
    drones = client.get("/api/drones").json()
    assert drones[0]["id"] == "atom2"
    assert drones[0]["cameras"]["wide-26mm-12mp"]["focal_mm"] == 4.5
    info = client.get("/api/camera", params={"drone": "atom2", "altitude": 100}).json()
    assert info["gsd_cm"] == pytest.approx(3.56, abs=0.01)
    assert info["footprint_w_m"] == pytest.approx(142.2, abs=0.1)
    assert client.get("/api/camera", params={"drone": "x", "altitude": 1}).status_code == 422


def test_import_kml_and_geojson(client):
    r = client.post("/api/import", params={"name": "a.kml"}, content=KML.encode())
    assert r.status_code == 200
    assert r.json()["polygon"]["type"] == "Polygon" and r.json()["line"] is None
    gj = json.dumps({"type": "Feature", "properties": {}, "geometry": LINE})
    r = client.post("/api/import", params={"name": "l.geojson"}, content=gj.encode())
    assert r.json()["line"]["type"] == "LineString"


def test_import_errors(client):
    assert client.post("/api/import", params={"name": "a.txt"}, content=b"x").status_code == 422
    empty = b'{"type":"Point","coordinates":[0,0]}'
    r = client.post("/api/import", params={"name": "e.geojson"}, content=empty)
    assert r.status_code == 422


def test_static_page_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "maps4drone" in r.text
    assert client.get("/app.js").status_code == 200
