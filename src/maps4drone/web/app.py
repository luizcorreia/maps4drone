"""Web API and static UI for planning missions in the browser."""

import argparse
import io
import tempfile
import time
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from shapely.errors import ShapelyError
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

from .. import atom2
from ..camera import Drone, load_drones
from ..elevation import Elevation, open_meteo_elevation
from ..io import read_area, read_line
from ..model import Mission, Waypoint
from ..planners.common import finish
from ..planners.corridor import plan_corridor
from ..planners.facade import plan_facade
from ..planners.orbit import plan_orbit
from ..planners.survey import SurveyParams, plan_survey
from ..stats import estimate

STATIC = Path(__file__).parent / "static"
DRONES = load_drones()

Mode = Literal["waypoints", "grid", "double_grid", "corridor", "orbit", "facade"]

EXPORT_README = """maps4drone - missao para o Potensic Atom 2

O app Potensic Eve so reconhece missoes que ele mesmo criou. Para usar estes arquivos:

1. No Potensic Eve, crie e salve uma missao qualquer (a "dummy").
2. No celular, abra Android/data/com.ipotensic.atom/files/Waypoint/<id>/
3. Substitua global.json e <id>.json dessa pasta por estes dois arquivos,
   RENOMEANDO o arquivo de waypoints para o mesmo nome do arquivo original.
4. Abra a missao no app, confira a rota, configure o temporizador de fotos
   para o intervalo indicado no planejamento e voe com seguranca.
"""


class Params(BaseModel):
    drone: str = "atom2"
    camera: str | None = None
    altitude: float = Field(default=100, gt=0, le=500, description="height (m); orbit height too")
    front: float = Field(default=80, ge=0, lt=100, description="front overlap, %")
    side: float = Field(default=70, ge=0, lt=100, description="side overlap, %")
    angle: float = Field(default=0, ge=0, lt=360, description="flight line bearing, 0 = north")
    interval: float = 3
    pitch: float = Field(default=-90, ge=-90, le=20)
    margin: float = Field(default=0, ge=0, le=200)
    speed: float = Field(default=5, gt=0, description="m/s for waypoints, orbit and facade")
    terrain: bool = False
    takeoff: tuple[float, float] | None = Field(default=None, description="[lng, lat]")
    terrain_step: float = Field(default=30, ge=5, le=200)
    lines: int = Field(default=3, ge=1, le=15)
    radius: float = Field(default=40, gt=0, le=1000)
    points: int = Field(default=12, ge=3, le=200)
    target_height: float = 0
    photo_each: bool = False
    wall_height: float = Field(default=20, gt=0, le=500)
    standoff: float = Field(default=15, gt=0, le=200)
    wall_side: Literal["left", "right"] = "left"


class PlanRequest(BaseModel):
    mode: Mode
    geometry: dict[str, Any] | None = None
    params: Params = Field(default_factory=Params)


app = FastAPI(title="maps4drone")


@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def get_elevation() -> Elevation:
    return open_meteo_elevation()


def _geometry(req: PlanRequest) -> BaseGeometry:
    if not req.geometry:
        raise ValueError("desenhe a geometria no mapa")
    try:
        return shape(req.geometry)
    except (KeyError, TypeError, ValueError, ShapelyError) as err:
        raise ValueError(f"geometria invalida: {err}") from err


def _lines(geom: BaseGeometry, minimum: int) -> list[tuple[float, float]]:
    coords = [(float(c[0]), float(c[1])) for c in getattr(geom, "coords", [])]
    if len(coords) < minimum:
        raise ValueError(f"a linha precisa de pelo menos {minimum} pontos")
    return coords


def _waypoint_mission(
    drone: Drone, geom: BaseGeometry, p: Params, elevation: Elevation | None
) -> Mission:
    if geom.geom_type == "MultiPoint":
        pts = [(g.x, g.y) for g in geom.geoms]
    else:
        pts = _lines(geom, 1)
    wps = [Waypoint(lat=y, lng=x, height=p.altitude, gimbal_pitch=p.pitch) for x, y in pts]
    mission = Mission(drone=drone, waypoints=wps, speed_ms=p.speed)
    return finish(mission, p.altitude, elevation, p.takeoff, p.terrain_step)


