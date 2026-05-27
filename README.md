# HomeAssistant WebCam Sensor

Read an analog gauge from an RTSP camera stream and expose the computed value for Home Assistant.

This repository contains three CLI scripts:

- `download_image.py`: captures one frame from an RTSP stream.
- `prepare_image.py`: crops/rotates/prepares the gauge image for pointer detection.
- `process_image.py`: detects the pointer angle, maps it to your scale points, and prints a numeric value.

## Installation

### 1) Clone and create a virtual environment

```bash
git clone https://github.com/Zergie/HomeAssistant-WebCam-Sensor.git
cd HomeAssistant-WebCam-Sensor
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If OpenCV installation fails with a wheel build error, force binary wheels and install headless OpenCV explicitly:

```bash
pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: opencv-python-headless
pip install -r requirements.txt
```

`opencv-python-headless` is used by this project because it avoids GUI dependencies and is usually more reliable on Home Assistant hosts and containers.

### 3) Verify with tests (optional but recommended)

```bash
pytest -q
```

## Script usage

### 1) Capture frame

```bash
python download_image.py \
  --rtsp-url "rtsp://user:pass@camera-ip:554/av_stream/ch0" \
  --output /tmp/frame.jpg
```

### 2) Prepare image

Use your calibrated center/radius.

```bash
python prepare_image.py \
  --input /tmp/frame.jpg \
  --output /tmp/image.jpg \
  --x 835 --y 400 --radius 350 \
  --rotate 0 \
  --sharpen 8.0
```

### 3) Process gauge value

Pass at least two scale points as `value,angle,distance`.

```bash
python process_image.py \
  --input /tmp/image.jpg \
  --point "0.0,-150,210" \
  --point "1.0,-197,280" \
  --point "1.5,-227,280" \
  --point "2.0,95,275" \
  --point "2.5,57,275" \
  --point "3.0,25,275" \
  --point "4.0,-32,230"
```

The script prints a single value to stdout (for example `1.73`).

## Home Assistant sensor integration

The easiest integration is a `command_line` sensor that executes all three steps and returns one numeric value.

### 1) Create a wrapper script

Create `/config/scripts/gauge_sensor.sh` in Home Assistant (or on the host where Home Assistant can execute commands):

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/config/homeassistant-webcam-sensor"
PYTHON="$PROJECT_DIR/.venv/bin/python"

RTSP_URL="rtsp://user:pass@camera-ip:554/av_stream/ch0"
X="835"
Y="400"
RADIUS="350"
ROTATE="0"
SHARPEN="8.0"

"$PYTHON" "$PROJECT_DIR/download_image.py" \
  --rtsp-url "$RTSP_URL" | \
"$PYTHON" "$PROJECT_DIR/prepare_image.py" \
  --x "$X" --y "$Y" --radius "$RADIUS" --rotate "$ROTATE" --sharpen "$SHARPEN" | \
"$PYTHON" "$PROJECT_DIR/process_image.py" \
  --point "0.0,-150,210" \
  --point "1.0,-197,280" \
  --point "1.5,-227,280" \
  --point "2.0,95,275" \
  --point "2.5,57,275" \
  --point "3.0,25,275" \
  --point "4.0,-32,230"
```

Make it executable:

```bash
chmod +x /config/scripts/gauge_sensor.sh
```

### 2) Add a command_line sensor

In `configuration.yaml`:

```yaml
command_line:
  - sensor:
      name: Boiler Pressure
      command: "/config/scripts/gauge_sensor.sh"
      unit_of_measurement: "bar"
      scan_interval: 60
      value_template: "{{ value | float(-99.99) }}"
```

Restart Home Assistant.

### 3) Optional availability template

If you want to mark `-99.99` as unavailable, add a template sensor:

```yaml
template:
  - sensor:
      - name: Boiler Pressure Filtered
        unit_of_measurement: "bar"
        state: >-
          {% set v = states('sensor.boiler_pressure') | float(-99.99) %}
          {{ iif(v == -99.99, this.state, v) }}
        availability: >-
          {{ states('sensor.boiler_pressure') not in ['unknown', 'unavailable', 'none'] }}
```

## Calibration tips

- Use `prepare_image.py --debug` first to verify center and radius overlay.
- Use `process_image.py --debug` to render pointer line and scale points on output image.
- Add more `--point` entries around nonlinear parts of the dial for better interpolation accuracy.
- Keep the camera fixed and stable; angle shifts will require recalibration.

## Notes

- `process_image.py` returns `-99.99` when pointer detection fails.
- The scripts are stream-friendly: they read from stdin and write to stdout if file paths are omitted.
- If OpenCV install is slow on low-power hardware, pre-build the venv on similar architecture or use a container image with OpenCV already installed.

## HAOS custom add-on (Python 3.11)

If you use Home Assistant OS with Python 3.12 in Core, use the custom add-on in this repository instead of installing OpenCV inside Home Assistant Core.

Add-on files are under `webcam_gauge_sensor` and the add-on image uses Python 3.11.

Important: this is a Home Assistant Add-on repository, not a HACS integration repository.

### 1) Add this repository as an add-on repository

In Home Assistant:

- Go to Settings -> Add-ons -> Add-on Store.
- Open menu (top-right) -> Repositories.
- Add this repository URL:

Do not add this repository in HACS. HACS validates integration/plugin structure and will show a "Repository structure ... is not compliant" error for add-on repositories.

```text
https://github.com/Zergie/HomeAssistant-WebCam-Sensor
```

### 2) Install and configure add-on

Install `WebCam Gauge Sensor` and set options similar to:

```yaml
rtsp_url: rtsp://user:pass@camera-ip:554/av_stream/ch0
x: 835
y: 400
radius: 350
rotate: 0.0
sharpen: 8.0
points:
  - 0.0,-150,210
  - 1.0,-197,280
  - 1.5,-227,280
  - 2.0,95,275
  - 2.5,57,275
  - 3.0,25,275
  - 4.0,-32,230
poll_interval: 60
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_username: ""
mqtt_password: ""
mqtt_topic: sensors/boiler_pressure
```

Start the add-on. It publishes the latest value (retained) to the configured MQTT topic.

If installation/build failed before, update to the latest repository commit and try install again.
The add-on now uses Debian system packages (`python3-opencv`) instead of pip-building OpenCV wheels.

If build still fails, check Supervisor logs in Home Assistant:

- Settings -> System -> Logs -> Supervisor
- or run `ha supervisor logs` in the HA CLI

### 3) Create MQTT sensor in Home Assistant

```yaml
mqtt:
  sensor:
    - name: Boiler Pressure
      state_topic: sensors/boiler_pressure
      unit_of_measurement: bar
      value_template: "{{ value | float(-99.99) }}"
```

### 4) Optional: treat fallback value as unavailable

```yaml
template:
  - sensor:
      - name: Boiler Pressure Filtered
        unit_of_measurement: "bar"
        state: >-
          {% set v = states('sensor.boiler_pressure') | float(-99.99) %}
          {{ iif(v == -99.99, this.state, v) }}
        availability: >-
          {{ states('sensor.boiler_pressure') not in ['unknown', 'unavailable', 'none'] }}
```
