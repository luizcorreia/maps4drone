import ast
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


def test_task_info_says_whether_the_photo_positions_exist(logic):
    info = logic.task_info("t", 1, "x", None, ["shots.geojson"])
    assert info["assets"]["shots"] is True
    assert info["extent"] is None


def test_task_info_tells_the_page_what_it_can_use(logic):
    info = logic.task_info(
        "t1", 7, "Fazenda", [-51.9, -23.1, -51.8, -23.0], ["orthophoto.tif", "dsm.tif"]
    )
    assert info["assets"] == {"orthophoto": True, "dsm": True, "dtm": False, "shots": False}
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


def test_webodm_can_find_the_plugin_class():
    """WebODM does getattr(import_module("plugins.<dir>"), "Plugin"): the package must export it."""
    assert (PLUGIN / "__init__.py").read_text().startswith("from .plugin import *")
    tree = ast.parse((PLUGIN / "plugin.py").read_text())
    classes = {
        n.name: [b.id for b in n.bases if isinstance(b, ast.Name)]
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef)
    }
    assert classes == {"Plugin": ["PluginBase"]}


def test_the_manifest_has_nothing_that_could_hide_the_plugin():
    """A webodmMinVersion above the running WebODM makes it skip the plugin without a word."""
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert "webodmMinVersion" not in manifest
    assert {"name", "version", "description"} <= set(manifest)


# ---- saved flight plans ----------------------------------------------------------------------


class FakeStore:
    """The slice of the plugin data store the plans use, kept in a dict of JSON values."""

    def __init__(self):
        self.data = {}

    def get_json(self, key, default=None):
        return json.loads(json.dumps(self.data.get(key, default)))  # a copy, as a database gives

    def set_json(self, key, value):
        self.data[key] = json.loads(json.dumps(value))

    def del_key(self, key):
        self.data.pop(key, None)

    def items(self, prefix):
        return [self.get_json(k) for k in self.data if k.startswith(prefix)]


def pid(n):
    """A plan id as the server makes them: 32 hex digits."""
    return f"{n:032x}"


def plan_body(name="Chácara norte", **overrides):
    request = {
        "mode": "grid",
        "geometry": AREA,
        "params": {"drone": "atom2", "altitude": 60},
        "ignored": "not kept",
    }
    return {"name": name, "request": {**request, **overrides}}


@pytest.fixture
def store():
    return FakeStore()


def test_a_saved_plan_keeps_what_the_planner_reads(logic, store):
    plan = logic.save_plan(store, 4, plan_body(), "luiz", "2026-10-18T10:00:00+00:00", pid(1))
    assert plan["id"] == pid(1) and plan["name"] == "Chácara norte"
    assert plan["status"] == "planned" and plan["task_id"] is None
    assert plan["created_by"] == plan["updated_by"] == "luiz"
    assert set(plan["request"]) == {"mode", "geometry", "params"}  # junk is dropped
    assert logic.list_plans(store, 4) == [plan]
    assert logic.list_plans(store, 5) == []  # another project's plans are another set
    assert list(store.data) == [f"plan:4:{pid(1)}"]  # one key per plan


def test_two_saves_at_once_cannot_overwrite_each_others_plan(logic, store):
    """Each plan has a key of its own, so the second save cannot rewrite the first one."""
    logic.save_plan(store, 4, plan_body("A"), "ana", "2026-10-18T10:00:00+00:00", pid(1))
    logic.save_plan(store, 4, plan_body("B"), "bia", "2026-10-18T10:00:00+00:00", pid(2))
    logic.link_plan(store, 4, pid(1), "5b0b5a54-0000-4000-8000-000000000001", "t", "ana")
    names = sorted((p["name"], p["status"]) for p in logic.list_plans(store, 4))
    assert names == [("A", "flown"), ("B", "planned")]


def test_the_most_recently_changed_plan_comes_first(logic, store):
    logic.save_plan(store, 4, plan_body("A"), "ana", "2026-10-18T10:00:00+00:00", pid(1))
    logic.save_plan(store, 4, plan_body("B"), "ana", "2026-10-18T11:00:00+00:00", pid(2))
    assert [p["name"] for p in logic.list_plans(store, 4)] == ["B", "A"]
    renamed = {**plan_body("A bis"), "id": pid(1)}
    logic.save_plan(store, 4, renamed, "ana", "2026-10-18T12:00:00+00:00", pid(3))
    assert [p["name"] for p in logic.list_plans(store, 4)] == ["A bis", "B"]


