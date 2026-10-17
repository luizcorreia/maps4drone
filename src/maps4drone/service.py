"""Planning, export and import behind every interface, with no web framework in sight.

The FastAPI app and the WebODM plugin are thin layers over these functions. Errors the
user can fix are ValueError (HTTP 422); a failing outside service is UpstreamError (502).
The pydantic models stick to what pydantic 1 and 2 share, since WebODM still ships 1.x.
"""

import io
import tempfile
import time
import urllib.error
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field
from shapely.errors import ShapelyError
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

from . import atom2, dji, thumbnail
from .camera import Drone, load_drones
from .elevation import Elevation
from .io import read_area, read_line
from .model import Mission, Waypoint
from .planners.common import EmptyRouteError, finish
from .planners.corridor import plan_corridor
from .planners.facade import plan_facade
from .planners.orbit import plan_orbit
from .planners.survey import SurveyParams, plan_survey
from .stats import estimate

DRONES = load_drones()

Mode = Literal["waypoints", "grid", "double_grid", "corridor", "orbit", "facade"]

EXPORT_README = """maps4drone - missao para o Potensic Atom 2

O app Potensic Eve so reconhece missoes que ele mesmo criou. Para usar estes arquivos:

1. No Potensic Eve, crie e salve uma missao qualquer (a "dummy").
2. No celular, abra Android/data/com.ipotensic.atom/files/Waypoint/<id>/
3. Substitua global.json e <id>.json dessa pasta por estes dois arquivos,
   RENOMEANDO o arquivo de waypoints para o mesmo nome do arquivo original.
   Se houver task_*.jpg (a miniatura mostrada na lista de missoes), substitua
   tambem o .jpg da pasta por ele, mantendo o nome do original.
4. Abra a missao no app, confira a rota, configure o temporizador de fotos
   para o intervalo indicado no planejamento e voe com seguranca.
"""


class Params(BaseModel):
    drone: str = "atom2"
    camera: Optional[str] = None
    altitude: float = Field(default=100, gt=0, le=500, description="height (m); orbit height too")
    front: float = Field(default=80, ge=0, lt=100, description="front overlap, %")
    side: float = Field(default=70, ge=0, lt=100, description="side overlap, %")
    angle: Optional[float] = Field(
        default=None, ge=0, lt=360, description="line bearing, 0 = north; null = long axis"
    )
    interval: float = 3
    pitch: float = Field(default=-90, ge=-90, le=20)
    margin: float = Field(default=0, ge=0, le=200)
    speed: float = Field(default=5, gt=0, description="m/s for waypoints, orbit and facade")
    terrain: bool = False
    takeoff: Optional[tuple[float, float]] = Field(default=None, description="[lng, lat]")
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
    geometry: Optional[dict[str, Any]] = None
    params: Params = Field(default_factory=Params)


class UpstreamError(Exception):
    """An outside service (elevation, tiles) failed; the request itself was fine."""


@dataclass(frozen=True)
class ExportFile:
    data: bytes
    media_type: str
    filename: str


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
    drone: Drone, geom: BaseGeometry, p: Params, elevation: Optional[Elevation]
) -> Mission:
    if geom.geom_type == "MultiPoint":
        pts = [(g.x, g.y) for g in geom.geoms]
    else:
        pts = _lines(geom, 1)
    wps = [Waypoint(lat=y, lng=x, height=p.altitude, gimbal_pitch=p.pitch) for x, y in pts]
    mission = Mission(drone=drone, waypoints=wps, speed_ms=p.speed)
    return finish(mission, p.altitude, elevation, p.takeoff, p.terrain_step)


def _build(req: PlanRequest, elevation: Elevation) -> Mission:
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
        if not isinstance(geom, (Polygon, MultiPolygon)):
            raise ValueError("a area precisa ser um poligono")
        if not geom.is_valid:
            raise ValueError("poligono invalido: as linhas se cruzam")
        try:
            mission = plan_survey(geom, drone, camera, params, terrain, p.takeoff)
        except EmptyRouteError as err:
            raise ValueError(
                "a area e pequena demais para esta altura e sobreposicao: "
                "diminua a altura ou a sobreposicao lateral, ou aumente a area"
            ) from err
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
    # surface the writer's validation errors while planning, not only on export
    if drone.export_format == "dji":
        dji.mission_kmz(mission)
    else:
        atom2.mission_files(mission)
    return mission


