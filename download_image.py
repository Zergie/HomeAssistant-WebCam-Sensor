#!/usr/bin/env python3
import argparse
import sys
import time
from typing import Optional

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture one image frame from an RTSP stream.")
    parser.add_argument("--rtsp-url", required=True, help="RTSP stream URL.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Open/read timeout in seconds. Default: 10")
    parser.add_argument("--retries", type=int, default=3, help="Capture retries. Default: 3")
    parser.add_argument("--output", help="Write image bytes to file instead of stdout.")
    return parser.parse_args()


def capture_image_bytes(rtsp_url: str, timeout: float, retries: int) -> bytes:
    last_error: Optional[Exception] = None
    timeout_ms = int(max(timeout, 0.1) * 1000)
    for _ in range(max(retries, 1)):
        cap: Optional[cv2.VideoCapture] = None
        try:
            # Set timeout at stream open where supported by the backend.
            if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC") and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                cap = cv2.VideoCapture(
                    rtsp_url,
                    cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms, cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms],
                )
            else:
                cap = cv2.VideoCapture(rtsp_url)

            if not cap.isOpened():
                raise RuntimeError("Failed to open RTSP stream.")

            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("Failed to read frame from RTSP stream.")

            encoded_ok, encoded = cv2.imencode(".jpg", frame)
            if not encoded_ok:
                raise RuntimeError("Failed to encode frame as JPEG.")
            return encoded.tobytes()
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
        finally:
            if cap is not None:
                cap.release()
    raise RuntimeError(f"Failed to capture RTSP frame after {max(retries, 1)} attempt(s): {last_error}")


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
        image_bytes = capture_image_bytes(args.rtsp_url, args.timeout, args.retries)
        write_output(image_bytes, args.output)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
