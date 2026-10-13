import math

from pyproj import Transformer

Coord = tuple[float, float]


class Projector:
    """Lon/lat <-> metric UTM coordinates for the zone containing a reference point."""

    def __init__(self, lon: float, lat: float) -> None:
        zone = int((lon + 180) // 6) + 1
        epsg = (32600 if lat >= 0 else 32700) + zone
        self._fwd = Transformer.from_crs(4326, epsg, always_xy=True)
        self._inv = Transformer.from_crs(epsg, 4326, always_xy=True)

    def forward(self, lon: float, lat: float) -> Coord:
        x, y = self._fwd.transform(lon, lat)
        return float(x), float(y)

    def inverse(self, x: float, y: float) -> Coord:
        lon, lat = self._inv.transform(x, y)
        return float(lon), float(lat)


def bearing_deg(dx: float, dy: float) -> float:
    """Compass bearing (0 = north, clockwise) of a vector in a metric east/north frame."""
    return math.degrees(math.atan2(dx, dy)) % 360


def wrap_180(angle: float) -> float:
    return (angle + 180) % 360 - 180
