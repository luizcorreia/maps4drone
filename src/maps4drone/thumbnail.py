"""Mission thumbnail for the Potensic Eve app (the task_<id>.jpg next to the mission files).

The app draws it once, when a mission is created, and lists it as the mission's preview;
replacing the JSON files leaves the old picture behind. This renders the same kind of
picture: a light map with the route in green, direction chevrons, numbered pins and a
height tag on each pin. Needs Pillow; the map tiles (OpenStreetMap, a few dozen per picture,
faded to a pale look) are optional and fetched best-effort.
"""

import io
import math
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from .model import Waypoint

WIDTH, HEIGHT = 2316, 1080
# One unit of zoom here is two OSM zoom levels' worth of pixels per tile: the picture is drawn
# at 512 px per tile of this zoom, which is exactly four 256 px tiles one level deeper.
TILE_PX = 512
OSM_TILE_PX = 256
MAX_ZOOM = 18  # OSM serves up to 19
FILL_FRACTION = 0.55  # share of the picture the route may span
MAX_PINS = 40
MAX_TAGGED = 12
SUPERSAMPLE = 2

BACKGROUND = (240, 229, 233)
ROUTE = (0, 200, 83)
ROUTE_EDGE = (0, 130, 60)
PIN = (0, 230, 118)
PIN_LAST = (0, 150, 70)
TAG = (95, 95, 95, 235)

TileFetcher = Callable[[int, int, int], bytes | None]
Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

_OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_ATTRIBUTION = "© OpenStreetMap contributors"
_CACHE_LIMIT = 1024
_tile_cache: dict[tuple[int, int, int], bytes] = {}


def osm_tiles(timeout: float = 6.0) -> TileFetcher:
    """OpenStreetMap tiles with a User-Agent, as its usage policy asks, and a small cache so a
    mission tweaked and exported again does not hit the server again. Failures give None."""

    def fetch(z: int, x: int, y: int) -> bytes | None:
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


@dataclass(frozen=True)
class View:
    """Web-Mercator window: which zoom, and where the picture's corner sits in the world."""

    zoom: int
    origin_x: float
    origin_y: float

    def project(self, lng: float, lat: float) -> tuple[float, float]:
        world = TILE_PX * 2**self.zoom
        x = (lng + 180) / 360 * world
        sin = math.sin(math.radians(lat))
        y = (0.5 - math.log((1 + sin) / (1 - sin)) / (4 * math.pi)) * world
        return x - self.origin_x, y - self.origin_y


def _world(zoom: int, lng: float, lat: float) -> tuple[float, float]:
    return View(zoom, 0, 0).project(lng, lat)


def fit_view(points: Sequence[tuple[float, float]]) -> View:
    """The most zoomed-in view that keeps the (lng, lat) points inside the picture."""
    zoom = MAX_ZOOM
    while zoom > 0:
        xs, ys = zip(*(_world(zoom, lng, lat) for lng, lat in points), strict=True)
        if (
            max(xs) - min(xs) <= WIDTH * FILL_FRACTION
            and max(ys) - min(ys) <= HEIGHT * FILL_FRACTION
        ):
            break
        zoom -= 1
    xs, ys = zip(*(_world(zoom, lng, lat) for lng, lat in points), strict=True)
    return View(zoom, (min(xs) + max(xs)) / 2 - WIDTH / 2, (min(ys) + max(ys)) / 2 - HEIGHT / 2)


