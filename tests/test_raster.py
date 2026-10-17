import pytest

rasterio = pytest.importorskip("rasterio")

import numpy as np  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from maps4drone.raster import raster_elevation  # noqa: E402

WEST, NORTH = -51.91, -23.14


def write(path, data, crs, transform, nodata=-9999.0):
    with rasterio.open(
        path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
        dtype="float32", crs=crs, transform=transform, nodata=nodata,
    ) as ds:  # fmt: skip
        ds.write(data.astype("float32"), 1)


@pytest.fixture
def geographic(tmp_path):
    """200 x 200 cells of 0.0001 deg; elevation is 700 + column, so it rises eastwards."""
    data = np.tile(700 + np.arange(200, dtype="float32"), (200, 1))
    path = tmp_path / "geo.tif"
    write(path, data, "EPSG:4326", from_origin(WEST, NORTH, 0.0001, 0.0001))
    return str(path)


def test_samples_a_raster_in_lon_lat(geographic):
    lookup = raster_elevation(geographic)
    centre = lambda col: WEST + (col + 0.5) * 0.0001  # noqa: E731 - cell edges are float-fragile
    lat = NORTH - 0.005
    assert lookup([(centre(0), lat), (centre(100), lat), (centre(50), lat)]) == [700, 800, 750]


def test_samples_a_projected_raster_by_converting_the_points(tmp_path):
    to_utm = Transformer.from_crs(4326, 31983, always_xy=True)
    x0, y0 = to_utm.transform(WEST, NORTH)
    data = np.tile(500 + np.arange(200, dtype="float32")[:, None], (1, 200))  # rises southwards
    path = tmp_path / "utm.tif"
    write(path, data, "EPSG:31983", from_origin(x0, y0, 5.0, 5.0))
    lookup = raster_elevation(str(path))
    x, y = x0 + 250, y0 - 100  # 250 m east, 100 m south of the corner
    lng, lat = Transformer.from_crs(31983, 4326, always_xy=True).transform(x, y)
    assert lookup([(lng, lat)])[0] == pytest.approx(500 + 100 / 5, abs=1)


def test_a_point_outside_the_raster_is_an_error(geographic):
    with pytest.raises(ValueError, match="nao cobre 1 ponto"):
        raster_elevation(geographic)([(-51.9, -23.15), (-50.0, -20.0)])


def test_a_no_data_cell_is_an_error(tmp_path):
    data = np.full((10, 10), 700.0, dtype="float32")
    data[5, 5] = -9999.0
    path = tmp_path / "hole.tif"
    write(path, data, "EPSG:4326", from_origin(WEST, NORTH, 0.0001, 0.0001))
    lookup = raster_elevation(str(path))
    assert lookup([(WEST + 0.00015, NORTH - 0.00015)]) == [700.0]
    with pytest.raises(ValueError, match="nao cobre"):
        lookup([(WEST + 0.00055, NORTH - 0.00055)])


def test_plugs_into_terrain_following(geographic):
    from maps4drone.model import Waypoint
    from maps4drone.terrain import follow_terrain

    route = [Waypoint(-23.1405, -51.9095, 80.0), Waypoint(-23.1405, -51.9005, 80.0)]
    followed = follow_terrain(route, 80.0, (-51.9095, -23.1405), raster_elevation(geographic), 30.0)
    heights = [w.height for w in followed]
    assert heights[0] == 80.0 and heights[-1] == pytest.approx(80.0 + 90, abs=1)
    assert heights == sorted(heights)
