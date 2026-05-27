import subprocess
import sys
from pathlib import Path

import cv2
import pytest

import process_image


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


POINT_ARGS = [
    "--point",
    "0.0,-150,210",
    "--point",
    "1.0,-197,280",
    "--point",
    "1.5,-227,280",
    "--point",
    "2.0,95,275",
    "--point",
    "2.5,57,275",
    "--point",
    "3.0,25,275",
    "--point",
    "4.0,-32,230",
]


def test_interpolated_points_follow_shortest_angle_path() -> None:
    points = [
        (1.5, -227.0, 280.0),
        (2.0, 95.0, 275.0),
    ]

    interpolated = process_image.build_interpolated_scale_points(points, spacing=0.1)
    by_value = {round(value, 1): (angle, distance) for value, angle, distance in interpolated}

    angle_1_6, _distance_1_6 = by_value[1.6]
    assert 120.0 <= angle_1_6 <= 131.0


def test_detect_pointer_on_prepared_fixture() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    image_path = repo_root / "tests" / "fixtures" / "image.jpg"

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Failed to load fixture image: {image_path}")

    detection = process_image.detect_pointer(image)
    assert detection is not None

    angle, _, _, _ = detection
    assert 105.0 <= angle <= 135.0


def test_process_image_debug_subprocess_returns_success(repo_root: Path) -> None:
    image_path = repo_root / "tests" / "fixtures" / "image.jpg"
    if not image_path.exists():
        raise RuntimeError(f"Missing test fixture: {image_path}")

    result = subprocess.run(
        [
            sys.executable,
            "process_image.py",
            "--input",
            str(image_path),
            *POINT_ARGS,
            "--debug",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo_root,
        check=False,
    )

    assert result.returncode == 0
    assert len(result.stdout) > 0


def test_process_image_value_from_copied_fixture(repo_root: Path) -> None:
    image_path = repo_root / "tests" / "fixtures" / "image.jpg"
    if not image_path.exists():
        raise RuntimeError(f"Missing test fixture: {image_path}")

    result = subprocess.run(
        [
            sys.executable,
            "process_image.py",
            "--input",
            str(image_path),
            *POINT_ARGS,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo_root,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode()
    value = float(result.stdout.decode().strip())
    assert round(value, 1) == 1.7