def _basemap(view: View, fetch: TileFetcher | None) -> tuple[Image.Image, bool]:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    if fetch is None:
        return canvas, False
    zoom = view.zoom + 1  # 256 px tiles one level deeper match the 512 px per tile of `view`
    count = 2**zoom
    columns = range(
        int(view.origin_x // OSM_TILE_PX), int((view.origin_x + WIDTH) // OSM_TILE_PX) + 1
    )
    rows = range(
        int(view.origin_y // OSM_TILE_PX), int((view.origin_y + HEIGHT) // OSM_TILE_PX) + 1
    )
    wanted = [(x, y) for x in columns for y in rows if 0 <= y < count]
    with ThreadPoolExecutor(max_workers=8) as pool:
        tiles = list(pool.map(lambda t: fetch(zoom, t[0] % count, t[1]), wanted))
    drawn = False
    for (x, y), data in zip(wanted, tiles, strict=True):
        if data is None:
            continue
        try:
            tile = Image.open(io.BytesIO(data)).convert("RGB")
        except OSError:
            continue
        canvas.paste(
            tile, (round(x * OSM_TILE_PX - view.origin_x), round(y * OSM_TILE_PX - view.origin_y))
        )
        drawn = True
    if drawn:  # fade the colours towards the app's pale map so the route stands out
        canvas = ImageEnhance.Color(canvas).enhance(0.3)
        canvas = Image.blend(canvas, Image.new("RGB", canvas.size, BACKGROUND), 0.35)
    return canvas, drawn


def _chevron(draw: ImageDraw.ImageDraw, x: float, y: float, angle: float, size: float) -> None:
    tip = (x + math.cos(angle) * size, y + math.sin(angle) * size)
    wings = [
        (x - math.cos(angle + side) * size * 0.9, y - math.sin(angle + side) * size * 0.9)
        for side in (0.9, -0.9)
    ]
    for wing in wings:
        draw.line([wing, tip], fill=(255, 255, 255, 235), width=SUPERSAMPLE * 3)


def _route(draw: ImageDraw.ImageDraw, pts: list[tuple[float, float]]) -> None:
    scaled = [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in pts]
    draw.line(scaled, fill=ROUTE_EDGE, width=SUPERSAMPLE * 17, joint="curve")
    draw.line(scaled, fill=ROUTE, width=SUPERSAMPLE * 12, joint="curve")
    gap = 80 * SUPERSAMPLE
    for (x0, y0), (x1, y1) in zip(scaled, scaled[1:], strict=False):
        length = math.hypot(x1 - x0, y1 - y0)
        angle = math.atan2(y1 - y0, x1 - x0)
        for k in range(max(1, int(length // gap))):
            t = (k + 0.5) * gap / length if length > gap else 0.5
            _chevron(draw, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, angle, 16 * SUPERSAMPLE)


def _pin(draw: ImageDraw.ImageDraw, font: Font, at: tuple[float, float],
         number: int, last: bool) -> None:  # fmt: skip
    x, y = at[0] * SUPERSAMPLE, at[1] * SUPERSAMPLE
    r = (36 if last else 28) * SUPERSAMPLE
    ring = 5 * SUPERSAMPLE
    draw.ellipse(
        [x - r - ring, y - r - ring, x + r + ring, y + r + ring], fill=(255, 255, 255, 255)
    )
    draw.ellipse([x - r, y - r, x + r, y + r], fill=PIN_LAST if last else PIN)
    draw.text((x, y), str(number), font=font, fill=(255, 255, 255), anchor="mm")


def _tag(draw: ImageDraw.ImageDraw, font: Font, at: tuple[float, float],
         height_m: float, last: bool) -> None:  # fmt: skip
    text = f"{height_m:.0f} m"
    x, y = at[0] * SUPERSAMPLE, (at[1] - (50 if last else 42)) * SUPERSAMPLE
    width, half = 118 * SUPERSAMPLE, 18 * SUPERSAMPLE
    draw.rounded_rectangle([x - width / 2, y - half, x + width / 2, y + half], 8 * SUPERSAMPLE, TAG)
    ix = x - width / 2 + 16 * SUPERSAMPLE  # the little I-beam that marks a height
    top, bottom, wing = y - 10 * SUPERSAMPLE, y + 10 * SUPERSAMPLE, 5 * SUPERSAMPLE
    for line in (
        [(ix - wing, top), (ix + wing, top)],
        [(ix - wing, bottom), (ix + wing, bottom)],
        [(ix, top), (ix, bottom)],
    ):
        draw.line(line, fill=(255, 255, 255), width=2 * SUPERSAMPLE)
    draw.text((x + 14 * SUPERSAMPLE, y), text, font=font, fill=(255, 255, 255), anchor="mm")


def _sample(count: int) -> list[int]:
    """Indices to number: every waypoint on short routes, an even spread on long ones."""
    if count <= MAX_PINS:
        return list(range(count))
    step = (count - 1) / (MAX_PINS - 1)
    return sorted({round(i * step) for i in range(MAX_PINS)})


def render_thumbnail(waypoints: Sequence[Waypoint], fetch_tile: TileFetcher | None = None) -> bytes:
    """JPEG bytes of the mission preview; the basemap is left plain without tiles."""
    if len(waypoints) < 2:
        raise ValueError("a thumbnail needs at least 2 waypoints")
    view = fit_view([(w.lng, w.lat) for w in waypoints])
    base, has_tiles = _basemap(view, fetch_tile)

    overlay = Image.new("RGBA", (WIDTH * SUPERSAMPLE, HEIGHT * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    pts = [view.project(w.lng, w.lat) for w in waypoints]
    _route(draw, pts)
    numbered = _sample(len(waypoints))
    pin_font = ImageFont.load_default(size=34 * SUPERSAMPLE)
    tag_font = ImageFont.load_default(size=24 * SUPERSAMPLE)
    last = len(waypoints) - 1
    for i in numbered:
        _pin(draw, pin_font, pts[i], i + 1, i == last)
    for i in numbered if len(numbered) <= MAX_TAGGED else (0, last):
        _tag(draw, tag_font, pts[i], waypoints[i].height, i == last)

    picture = Image.alpha_composite(
        base.convert("RGBA"), overlay.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    ).convert("RGB")
    if has_tiles:
        credit = ImageDraw.Draw(picture)
        credit.text(
            (WIDTH - 14, HEIGHT - 10),
            _ATTRIBUTION,
            font=ImageFont.load_default(size=22),
            fill=(110, 110, 110),
            anchor="rd",
        )
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=85)
    return out.getvalue()
