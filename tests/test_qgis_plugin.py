import configparser
import importlib.util
import os
import sys
import zipfile
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Polygon

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "qgis_plugin" / "maps4drone_qgis"
sys.path.insert(0, str(ROOT / "qgis_plugin"))

from maps4drone_qgis import geometry  # noqa: E402

from maps4drone import __version__  # noqa: E402
from maps4drone.model import Mission, Waypoint  # noqa: E402
from maps4drone.stats import estimate  # noqa: E402


def _build_module():
    spec = importlib.util.spec_from_file_location(
        "build_qgis_plugin", ROOT / "scripts" / "build_qgis_plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SHELL = [(-51.9, -23.1), (-51.8, -23.1), (-51.8, -23.0), (-51.9, -23.1)]
SQUARE = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]
HOLE = [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]


def test_polygons_from_rings_single_and_multi():
    single = geometry.polygons_from_rings([[SQUARE]])
    assert isinstance(single, Polygon) and single.area == 16
    multi = geometry.polygons_from_rings([[SQUARE], [[(x + 10, y) for x, y in SQUARE]]])
    assert isinstance(multi, MultiPolygon) and multi.area == 32


def test_polygons_keep_holes_and_skip_degenerate():
    poly = geometry.polygons_from_rings([[SQUARE, HOLE], [[(0, 0), (1, 1)]], []])
    assert isinstance(poly, Polygon) and poly.area == 15


def test_polygons_need_one_valid_ring():
    with pytest.raises(ValueError, match="no polygon"):
        geometry.polygons_from_rings([[[(0, 0), (1, 1)]]])


def test_first_line():
    assert geometry.first_line([[(0, 0)], [(1, 2), (3, 4)]]) == [(1.0, 2.0), (3.0, 4.0)]
    with pytest.raises(ValueError, match="no line"):
        geometry.first_line([[(0, 0)]])


@pytest.fixture
def mission(atom2):
    wps = [
        Waypoint(-23.1, -51.9, 100.0, yaw=None),
        Waypoint(
            -23.2, -51.8, 80.0, gimbal_pitch=-45, yaw=90, speed=3.0, action="PHOTO", hover_time=1
        ),
    ]
    return Mission(drone=atom2, waypoints=wps, speed_ms=5.0, shoot_interval_s=3.0, area_m2=20000)


def test_waypoint_rows_match_declared_fields(mission):
    rows = geometry.waypoint_rows(mission)
    assert all(len(r) == len(geometry.WAYPOINT_FIELDS) for r in rows)
    assert rows[0] == (1, -23.1, -51.9, 100.0, 5.0, -90.0, None, "NONE", 0)
    assert rows[1][4] == 3.0 and rows[1][6] == 90 and rows[1][7] == "PHOTO"


def test_route_row_and_coords(mission):
    stats = estimate(mission)
    row = geometry.route_row(mission, stats)
    assert len(row) == len(geometry.ROUTE_FIELDS)
    assert row[0] == 2 and row[3] == 5.0 and row[5] == pytest.approx(2.0)
    assert geometry.route_coords(mission) == [(-51.9, -23.1), (-51.8, -23.2)]


def test_summary_text_has_timer_reminder_and_warnings(mission):
    mission.warnings.append("too high")
    text = geometry.summary_text(mission, estimate(mission))
    assert "camera timer to 3 s" in text
    assert "WARNING   : too high" in text
    assert "area      : 2.00 ha" in text


def test_metadata_has_required_keys():
    meta = configparser.ConfigParser()
    meta.read(PLUGIN_DIR / "metadata.txt")
    general = meta["general"]
    for key in (
        "name",
        "qgisMinimumVersion",
        "description",
        "version",
        "author",
        "email",
        "about",
        "tracker",
        "repository",
        "supportsQt6",
        "icon",
    ):
        assert general.get(key), key
    assert general["name"] == "maps4drone"
    assert general["qgisMinimumVersion"] == "3.28"
    assert general["supportsQt6"] == "True"
    assert (PLUGIN_DIR / general["icon"]).is_file()
    assert (PLUGIN_DIR / "LICENSE").read_text().startswith("MIT License")