def test_updating_a_plan_keeps_its_origin_and_task_link(logic, store):
    logic.save_plan(store, 4, plan_body(), "ana", "2026-10-18T10:00:00+00:00", pid(1))
    logic.link_plan(store, 4, pid(1), "task-1", "2026-10-18T11:00:00+00:00", "ana")
    body = {**plan_body("Renomeado"), "id": pid(1)}
    updated = logic.save_plan(store, 4, body, "bia", "2026-10-18T12:00:00+00:00", pid(9))
    assert updated["id"] == pid(1) and updated["name"] == "Renomeado"
    assert updated["created_by"] == "ana" and updated["updated_by"] == "bia"
    assert updated["created_at"] == "2026-10-18T10:00:00+00:00"
    assert updated["task_id"] == "task-1" and updated["status"] == "flown"
    assert len(logic.list_plans(store, 4)) == 1


def test_a_plan_must_have_a_name_and_a_drawn_geometry(logic, store):
    save = lambda body: logic.save_plan(store, 4, body, "ana", "t", pid(1))  # noqa: E731
    with pytest.raises(ValueError, match="nome"):
        save(plan_body("   "))
    with pytest.raises(ValueError, match="120"):
        save(plan_body("x" * 121))
    with pytest.raises(ValueError, match="desenhe"):
        save({"name": "Vazio", "request": {"mode": "grid", "params": {}}})
    with pytest.raises(ValueError, match="front"):
        save(plan_body(params={"front": 150}))
    with pytest.raises(ValueError, match="pedido"):
        save({"name": "Sem pedido"})
    with pytest.raises(ValueError):
        save("not an object")
    assert logic.list_plans(store, 4) == []  # nothing half-saved


def test_a_huge_plan_is_refused(logic, store):
    big = {"type": "MultiPoint", "coordinates": [[-51.9 + i * 1e-6, -23.1] for i in range(12_000)]}
    body = plan_body(mode="waypoints", geometry=big)
    with pytest.raises(ValueError, match="grande demais"):
        logic.save_plan(store, 4, body, "ana", "t", pid(1))


def test_a_project_has_a_limit_of_plans(logic, store):
    for i in range(logic.MAX_PLANS_PER_PROJECT):
        logic.save_plan(store, 4, plan_body(f"P{i}"), "ana", f"t{i:04d}", pid(i + 1))
    with pytest.raises(ValueError, match="apague"):
        logic.save_plan(store, 4, plan_body("one too many"), "ana", "t9999", pid(999))
    # updating an existing one is still fine at the limit
    logic.save_plan(store, 4, {**plan_body("renamed"), "id": pid(1)}, "ana", "t9999", pid(999))


def test_updating_a_plan_that_is_gone_says_so(logic, store):
    with pytest.raises(logic.PlanNotFound):
        logic.save_plan(store, 4, {**plan_body(), "id": pid(7)}, "ana", "t", pid(1))


def test_an_id_that_is_not_one_of_ours_never_reaches_the_store(logic, store):
    """The id comes from the client: a key like "plan:4:x:y" or a path must not be buildable."""
    store.data["plan:5:" + pid(1)] = {"id": pid(1)}  # another project's plan
    for evil in ("../5/" + pid(1), "x:y", pid(1)[:-1], pid(1).upper(), "", "a" * 33):
        with pytest.raises(logic.PlanNotFound):
            logic.delete_plan(store, 4, evil)
        with pytest.raises(logic.PlanNotFound):
            logic.link_plan(store, 4, evil, None, "t", "ana")
    assert "plan:5:" + pid(1) in store.data  # untouched


def test_deleting_removes_only_that_plan(logic, store):
    logic.save_plan(store, 4, plan_body("A"), "ana", "t1", pid(1))
    logic.save_plan(store, 4, plan_body("B"), "ana", "t2", pid(2))
    logic.delete_plan(store, 4, pid(1))
    assert [p["id"] for p in logic.list_plans(store, 4)] == [pid(2)]
    with pytest.raises(logic.PlanNotFound):
        logic.delete_plan(store, 4, pid(1))


def test_linking_a_task_marks_the_plan_flown_and_unlinking_undoes_it(logic, store):
    logic.save_plan(store, 4, plan_body(), "ana", "t1", pid(1))
    flown = logic.link_plan(store, 4, pid(1), "task-9", "t2", "bia")
    assert (flown["status"], flown["task_id"], flown["updated_by"]) == ("flown", "task-9", "bia")
    assert logic.list_plans(store, 4)[0]["task_id"] == "task-9"
    planned = logic.link_plan(store, 4, pid(1), None, "t3", "bia")
    assert (planned["status"], planned["task_id"]) == ("planned", None)
    with pytest.raises(logic.PlanNotFound):
        logic.link_plan(store, 4, pid(5), "task-9", "t4", "bia")


def test_stray_values_under_the_prefix_do_not_break_the_list(logic, store):
    logic.save_plan(store, 4, plan_body(), "ana", "t1", pid(1))
    store.data["plan:4:" + pid(2)] = {"not": "a plan"}
    store.data["plan:4:" + pid(3)] = "garbage"
    assert [p["id"] for p in logic.list_plans(store, 4)] == [pid(1)]
