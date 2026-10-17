from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiPolygon, Polygon

LonLat = tuple[float, float]


def _kml_coords(text: str) -> list[LonLat]:
    pts = []
    for token in text.split():
        lon, lat, *_ = token.split(",")
        pts.append((float(lon), float(lat)))
    return pts


def _load_kml(data: bytes) -> tuple[list[Polygon], list[LineString]]:
    root = ET.fromstring(data)
    polygons: list[Polygon] = []
    lines: list[LineString] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "Polygon":
            rings = [
                _kml_coords(c.text or "")
                for c in el.iter()
                if c.tag.rsplit("}", 1)[-1] == "coordinates"
            ]
            polygons.append(Polygon(rings[0], rings[1:]))
        elif tag == "LineString":
            coords = next(c for c in el.iter() if c.tag.rsplit("}", 1)[-1] == "coordinates")
            lines.append(LineString(_kml_coords(coords.text or "")))
    return polygons, lines


def _geojson_geometries(obj: dict[str, Any]) -> list[dict[str, Any]]:
    kind = obj.get("type")
    if kind == "FeatureCollection":
        return [g for f in obj["features"] for g in _geojson_geometries(f)]
    if kind == "Feature":
        return _geojson_geometries(obj["geometry"])
    if kind == "GeometryCollection":
        return [g for sub in obj["geometries"] for g in _geojson_geometries(sub)]
    return [obj]


def _load_geojson(data: bytes) -> tuple[list[Polygon], list[LineString]]:
    polygons: list[Polygon] = []
    lines: list[LineString] = []
    for g in _geojson_geometries(json.loads(data)):
        c = g["coordinates"]
        if g["type"] == "Polygon":
            polygons.append(Polygon([p[:2] for p in c[0]], [[p[:2] for p in h] for h in c[1:]]))
        elif g["type"] == "MultiPolygon":
            polygons += [
                Polygon([p[:2] for p in poly[0]], [[p[:2] for p in h] for h in poly[1:]])
                for poly in c
            ]
        elif g["type"] == "LineString":
            lines.append(LineString([p[:2] for p in c]))
    return polygons, lines


def _load(path: Path) -> tuple[list[Polygon], list[LineString]]:
    suffix = path.suffix.lower()
    if suffix == ".kmz":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".kml"))
            return _load_kml(z.read(name))
    if suffix == ".kml":
        return _load_kml(path.read_bytes())
    if suffix in (".geojson", ".json"):
        return _load_geojson(path.read_bytes())
    raise ValueError(f"unsupported file type {suffix!r} (use .kml, .kmz or .geojson)")


def read_area(path: Path) -> Polygon | MultiPolygon:
    polygons, _ = _load(path)
    if not polygons:
        raise ValueError(f"no polygon found in {path}")
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def read_line(path: Path) -> list[LonLat]:
    _, lines = _load(path)
    if not lines:
        raise ValueError(f"no line found in {path}")
    return [(float(x), float(y)) for x, y in lines[0].coords]
