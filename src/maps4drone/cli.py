from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__, atom2, dji
from .camera import Drone, load_drones
from .elevation import open_meteo_elevation
from .io import read_area, read_line
from .model import Mission
from .planners.corridor import plan_corridor
from .planners.facade import plan_facade
from .planners.orbit import plan_orbit
from .planners.survey import SurveyParams, plan_survey
from .stats import estimate, format_duration


def _latlng(text: str) -> tuple[float, float]:
    lat, lng = (float(v) for v in text.split(","))
    return lng, lat  # internal order is (lon, lat)


def _survey_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--altitude", type=float, default=100, help="height above ground, m")
    p.add_argument("--front", type=float, default=80, help="front overlap, %%")
    p.add_argument("--side", type=float, default=70, help="side overlap, %%")
    p.add_argument(
        "--angle",
        type=float,
        help="flight line bearing, 0 = north (default: along the long axis of the area)",
    )
    p.add_argument("--interval", type=float, default=3, help="camera shooting interval, s")
    p.add_argument("--pitch", type=float, default=-90, help="gimbal pitch, degrees")
    p.add_argument("--terrain", action="store_true", help="follow terrain (needs --takeoff)")
    p.add_argument("--takeoff", type=_latlng, metavar="LAT,LNG", help="takeoff point")
    p.add_argument("--terrain-step", type=float, default=30, help="terrain sample spacing, m")


def _params(a: argparse.Namespace, **extra: object) -> SurveyParams:
    return SurveyParams(
        altitude_m=a.altitude,
        front_overlap=a.front / 100,
        side_overlap=a.side / 100,
        heading_deg=a.angle,
        interval_s=a.interval,
        gimbal_pitch=a.pitch,
        terrain_step_m=a.terrain_step,
        **extra,  # type: ignore[arg-type]
    )


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="maps4drone", description=__doc__)
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--drones-file", type=Path, help="custom drone catalog JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--drone", default="atom2")
        p.add_argument("--camera")
        p.add_argument("--out", type=Path, default=Path("out"), help="output directory")
        p.add_argument("--replace", type=Path, help="existing Atom 2 mission folder to overwrite")
        p.add_argument("--legacy-poi-list", action="store_true", help="append ';[]' (old firmware)")

    sub.add_parser("drones", help="list built-in drones")

    g = sub.add_parser("grid", help="survey a polygon (.kml/.kmz/.geojson)")
    g.add_argument("area", type=Path)
    g.add_argument("--double", action="store_true", help="second perpendicular pass")
    g.add_argument("--margin", type=float, default=0, help="grow the area by this many m")
    _survey_args(g)
    common(g)

    c = sub.add_parser("corridor", help="follow a line (road, rail, river)")
    c.add_argument("line", type=Path)
    c.add_argument("--lines", type=int, default=3, help="odd number of passes")
    _survey_args(c)
    common(c)

    o = sub.add_parser("orbit", help="circle a point of interest")
    o.add_argument("--center", type=_latlng, required=True, metavar="LAT,LNG")
    o.add_argument("--radius", type=float, required=True)
    o.add_argument("--height", type=float, required=True)
    o.add_argument("--points", type=int, default=12)
    o.add_argument("--target-height", type=float, default=0)
    o.add_argument("--speed", type=float, default=3)
    o.add_argument("--photo-each", action="store_true")
    common(o)

    f = sub.add_parser("facade", help="vertical grid in front of a wall")
    f.add_argument("--base-a", type=_latlng, required=True, metavar="LAT,LNG")
    f.add_argument("--base-b", type=_latlng, required=True, metavar="LAT,LNG")
    f.add_argument("--wall-height", type=float, required=True)
    f.add_argument("--standoff", type=float, default=15)
    f.add_argument("--front", type=float, default=75)
    f.add_argument("--side", type=float, default=70)
    f.add_argument("--wall-side", choices=["left", "right"], default="left")
    f.add_argument("--speed", type=float, default=1.5)
    common(f)
    return ap


def _preview(mission: Mission) -> dict[str, object]:
    coords = [[w.lng, w.lat] for w in mission.waypoints]
    features: list[dict[str, object]] = [
        {
            "type": "Feature",
            "properties": {"kind": "route"},
            "geometry": {"type": "LineString", "coordinates": coords},
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


def _report(mission: Mission) -> None:
    s = estimate(mission)
    print(f"waypoints : {s.waypoints}")
    print(f"distance  : {s.distance_m / 1000:.2f} km at {mission.speed_ms:.1f} m/s")
    print(f"duration  : ~{format_duration(s.duration_s)} ({s.batteries} battery)")
    print("images    : " + ", ".join(f"~{n} @ {i:g}s" for i, n in s.images.items()))
    if s.area_ha is not None:
        print(f"area      : {s.area_ha:.2f} ha")
    if mission.shoot_interval_s:
        print(
            f"IMPORTANT : set the app camera timer to {mission.shoot_interval_s:g} s before flying"
        )
    for w in mission.warnings:
        print(f"WARNING   : {w}", file=sys.stderr)


def _build(a: argparse.Namespace, drone_id: str, drones: dict[str, Drone]) -> Mission:
    drone = drones[drone_id]
    camera = drone.camera(a.camera)
    elevation = open_meteo_elevation() if getattr(a, "terrain", False) else None
    takeoff = getattr(a, "takeoff", None)
    if a.cmd == "grid":
        params = _params(a, double=a.double, margin_m=a.margin)
        return plan_survey(read_area(a.area), drone, camera, params, elevation, takeoff)
    if a.cmd == "corridor":
        return plan_corridor(
            read_line(a.line), drone, camera, _params(a), a.lines, elevation, takeoff
        )
    if a.cmd == "orbit":
        return plan_orbit(
            drone, a.center, a.radius, a.height, a.points, a.target_height, a.speed, a.photo_each
        )
    return plan_facade(
        drone,
        camera,
        a.base_a,
        a.base_b,
        a.wall_height,
        a.standoff,
        a.front / 100,
        a.side / 100,
        a.wall_side,
        a.speed,
    )


def _write_dji(mission: Mission, out: Path) -> Path:
    """The DJI KMZ (several, when the route needs more than one flight) next to the preview."""
    out.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    files = dji.mission_kmz(mission)
    for n, data in enumerate(files, 1):
        suffix = f"-voo{n}de{len(files)}" if len(files) > 1 else ""
        (out / f"maps4drone-{stamp}{suffix}.kmz").write_bytes(data)
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    drones = load_drones(args.drones_file)
    if args.cmd == "drones":
        for d in drones.values():
            print(f"{d.id}\t{d.name}\tcameras: {', '.join(d.cameras)}")
        return 0
    try:
        if args.drone not in drones:
            raise ValueError(f"unknown drone {args.drone!r}, have {list(drones)}")
        if getattr(args, "terrain", False) and not args.takeoff:
            raise ValueError("--terrain needs --takeoff LAT,LNG")
        mission = _build(args, args.drone, drones)
        if mission.drone.export_format == "dji":
            if args.replace:
                raise ValueError("--replace is for the Potensic Atom 2 only")
            folder = _write_dji(mission, args.out)
        elif args.replace:
            folder = atom2.replace_mission(mission, args.replace, args.legacy_poi_list)
        else:
            folder = atom2.write_mission(mission, args.out, legacy_poi_list=args.legacy_poi_list)
    except (ValueError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "preview.geojson").write_text(json.dumps(_preview(mission)))
    _report(mission)
    print(f"mission   : {folder}")
    return 0
