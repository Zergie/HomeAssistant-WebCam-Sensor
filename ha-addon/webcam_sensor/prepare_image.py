#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Optional

import cv2
import numpy as np


DEFAULT_CIRCLE_PADDING_RATIO = 0.0


def _build_pointer_ready_grayscale(image: np.ndarray, sharpen: float) -> np.ndarray:
    sharpen = max(0.0, float(sharpen))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    soft = cv2.GaussianBlur(gray, (3, 3), 0)
    weighted = cv2.addWeighted(gray, 1.0 + (0.25 * sharpen), soft, -0.25 * sharpen, 0)
    return weighted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare image bytes from file/stdin and write to file/stdout.")
    parser.add_argument("--input", help="Input image path. If omitted, reads image bytes from stdin.")
    parser.add_argument("--output", help="Output image path. If omitted, writes image bytes to stdout.")
    parser.add_argument("--x", type=int, required=True, help="Gauge center X in input image pixels.")
    parser.add_argument("--y", type=int, required=True, help="Gauge center Y in input image pixels.")
    parser.add_argument("--radius", type=int, required=True, help="Gauge radius in input image pixels.")
    parser.add_argument("--rotate", type=float, default=0.0, help="Rotation in degrees (counterclockwise). Default: 0.0")
    parser.add_argument("--sharpen", type=float, default=1.0, help="Sharpen strength for non-debug output. Use 0 to disable. Default: 1.0")
    parser.add_argument("--debug", action="store_true", help="Mark detected circle center and size in the output image.")
    return parser.parse_args()


def read_input_bytes(input_path: Optional[str]) -> bytes:
    if input_path:
        with open(input_path, "rb") as f:
            return f.read()
    return sys.stdin.buffer.read()


def decode_image(image_bytes: bytes) -> np.ndarray:
    if not image_bytes:
        raise RuntimeError("No input image bytes were provided.")
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Failed to decode input image bytes.")
    return image


def _crop_from_circle(
    image: np.ndarray,
    center_x: int,
    center_y: int,
    radius: int,
    padding_ratio: float,
) -> tuple[np.ndarray, tuple[int, int], int]:
    if radius <= 0:
        raise RuntimeError("Provided gauge radius must be greater than zero.")

    pad_radius = int(round(radius * (1.0 + padding_ratio)))
    h, w = image.shape[:2]

    x1 = max(0, center_x - pad_radius)
    y1 = max(0, center_y - pad_radius)
    x2 = min(w, center_x + pad_radius)
    y2 = min(h, center_y + pad_radius)

    if x2 <= x1 or y2 <= y1:
        raise RuntimeError("Provided gauge alignment creates invalid crop bounds.")
    cropped = image[y1:y2, x1:x2]
    center_in_crop = (center_x - x1, center_y - y1)
    return cropped, center_in_crop, radius
def prepare_image(image: np.ndarray, rotate: float, debug: bool, x: int, y: int, radius: int, sharpen: float) -> np.ndarray:
    detected_x, detected_y, detected_radius = int(x), int(y), int(radius)

    if debug:
        prepared = image.copy()
        debug_center = (detected_x, detected_y)
    else:
        prepared, debug_center, detected_radius = _crop_from_circle(
            image,
            detected_x,
            detected_y,
            detected_radius,
            DEFAULT_CIRCLE_PADDING_RATIO,
        )

    if rotate != 0.0:
        height, width = prepared.shape[:2]
        center = (width / 2.0, height / 2.0)
        matrix = cv2.getRotationMatrix2D(center, rotate, 1.0)
        prepared = cv2.warpAffine(prepared, matrix, (width, height))

        point = np.array([debug_center[0], debug_center[1], 1.0], dtype=np.float32)
        rotated_point = matrix @ point
        debug_center = (int(round(rotated_point[0])), int(round(rotated_point[1])))

    if debug:
        marker_size = max(12, min(prepared.shape[:2]) // 12)
        thickness = 2
        cv2.circle(prepared, debug_center, max(1, detected_radius), (0, 255, 0), thickness, cv2.LINE_AA)
        cv2.drawMarker(
            prepared,
            debug_center,
            (0, 0, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=marker_size,
            thickness=thickness,
            line_type=cv2.LINE_AA,
        )
        label_pos = (10, max(18, min(prepared.shape[0] - 8, 24)))
        cv2.putText(
            prepared,
            f"r={detected_radius}px d={detected_radius * 2}px",
            label_pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
        return prepared

    return _build_pointer_ready_grayscale(prepared, sharpen)


def encode_image(prepared: np.ndarray, output_path: Optional[str]) -> bytes:
    ext = ".png"
    if output_path:
        _, path_ext = os.path.splitext(output_path)
        if path_ext:
            ext = path_ext.lower()
    ok, encoded = cv2.imencode(ext, prepared)
    if not ok:
        raise RuntimeError(f"Failed to encode prepared image using extension '{ext}'.")
    return encoded.tobytes()


def write_output(image_bytes: bytes, output_path: Optional[str]) -> None:
    if output_path:
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        return
    sys.stdout.buffer.write(image_bytes)
    sys.stdout.buffer.flush()


def main() -> int:
    args = parse_args()
    try:
        raw = read_input_bytes(args.input)
        image = decode_image(raw)
        prepared = prepare_image(image, args.rotate, args.debug, args.x, args.y, args.radius, args.sharpen)
        encoded = encode_image(prepared, args.output)
        write_output(encoded, args.output)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
