import math

import pytest

from maps4drone.geo import Projector
from maps4drone.planners.corridor import plan_corridor
from maps4drone.planners.facade import plan_facade
from maps4drone.planners.orbit import plan_orbit
from maps4drone.planners.survey import SurveyParams

LINE = [(-51.9000, -23.1500), (-51.8990, -23.1490), (-51.8970, -23.1490)]


def test_corridor_three_passes(atom2):
    m = plan_corridor(LINE, atom2, atom2.camera(), SurveyParams(), lines=3)
    assert len(m.waypoints) == 9
    proj = Projector(*LINE[0])
    first, last = (proj.forward(w.lng, w.lat) for w in (m.waypoints[0], m.waypoints[-1]))
    assert math.dist(first, last) > 0


def test_corridor_needs_odd_lines(atom2):
    with pytest.raises(ValueError, match="odd"):
        plan_corridor(LINE, atom2, atom2.camera(), SurveyParams(), lines=2)


def test_orbit_points_on_circle_facing_center(atom2):
    center = (-51.9, -23.15)
    m = plan_orbit(atom2, center, radius_m=40, height_m=40, points=8)
    proj = Projector(*center)
    cx, cy = proj.forward(*center)
    for w in m.waypoints:
        x, y = proj.forward(w.lng, w.lat)
        assert math.hypot(x - cx, y - cy) == pytest.approx(40, abs=0.01)
        assert w.gimbal_pitch == pytest.approx(-45, abs=0.01)
    # first point is north of the center, so the nose points south
    assert abs(m.waypoints[0].yaw) == 180


def test_orbit_needs_three_points(atom2):
    with pytest.raises(ValueError, match="3 points"):
        plan_orbit(atom2, (-51.9, -23.15), 40, 40, points=2)


def test_facade_grid_covers_wall(atom2):
    a, b = (-51.9000, -23.1500), (-51.8995, -23.1500)  # ~52 m wall running east
    m = plan_facade(atom2, atom2.camera(), a, b, wall_height_m=20, standoff_m=15)
    assert all(w.action == "PHOTO" and w.gimbal_pitch == 0 for w in m.waypoints)
    heights = sorted({round(w.height, 1) for w in m.waypoints})
    fh = atom2.camera().footprint_m(15)[1]
    assert heights[0] == pytest.approx(fh / 2, abs=0.1)
    assert heights[-1] == pytest.approx(20 - fh / 2, abs=0.1)
    # wall runs west->east, drone on the left (north) side, nose pointing south
    assert {abs(w.yaw) for w in m.waypoints} == {180}
    assert all(w.lat > a[1] for w in m.waypoints)


def test_facade_rejects_bad_side(atom2):
    with pytest.raises(ValueError, match="side"):
        plan_facade(atom2, atom2.camera(), (-51.9, -23.15), (-51.899, -23.15), 10, side="up")
