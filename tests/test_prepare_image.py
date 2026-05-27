import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import pytest

import prepare_image


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def frame_path(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "frame.jpg"


@pytest.fixture(scope="module")
def image(frame_path: Path):
    img = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Failed to load fixture image: {frame_path}")
    return img


def test_detect_target_circle_on_fixture(image) -> None:
    x, y, r = prepare_image.detect_target_circle(image)
    assert 650 <= x <= 780, f"Unexpected x center: {x}"
    assert 260 <= y <= 390, f"Unexpected y center: {y}"
    assert 80 <= r <= 160, f"Unexpected radius: {r}"


def test_prepare_image_debug_is_color_and_uncropped(image) -> None:
    out = prepare_image.prepare_image(image, rotate=-90.0, debug=True)
    assert out.shape == image.shape
    assert out.ndim == 3
    assert out.shape[2] == 3


def test_prepare_image_non_debug_is_grayscale_and_cropped(image) -> None:
    out = prepare_image.prepare_image(image, rotate=-90.0, debug=False)
    assert out.ndim == 2
    assert out.shape[0] < image.shape[0]
    assert out.shape[1] < image.shape[1]
    assert abs(out.shape[0] - out.shape[1]) <= 6


def test_cli_debug_completes_within_timeout(repo_root: Path, frame_path: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                sys.executable,
                "prepare_image.py",
                "--input",
                str(frame_path),
                "--output",
                str(out_path),
                "--debug",
            ],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    finally:
        out_path.unlink(missing_ok=True)
