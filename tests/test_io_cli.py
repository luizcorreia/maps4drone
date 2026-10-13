import json
import zipfile

import pytest

from maps4drone.cli import main
from maps4drone.io import read_area, read_line

KML = """<?xml version="1.0"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon>
<outerBoundaryIs><LinearRing><coordinates>
-51.9000,-23.1500,0 -51.8964,-23.1500,0 -51.8964,-23.1473,0 -51.9000,-23.1473,0 -51.9000,-23.1500,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><LineString>
<coordinates>-51.9,-23.15 -51.89,-23.14</coordinates>
</LineString></Placemark>
</Document></kml>"""


def test_read_kml_kmz_geojson(tmp_path):
    kml = tmp_path / "a.kml"
    kml.write_text(KML)
    kmz = tmp_path / "a.kmz"
    with zipfile.ZipFile(kmz, "w") as z:
        z.writestr("doc.kml", KML)
    gj = tmp_path / "a.geojson"
    gj.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-51.9, -23.15],
                                    [-51.8964, -23.15],
                                    [-51.8964, -23.1473],
                                    [-51.9, -23.15],
                                ]
                            ],
                        },
                    }
                ],
            }
        )
    )
    areas = [read_area(p).area for p in (kml, kmz, gj)]
    assert all(a > 0 for a in areas)
    assert read_line(kml) == [(-51.9, -23.15), (-51.89, -23.14)]


def test_unsupported_and_empty(tmp_path):
    bad = tmp_path / "a.txt"
    bad.write_text("x")
    with pytest.raises(ValueError, match="unsupported"):
        read_area(bad)
    empty = tmp_path / "e.geojson"
    empty.write_text('{"type":"Point","coordinates":[0,0]}')
    with pytest.raises(ValueError, match="no polygon"):
        read_area(empty)


def test_cli_grid_end_to_end(tmp_path, capsys):
    kml = tmp_path / "a.kml"
    kml.write_text(KML)
    out = tmp_path / "out"
    assert main(["grid", str(kml), "--out", str(out), "--angle", "35"]) == 0
    text = capsys.readouterr().out
    assert "set the app camera timer to 3 s" in text
    folder = next(p for p in out.iterdir() if p.is_dir())
    assert len(json.loads((folder / f"{folder.name}.json").read_text())) > 4
    assert json.loads((out / "preview.geojson").read_text())["type"] == "FeatureCollection"


def test_cli_errors(tmp_path, capsys):
    kml = tmp_path / "a.kml"
    kml.write_text(KML)
    assert main(["grid", str(kml), "--out", str(tmp_path), "--terrain"]) == 1
    assert "takeoff" in capsys.readouterr().err
    assert main(["grid", str(kml), "--out", str(tmp_path), "--interval", "1"]) == 1
    assert main(["grid", str(kml), "--drone", "nope", "--out", str(tmp_path)]) == 1


def test_cli_orbit_facade_drones(tmp_path, capsys):
    assert main(["drones"]) == 0
    assert "Potensic Atom 2" in capsys.readouterr().out
    assert (
        main(
            [
                "orbit",
                "--center=-23.15,-51.9",
                "--radius",
                "30",
                "--height",
                "30",
                "--out",
                str(tmp_path / "o"),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "facade",
                "--base-a=-23.15,-51.9",
                "--base-b=-23.15,-51.899",
                "--wall-height",
                "15",
                "--out",
                str(tmp_path / "f"),
            ]
        )
        == 0
    )
