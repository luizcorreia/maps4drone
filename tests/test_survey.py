import math

import pytest

from maps4drone.geo import Projector
from maps4drone.planners.survey import SurveyParams, plan_survey
from maps4drone.stats import estimate


def _xy(mission):
    w0 = mission.waypoints[0]
    proj = Projector(w0.lng, w0.lat)
    return [proj.forward(w.lng, w.lat) for w in mission.waypoints]


def test_grid_lines_are_parallel_and_evenly_spaced(atom2, square):
    m = plan_survey(square, atom2, atom2.camera(), SurveyParams(heading_deg=0))
    pts = _xy(m)
    assert len(pts) % 2 == 0
    xs = sorted({round(p[0], 1) for p in pts})
    gaps = [b - a for a, b in zip(xs, xs[1:], strict=False)]
    assert gaps == pytest.approx([42.67] * len(gaps), abs=0.15)
    # north-south lines: both ends of every line share the same x
    for (x0, _), (x1, _) in zip(pts[::2], pts[1::2], strict=True):
        assert x0 == pytest.approx(x1, abs=0.01)


def test_serpentine_alternates_direction(atom2, square):
    pts = _xy(plan_survey(square, atom2, atom2.camera(), SurveyParams()))
    dys = [b[1] - a[1] for a, b in zip(pts[::2], pts[1::2], strict=True)]
    assert all(d1 * d2 < 0 for d1, d2 in zip(dys, dys[1:], strict=False))


def test_heading_rotates_lines(atom2, square):
    pts = _xy(plan_survey(square, atom2, atom2.camera(), SurveyParams(heading_deg=90)))
    for (_, y0), (_, y1) in zip(pts[::2], pts[1::2], strict=True):
        assert y0 == pytest.approx(y1, abs=0.01)  # east-west lines


def test_all_waypoints_stay_inside_area(atom2, square):
    m = plan_survey(square, atom2, atom2.camera(), SurveyParams(heading_deg=35))
    for w in m.waypoints:
        assert -51.9001 <= w.lng <= -51.8963 and -23.1501 <= w.lat <= -23.1472


def test_double_grid_has_two_perpendicular_passes(atom2, square):
    single = plan_survey(square, atom2, atom2.camera(), SurveyParams())
    double = plan_survey(square, atom2, atom2.camera(), SurveyParams(double=True))
    assert len(double.waypoints) > len(single.waypoints)
    pts = _xy(double)[len(single.waypoints) :]
    for (_, y0), (_, y1) in zip(pts[::2], pts[1::2], strict=True):
        assert y0 == pytest.approx(y1, abs=0.01)


def test_speed_from_interval_and_cap(atom2, square):
    m = plan_survey(square, atom2, atom2.camera(), SurveyParams(interval_s=3))
    assert m.speed_ms == 7.1  # floored to 0.1 so overlap never drops below target
    assert not m.warnings
    low = plan_survey(square, atom2, atom2.camera(), SurveyParams(altitude_m=300, interval_s=5))
    assert low.speed_ms <= atom2.max_speed_ms
    assert any("legal limit" in w for w in low.warnings)


def test_invalid_interval(atom2, square):
    with pytest.raises(ValueError, match="interval"):
        plan_survey(square, atom2, atom2.camera(), SurveyParams(interval_s=1))


def test_concave_polygon_yields_multiple_segments_per_line(atom2):
    from shapely.geometry import Polygon

    u = Polygon(
        [
            (-51.900, -23.150),
            (-51.896, -23.150),
            (-51.896, -23.146),
            (-51.8975, -23.146),
            (-51.8975, -23.1485),
            (-51.8985, -23.1485),
            (-51.8985, -23.146),
            (-51.900, -23.146),
        ]
    )
    m = plan_survey(u, atom2, atom2.camera(), SurveyParams())
    assert len(m.waypoints) > 2 * 8  # lines crossing the notch are split in two


def test_terrain_following_keeps_agl(atom2, square):
    def slope(points):  # ground rises 1 m per 0.0001 deg of latitude
        return [700 + (lat + 23.15) * 10_000 for _, lat in points]

    takeoff = (-51.9, -23.15)
    m = plan_survey(square, atom2, atom2.camera(), SurveyParams(), slope, takeoff)
    base = slope([takeoff])[0]
    for w in m.waypoints:
        assert w.height == pytest.approx(100 + slope([(w.lng, w.lat)])[0] - base, abs=1e-6)
    assert len(m.waypoints) > len(
        plan_survey(square, atom2, atom2.camera(), SurveyParams()).waypoints
    )


def test_terrain_needs_takeoff(atom2, square):
    with pytest.raises(ValueError, match="takeoff"):
        plan_survey(square, atom2, atom2.camera(), SurveyParams(), lambda p: [0.0] * len(p))


def test_stats_follow_reference_formula(atom2, square):
    m = plan_survey(square, atom2, atom2.camera(), SurveyParams())
    s = estimate(m)
    assert s.waypoints == len(m.waypoints)
    assert s.duration_s == pytest.approx(s.distance_m / m.speed_ms, rel=0.01)
    assert s.images[3] == round(s.duration_s / 3)
    assert s.area_ha == pytest.approx(11.9, abs=1.0)
    assert s.batteries >= 1
    assert math.isfinite(s.distance_m)


def test_terrain_warning_uses_agl_not_takeoff_relative_height(atom2, square):
    hill = lambda pts: [800.0 + 0.1 * i for i, _ in enumerate(pts)]  # noqa: E731
    m = plan_survey(square, atom2, atom2.camera(), SurveyParams(), hill, (-51.9, -23.15))
    assert not any("legal limit" in w for w in m.warnings)
