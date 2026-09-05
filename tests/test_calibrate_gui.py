from pathlib import Path

import pytest

import calibrate_gui


def test_load_config_reads_options_not_schema() -> None:
    settings = calibrate_gui.load_config(Path("webcam_gauge_sensor/config.yaml"))

    assert settings["x"] == 835
    assert settings["y"] == 400
    assert settings["points"] == [
        "0.0,-150,210",
        "1.0,-197,280",
        "1.5,-227,280",
        "2.0,95,275",
        "2.5,57,275",
        "3.0,25,275",
        "4.0,-32,230",
    ]


def test_move_point_preserves_negative_angle_revolution() -> None:
    original = [1.5, -227.0, 280.0]
    x, y = calibrate_gui.point_xy((300.0, 300.0), original)

    angle, distance = calibrate_gui.move_point((300.0, 300.0), original[1], x, y)

    assert angle == pytest.approx(-227.0)
    assert distance == pytest.approx(280.0)


def test_point_round_trip_accounts_for_preparation_rotation() -> None:
    original = [2.0, 95.0, 275.0]
    x, y = calibrate_gui.point_xy((400.0, 300.0), original, rotate=15.0)

    angle, distance = calibrate_gui.move_point((400.0, 300.0), original[1], x, y, rotate=15.0)

    assert angle == pytest.approx(95.0)
    assert distance == pytest.approx(275.0)


def test_radius_is_distance_from_center() -> None:
    assert calibrate_gui.radius_from_xy((100.0, 100.0), 130.0, 140.0) == 50


def test_home_assistant_export_round_trip(tmp_path) -> None:
    settings = calibrate_gui.load_config(calibrate_gui.DEFAULT_CONFIG)
    settings.update(y=443, rotate=12.5, sharpen=8.0, mqtt_password="special: # password")
    text = calibrate_gui.format_config(settings)
    assert "'y': 443" in text
    assert "  - " in text
    path = tmp_path / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    assert calibrate_gui.load_config(path) == settings