def build_mission(req: PlanRequest, elevation: Elevation) -> Mission:
    """Plan the mission, turning an elevation service failure into UpstreamError."""
    try:
        return _build(req, elevation)
    except urllib.error.HTTPError as err:
        if err.code == 429:
            raise UpstreamError(
                "o servico de elevacao limitou as consultas: aguarde um minuto e tente de novo"
            ) from err
        raise UpstreamError(f"falha ao consultar a elevacao: {err}") from err
    except OSError as err:
        raise UpstreamError(f"falha ao consultar a elevacao: {err}") from err


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


def plan_payload(mission: Mission) -> dict[str, Any]:
    s = estimate(mission, mission.drone.shoot_intervals_s)
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


def drones_payload() -> list[dict[str, Any]]:
    return [asdict(d) for d in DRONES.values()]


def camera_payload(drone: str, altitude: float, camera: Optional[str] = None) -> dict[str, float]:
    if drone not in DRONES:
        raise ValueError(f"drone desconhecido: {drone}")
    cam = DRONES[drone].camera(camera)
    width, height = cam.footprint_m(altitude)
    return {"gsd_cm": cam.gsd_m(altitude) * 100, "footprint_w_m": width, "footprint_h_m": height}


def _thumbnail(mission: Mission, tiles: thumbnail.TileFetcher) -> Optional[bytes]:
    """The mission preview, or None when it cannot be drawn: it is only a nicety."""
    try:
        return thumbnail.render_thumbnail(mission.waypoints, tiles)
    except (ImportError, ValueError, OSError):
        return None


def export_mission(
    mission: Mission, tiles: thumbnail.TileFetcher, now_ms: Optional[int] = None
) -> ExportFile:
    """The files to take to the aircraft: a zip for the Atom 2, a KMZ (or zip of KMZ) for DJI."""
    stamp = int(time.time() * 1000) if now_ms is None else now_ms
    if mission.drone.export_format == "dji":
        files = dji.mission_kmz(mission)
        if len(files) == 1:
            return ExportFile(
                files[0], "application/vnd.google-earth.kmz", f"maps4drone-{stamp}.kmz"
            )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for n, data in enumerate(files, 1):
                z.writestr(f"maps4drone-{stamp}_voo{n}de{len(files)}.kmz", data)
        return ExportFile(buf.getvalue(), "application/zip", f"maps4drone-{stamp}-voos.zip")
    global_json, body = atom2.mission_files(mission)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("global.json", global_json)
        z.writestr(f"{stamp}.json", body)
        if (preview := _thumbnail(mission, tiles)) is not None:
            z.writestr(f"task_{stamp - 32}.jpg", preview)
        z.writestr("README.txt", EXPORT_README)
    return ExportFile(buf.getvalue(), "application/zip", f"maps4drone-{stamp}.zip")


def import_payload(name: str, data: bytes) -> dict[str, Any]:
    """Raw .kml/.kmz/.geojson bytes -> the first polygon and/or line found."""
    suffix = Path(name).suffix.lower()
    if suffix not in (".kml", ".kmz", ".geojson", ".json"):
        raise ValueError("formato nao suportado (use .kml, .kmz ou .geojson)")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        result: dict[str, Any] = {"polygon": None, "line": None}
        try:
            result["polygon"] = mapping(read_area(path))
        except (ValueError, ShapelyError, StopIteration):
            pass
        try:
            result["line"] = {"type": "LineString", "coordinates": read_line(path)}
        except (ValueError, ShapelyError, StopIteration):
            pass
    if result["polygon"] is None and result["line"] is None:
        raise ValueError("nenhum poligono ou linha encontrado no arquivo")
    return result