def test_plugin_sources_use_only_qgis_pyqt():
    for path in PLUGIN_DIR.glob("*.py"):
        text = path.read_text()
        assert "PyQt5" not in text and "from PyQt" not in text, path.name


def test_build_zip_layout(tmp_path):
    target = _build_module().build(tmp_path)
    assert target.name == f"maps4drone-qgis-{__version__}.zip"
    with zipfile.ZipFile(target) as z:
        names = set(z.namelist())
        for expected in (
            "maps4drone_qgis/metadata.txt",
            "maps4drone_qgis/__init__.py",
            "maps4drone_qgis/plugin.py",
            "maps4drone_qgis/algorithms.py",
            "maps4drone_qgis/provider.py",
            "maps4drone_qgis/dialog.py",
            "maps4drone_qgis/icon.svg",
            "maps4drone_qgis/LICENSE",
            "maps4drone_qgis/vendor/maps4drone/__init__.py",
            "maps4drone_qgis/vendor/maps4drone/atom2.py",
            "maps4drone_qgis/vendor/maps4drone/drones.json",
            "maps4drone_qgis/vendor/maps4drone/planners/survey.py",
        ):
            assert expected in names, expected
        assert not any("/vendor/maps4drone/web/" in n for n in names)
        assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
        meta = configparser.ConfigParser()
        meta.read_string(z.read("maps4drone_qgis/metadata.txt").decode())
        assert meta["general"]["version"] == __version__


def test_built_zip_core_imports_in_isolation(tmp_path):
    """The vendored core must be importable on its own from the zip's vendor dir."""
    import subprocess

    target = _build_module().build(tmp_path)
    extract = tmp_path / "x"
    with zipfile.ZipFile(target) as z:
        z.extractall(extract)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import maps4drone, maps4drone.cli;"
        "from maps4drone.camera import load_drones; print(maps4drone.__file__, list(load_drones()))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code, str(extract / "maps4drone_qgis" / "vendor")],
        env={"PYTHONPATH": os.pathsep.join(p for p in sys.path if p)},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "vendor" in out and "atom2" in out


def test_ensure_core_reports_missing_module(monkeypatch):
    from maps4drone_qgis import _deps

    real_import = _deps.importlib.import_module

    def fake(name):
        if name == "shapely":
            raise ImportError("No module named 'shapely'")
        return real_import(name)

    monkeypatch.setattr(_deps.importlib, "import_module", fake)
    message = _deps.ensure_core()
    assert message and "shapely" in message and "pip install" in message


def test_ensure_core_ok_here():
    from maps4drone_qgis import _deps

    assert _deps.ensure_core() is None


def test_ensure_core_old_python(monkeypatch):
    from maps4drone_qgis import _deps

    monkeypatch.setattr(_deps.sys, "version_info", (3, 8, 0))
    assert "3.9" in _deps.ensure_core()


@pytest.fixture(scope="module")
def qgis_env():
    """Headless QGIS with the maps4drone provider registered. Skipped without qgis."""
    pytest.importorskip("qgis.core")
    from qgis.core import QgsApplication

    app = QgsApplication([], False)
    app.initQgis()
    sys.path.append(f"{QgsApplication.pkgDataPath()}/python/plugins")
    from maps4drone_qgis.provider import Maps4DroneProvider
    from processing.core.Processing import Processing

    Processing.initialize()
    provider = Maps4DroneProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    yield
    registry = QgsApplication.processingRegistry()
    if registry.providerById("maps4drone") is not None:
        registry.removeProvider(registry.providerById("maps4drone"))
    app.exitQgis()


