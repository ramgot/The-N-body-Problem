#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trajectory loader and Tkinter viewer for N-body simulation output."""

from __future__ import annotations

import argparse
import csv
import math
import os
import queue
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    TKINTER_IMPORT_ERROR = None
except ImportError as exc:
    tk = None
    filedialog = messagebox = ttk = None
    TKINTER_IMPORT_ERROR = exc

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "benchmark_results"
MPLCONFIG_DIR = RESULTS_DIR / "matplotlib_cache"
MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

import numpy as np

if TKINTER_IMPORT_ERROR is None:
    import matplotlib

    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
else:
    FigureCanvasTkAgg = NavigationToolbar2Tk = Figure = None


AU = 1.496e11
BINARY_FILE_MAGIC = b"NBODYTRJBIN1\0\0\0\0"
BINARY_FRAME_MAGIC = b"FRAME001"
BINARY_HEADER_STRUCT = struct.Struct("<16sIIIII")
BINARY_FRAME_STRUCT = struct.Struct("<8sQdQ")
BINARY_ARRAY_NAMES = ("mass", "x", "y", "z", "vx", "vy", "vz", "ax", "ay", "az")


@dataclass
class TrajectoryData:
    path: Path
    steps: np.ndarray
    times: np.ndarray
    positions: np.ndarray
    masses: np.ndarray | None
    total_frames: int
    total_bodies: int
    sampled_frames: int
    sampled_bodies: int
    source_format: str


def detect_trajectory_format(path: str | Path, requested: str = "auto") -> str:
    requested = (requested or "auto").lower()
    if requested in {"binary", "bin"}:
        return "binary"
    if requested == "csv":
        return "csv"
    if requested != "auto":
        raise ValueError("Формат должен быть auto, csv или binary")

    path = Path(path)
    with path.open("rb") as trajectory_file:
        prefix = trajectory_file.read(len(BINARY_FILE_MAGIC))
    if prefix == BINARY_FILE_MAGIC:
        return "binary"
    if path.suffix.lower() == ".bin":
        return "binary"
    return "csv"


def _sample_indices(total: int, limit: int) -> list[int]:
    if total <= 0:
        return []
    if limit <= 0 or total <= limit:
        return list(range(total))
    if limit == 1:
        return [0]
    return sorted({round(index * (total - 1) / (limit - 1)) for index in range(limit)})


def _parse_csv_step(row: list[str]) -> int | None:
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _iter_csv_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(line for line in csvfile if not line.lstrip().startswith("#"))
        for row in reader:
            if row:
                yield row


def _scan_csv_trajectory(path: Path) -> tuple[int, int]:
    frame_count = 0
    first_frame_bodies = 0
    current_step = None
    in_first_frame = True

    for row in _iter_csv_rows(path):
        step = _parse_csv_step(row)
        if step is None or len(row) < 7:
            continue
        if current_step is None or step != current_step:
            current_step = step
            frame_count += 1
            in_first_frame = frame_count == 1
        if in_first_frame:
            first_frame_bodies += 1

    return frame_count, first_frame_bodies


def read_csv_trajectory(path: str | Path, max_frames: int = 600, max_bodies: int = 200) -> TrajectoryData:
    path = Path(path)
    total_frames, total_bodies = _scan_csv_trajectory(path)
    if total_frames == 0 or total_bodies == 0:
        raise ValueError("CSV-файл не содержит кадров траектории")

    selected_indices = _sample_indices(total_frames, max_frames)
    selected_lookup = {frame_index: sample_index for sample_index, frame_index in enumerate(selected_indices)}
    sampled_frames = len(selected_indices)
    sampled_bodies = min(total_bodies, max_bodies)

    steps = np.zeros(sampled_frames, dtype=np.uint64)
    times = np.zeros(sampled_frames, dtype=np.float64)
    masses = np.full(sampled_bodies, np.nan, dtype=np.float64)
    positions = np.full((sampled_frames, sampled_bodies, 3), np.nan, dtype=np.float64)

    current_step = None
    frame_index = -1
    for row in _iter_csv_rows(path):
        step = _parse_csv_step(row)
        if step is None or len(row) < 7:
            continue
        if current_step is None or step != current_step:
            current_step = step
            frame_index += 1

        sample_index = selected_lookup.get(frame_index)
        if sample_index is None:
            continue

        try:
            body_index = int(row[2])
        except (TypeError, ValueError):
            continue
        if body_index < 0 or body_index >= sampled_bodies:
            continue

        try:
            steps[sample_index] = int(row[0])
            times[sample_index] = float(row[1])
            if sample_index == 0:
                masses[body_index] = float(row[3])
            positions[sample_index, body_index, 0] = float(row[4])
            positions[sample_index, body_index, 1] = float(row[5])
            positions[sample_index, body_index, 2] = float(row[6])
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"Некорректная строка траектории CSV: {row}") from exc

    if np.isnan(masses).all():
        masses = None
    return TrajectoryData(
        path=path,
        steps=steps,
        times=times,
        positions=positions,
        masses=masses,
        total_frames=total_frames,
        total_bodies=total_bodies,
        sampled_frames=sampled_frames,
        sampled_bodies=sampled_bodies,
        source_format="csv",
    )


