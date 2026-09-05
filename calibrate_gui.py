#!/usr/bin/env python3
"""Mouse-driven editor for the gauge center and scale points."""

import argparse
import math
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import cv2
import numpy as np
import yaml
from webcam_gauge_sensor.prepare_image import _build_pointer_ready_grayscale


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "webcam_gauge_sensor" / "config.yaml"
SAVED_CONFIG = ROOT / "calibration-settings.yaml"


def load_config(path: Path) -> dict[str, object]:
    """Read either an add-on manifest or a Home Assistant options file."""
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError("Configuration must be a YAML mapping.")
    return settings.get("options", settings)


class ConfigDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def represent_string(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="'" if value == "y" else None)


ConfigDumper.add_representer(str, represent_string)


def format_config(settings: dict[str, object]) -> str:
    return yaml.dump(settings, Dumper=ConfigDumper, sort_keys=False, allow_unicode=True)


def parse_point(text: str) -> list[float]:
    value, angle, distance = (float(part.strip()) for part in text.split(","))
    return [value, angle, distance]


def point_xy(center: tuple[float, float], point: list[float], rotate: float = 0.0) -> tuple[float, float]:
    _, angle, distance = point
    radians = math.radians(angle - rotate)
    return center[0] + distance * math.cos(radians), center[1] - distance * math.sin(radians)


def move_point(
    center: tuple[float, float], old_angle: float, x: float, y: float, rotate: float = 0.0
) -> tuple[float, float]:
    dx, dy = x - center[0], center[1] - y
    angle = math.degrees(math.atan2(dy, dx)) + rotate
    # Keep the configured angle's revolution (for example -227 rather than 133).
    angle += 360.0 * round((old_angle - angle) / 360.0)
    return angle, math.hypot(dx, dy)


def radius_from_xy(center: tuple[float, float], x: float, y: float) -> int:
    return max(1, round(math.hypot(x - center[0], y - center[1])))