def _area_layer():
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "area", "memory")
    feature = QgsFeature()
    feature.setGeometry(
        QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(-51.9000, -23.1500),
                    QgsPointXY(-51.8964, -23.1500),
                    QgsPointXY(-51.8964, -23.1473),
                    QgsPointXY(-51.9000, -23.1473),
                ]
            ]
        )
    )
    layer.dataProvider().addFeature(feature)
    return layer


def test_survey_grid_in_qgis(qgis_env, tmp_path):
    import processing

    result = processing.run(
        "maps4drone:survey_grid",
        {
            "INPUT": _area_layer(),
            "ANGLE": 35,
            "OUTPUT_LINES": "memory:",
            "OUTPUT_POINTS": "memory:",
            "MISSION_DIR": str(tmp_path / "mission"),
        },
    )
    assert result["OUTPUT_POINTS"].featureCount() > 4
    assert result["OUTPUT_LINES"].featureCount() == 1
    folder = Path(result["MISSION_FOLDER"])
    assert (folder / "global.json").is_file() and (folder / f"{folder.name}.json").is_file()
    assert "camera timer" in result["SUMMARY"]


def test_survey_grid_reprojects_input(qgis_env):
    import processing

    projected = processing.run(
        "native:reprojectlayer",
        {"INPUT": _area_layer(), "TARGET_CRS": "EPSG:31982", "OUTPUT": "memory:"},
    )["OUTPUT"]
    assert projected.crs().authid() == "EPSG:31982"
    out = processing.run(
        "maps4drone:survey_grid",
        {"INPUT": projected, "OUTPUT_LINES": "memory:", "OUTPUT_POINTS": "memory:"},
    )
    first = next(out["OUTPUT_POINTS"].getFeatures())
    assert -51.91 < first["lng"] < -51.89 and -23.16 < first["lat"] < -23.14


def test_replace_existing_dummy_folder(qgis_env, tmp_path):
    import processing

    dummy = tmp_path / "1790000000000"
    dummy.mkdir()
    (dummy / "global.json").write_text("{}")
    (dummy / "1790000000000.json").write_text("[]")
    result = processing.run(
        "maps4drone:survey_grid",
        {
            "INPUT": _area_layer(),
            "REPLACE_DIR": str(dummy),
            "OUTPUT_LINES": "memory:",
            "OUTPUT_POINTS": "memory:",
        },
    )
    assert Path(result["MISSION_FOLDER"]) == dummy
    assert (dummy / "1790000000000.json").read_text().startswith('[{"action"')