def build_mission(req: PlanRequest, elevation: Elevation) -> Mission:
    p = req.params
    if p.drone not in DRONES:
        raise ValueError(f"drone desconhecido: {p.drone}")
    drone = DRONES[p.drone]
    camera = drone.camera(p.camera)
    geom = _geometry(req)
    survey_modes = ("waypoints", "grid", "double_grid", "corridor")
    if p.terrain and req.mode not in survey_modes:
        raise ValueError("seguir o terreno nao e suportado neste modo")
    terrain = elevation if p.terrain else None
    if terrain is not None and p.takeoff is None:
        raise ValueError("defina o ponto de decolagem para seguir o terreno")
    params = SurveyParams(
        altitude_m=p.altitude,
        front_overlap=p.front / 100,
        side_overlap=p.side / 100,
        heading_deg=p.angle,
        interval_s=p.interval,
        gimbal_pitch=p.pitch,
        margin_m=p.margin,
        double=req.mode == "double_grid",
        terrain_step_m=p.terrain_step,
    )
    if req.mode in ("grid", "double_grid"):
        if not isinstance(geom, Polygon | MultiPolygon):
            raise ValueError("a area precisa ser um poligono")
        if not geom.is_valid:
            raise ValueError("poligono invalido: as linhas se cruzam")
        mission = plan_survey(geom, drone, camera, params, terrain, p.takeoff)
    elif req.mode == "corridor":
        mission = plan_corridor(_lines(geom, 2), drone, camera, params, p.lines, terrain, p.takeoff)
    elif req.mode == "orbit":
        if geom.geom_type != "Point":
            raise ValueError("a orbita precisa de um ponto central")
        center = (geom.x, geom.y)
        mission = plan_orbit(
            drone, center, p.radius, p.altitude, p.points, p.target_height, p.speed, p.photo_each
        )
    elif req.mode == "facade":
        a, *_, b = _lines(geom, 2)
        mission = plan_facade(
            drone, camera, a, b, p.wall_height, p.standoff,
            p.front / 100, p.side / 100, p.wall_side, p.speed,
        )  # fmt: skip
    else:
        mission = _waypoint_mission(drone, geom, p, terrain)
    atom2.mission_files(mission)  # surface validation errors while planning
    return mission


def _plan_or_raise(req: PlanRequest, elevation: Elevation) -> Mission:
    try:
        return build_mission(req, elevation)
    except OSError as err:
        raise HTTPException(502, f"falha ao consultar a elevacao: {err}") from err


def _preview(mission: Mission) -> dict[str, Any]:
    route = [[w.lng, w.lat] for w in mission.waypoints]
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {"kind": "route"},
            "geometry": {"type": "LineString", "coordinates": route},
        }
    ]
    features += [
        {
            "type": "Feature",
            "properties": {"kind": "waypoint", "index": i, "height": w.height},
            "geometry": {"type": "Point", "coordinates": [w.lng, w.lat]},
        }
        for i, w in enumerate(mission.waypoints)
    ]
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/drones")
def drones() -> list[dict[str, Any]]:
    return [asdict(d) for d in DRONES.values()]


@app.get("/api/camera")
def camera_info(drone: str, altitude: float, camera: str | None = None) -> dict[str, float]:
    if drone not in DRONES:
        raise ValueError(f"drone desconhecido: {drone}")
    cam = DRONES[drone].camera(camera)
    width, height = cam.footprint_m(altitude)
    return {"gsd_cm": cam.gsd_m(altitude) * 100, "footprint_w_m": width, "footprint_h_m": height}


@app.post("/api/plan")
def plan(
    req: PlanRequest, elevation: Annotated[Elevation, Depends(get_elevation)]
) -> dict[str, Any]:
    mission = _plan_or_raise(req, elevation)
    s = estimate(mission)
    return {
        "geojson": _preview(mission),
        "stats": {
            "waypoints": s.waypoints,
            "distance_m": s.distance_m,
            "duration_s": s.duration_s,
            "batteries": s.batteries,
            "images": {f"{i:g}": n for i, n in s.images.items()},
            "area_ha": s.area_ha,
        },
        "warnings": mission.warnings,
        "speed": mission.speed_ms,
        "interval": mission.shoot_interval_s,
    }


@app.post("/api/export")
def export(req: PlanRequest, elevation: Annotated[Elevation, Depends(get_elevation)]) -> Response:
    mission = _plan_or_raise(req, elevation)
    global_json, body = atom2.mission_files(mission)
    mission_id = int(time.time() * 1000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("global.json", global_json)
        z.writestr(f"{mission_id}.json", body)
        z.writestr("README.txt", EXPORT_README)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="maps4drone-{mission_id}.zip"'},
    )


@app.post("/api/import")
async def import_file(request: Request, name: str) -> dict[str, Any]:
    """Raw file body (.kml/.kmz/.geojson); returns the first polygon and/or line found."""
    suffix = Path(name).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(await request.body())
        result: dict[str, Any] = {"polygon": None, "line": None}
        try:
            result["polygon"] = mapping(read_area(path))
        except (ValueError, ShapelyError, StopIteration):
            pass
        try:
            result["line"] = {"type": "LineString", "coordinates": read_line(path)}
        except (ValueError, ShapelyError, StopIteration):
            pass
        if suffix not in (".kml", ".kmz", ".geojson", ".json"):
            raise ValueError("formato nao suportado (use .kml, .kmz ou .geojson)")
    if result["polygon"] is None and result["line"] is None:
        raise ValueError("nenhum poligono ou linha encontrado no arquivo")
    return result


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(prog="maps4drone-web")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
