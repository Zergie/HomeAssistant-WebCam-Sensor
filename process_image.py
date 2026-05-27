#!/usr/bin/env python3
import argparse
import math
import sys
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process gauge image as text value or annotated debug JPEG.")
    parser.add_argument("--input", help="Input image path. If omitted, reads image bytes from stdin.")
    parser.add_argument(
        "--point",
        action="append",
        required=True,
        metavar="VALUE,ANGLE,DISTANCE",
        help="Scale point as value,angle,distance (degrees and pixels from center). Repeat for multiple points.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write annotated JPEG bytes to stdout instead of text output.",
    )
    return parser.parse_args()


def validate_mapping(mapping: Sequence[Tuple[float, float]], name: str) -> List[Tuple[float, float]]:
    if len(mapping) < 2:
        raise RuntimeError(f"{name} must contain at least 2 points.")

    items = sorted(list(mapping), key=lambda item: item[0])
    prev_angle: Optional[float] = None
    validated: List[Tuple[float, float]] = []
    for angle, value in items:
        if not isinstance(angle, (int, float)) or not isinstance(value, (int, float)):
            raise RuntimeError(f"{name} angles and values must be numeric.")
        angle_f = float(angle)
        value_f = float(value)
        if prev_angle is not None and angle_f <= prev_angle:
            raise RuntimeError(f"{name} angles must be strictly increasing.")
        prev_angle = angle_f
        validated.append((angle_f, value_f))
    return validated


def parse_polar_point(point_text: str) -> Tuple[float, float, float]:
    parts = [part.strip() for part in point_text.split(",")]
    if len(parts) != 3:
        raise RuntimeError(f"Invalid --point '{point_text}'. Expected format: value,angle,distance")

    try:
        value = float(parts[0])
        angle = float(parts[1])
        distance = float(parts[2])
    except ValueError as exc:
        raise RuntimeError(f"Invalid --point '{point_text}'. value, angle and distance must be numeric.") from exc

    if distance <= 0.0:
        raise RuntimeError(f"Invalid --point '{point_text}'. distance must be greater than zero.")

    return value, angle, distance


def build_scale_points(
    point_args: Sequence[str],
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float, float]]]:
    if len(point_args) < 2:
        raise RuntimeError("At least two --point arguments are required.")

    parsed = [parse_polar_point(point_text) for point_text in point_args]
    parsed_sorted = sorted(parsed, key=lambda item: item[0])

    angle_value_mapping = validate_mapping([(angle, value) for value, angle, _ in parsed_sorted], "Point mapping")
    return angle_value_mapping, parsed_sorted


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


