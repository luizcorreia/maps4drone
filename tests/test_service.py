import io
import json
import urllib.error
import zipfile

import pytest

from maps4drone import service
from maps4drone.service import PlanRequest, UpstreamError

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
NO_TILES = lambda z, x, y: None  # noqa: E731


def request(mode="grid", geometry=AREA, **params):
    return PlanRequest(mode=mode, geometry=geometry, params=params)


def flat(points):
    return [0.0] * len(points)


def test_plan_payload_describes_the_route_and_its_numbers():
    mission = service.build_mission(request(interval=2), flat)
    payload = service.plan_payload(mission)
    assert payload["stats"]["waypoints"] == len(mission.waypoints)
    assert set(payload["stats"]["images"]) == {"2", "3", "5"}
    assert payload["geojson"]["features"][0]["properties"]["kind"] == "route"
    assert payload["interval"] == 2 and payload["speed"] > 0


def test_params_are_validated_by_the_models():
    with pytest.raises(ValueError):
        request(front=120)
    assert request().params.angle is None  # automatic bearing by default


def test_user_mistakes_are_value_errors():
    with pytest.raises(ValueError, match="desenhe a geometria"):
        service.build_mission(PlanRequest(mode="grid"), flat)
    with pytest.raises(ValueError, match="drone desconhecido"):
        service.build_mission(request(drone="nope"), flat)
    with pytest.raises(ValueError, match="ponto de decolagem"):
        service.build_mission(request(terrain=True), flat)


def test_a_failing_elevation_service_is_an_upstream_error():
    def limited(points):
        raise urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]

    def down(points):
        raise OSError("no route to host")

    terrain = {"terrain": True, "takeoff": (-51.9, -23.15)}
    with pytest.raises(UpstreamError, match="limitou as consultas"):
        service.build_mission(request(**terrain), limited)
    with pytest.raises(UpstreamError, match="falha ao consultar a elevacao"):
        service.build_mission(request(**terrain), down)


def test_atom2_export_is_a_zip_with_the_mission_files():
    mission = service.build_mission(request(), flat)
    file = service.export_mission(mission, NO_TILES, now_ms=1_700_000_000_000)
    assert file.media_type == "application/zip"
    assert file.filename == "maps4drone-1700000000000.zip"
    with zipfile.ZipFile(io.BytesIO(file.data)) as z:
        assert {"global.json", "1700000000000.json", "README.txt"} <= set(z.namelist())
        assert "task_1699999999968.jpg" in z.namelist()
        assert isinstance(json.loads(z.read("1700000000000.json")), list)


def test_dji_export_is_a_kmz_or_a_zip_of_them():
    short = service.export_mission(service.build_mission(request(drone="mini4pro"), flat), NO_TILES)
    assert short.media_type == "application/vnd.google-earth.kmz"
    long = service.export_mission(
        service.build_mission(request(drone="mini4pro", altitude=30, front=90, side=90), flat),
        NO_TILES,
        now_ms=5,
    )
    assert long.media_type == "application/zip" and long.filename == "maps4drone-5-voos.zip"
    with zipfile.ZipFile(io.BytesIO(long.data)) as z:
        assert len(z.namelist()) > 1 and all(n.endswith(".kmz") for n in z.namelist())


def test_import_reads_a_polygon_and_refuses_other_formats():
    geojson = json.dumps({"type": "Feature", "properties": {}, "geometry": AREA}).encode()
    result = service.import_payload("area.geojson", geojson)
    assert result["polygon"]["type"] == "Polygon"
    with pytest.raises(ValueError, match="formato nao suportado"):
        service.import_payload("area.txt", b"x")
    with pytest.raises(ValueError, match="nenhum poligono"):
        service.import_payload("empty.geojson", b'{"type":"Point","coordinates":[0,0]}')


def test_camera_payload_gives_gsd_and_footprint():
    payload = service.camera_payload("atom2", 100)
    assert payload["gsd_cm"] == pytest.approx(3.5556, abs=1e-3)
    with pytest.raises(ValueError, match="drone desconhecido"):
        service.camera_payload("nope", 100)


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("trunc.kml", b"<kml><oops"),
        ("fake.kmz", b"this is not a zip"),
        ("nullgeom.geojson", b'{"type":"Feature","properties":{},"geometry":null}'),
        ("bare.geojson", b'{"type":"Polygon"}'),
        (
            "empty.kml",
            b"<kml xmlns='http://www.opengis.net/kml/2.2'><Placemark><Polygon/></Placemark></kml>",
        ),
        ("garbage.json", b"\xff\xfe\x00 not json"),
    ],
)
def test_a_malformed_upload_is_a_value_error_not_a_crash(name, data):
    with pytest.raises(ValueError):
        service.import_payload(name, data)


def test_an_oversized_upload_is_refused_before_it_is_parsed():
    with pytest.raises(ValueError, match="MB"):
        service.import_payload("big.geojson", b" " * (service.MAX_IMPORT_BYTES + 1))


@pytest.mark.parametrize("mode", ["waypoints", "corridor", "facade"])
def test_a_polygon_where_a_line_is_needed_is_a_value_error(mode):
    with pytest.raises(ValueError, match="esperava uma linha"):
        service.build_mission(request(mode=mode), flat)


def test_the_service_imports_without_pillow_and_the_export_just_drops_the_picture():
    import subprocess
    import sys

    code = (
        "import sys; sys.modules['PIL'] = None\n"
        "from maps4drone import service\n"
        "from maps4drone.service import PlanRequest\n"
        "area = {'type':'Polygon','coordinates':[[[-51.9,-23.15],[-51.8964,-23.15],"
        "[-51.8964,-23.1473],[-51.9,-23.1473],[-51.9,-23.15]]]}\n"
        "req = PlanRequest(mode='grid', geometry=area, params={})\n"
        "m = service.build_mission(req, lambda p: [0.0] * len(p))\n"
        "f = service.export_mission(m, lambda z, x, y: None)\n"
        "import zipfile, io; names = zipfile.ZipFile(io.BytesIO(f.data)).namelist()\n"
        "print('OK', sorted(names)[-1], any(n.endswith('.jpg') for n in names))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().startswith("OK") and out.stdout.strip().endswith("False")
