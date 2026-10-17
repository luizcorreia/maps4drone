import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "webodm_plugin" / "maps4drone"
rasterio = pytest.importorskip("rasterio")

import numpy as np  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from tests.test_service import AREA  # noqa: E402

from maps4drone import service  # noqa: E402


def load(name: str, path: Path):
    """Load a file of the plugin on its own: its package name would shadow the core's."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def logic():
    return load("plugin_logic", PLUGIN / "logic.py")


@pytest.fixture
def dsm(tmp_path):
    """A DSM over the test area that rises 1 m per 0.00001 deg of longitude eastwards."""
    west, north, size = -51.905, -23.14, 0.00005
    cols = 300
    data = np.tile(700 + np.arange(cols, dtype="float32") * 5 * size / 0.00005 / 5, (250, 1))
    path = tmp_path / "dsm.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=250, width=cols, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(west, north, size, size), nodata=-9999.0,
    ) as ds:  # fmt: skip
        ds.write(data, 1)
    return str(path)


def test_the_plan_body_keeps_the_dem_choice_apart(logic):
    req, layer = logic.parse_plan_body(
        {"mode": "grid", "geometry": AREA, "params": {"terrain": True}, "dem": {"layer": "DTM"}}
    )
    assert layer == "dtm" and req.params.terrain is True
    _, none = logic.parse_plan_body({"mode": "grid", "geometry": AREA})
    assert none is None


def test_bad_bodies_become_readable_errors(logic):
    with pytest.raises(ValueError, match="front"):
        logic.parse_plan_body({"mode": "grid", "geometry": AREA, "params": {"front": 150}})
    with pytest.raises(ValueError, match="desconhecido"):
        logic.parse_plan_body({"mode": "grid", "dem": {"layer": "lidar"}})
    with pytest.raises(ValueError):
        logic.parse_plan_body({"mode": "teleport"})


def test_the_task_without_the_asked_model_is_refused(logic):
    with pytest.raises(ValueError, match="nao tem DSM"):
        logic.elevation_for("dsm", ["orthophoto.tif"], lambda asset: "x")
    assert callable(logic.elevation_for(None, [], None))  # online service when no task is involved


def test_terrain_following_uses_the_tasks_dsm(logic, dsm):
    elevation = logic.elevation_for("dsm", ["dsm.tif"], lambda asset: dsm)
    req, _ = logic.parse_plan_body(
        {
            "mode": "grid",
            "geometry": AREA,
            "params": {"terrain": True, "takeoff": [-51.9, -23.15], "altitude": 60},
        }
    )
    mission = service.build_mission(req, elevation)
    heights = [w.height for w in mission.waypoints]
    assert len(set(round(h, 1) for h in heights)) > 1  # not a flat 60 m: the ground varies
    assert all(h > 0 for h in heights) or min(heights) > -50


def test_task_info_tells_the_page_what_it_can_use(logic):
    info = logic.task_info(
        "t1", 7, "Fazenda", [-51.9, -23.1, -51.8, -23.0], ["orthophoto.tif", "dsm.tif"]
    )
    assert info["assets"] == {"orthophoto": True, "dsm": True, "dtm": False}
    assert info["tiles"] == "/api/projects/7/tasks/t1/orthophoto/tiles/{z}/{x}/{y}.png"
    assert info["extent"] == [-51.9, -23.1, -51.8, -23.0]


def test_the_build_ships_the_plugin_and_the_core_without_the_web_app(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_webodm_plugin as build
    finally:
        sys.path.pop(0)
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<title>ui</title>")
    zip_path = build.build(tmp_path / "out", ui)
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("maps4drone/manifest.json"))
    assert {
        "maps4drone/plugin.py",
        "maps4drone/views.py",
        "maps4drone/logic.py",
        "maps4drone/requirements.txt",
        "maps4drone/vendor/maps4drone/service.py",
        "maps4drone/vendor/maps4drone/drones.json",
        "maps4drone/public/index.html",
        "maps4drone/public/main.js",
    } <= names
    assert not any("/web/" in n for n in names if "vendor" in n)
    assert zip_path.name == f"maps4drone-webodm-{manifest['version']}.zip"


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is needed to run the button script")
def test_the_task_button_opens_the_planner_on_that_task(tmp_path):
    runner = tmp_path / "run.js"
    runner.write_text(
        """
        const fs = require("fs");
        let callback;
        global.PluginsAPI = { Dashboard: { addTaskActionButton: (cb) => { callback = cb; } } };
        global.React = { createElement: (type, props, ...children) => ({ type, props, children }) };
        let href = null;
        global.location = { set href(v) { href = v; }, get href() { return href; } };
        eval(fs.readFileSync(process.argv[2], "utf8"));
        const withMap = callback({ task: { id: "a b", available_assets: ["dsm.tif"] } });
        withMap.props.onClick();
        const results = {
          type: withMap.type,
          href,
          without: callback({ task: { id: "x", available_assets: ["all.zip"] } }) === undefined,
          none: callback({ task: { id: "x", available_assets: null } }) === undefined,
        };
        console.log(JSON.stringify(results));
        """
    )
    out = subprocess.run(
        [NODE, str(runner), str(PLUGIN / "public" / "main.js")], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {
        "type": "button",
        "href": "/plugins/maps4drone/index.html?task=a%20b",
        "without": True,
        "none": True,
    }


def test_the_plugin_loads_its_button_script_and_guards_the_planner():
    source = (PLUGIN / "plugin.py").read_text()
    assert 'return ["main.js"]' in source
    assert "request.user.is_authenticated" in source and '.endswith("/main.js")' in source