def _detect_pointer_radially(image: np.ndarray) -> Optional[Tuple[float, Tuple[float, float], Tuple[float, float], Tuple[float, float]]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    h, w = image.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    min_dim = float(min(h, w))
    radial_fracs = np.linspace(0.05, 0.38, 34)

    best_score: Optional[Tuple[int, float, float]] = None
    best_angle: Optional[float] = None
    best_tip: Optional[Tuple[float, float]] = None

    for angle in range(360):
        rad = math.radians(float(angle))
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        darkness_samples: List[float] = []
        sample_points: List[Tuple[float, float]] = []
        for frac in radial_fracs:
            r = min_dim * float(frac)
            x = int(round(cx + r * cos_a))
            y = int(round(cy - r * sin_a))
            if 0 <= x < w and 0 <= y < h:
                darkness_samples.append((255.0 - float(blurred[y, x])) / 255.0)
                sample_points.append((float(x), float(y)))

        if not darkness_samples:
            continue

        longest_run = 0
        current_run = 0
        run_tip_index = 0
        for idx, darkness in enumerate(darkness_samples):
            if darkness >= 0.40:
                current_run += 1
                if current_run > longest_run:
                    longest_run = current_run
                    run_tip_index = idx
            else:
                current_run = 0

        score = (
            longest_run,
            float(np.mean(darkness_samples)),
            float(np.percentile(np.array(darkness_samples, dtype=np.float32), 80.0)),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_angle = float(angle)
            best_tip = sample_points[run_tip_index]

    if best_score is None or best_score[0] < 10 or best_score[1] < 0.40 or best_angle is None or best_tip is None:
        return None

    center = (cx, cy)
    dx = best_tip[0] - center[0]
    dy = center[1] - best_tip[1]
    angle = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
    return angle, center, best_tip, center


def detect_pointer(image: np.ndarray) -> Optional[Tuple[float, Tuple[float, float], Tuple[float, float], Tuple[float, float]]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=50,
        minLineLength=max(20, min(image.shape[:2]) // 5),
        maxLineGap=10,
    )
    if lines is None:
        # Fall back to radial detection when line detection finds no candidates.
        return _detect_pointer_radially(image)

    h, w = image.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    near_center_threshold = min(h, w) * 0.20

    best: Optional[Tuple[float, Tuple[float, float], Tuple[float, float]]] = None
    for line in lines:
        x1, y1, x2, y2 = line[0]
        p1 = (float(x1), float(y1))
        p2 = (float(x2), float(y2))

        d1 = math.hypot(p1[0] - cx, p1[1] - cy)
        d2 = math.hypot(p2[0] - cx, p2[1] - cy)
        if min(d1, d2) > near_center_threshold:
            continue

        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if best is None:
            best = (length, p1, p2)
            continue

        if length > best[0]:
            best = (length, p1, p2)

    if best is None:
        return _detect_pointer_radially(image)

    _, p1, p2 = best
    tip = p1 if math.hypot(p1[0] - cx, p1[1] - cy) > math.hypot(p2[0] - cx, p2[1] - cy) else p2

    center = (cx, cy)
    dx = tip[0] - center[0]
    dy = center[1] - tip[1]
    angle = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
    return angle, center, tip, (p1 if tip == p2 else p2)


def encode_jpeg(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("Failed to encode annotated image as JPEG.")
    return encoded.tobytes()


def _interpolate_angle_shortest_path(start_angle: float, end_angle: float, fraction: float) -> float:
    start_norm = float(start_angle) % 360.0
    end_norm = float(end_angle) % 360.0
    delta = ((end_norm - start_norm + 540.0) % 360.0) - 180.0
    return (start_norm + float(fraction) * delta) % 360.0


def interpolate_point_by_value(value: float, points: Sequence[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    ordered = sorted(points, key=lambda item: item[0])
    if len(ordered) < 2:
        raise RuntimeError("Point list must contain at least two scale points.")

    value_f = float(value)
    for i in range(len(ordered) - 1):
        v1, a1, d1 = ordered[i]
        v2, a2, d2 = ordered[i + 1]
        if v1 <= value_f <= v2:
            if v2 == v1:
                return value_f, float(a2), float(d2)
            fraction = (value_f - v1) / (v2 - v1)
            angle = _interpolate_angle_shortest_path(float(a1), float(a2), fraction)
            distance = float(d1) + fraction * (float(d2) - float(d1))
            return value_f, angle, distance

    if value_f <= ordered[0][0]:
        _v, a, d = ordered[0]
        return value_f, float(a), float(d)

    _v, a, d = ordered[-1]
    return value_f, float(a), float(d)


def build_interpolated_scale_points(
    points: Sequence[Tuple[float, float, float]],
    spacing: float = 0.1,
) -> List[Tuple[float, float, float]]:
    if len(points) < 2:
        return []
    if spacing <= 0.0:
        raise RuntimeError("Scale marker spacing must be greater than zero.")

    ordered = sorted(points,key=lambda item: item[0])
    min_value = float(ordered[0][0])
    max_value = float(ordered[-1][0])
    existing_values = {round(float(value), 10) for value, _angle, _distance in ordered}

    start_index = int(math.ceil(min_value / spacing))
    end_index = int(math.floor(max_value / spacing))

    interpolated: List[Tuple[float, float, float]] = []
    for idx in range(start_index, end_index + 1):
        marker_value = round(idx * spacing, 10)
        if marker_value in existing_values:
            continue
        interpolated.append(interpolate_point_by_value(marker_value, ordered))

    return interpolated

def draw_text_with_outline(
    image: np.ndarray,
    text: str,
    position: Tuple[int, int],
    font_scale: float,
    color: Tuple[int, int, int],
    thickness: int,
) -> None:
    x, y = position
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)


def draw_dashed_line(
    image: np.ndarray,
    start: Tuple[float, float],
    end: Tuple[float, float],
    color: Tuple[int, int, int],
    thickness: int = 1,
    dash_length: float = 8.0,
    gap_length: float = 5.0,
) -> None:
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    total_len = math.hypot(dx, dy)
    if total_len <= 0.0:
        return

    ux = dx / total_len
    uy = dy / total_len
    distance = 0.0
    while distance < total_len:
        seg_start = distance
        seg_end = min(distance + dash_length, total_len)
        sx = int(round(x1 + ux * seg_start))
        sy = int(round(y1 + uy * seg_start))
        ex = int(round(x1 + ux * seg_end))
        ey = int(round(y1 + uy * seg_end))
        cv2.line(image, (sx, sy), (ex, ey), color, thickness)
        distance += dash_length + gap_length

def draw_scale_markers(
    image: np.ndarray,
    center: Tuple[float, float],
    points: List[Tuple[float, float, float]],
    marker_color: Tuple[int, int, int] = (0, 255, 255),
    marker_radius: int = 4,
    draw_labels: bool = True,
) -> None:
    cx, cy = center
    h, w = image.shape[:2]

    for scale_value, angle, distance in points:
        rad = math.radians(angle)
        tick_x = int(round(cx + distance * math.cos(rad)))
        tick_y = int(round(cy - distance * math.sin(rad)))
        tick_x = max(0, min(w - 1, tick_x))
        tick_y = max(0, min(h - 1, tick_y))

        cv2.circle(image, (tick_x, tick_y), marker_radius, marker_color, thickness=-1)

        if not draw_labels:
            continue

        label_x = int(round(cx + (distance + 16.0) * math.cos(rad)))
        label_y = int(round(cy - (distance + 16.0) * math.sin(rad)))
        label_x = max(0, min(w - 1, label_x))
        label_y = max(12, min(h - 1, label_y))
        draw_text_with_outline(image, f"{scale_value:.1f}", (label_x, label_y), 0.4, marker_color, 1)


def build_annotated_image(
    image: np.ndarray,
    points: List[Tuple[float, float, float]],
    interpolated_points: List[Tuple[float, float, float]],
    detection: Optional[Tuple[float, Tuple[float, float], Tuple[float, float], Tuple[float, float]]],
    value: float,
    warning: Optional[str],
) -> np.ndarray:
    canvas = image.copy()
    if canvas.ndim == 2:
        canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)

    h, w = canvas.shape[:2]
    if detection is None:
        center = (w / 2.0, h / 2.0)
    else:
        _angle, center, tip, tail = detection
        cv2.line(canvas, (int(round(tail[0])), int(round(tail[1]))), (int(round(tip[0])), int(round(tip[1]))), (0, 0, 255), 2)

        tip_dx = tip[0] - center[0]
        tip_dy = tip[1] - center[1]
        tip_len = math.hypot(tip_dx, tip_dy)
        if tip_len > 0.0:
            extend_len = max(24.0, tip_len * 0.18)
            ux = tip_dx / tip_len
            uy = tip_dy / tip_len
            ext_tip = (tip[0] + ux * extend_len, tip[1] + uy * extend_len)
            draw_dashed_line(canvas, tip, ext_tip, (0, 0, 255), thickness=2)

        cv2.circle(canvas, (int(round(center[0])), int(round(center[1]))), 4, (255, 0, 0), thickness=-1)

    draw_scale_markers(canvas, center, interpolated_points, marker_color=(255, 255, 0), marker_radius=2, draw_labels=False)
    draw_scale_markers(canvas, center, points)

    draw_text_with_outline(canvas, f"value: {value:.2f}", (10, 20), 0.4, (0, 255, 0), 1)
    if warning:
        draw_text_with_outline(canvas, warning, (10, 64), 0.4, (0, 0, 255), 1)
    return canvas


def interpolate_value(angle: float, mapping: List[Tuple[float, float]]) -> float:
    if len(mapping) < 2:
        raise RuntimeError("Interpolation mapping must contain at least two points.")

    ordered = sorted(mapping, key=lambda item: item[0])
    extended = ordered + [(ordered[0][0] + 360.0, ordered[0][1])]

    angle_norm = float(angle)
    while angle_norm < ordered[0][0]:
        angle_norm += 360.0
    while angle_norm > extended[-1][0]:
        angle_norm -= 360.0

    for i in range(len(extended) - 1):
        a1, v1 = extended[i]
        a2, v2 = extended[i + 1]
        if a1 <= angle_norm <= a2:
            if a2 == a1:
                return v2
            fraction = (angle_norm - a1) / (a2 - a1)
            return v1 + fraction * (v2 - v1)

    return extended[-1][1]


def main() -> int:
    args = parse_args()
    try:
        raw = read_input_bytes(args.input)
        image = decode_image(raw)
        detection = detect_pointer(image)

        if detection is None:
            center = (image.shape[1] / 2.0, image.shape[0] / 2.0)
        else:
            center = detection[1]

        angle_value_mapping, scale_points = build_scale_points(args.point)
        interpolated_scale_points = build_interpolated_scale_points(scale_points, spacing=0.1)

        if args.debug:
            warnings: List[str] = []
            if detection is None:
                warnings.append("WARNING: Pointer detection failed.")
                value = -99.99
            else:
                angle = detection[0]
                value = interpolate_value(angle, angle_value_mapping)

            for warning in warnings:
                print(warning, file=sys.stderr)

            annotated = build_annotated_image(
                image,
                scale_points,
                interpolated_scale_points,
                detection,
                value,
                warnings[0] if warnings else None,
            )
            sys.stdout.buffer.write(encode_jpeg(annotated))
            sys.stdout.buffer.flush()
            return 0

        if detection is None:
            print("WARNING: Pointer detection failed.", file=sys.stderr)
            print(f"{-99.99:.2f}")
            return 0

        angle = detection[0]
        value = interpolate_value(angle, angle_value_mapping)
        print(f"{value:.2f}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
