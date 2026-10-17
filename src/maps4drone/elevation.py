import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence

LonLat = tuple[float, float]
Elevation = Callable[[Sequence[LonLat]], list[float]]

_OPEN_METEO = "https://api.open-meteo.com/v1/elevation"
_BATCH = 100
_CACHE_DECIMALS = 4  # about 11 m, finer than the 90 m DEM
_CACHE_LIMIT = 200_000

_cache: dict[LonLat, float] = {}


def _key(point: LonLat) -> LonLat:
    return (round(point[0], _CACHE_DECIMALS), round(point[1], _CACHE_DECIMALS))


def open_meteo_elevation(timeout: float = 20.0) -> Elevation:
    """Online elevation (Copernicus 90 m DEM) through the free Open-Meteo API."""

    def fetch(chunk: Sequence[LonLat]) -> list[float]:
        query = urllib.parse.urlencode(
            {
                "latitude": ",".join(f"{lat:.6f}" for _, lat in chunk),
                "longitude": ",".join(f"{lon:.6f}" for lon, _ in chunk),
            }
        )
        with urllib.request.urlopen(f"{_OPEN_METEO}?{query}", timeout=timeout) as resp:
            return [float(v) for v in json.load(resp)["elevation"]]

    def lookup(points: Sequence[LonLat]) -> list[float]:
        """Cached per rounded point, so tweaking altitude or overlap never refetches.

        The answer is gathered in a local dict: the shared cache may be cleared meanwhile (it
        is bounded, and other requests use it), and that must not cost this call its values.
        """
        keys = list(dict.fromkeys(map(_key, points)))
        found = {k: v for k in keys if (v := _cache.get(k)) is not None}
        missing = [k for k in keys if k not in found]
        for i in range(0, len(missing), _BATCH):
            chunk = missing[i : i + _BATCH]
            values = fetch(chunk)
            if len(values) != len(chunk):
                raise RuntimeError("elevation service returned an unexpected number of values")
            found.update(zip(chunk, values))
            if len(_cache) > _CACHE_LIMIT:
                _cache.clear()
            _cache.update(zip(chunk, values))
        return [found[_key(p)] for p in points]

    return lookup
