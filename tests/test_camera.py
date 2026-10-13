import pytest

from maps4drone.camera import load_drones


def test_atom2_matches_reference_numbers(atom2):
    cam = atom2.camera()
    assert cam.gsd_m(100) == pytest.approx(0.0356, abs=1e-4)  # 3.56 cm/px
    assert cam.footprint_m(100)[0] == pytest.approx(142.2, abs=0.1)  # coverage width


def test_spacing_and_speed(atom2):
    cam = atom2.camera()
    assert cam.line_spacing_m(100, 0.70) == pytest.approx(42.67, abs=0.01)
    shot = cam.shot_distance_m(100, 0.80)
    assert shot == pytest.approx(21.33, abs=0.01)
    assert shot / 3 == pytest.approx(7.1, abs=0.05)


def test_unknown_camera(atom2):
    with pytest.raises(ValueError, match="unknown camera"):
        atom2.camera("nope")


def test_custom_catalog(tmp_path, atom2):
    path = tmp_path / "d.json"
    path.write_text(
        '{"x": {"name": "X", "default_camera": "c", "flight_minutes": 10,'
        ' "max_speed_ms": 5, "max_height_m": 50, "shoot_intervals_s": [2],'
        ' "cameras": {"c": {"sensor_w_mm": 1, "sensor_h_mm": 1, "focal_mm": 1,'
        ' "image_w": 1, "image_h": 1}}}}'
    )
    assert load_drones(path)["x"].name == "X"
