# AGENTS.md

This repository contains Python scripts for reading an analog gauge from an RTSP camera and a Home Assistant custom add-on.

## Purpose

Use this file as the canonical agent instruction entry point for future work in this repository.

## Current State

- Core scripts: `download_image.py`, `prepare_image.py`, `process_image.py`.
- Tests: `pytest` tests under `tests/`.
- Home Assistant add-on scaffold: `ha-addon/webcam_sensor`.

## Agent Behavior In This Repo

- Keep changes small and explicit until a baseline project structure exists.
- Before implementing features, inspect the current tree and infer stack from committed files.
- When introducing initial tooling (for example lint/test/build), document exact commands in this file.
- Prefer linking to repository docs (README, CONTRIBUTING, docs/) once they exist rather than duplicating content here.

## Verified Commands

- Install local dev dependencies: `pip install -r requirements.txt`
- Run tests: `pytest -q`
- Script pipeline example:
	- `python download_image.py --rtsp-url "..." --output /tmp/frame.jpg`
	- `python prepare_image.py --input /tmp/frame.jpg --output /tmp/image.jpg --x 835 --y 400 --radius 350 --sharpen 8.0`
	- `python process_image.py --input /tmp/image.jpg --point "0.0,-150,210" --point "1.0,-197,280"`

## Add-on Notes

- Add-on repository metadata: `ha-addon/repository.yaml`
- Add-on slug: `webcam_gauge_sensor`
- Add-on runtime entrypoint: `ha-addon/webcam_sensor/run.py`

## Update Checklist (when project files are added)

- Add verified build, test, and run commands.
- Add key directories and ownership boundaries.
- Add coding and testing conventions unique to this repository.
- Add known environment pitfalls and setup notes.