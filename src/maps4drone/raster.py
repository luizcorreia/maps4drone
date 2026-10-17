"""Terrain elevation from a raster DEM or DSM (GeoTIFF), e.g. the one WebODM produced.

rasterio is imported on use: the rest of the package, and the QGIS plugin, do not need it.
"""

from __future__ import annotations

from collections.abc import Sequence

from .elevation import Elevation, LonLat

MISSING_REPORT_LIMIT = 3


def raster_elevation(path: str, band: int = 1) -> Elevation:
    """Elevation lookup that samples `path` at (lon, lat) points, in whatever CRS it has.

    The file is opened per lookup, so the function is safe to share between threads.
    A point outside the raster, or on a no-data cell, is an error: flying a terrain-following
    route over a hole in the model would mean guessing the ground height.
    """

    def lookup(points: Sequence[LonLat]) -> list[float]:
        import rasterio
        from rasterio.warp import transform

        with rasterio.open(path) as ds:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            if ds.crs is not None and ds.crs.to_epsg() != 4326:
                xs, ys = transform("EPSG:4326", ds.crs, xs, ys)
            samples = list(ds.sample(zip(xs, ys), indexes=band, masked=True))
        values = [s[0] for s in samples]
        missing = [i for i, v in enumerate(values) if v is None or bool(getattr(v, "mask", False))]
        if missing:
            shown = ", ".join(
                f"{points[i][1]:.5f}, {points[i][0]:.5f}" for i in missing[:MISSING_REPORT_LIMIT]
            )
            raise ValueError(
                f"o modelo de elevacao nao cobre {len(missing)} ponto(s) da rota "
                f"(por exemplo lat, lng {shown}): o modelo so cobre a regiao fotografada, "
                "com bordas sem dado; mantenha a area e a decolagem dentro dela"
            )
        return [float(v) for v in values]

    return lookup
