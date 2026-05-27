#!/usr/bin/env python3
"""Compatibility wrapper for local CLI usage.

Source of truth lives in webcam_gauge_sensor/prepare_image.py.
"""

from webcam_gauge_sensor.prepare_image import *  # noqa: F401,F403
from webcam_gauge_sensor.prepare_image import main as _main


if __name__ == "__main__":
    raise SystemExit(_main())