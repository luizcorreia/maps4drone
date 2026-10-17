import io

import pytest
from PIL import Image

from maps4drone import thumbnail
from maps4drone.model import Waypoint
from maps4drone.thumbnail import HEIGHT, PIN, WIDTH, fit_view, render_thumbnail

ROUTE = [
    Waypoint(-20.14659, -44.89771, 100.0),
    Waypoint(-20.14681, -44.89700, 100.0),
    Waypoint(-20.14760, -44.89715, 100.0),
    Waypoint(-20.14790, -44.89790, 100.0),
]


def decode(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def near(a: tuple[int, ...], b: tuple[int, ...], tol: int = 20) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_matches_the_size_and_format_of_the_apps_thumbnails():
    data = render_thumbnail(ROUTE)
    assert data[:3] == b"\xff\xd8\xff"
    assert decode(data).size == (2316, 1080) == (WIDTH, HEIGHT)


def test_route_is_centred_and_fits_the_picture():
    view = fit_view([(w.lng, w.lat) for w in ROUTE])
    pts = [view.project(w.lng, w.lat) for w in ROUTE]
    assert all(0 < x < WIDTH and 0 < y < HEIGHT for x, y in pts)
    xs, ys = zip(*pts)
    assert (min(xs) + max(xs)) / 2 == pytest.approx(WIDTH / 2, abs=1)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(HEIGHT / 2, abs=1)


def test_pins_sit_on_the_waypoints():
    image = decode(render_thumbnail(ROUTE))
    view = fit_view([(w.lng, w.lat) for w in ROUTE])
    for w in ROUTE[:-1]:
        x, y = view.project(w.lng, w.lat)
        # beside the number, well inside the pin's disc
        assert near(image.getpixel((round(x) + 13, round(y) + 13)), PIN)


def test_a_far_longer_route_zooms_out():
    long_route = [Waypoint(-20.0, -44.9, 50.0), Waypoint(-20.3, -44.5, 50.0)]
    near_view = fit_view([(w.lng, w.lat) for w in ROUTE])
    far_view = fit_view([(w.lng, w.lat) for w in long_route])
    assert far_view.zoom < near_view.zoom


def test_tiles_are_painted_under_the_route_and_credited():
    tile = Image.new("RGB", (256, 256), (10, 200, 10))
    buf = io.BytesIO()
    tile.save(buf, "PNG")
    asked: list[tuple[int, int, int]] = []

    def fetch(z: int, x: int, y: int) -> bytes:
        asked.append((z, x, y))
        return buf.getvalue()

    image = decode(render_thumbnail(ROUTE, fetch))
    view = fit_view([(w.lng, w.lat) for w in ROUTE])
    assert asked and {z for z, _, _ in asked} == {view.zoom + 1}  # 256 px tiles one level deeper
    corner = image.getpixel((5, 5))
    assert corner[1] > corner[0] + 20  # greenish, though faded towards the pale background


def test_missing_tiles_leave_a_plain_background():
    image = decode(render_thumbnail(ROUTE, lambda z, x, y: None))
    assert near(image.getpixel((5, 5)), thumbnail.BACKGROUND)


def test_unreadable_tile_data_is_ignored():
    image = decode(render_thumbnail(ROUTE, lambda z, x, y: b"not an image"))
    assert near(image.getpixel((5, 5)), thumbnail.BACKGROUND)


def test_long_routes_number_a_bounded_set_of_pins():
    assert thumbnail._sample(6) == [0, 1, 2, 3, 4, 5]
    many = thumbnail._sample(500)
    assert len(many) <= thumbnail.MAX_PINS and many[0] == 0 and many[-1] == 499


def test_a_single_waypoint_has_nothing_to_draw():
    with pytest.raises(ValueError, match="at least 2"):
        render_thumbnail(ROUTE[:1])