def _read_binary_header(binary_file) -> tuple[str, int, int, int]:
    raw_header = binary_file.read(BINARY_HEADER_STRUCT.size)
    if len(raw_header) != BINARY_HEADER_STRUCT.size:
        raise ValueError("Бинарный файл траектории слишком короткий")
    magic, version, endian_marker, scalar_size, arrays_per_frame, layout = BINARY_HEADER_STRUCT.unpack(raw_header)
    if magic != BINARY_FILE_MAGIC:
        raise ValueError("Неизвестный magic-заголовок бинарной траектории")
    if endian_marker != 0x01020304:
        raise ValueError("Неподдерживаемый порядок байтов бинарной траектории")
    if version != 1 or scalar_size != 8 or arrays_per_frame != len(BINARY_ARRAY_NAMES) or layout != 1:
        raise ValueError("Неподдерживаемая версия бинарной траектории")
    return "<f8", scalar_size, arrays_per_frame, layout


def _scan_binary_trajectory(path: Path) -> tuple[str, list[tuple[int, float, int, int]]]:
    frames = []
    with path.open("rb") as binary_file:
        dtype, scalar_size, arrays_per_frame, _layout = _read_binary_header(binary_file)
        while True:
            frame_offset = binary_file.tell()
            raw_frame = binary_file.read(BINARY_FRAME_STRUCT.size)
            if not raw_frame:
                break
            if len(raw_frame) != BINARY_FRAME_STRUCT.size:
                raise ValueError("Поврежденная запись кадра в бинарной траектории")
            frame_magic, step, time_s, n_bodies = BINARY_FRAME_STRUCT.unpack(raw_frame)
            if frame_magic != BINARY_FRAME_MAGIC:
                raise ValueError(f"Некорректный кадр бинарной траектории по смещению {frame_offset}")
            data_offset = binary_file.tell()
            frame_bytes = arrays_per_frame * int(n_bodies) * scalar_size
            binary_file.seek(frame_bytes, os.SEEK_CUR)
            frames.append((int(step), float(time_s), int(n_bodies), data_offset))
    return dtype, frames


def _read_binary_array(binary_file, dtype: np.dtype, n_bodies: int, sampled_bodies: int) -> np.ndarray:
    raw = binary_file.read(sampled_bodies * dtype.itemsize)
    if len(raw) != sampled_bodies * dtype.itemsize:
        raise ValueError("Неожиданный конец бинарной траектории")
    values = np.frombuffer(raw, dtype=dtype).astype(np.float64, copy=True)
    remaining = n_bodies - sampled_bodies
    if remaining > 0:
        binary_file.seek(remaining * dtype.itemsize, os.SEEK_CUR)
    return values


