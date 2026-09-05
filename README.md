# HomeAssistant WebCam Sensor

Read an analog gauge from an RTSP camera stream and expose the computed value for Home Assistant.

This repository provides a Home Assistant OS custom add-on that reads an analog gauge from an RTSP camera stream and publishes values over MQTT.

## What the add-on does

The `WebCam Gauge Sensor` add-on runs a full gauge-reading pipeline on each poll interval:

1. Captures a frame from your RTSP camera.
2. Crops and sharpens the configured gauge area.
3. Detects the needle angle and maps it to your configured scale points.
4. Publishes the computed numeric value to the configured MQTT topic.

This gives Home Assistant a stable sensor value from a physical analog gauge without requiring direct hardware integration.

Example annotated gauge output:

![Annotated gauge output](.images/gauge_annotated.jpeg)

Example Home Assistant view:

![Home Assistant sensor view](.images/Screenshot%202026-05-28%20051459.png)

## Calibration Notebook

The calibration GUI includes rotation (-180 to 180 degrees) and sharpen (0 to 20) sliders.
The preview rotates and sharpens immediately; scale markers stay in their calibrated positions.
The image fits the resized window while preserving its aspect ratio. Paste Home Assistant
options into the settings box and click **Apply pasted options** to load and save them.
The current camera frame remains in use when applying options; a changed camera URL is used
on the next launch.
It automatically saves settings to `calibration-settings.yaml` after edits and restores them
on launch. This local file contains the full Home Assistant options, including credentials,
and is excluded from Git. To import existing Home Assistant options, save them as YAML and run
`python calibrate_gui.py --config path/to/options.yaml`. Copy config exports the full options
with the edited calibration values. Install GUI dependencies with `pip install -r requirements.txt`.

Use [calibrate.ipynb](calibrate.ipynb) to find and validate your gauge settings before finalizing add-on options.

For mouse-driven calibration, either save a camera frame or set `RTSP_URL` as in the notebook, then run:

```text
python calibrate_gui.py --input path/to/frame.jpg
python calibrate_gui.py
```

Drag the red center, green radius handle, or any yellow scale point. The tool loads the initial `x`, `y`, `radius`, and `points` from `webcam_gauge_sensor/config.yaml`, follows the notebook's download/prepare/process workflow, and shows a configuration block ready to copy into Home Assistant.

When to use it:

1. During first-time setup, to determine `x`, `y`, `radius`, `sharpen`, and `points` values.
2. After camera movement, zoom/focus changes, or lighting changes that affect needle detection.
3. When MQTT readings are unstable, incorrect, or frequently return the fallback value.

After calibration, copy the final values from the notebook into the add-on configuration in Home Assistant.

## Installation

### HAOS custom add-on (Python 3.11)

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
