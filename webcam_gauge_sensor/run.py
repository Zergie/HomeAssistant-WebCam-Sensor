#!/usr/bin/env python3
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import paho.mqtt.client as mqtt

import download_image
import prepare_image
import process_image


_LOG = logging.getLogger("webcam_gauge_addon")
_OPTIONS_PATH = Path("/data/options.json")


@dataclass
class Settings:
    rtsp_url: str
    x: int
    y: int
    radius: int
    rotate: float
    sharpen: float
    points: List[str]
    poll_interval: int
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_topic: str


def _load_options() -> dict:
    if not _OPTIONS_PATH.exists():
        raise RuntimeError("Missing /data/options.json. Configure add-on options in Home Assistant.")

    with _OPTIONS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _str_or_default(value: Optional[str], default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def load_settings() -> Settings:
    raw = _load_options()

    rtsp_url = _str_or_default(raw.get("rtsp_url")).strip()
    if not rtsp_url:
        raise RuntimeError("Option 'rtsp_url' is required.")

    points = raw.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise RuntimeError("Option 'points' must contain at least two entries.")

    return Settings(
        rtsp_url=rtsp_url,
        x=int(raw.get("x", 835)),
        y=int(raw.get("y", 400)),
        radius=int(raw.get("radius", 350)),
        rotate=float(raw.get("rotate", 0.0)),
        sharpen=float(raw.get("sharpen", 8.0)),
        points=[str(p) for p in points],
        poll_interval=max(5, int(raw.get("poll_interval", 60))),
        mqtt_host=_str_or_default(raw.get("mqtt_host"), "core-mosquitto"),
        mqtt_port=int(raw.get("mqtt_port", 1883)),
        mqtt_username=_str_or_default(raw.get("mqtt_username")),
        mqtt_password=_str_or_default(raw.get("mqtt_password")),
        mqtt_topic=_str_or_default(raw.get("mqtt_topic"), "sensors/boiler_pressure"),
    )


def compute_value(settings: Settings) -> float:
    frame_bytes = download_image.capture_image_bytes(settings.rtsp_url, timeout=10.0, retries=3)
    frame = prepare_image.decode_image(frame_bytes)

    prepared = prepare_image.prepare_image(
        frame,
        rotate=settings.rotate,
        debug=False,
        x=settings.x,
        y=settings.y,
        radius=settings.radius,
        sharpen=settings.sharpen,
    )

    if prepared.ndim == 2:
        prepared = np.dstack((prepared, prepared, prepared))

    angle_value_mapping, _scale_points = process_image.build_scale_points(settings.points)
    detection = process_image.detect_pointer(prepared)
    if detection is None:
        return -99.99

    angle = detection[0]
    value = process_image.interpolate_value(angle, angle_value_mapping)
    return float(round(value, 2))


def _build_client(settings: Settings) -> mqtt.Client:
    client_id = f"webcam-gauge-{os.getpid()}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)

    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)

    return client


def publish_value(client: mqtt.Client, settings: Settings, value: float) -> None:
    payload = f"{value:.2f}"
    result = client.publish(settings.mqtt_topic, payload=payload, qos=1, retain=True)
    result.wait_for_publish(timeout=5)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = load_settings()
    _LOG.info("Starting gauge publisher. topic=%s poll_interval=%ss", settings.mqtt_topic, settings.poll_interval)

    client = _build_client(settings)
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)
    client.loop_start()

    try:
        while True:
            try:
                value = compute_value(settings)
                publish_value(client, settings, value)
                _LOG.info("Published %s=%0.2f", settings.mqtt_topic, value)
            except Exception as exc:
                _LOG.exception("Gauge processing failed: %s", exc)
                try:
                    publish_value(client, settings, -99.99)
                except Exception:
                    _LOG.exception("Failed to publish fallback value")

            time.sleep(settings.poll_interval)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