def read_binary_trajectory(path: str | Path, max_frames: int = 600, max_bodies: int = 200) -> TrajectoryData:
    path = Path(path)
    dtype_name, frames = _scan_binary_trajectory(path)
    if not frames:
        raise ValueError("Бинарный файл не содержит кадров траектории")

    dtype = np.dtype(dtype_name)
    total_frames = len(frames)
    total_bodies = frames[0][2]
    if any(frame[2] != total_bodies for frame in frames):
        raise ValueError("В бинарной траектории меняется число тел между кадрами")

    selected_indices = _sample_indices(total_frames, max_frames)
    selected_frames = [frames[index] for index in selected_indices]
    sampled_frames = len(selected_frames)
    sampled_bodies = min(total_bodies, max_bodies)

    steps = np.zeros(sampled_frames, dtype=np.uint64)
    times = np.zeros(sampled_frames, dtype=np.float64)
    masses = np.zeros(sampled_bodies, dtype=np.float64)
    positions = np.zeros((sampled_frames, sampled_bodies, 3), dtype=np.float64)

    with path.open("rb") as binary_file:
        _read_binary_header(binary_file)
        for sample_index, (step, time_s, n_bodies, data_offset) in enumerate(selected_frames):
            steps[sample_index] = step
            times[sample_index] = time_s
            binary_file.seek(data_offset, os.SEEK_SET)

            frame_mass = _read_binary_array(binary_file, dtype, n_bodies, sampled_bodies)
            frame_x = _read_binary_array(binary_file, dtype, n_bodies, sampled_bodies)
            frame_y = _read_binary_array(binary_file, dtype, n_bodies, sampled_bodies)
            frame_z = _read_binary_array(binary_file, dtype, n_bodies, sampled_bodies)

            if sample_index == 0:
                masses[:] = frame_mass
            positions[sample_index, :, 0] = frame_x
            positions[sample_index, :, 1] = frame_y
            positions[sample_index, :, 2] = frame_z

    return TrajectoryData(
        path=path,
        steps=steps,
        times=times,
        positions=positions,
        masses=masses,
        total_frames=total_frames,
        total_bodies=total_bodies,
        sampled_frames=sampled_frames,
        sampled_bodies=sampled_bodies,
        source_format="binary",
    )


def read_trajectory(
    path: str | Path,
    fmt: str = "auto",
    max_frames: int = 600,
    max_bodies: int = 200,
) -> TrajectoryData:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    if max_frames < 1:
        raise ValueError("Максимум кадров должен быть положительным")
    if max_bodies < 1:
        raise ValueError("Максимум тел должен быть положительным")

    detected = detect_trajectory_format(path, fmt)
    if detected == "binary":
        return read_binary_trajectory(path, max_frames=max_frames, max_bodies=max_bodies)
    return read_csv_trajectory(path, max_frames=max_frames, max_bodies=max_bodies)


BaseTrajectoryViewerFrame = ttk.Frame if ttk is not None else object


