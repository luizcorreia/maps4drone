import math
from collections.abc import Sequence

Point = tuple[float, float]


def serpentine(lines: Sequence[Sequence[Point]]) -> list[Point]:
    """Chain parallel lines into one route, flipping every other line."""
    route: list[Point] = []
    for i, line in enumerate(lines):
        route.extend(line if i % 2 == 0 else line[::-1])
    return route


def closest_end_first(route: Sequence[Point], origin: Point) -> list[Point]:
    """Return the route or its reverse, whichever starts nearer to origin."""
    if math.dist(origin, route[-1]) < math.dist(origin, route[0]):
        return list(route[::-1])
    return list(route)