def load_frame(args: argparse.Namespace) -> bytes:
    if args.input:
        return args.input.read_bytes()
    rtsp_url = args.rtsp_url or os.environ.get("RTSP_URL")
    if not rtsp_url:
        raise RuntimeError("Provide --input, --rtsp-url, or set RTSP_URL.")
    result = subprocess.run(
        [sys.executable, str(ROOT / "webcam_gauge_sensor" / "download_image.py"), "--rtsp-url", rtsp_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout


class CalibrationApp:
    def __init__(
        self, root: tk.Tk, args: argparse.Namespace, settings: dict[str, object], frame: bytes
    ) -> None:
        self.root = root
        self.args = args
        self.settings = settings.copy()
        self.frame = frame
        self.image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if self.image is None:
            raise RuntimeError("Could not decode the camera frame.")

        self.x = float(args.x if args.x is not None else settings["x"])
        self.y = float(args.y if args.y is not None else settings["y"])
        self.radius = int(args.radius if args.radius is not None else settings["radius"])
        self.rotate = float(args.rotate if args.rotate is not None else settings["rotate"])
        self.sharpen = float(args.sharpen if args.sharpen is not None else settings["sharpen"])
        point_texts = args.point if args.point else settings["points"]
        self.points = [parse_point(str(point)) for point in point_texts]
        if len(self.points) < 2:
            raise RuntimeError("At least two configured points are required.")

        height, width = self.image.shape[:2]
        self.scale = min(1.0, (root.winfo_screenwidth() - 390) / width, (root.winfo_screenheight() - 150) / height)
        self.offset_x = self.offset_y = 0.0

        root.title("Gauge calibration")
        body = ttk.Frame(root, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)
        self.canvas = tk.Canvas(body, width=int(width*self.scale), height=int(height*self.scale), highlightthickness=0)
        self.canvas.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.output = tk.Text(body, width=38, height=20, wrap="none")
        self.output.grid(row=3, column=1, sticky="nsew", padx=(10, 0))
        self.status = ttk.Label(body, text="", wraplength=290)
        self.status.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=8)
        buttons = ttk.Frame(body)
        buttons.grid(row=1, column=1, sticky="ew", padx=(10, 0))
        ttk.Button(buttons, text="Run processor", command=self.run_processor).pack(side="left")
        ttk.Button(buttons, text="Copy config", command=self.copy_config).pack(side="left", padx=8)
        ttk.Button(buttons, text="Apply pasted options", command=self.apply_options).pack(side="left")

        controls = ttk.Frame(body)
        controls.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.slider_job = None
        self.sliders = {}
        for name, lower, upper, resolution in (("rotate", -180, 180, 0.1), ("sharpen", 0, 20, 0.1)):
            slider = tk.Scale(controls, label=name.capitalize(), from_=lower, to=upper,
                              resolution=resolution, orient="horizontal", length=290)
            slider.set(getattr(self, name))
            slider.configure(command=lambda value, field=name: self.change_slider(field, value))
            slider.pack(fill="x")
            self.sliders[name] = slider

        self.dragging: int | str | None = None
        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.bind("<Configure>", lambda _event: self.draw(update_text=False))
        root.bind("<Escape>", lambda _event: self.close())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.draw()
        root.after(50, self.run_processor)

    def draw(self, update_text: bool = True) -> None:
        height, width = self.image.shape[:2]
        canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if canvas_w > 1 and canvas_h > 1:
            self.scale = min(canvas_w / width, canvas_h / height)
        self.offset_x = max(0, (canvas_w - width*self.scale) / 2)
        # Bottom-align the preview with the settings text box.
        self.offset_y = max(0, canvas_h - height*self.scale)
        matrix = cv2.getRotationMatrix2D((self.x, self.y), self.rotate, 1.0)
        rotated = cv2.warpAffine(self.image, matrix, (width, height))
        preview = _build_pointer_ready_grayscale(rotated, self.sharpen)
        shown = cv2.resize(preview, (max(1, round(width*self.scale)), max(1, round(height*self.scale))))
        ppm = f"P5\n{shown.shape[1]} {shown.shape[0]}\n255\n".encode() + shown.tobytes()
        self.photo = tk.PhotoImage(data=ppm, format="PPM")
        self.canvas.itemconfigure(self.image_item, image=self.photo)
        self.canvas.coords(self.image_item, self.offset_x, self.offset_y)
        self.canvas.delete("marker")
        sx, sy, sr = self.x * self.scale + self.offset_x, self.y * self.scale + self.offset_y, self.radius * self.scale
        self.canvas.create_oval(sx - sr, sy - sr, sx + sr, sy + sr, outline="#35d04f", width=2, tags="marker")
        self.canvas.create_oval(sx + sr - 7, sy - 7, sx + sr + 7, sy + 7, fill="#35d04f", outline="black", width=2, tags="marker")
        self.draw_outlined_text(sx + sr + 10, sy - 10, f"radius {self.radius}")
        self.canvas.create_line(sx - 10, sy, sx + 10, sy, fill="#ff4040", width=3, tags="marker")
        self.canvas.create_line(sx, sy - 10, sx, sy + 10, fill="#ff4040", width=3, tags="marker")
        for value, angle, distance in self.points:
            px, py = point_xy((self.x, self.y), [value, angle, distance])
            px, py = px * self.scale + self.offset_x, py * self.scale + self.offset_y
            self.canvas.create_line(sx, sy, px, py, fill="#ffe04b", dash=(3, 4), tags="marker")
            self.canvas.create_oval(px - 6, py - 6, px + 6, py + 6, fill="#ffe04b", tags="marker")
            self.draw_outlined_text(px + 9, py - 9, f"{value:g}")
        if update_text:
            self.output.delete("1.0", "end")
            self.output.insert("1.0", self.config_text())

    def draw_outlined_text(self, x: float, y: float, text: str) -> None:
        for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
            self.canvas.create_text(x + dx, y + dy, text=text, fill="black", anchor="sw", tags="marker")
        self.canvas.create_text(x, y, text=text, fill="white", anchor="sw", tags="marker")

    def nearest_handle(self, x: float, y: float) -> int | str | None:
        handles = [("center", self.x, self.y), ("radius", self.x + self.radius, self.y)] + [
            (index, *point_xy((self.x, self.y), point)) for index, point in enumerate(self.points)
        ]
        target, distance = min(((name, math.hypot(x - px, y - py)) for name, px, py in handles), key=lambda item: item[1])
        return target if distance * self.scale <= 15 else None

    def start_drag(self, event: tk.Event) -> None:
        self.dragging = self.nearest_handle((event.x-self.offset_x) / self.scale, (event.y-self.offset_y) / self.scale)
        self.drag_center = (self.x, self.y)

    def drag(self, event: tk.Event) -> None:
        x = min(max((event.x-self.offset_x) / self.scale, 0.0), self.image.shape[1] - 1.0)
        y = min(max((event.y-self.offset_y) / self.scale, 0.0), self.image.shape[0] - 1.0)
        if self.dragging == "center":
            inverse = cv2.getRotationMatrix2D(self.drag_center, -self.rotate, 1.0)
            self.x, self.y = inverse @ np.array([x, y, 1.0])
        elif self.dragging == "radius":
            self.radius = radius_from_xy((self.x, self.y), x, y)
        elif isinstance(self.dragging, int):
            point = self.points[self.dragging]
            point[1], point[2] = move_point((self.x, self.y), point[1], x, y)
        self.draw()

    def stop_drag(self, _event: tk.Event) -> None:
        if self.dragging is not None:
            self.dragging = None
            self.run_processor()

    def point_texts(self) -> list[str]:
        return [f"{value:g},{angle:.1f},{distance:.1f}" for value, angle, distance in self.points]

    def config_text(self) -> str:
        settings = self.settings.copy()
        settings.update(x=round(self.x), y=round(self.y), radius=self.radius,
                        rotate=self.rotate, sharpen=self.sharpen, points=self.point_texts())
        return format_config(settings)

    def save_settings(self) -> None:
        self.args.settings.write_text(self.config_text(), encoding="utf-8")

    def close(self) -> None:
        self.save_settings()
        self.root.destroy()

    def change_slider(self, name: str, value: str) -> None:
        setattr(self, name, float(value))
        self.draw()
        self.save_settings()
        if self.slider_job is not None:
            self.root.after_cancel(self.slider_job)
        self.slider_job = self.root.after(300, self.process_slider)

    def process_slider(self) -> None:
        self.slider_job = None
        self.run_processor()

    def copy_config(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.config_text())
        self.status.config(text="Configuration copied to the clipboard.")

    def apply_options(self) -> None:
        try:
            incoming = yaml.safe_load(self.output.get("1.0", "end"))
            if not isinstance(incoming, dict):
                raise ValueError("Paste a YAML options mapping.")
            settings = self.settings | incoming
            values = {name: float(settings[name]) for name in ("x", "y", "radius", "rotate", "sharpen")}
            if not all(math.isfinite(v) for v in values.values()) or values["radius"] < 1 or values["sharpen"] < 0:
                raise ValueError("Use finite numbers, a positive radius and nonnegative sharpen.")
            points = [parse_point(str(p)) for p in settings["points"]]
            if len(points) < 2 or any(not all(math.isfinite(v) for v in p) or p[2] <= 0 for p in points):
                raise ValueError("Provide at least two valid scale points with positive distances.")
        except (ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
            self.status.config(text=f"Invalid options: {exc}")
            return
        self.settings = settings
        for name, value in values.items():
            setattr(self, name, int(value) if name == "radius" else value)
        self.points = points
        for name, slider in self.sliders.items():
            slider.configure(command="")
            slider.configure(from_=min(float(slider.cget("from")), getattr(self, name)),
                             to=max(float(slider.cget("to")), getattr(self, name)))
            slider.set(getattr(self, name))
            slider.configure(command=lambda value, field=name: self.change_slider(field, value))
        self.draw()
        self.run_processor()

    def run_processor(self) -> None:
        self.save_settings()
        prepare = subprocess.run(
            [sys.executable, str(ROOT / "webcam_gauge_sensor" / "prepare_image.py"),
             "--x", str(round(self.x)), "--y", str(round(self.y)), "--radius", str(self.radius),
             "--rotate", str(self.rotate), "--sharpen", str(self.sharpen)],
            input=self.frame, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if prepare.returncode != 0:
            self.status.config(text=prepare.stderr.decode(errors="replace").strip())
            return
        command = [sys.executable, str(ROOT / "webcam_gauge_sensor" / "process_image.py")]
        for point in self.point_texts():
            command.extend(("--point", point))
        result = subprocess.run(command, input=prepare.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        error = (prepare.stderr + result.stderr).decode(errors="replace").strip()
        value = result.stdout.decode(errors="replace").strip()
        self.status.config(text=error or f"process_image.py value: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="Saved camera frame; otherwise RTSP_URL is used.")
    source.add_argument("--rtsp-url", help="Capture a frame from this URL; defaults to RTSP_URL.")
    parser.add_argument("--config", type=Path, help="Import add-on config.yaml or Home Assistant options YAML.")
    parser.add_argument("--settings", type=Path, default=SAVED_CONFIG, help="File for automatically saved settings.")
    parser.add_argument("--x", type=int)
    parser.add_argument("--y", type=int)
    parser.add_argument("--radius", type=int)
    parser.add_argument("--rotate", type=float)
    parser.add_argument("--sharpen", type=float)
    parser.add_argument("--point", action="append", help="Override a point as VALUE,ANGLE,DISTANCE; repeat as needed.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = load_config(DEFAULT_CONFIG)
        if args.config:
            settings.update(load_config(args.config))
        elif args.settings.exists():
            settings.update(load_config(args.settings))
        args.rtsp_url = args.rtsp_url or os.environ.get("RTSP_URL") or settings.get("rtsp_url")
        settings["rtsp_url"] = args.rtsp_url or ""
        frame = load_frame(args)
        root = tk.Tk()
        CalibrationApp(root, args, settings, frame)
        root.mainloop()
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
