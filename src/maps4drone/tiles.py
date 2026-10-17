"""Map tiles for the mission thumbnail, fetched best-effort and cached.

Kept apart from thumbnail.py so that importing the service does not need Pillow.
"""

import urllib.request
from collections.abc import Callable
from typing import Optional

TileFetcher = Callable[[int, int, int], Optional[bytes]]

_OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_CACHE_LIMIT = 1024
_tile_cache: dict[tuple[int, int, int], bytes] = {}


def osm_tiles(timeout: float = 6.0) -> TileFetcher:
    """OpenStreetMap tiles with a User-Agent, as its usage policy asks, and a small cache so a
    mission tweaked and exported again does not hit the server again. Failures give None."""

    def fetch(z: int, x: int, y: int) -> Optional[bytes]:
        if (cached := _tile_cache.get((z, x, y))) is not None:
            return cached
        request = urllib.request.Request(
            _OSM.format(z=z, x=x, y=y), headers={"User-Agent": "maps4drone"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                data: bytes = resp.read()
        except OSError:
            return None
        if len(_tile_cache) >= _CACHE_LIMIT:
            _tile_cache.clear()
        _tile_cache[(z, x, y)] = data
        return data

    return fetch