def test_terrain_following_with_dem(qgis_env, tmp_path):
    gdal = pytest.importorskip("osgeo.gdal")
    osr = pytest.importorskip("osgeo.osr")
    import processing
    from qgis.core import QgsProcessingException

    dem = tmp_path / "dem.tif"
    ds = gdal.GetDriverByName("GTiff").Create(str(dem), 100, 100, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((-51.91, 0.0002, 0, -23.14, 0, -0.0002))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    rows = [[700.0 + 0.5 * r] * 100 for r in range(100)]  # ground falls toward the south
    import numpy as np

    ds.GetRasterBand(1).WriteArray(np.array(rows, dtype="float32"))
    ds.FlushCache()
    ds = None

    params = {
        "INPUT": _area_layer(),
        "DEM": str(dem),
        "TAKEOFF": "-51.9,-23.1473 [EPSG:4326]",
        "OUTPUT_LINES": "memory:",
        "OUTPUT_POINTS": "memory:",
    }
    out = processing.run("maps4drone:survey_grid", params)
    heights = [f["height"] for f in out["OUTPUT_POINTS"].getFeatures()]
    assert max(heights) - min(heights) > 5  # rises as the ground rises relative to takeoff
    assert out["OUTPUT_POINTS"].featureCount() > 20  # densified at the terrain step

    del params["TAKEOFF"]
    with pytest.raises(QgsProcessingException, match="takeoff"):
        processing.run("maps4drone:survey_grid", params, is_child_algorithm=False)


def test_core_errors_become_processing_errors(qgis_env):
    import processing
    from qgis.core import QgsProcessingException

    with pytest.raises(QgsProcessingException, match="interval"):
        processing.run(
            "maps4drone:survey_grid",
            {
                "INPUT": _area_layer(),
                "INTERVAL": 1,
                "OUTPUT_LINES": "memory:",
                "OUTPUT_POINTS": "memory:",
            },
        )


def test_corridor_orbit_facade_in_qgis(qgis_env):
    import processing
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

    line = QgsVectorLayer("LineString?crs=EPSG:4326", "axis", "memory")
    axis = QgsFeature()
    axis.setGeometry(
        QgsGeometry.fromPolylineXY([QgsPointXY(-51.90, -23.15), QgsPointXY(-51.89, -23.14)])
    )
    line.dataProvider().addFeature(axis)
    sinks = {"OUTPUT_LINES": "memory:", "OUTPUT_POINTS": "memory:"}
    corridor = processing.run("maps4drone:corridor", {"INPUT": line, "LINES": 3, **sinks})
    assert corridor["OUTPUT_POINTS"].featureCount() == 6

    orbit = processing.run(
        "maps4drone:orbit",
        {"CENTER": "-51.9,-23.15 [EPSG:4326]", "RADIUS": 40, "HEIGHT": 40, "POINTS": 8, **sinks},
    )
    assert orbit["OUTPUT_POINTS"].featureCount() == 8

    facade = processing.run(
        "maps4drone:facade",
        {
            "BASE_A": "-51.9,-23.15 [EPSG:4326]",
            "BASE_B": "-51.8995,-23.15 [EPSG:4326]",
            "WALL_HEIGHT": 20,
            **sinks,
        },
    )
    assert facade["OUTPUT_POINTS"].featureCount() > 1


class _StubIface:
    def __init__(self):
        self.calls = []
        self.warnings = []

    def mainWindow(self):
        return None

    def addPluginToMenu(self, menu, action):
        self.calls.append(("menu", menu))

    def removePluginMenu(self, menu, action):
        self.calls.append(("unmenu", menu))

    def addToolBarIcon(self, action):
        self.calls.append(("toolbar",))

    def removeToolBarIcon(self, action):
        self.calls.append(("untoolbar",))

    def messageBar(self):
        outer = self

        class Bar:
            def pushWarning(self, title, text):
                outer.warnings.append((title, text))

        return Bar()


# keep last: it unregisters the provider the other tests rely on
def test_plugin_gui_lifecycle_and_missing_deps_message(qgis_env, monkeypatch):
    import maps4drone_qgis
    import maps4drone_qgis.plugin as plugin_module
    from qgis.core import QgsApplication

    registry = QgsApplication.processingRegistry()
    registry.removeProvider(registry.providerById("maps4drone"))
    iface = _StubIface()
    plugin = maps4drone_qgis.classFactory(iface)
    plugin.initGui()
    assert plugin.problem is None and plugin.provider is not None
    assert registry.providerById("maps4drone") is not None
    assert ("menu", "&maps4drone") in iface.calls and ("toolbar",) in iface.calls
    plugin.unload()
    assert registry.providerById("maps4drone") is None
    assert ("unmenu", "&maps4drone") in iface.calls

    monkeypatch.setattr(plugin_module, "ensure_core", lambda: "Could not import 'shapely'")
    broken_iface = _StubIface()
    broken = plugin_module.Maps4DronePlugin(broken_iface)
    broken.initGui()
    assert broken.provider is None and broken_iface.warnings
    shown = []
    monkeypatch.setattr(plugin_module.QMessageBox, "critical", lambda *a: shown.append(a[2]))
    broken.run()
    assert shown == ["Could not import 'shapely'"]
    broken.unload()


def test_algorithms_run_on_the_main_thread(qgis_env):
    from qgis.core import Qgis, QgsApplication

    for alg in QgsApplication.processingRegistry().providerById("maps4drone").algorithms():
        assert alg.flags() & Qgis.ProcessingAlgorithmFlag.NoThreading
