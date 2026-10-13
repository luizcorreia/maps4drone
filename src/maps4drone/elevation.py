import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence

LonLat = tuple[float, float]
Elevation = Callable[[Sequence[LonLat]], list[float]]

_OPEN_METEO = "https://api.open-meteo.com/v1/elevation"
_BATCH = 100


def open_meteo_elevation(timeout: float = 20.0) -> Elevation:
    """Online elevation (Copernicus 90 m DEM) through the free Open-Meteo API."""

    def lookup(points: Sequence[LonLat]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(points), _BATCH):
            chunk = points[i : i + _BATCH]
            query = urllib.parse.urlencode(
                {
                    "latitude": ",".join(f"{lat:.6f}" for _, lat in chunk),
                    "longitude": ",".join(f"{lon:.6f}" for lon, _ in chunk),
                }
            )
            with urllib.request.urlopen(f"{_OPEN_METEO}?{query}", timeout=timeout) as resp:
                out.extend(float(v) for v in json.load(resp)["elevation"])
        if len(out) != len(points):
            raise RuntimeError("elevation service returned an unexpected number of values")
        return out

    return lookup