class TrajectoryViewerFrame(BaseTrajectoryViewerFrame):
    def __init__(
        self,
        master,
        *,
        initial_path: str | Path = "",
        initial_format: str = "auto",
        initial_max_frames: int = 600,
        initial_max_bodies: int = 200,
    ):
        if TKINTER_IMPORT_ERROR is not None:
            raise RuntimeError("Tkinter is not installed. Install python3-tk to use the trajectory viewer.")
        super().__init__(master)
        self.load_queue = queue.Queue()
        self.trajectory: TrajectoryData | None = None
        self.frame_index = 0
        self.playing = False
        self.after_id = None
        self.scatter = None
        self.trail_lines = []
        self.axis_indices = (0, 1)
        self.unit_scale = 1.0
        self.unit_name = "m"

        self.path_var = tk.StringVar(value=str(initial_path) if initial_path else "")
        self.format_var = tk.StringVar(value=initial_format)
        self.projection_var = tk.StringVar(value="XY")
        self.unit_var = tk.StringVar(value="auto")
        self.max_frames_var = tk.StringVar(value=str(initial_max_frames))
        self.max_bodies_var = tk.StringVar(value=str(initial_max_bodies))
        self.speed_var = tk.StringVar(value="30")
        self.trails_var = tk.BooleanVar(value=True)
        self.frame_var = tk.IntVar(value=0)
        self.status_var = tk.StringVar(value="Траектория не загружена")
        self.play_button_text = tk.StringVar(value="Пуск")

        self._build_ui()
        self.after(100, self._poll_load_queue)

    def set_path(self, path: str | Path, fmt: str = "auto"):
        self.path_var.set(str(path))
        if fmt:
            self.format_var.set("binary" if fmt == "bin" else fmt)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Файл").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.path_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(controls, text="Выбрать", command=self._pick_file).grid(
            row=0, column=2, sticky="ew", padx=(8, 0), pady=3
        )
        ttk.Button(controls, text="Загрузить", command=self.load_trajectory).grid(
            row=0, column=3, sticky="ew", padx=(8, 0), pady=3
        )

        ttk.Label(controls, text="Формат").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(
            controls,
            textvariable=self.format_var,
            values=["auto", "csv", "binary"],
            state="readonly",
            width=12,
        ).grid(row=1, column=1, sticky="w", pady=3)

        options = ttk.Frame(controls)
        options.grid(row=1, column=1, columnspan=3, sticky="e", pady=3)
        ttk.Label(options, text="Проекция").pack(side="left")
        ttk.Combobox(
            options,
            textvariable=self.projection_var,
            values=["XY", "XZ", "YZ"],
            state="readonly",
            width=6,
        ).pack(side="left", padx=(6, 14))
        ttk.Label(options, text="Единицы").pack(side="left")
        ttk.Combobox(
            options,
            textvariable=self.unit_var,
            values=["auto", "m", "km", "AU"],
            state="readonly",
            width=7,
        ).pack(side="left", padx=(6, 14))
        ttk.Label(options, text="Кадры").pack(side="left")
        ttk.Entry(options, textvariable=self.max_frames_var, width=7).pack(side="left", padx=(6, 14))
        ttk.Label(options, text="Тела").pack(side="left")
        ttk.Entry(options, textvariable=self.max_bodies_var, width=7).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(options, text="Следы", variable=self.trails_var, command=self._redraw).pack(side="left")

        figure = Figure(figsize=(7, 5), dpi=100)
        self.ax = figure.add_subplot(111)
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.grid(True, alpha=0.25)
        self.ax.set_title("Загрузите файл траектории")

        canvas_frame = ttk.Frame(self)
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self.canvas = FigureCanvasTkAgg(figure, master=canvas_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, canvas_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.grid(row=1, column=0, sticky="ew")

        playback = ttk.Frame(self)
        playback.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        playback.columnconfigure(3, weight=1)
        ttk.Button(playback, text="|<", width=4, command=self._first_frame).grid(row=0, column=0)
        ttk.Button(playback, text="<", width=4, command=self._previous_frame).grid(row=0, column=1, padx=(4, 0))
        ttk.Button(playback, textvariable=self.play_button_text, width=8, command=self._toggle_play).grid(
            row=0, column=2, padx=(8, 0)
        )
        self.frame_scale = ttk.Scale(
            playback,
            orient="horizontal",
            from_=0,
            to=0,
            variable=self.frame_var,
            command=self._on_scale,
        )
        self.frame_scale.grid(row=0, column=3, sticky="ew", padx=8)
        ttk.Button(playback, text=">", width=4, command=self._next_frame).grid(row=0, column=4)
        ttk.Button(playback, text=">|", width=4, command=self._last_frame).grid(row=0, column=5, padx=(4, 0))
        ttk.Label(playback, text="FPS").grid(row=0, column=6, padx=(14, 4))
        ttk.Entry(playback, textvariable=self.speed_var, width=5).grid(row=0, column=7)

        ttk.Label(self, textvariable=self.status_var).grid(row=3, column=0, sticky="ew", pady=(6, 0))

        self.projection_var.trace_add("write", lambda *_args: self._redraw())
        self.unit_var.trace_add("write", lambda *_args: self._redraw())

    def _pick_file(self):
        path = filedialog.askopenfilename(
            initialdir=str(ROOT),
            filetypes=[
                ("Trajectory", "*.bin *.csv"),
                ("Binary trajectory", "*.bin"),
                ("CSV trajectory", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.path_var.set(path)
            if Path(path).suffix.lower() == ".bin":
                self.format_var.set("binary")
            elif Path(path).suffix.lower() == ".csv":
                self.format_var.set("csv")

    def _positive_int(self, variable: tk.StringVar, name: str) -> int:
        try:
            value = int(variable.get())
        except ValueError as exc:
            raise ValueError(f"{name}: нужно целое число") from exc
        if value < 1:
            raise ValueError(f"{name}: значение должно быть больше нуля")
        return value

    def load_trajectory(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror("Файл не выбран", "Выбери CSV или binary-файл траектории.")
            return
        try:
            max_frames = self._positive_int(self.max_frames_var, "Кадры")
            max_bodies = self._positive_int(self.max_bodies_var, "Тела")
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return

        self._stop_playback()
        self.status_var.set("Загрузка траектории...")
        load_args = (path, self.format_var.get(), max_frames, max_bodies)

        def worker():
            try:
                data = read_trajectory(*load_args)
                self.load_queue.put(("loaded", data))
            except Exception as exc:
                self.load_queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_load_queue(self):
        try:
            while True:
                kind, payload = self.load_queue.get_nowait()
                if kind == "loaded":
                    self._set_trajectory(payload)
                elif kind == "error":
                    self.status_var.set("Траектория не загружена")
                    messagebox.showerror("Ошибка загрузки", str(payload))
        except queue.Empty:
            pass
        self.after(100, self._poll_load_queue)

    def _set_trajectory(self, trajectory: TrajectoryData):
        self.trajectory = trajectory
        self.frame_index = 0
        self.frame_var.set(0)
        self.frame_scale.configure(to=max(0, trajectory.sampled_frames - 1))
        self.format_var.set(trajectory.source_format)
        self._prepare_plot()
        self._draw_frame(0)
        self._update_status()

    def _prepare_plot(self):
        self.ax.clear()
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.grid(True, alpha=0.25)
        self._update_projection_and_units()
        x_axis, y_axis = self.axis_indices
        positions = self.trajectory.positions[:, :, [x_axis, y_axis]] / self.unit_scale
        finite_positions = positions[np.isfinite(positions)]
        if finite_positions.size:
            min_value = float(np.nanmin(positions))
            max_value = float(np.nanmax(positions))
        else:
            min_value, max_value = -1.0, 1.0
        if math.isclose(min_value, max_value):
            min_value -= 1.0
            max_value += 1.0
        margin = 0.06 * (max_value - min_value)
        self.ax.set_xlim(min_value - margin, max_value + margin)
        self.ax.set_ylim(min_value - margin, max_value + margin)
        self.ax.set_xlabel(f"{self.projection_var.get()[0]}, {self.unit_name}")
        self.ax.set_ylabel(f"{self.projection_var.get()[1]}, {self.unit_name}")

        colors = np.linspace(0.0, 1.0, self.trajectory.sampled_bodies)
        sizes = self._marker_sizes()
        first_frame = positions[0]
        self.scatter = self.ax.scatter(
            first_frame[:, 0],
            first_frame[:, 1],
            s=sizes,
            c=colors,
            cmap="viridis",
            alpha=0.9,
            edgecolors="none",
        )

        self.trail_lines = []
        trail_count = min(self.trajectory.sampled_bodies, 50)
        for body_index in range(trail_count):
            line, = self.ax.plot([], [], linewidth=0.8, alpha=0.45)
            self.trail_lines.append(line)

        self.canvas.draw_idle()

    def _marker_sizes(self) -> np.ndarray:
        bodies = self.trajectory.sampled_bodies
        if self.trajectory.masses is None or len(self.trajectory.masses) == 0:
            return np.full(bodies, 24.0)
        masses = np.asarray(self.trajectory.masses, dtype=np.float64)
        finite = masses[np.isfinite(masses) & (masses > 0)]
        if finite.size == 0:
            return np.full(bodies, 24.0)
        scaled = np.sqrt(np.maximum(masses, np.nanmin(finite)) / np.nanmax(finite))
        return 18.0 + 70.0 * scaled

    def _update_projection_and_units(self):
        projection = self.projection_var.get()
        self.axis_indices = {
            "XY": (0, 1),
            "XZ": (0, 2),
            "YZ": (1, 2),
        }.get(projection, (0, 1))

        unit = self.unit_var.get()
        if unit == "auto":
            max_abs = float(np.nanmax(np.abs(self.trajectory.positions)))
            if max_abs >= 0.05 * AU:
                unit = "AU"
            elif max_abs >= 1.0e6:
                unit = "km"
            else:
                unit = "m"
        if unit == "AU":
            self.unit_scale = AU
            self.unit_name = "AU"
        elif unit == "km":
            self.unit_scale = 1000.0
            self.unit_name = "km"
        else:
            self.unit_scale = 1.0
            self.unit_name = "m"

    def _draw_frame(self, frame_index: int):
        if self.trajectory is None or self.scatter is None:
            return
        frame_index = max(0, min(frame_index, self.trajectory.sampled_frames - 1))
        self.frame_index = frame_index
        x_axis, y_axis = self.axis_indices
        current = self.trajectory.positions[frame_index, :, [x_axis, y_axis]] / self.unit_scale
        self.scatter.set_offsets(current)

        if self.trails_var.get():
            history = self.trajectory.positions[: frame_index + 1, :, [x_axis, y_axis]] / self.unit_scale
            for body_index, line in enumerate(self.trail_lines):
                line.set_data(history[:, body_index, 0], history[:, body_index, 1])
        else:
            for line in self.trail_lines:
                line.set_data([], [])

        step = int(self.trajectory.steps[frame_index])
        time_days = float(self.trajectory.times[frame_index]) / 86400.0
        self.ax.set_title(f"Шаг {step}, t = {time_days:.3g} сут.")
        self.canvas.draw_idle()
        self._update_status()

    def _update_status(self):
        if self.trajectory is None:
            return
        self.status_var.set(
            f"{self.trajectory.path.name}: {self.trajectory.source_format}, "
            f"кадр {self.frame_index + 1}/{self.trajectory.sampled_frames} "
            f"(всего {self.trajectory.total_frames}), "
            f"тел {self.trajectory.sampled_bodies}/{self.trajectory.total_bodies}"
        )

    def _redraw(self):
        if self.trajectory is None:
            return
        self._prepare_plot()
        self._draw_frame(self.frame_index)

    def _on_scale(self, value):
        if self.trajectory is None:
            return
        self._draw_frame(int(float(value)))

    def _set_frame(self, frame_index: int):
        if self.trajectory is None:
            return
        frame_index = max(0, min(frame_index, self.trajectory.sampled_frames - 1))
        self.frame_var.set(frame_index)
        self._draw_frame(frame_index)

    def _first_frame(self):
        self._set_frame(0)

    def _previous_frame(self):
        self._set_frame(self.frame_index - 1)

    def _next_frame(self):
        if self.trajectory is None:
            return
        if self.frame_index >= self.trajectory.sampled_frames - 1:
            self._stop_playback()
            return
        self._set_frame(self.frame_index + 1)

    def _last_frame(self):
        if self.trajectory is not None:
            self._set_frame(self.trajectory.sampled_frames - 1)

    def _toggle_play(self):
        if self.trajectory is None:
            return
        if self.playing:
            self._stop_playback()
        else:
            self.playing = True
            self.play_button_text.set("Пауза")
            self._schedule_next_frame()

    def _stop_playback(self):
        self.playing = False
        self.play_button_text.set("Пуск")
        if self.after_id is not None:
            self.after_cancel(self.after_id)
            self.after_id = None

    def _schedule_next_frame(self):
        if not self.playing:
            return
        try:
            fps = float(self.speed_var.get())
        except ValueError:
            fps = 30.0
        fps = min(max(fps, 1.0), 120.0)
        interval_ms = max(1, int(1000.0 / fps))
        self.after_id = self.after(interval_ms, self._playback_step)

    def _playback_step(self):
        self.after_id = None
        if not self.playing or self.trajectory is None:
            return
        if self.frame_index >= self.trajectory.sampled_frames - 1:
            self._stop_playback()
            return
        self._next_frame()
        self._schedule_next_frame()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="View N-body trajectory CSV or binary files")
    parser.add_argument("trajectory", nargs="?", help="Trajectory file to open")
    parser.add_argument("--format", choices=["auto", "csv", "binary", "bin"], default="auto")
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--max-bodies", type=int, default=200)
    args = parser.parse_args(argv)

    if TKINTER_IMPORT_ERROR is not None:
        print("Tkinter is not installed. Install python3-tk to use the trajectory viewer.")
        print(f"Import error: {TKINTER_IMPORT_ERROR}")
        return 1

    root = tk.Tk()
    root.title("N-body trajectory viewer")
    root.geometry("1080x760")
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass

    viewer = TrajectoryViewerFrame(
        root,
        initial_path=args.trajectory or "",
        initial_format="binary" if args.format == "bin" else args.format,
        initial_max_frames=args.max_frames,
        initial_max_bodies=args.max_bodies,
    )
    viewer.pack(fill="both", expand=True, padx=10, pady=10)
    if args.trajectory:
        root.after(100, viewer.load_trajectory)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
