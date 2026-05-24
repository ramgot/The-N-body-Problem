#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windowed launcher for N-body simulations and benchmarks."""

import csv
import codecs
import datetime
import json
import math
import os
import queue
import random
import shlex
import subprocess
import sys
import tempfile
import threading
import time
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
os.chdir(ROOT)

import benchmark

CONFIG_DIR = ROOT / "configs"
RESULTS_DIR = ROOT / "benchmark_results"

G = 6.67430e-11
SOLAR_MASS = 1.989e30
AU = 1.496e11


def count_body_rows(path):
    rows = 0
    with Path(path).open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(line for line in csvfile if not line.lstrip().startswith("#"))
        for row in reader:
            if not row:
                continue
            try:
                float(row[0])
            except (ValueError, TypeError):
                continue
            rows += 1
    return rows


def write_random_body_file(path, n_bodies, total_mass, radius, seed):
    rng = random.Random(seed)
    mass_per_body = total_mass / float(n_bodies)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as csvfile:
        csvfile.write("# nbody-bodies-v1\n")
        csvfile.write(f"# seed={seed}, n={n_bodies}, total_mass={total_mass}, radius={radius}\n")
        writer = csv.writer(csvfile)
        writer.writerow(["mass", "x", "y", "z", "vx", "vy", "vz"])

        for _ in range(n_bodies):
            r = radius * (rng.random() ** (1.0 / 3.0))
            theta = math.acos(rng.uniform(-1.0, 1.0))
            phi = 2.0 * math.pi * rng.random()
            sin_theta = math.sin(theta)

            x = r * sin_theta * math.cos(phi)
            y = r * sin_theta * math.sin(phi)
            z = r * math.cos(theta)

            speed = math.sqrt(G * total_mass / (r + 1e6))
            vx = speed * sin_theta * math.cos(phi)
            vy = speed * sin_theta * math.sin(phi)
            vz = speed * math.cos(theta)

            writer.writerow([mass_per_body, x, y, z, vx, vy, vz])


class NBodyGui:
    def __init__(self, root):
        self.root = root
        self.root.title("N-body benchmark launcher")
        self.root.geometry("1080x760")
        self.log_queue = queue.Queue()
        self.running = False
        self.run_started_at = None
        self.active_command = ""
        self.status_after_id = None

        self._create_vars()
        self._build_ui()
        self._poll_log_queue()

    def _create_vars(self):
        cpu_count = str(os.cpu_count() or 1)

        self.sim_method = tk.StringVar(value="serial")
        self.sim_n = tk.StringVar(value="100")
        self.sim_dt = tk.StringVar(value="3600")
        self.sim_t_hours = tk.StringVar(value="24")
        self.sim_scenario = tk.StringVar(value="auto")
        self.sim_body_file = tk.StringVar(value="")
        self.sim_threads = tk.StringVar(value=cpu_count)
        self.sim_device = tk.StringVar(value="auto")
        self.sim_csv = tk.StringVar(value=str(RESULTS_DIR / "single_runs.csv"))
        self.sim_write_trajectory = tk.BooleanVar(value=False)
        self.sim_trajectory = tk.StringVar(value=str(RESULTS_DIR / "trajectory.csv"))
        self.sim_trajectory_format = tk.StringVar(value="csv")
        self.sim_trajectory_fields = tk.StringVar(value="full")
        self.sim_trajectory_stride = tk.StringVar(value="1")

        self.method_vars = {
            "serial": tk.BooleanVar(value=True),
            "openmp": tk.BooleanVar(value=True),
            "sycl": tk.BooleanVar(value=False),
        }
        self.bench_n_values = tk.StringVar(value="3,10,100,1000")
        self.bench_times = tk.StringVar(value="24,168,720,8760")
        self.bench_dt = tk.StringVar(value="3600")
        self.bench_scenario = tk.StringVar(value="auto-by-n")
        self.bench_body_file = tk.StringVar(value="")
        self.bench_threads = tk.StringVar(value=cpu_count)
        self.bench_device = tk.StringVar(value="auto")
        self.bench_csv = tk.StringVar(value=str(RESULTS_DIR / "benchmark_results.csv"))
        self.bench_plots = tk.StringVar(value=str(RESULTS_DIR / "plots"))
        self.bench_write_trajectory = tk.BooleanVar(value=False)
        self.bench_trajectory = tk.StringVar(value=str(RESULTS_DIR / "trajectories"))
        self.bench_trajectory_format = tk.StringVar(value="csv")
        self.bench_trajectory_fields = tk.StringVar(value="full")
        self.bench_trajectory_stride = tk.StringVar(value="1")
        self.bench_force = tk.BooleanVar(value=True)
        self.bench_make_plots = tk.BooleanVar(value=True)
        self.bench_default_skips = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="Готово")

        self.gen_n = tk.StringVar(value="100")
        self.gen_seed = tk.StringVar(value="12345")
        self.gen_total_mass = tk.StringVar(value="")
        self.gen_radius = tk.StringVar(value=str(2.0 * AU))
        self.gen_output = tk.StringVar(value=str(CONFIG_DIR / "random_100_seed_12345.bodies.csv"))

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))

        sim_tab = ttk.Frame(notebook, padding=12)
        bench_tab = ttk.Frame(notebook, padding=12)
        config_tab = ttk.Frame(notebook, padding=12)
        notebook.add(sim_tab, text="Симуляция")
        notebook.add(bench_tab, text="Бенчмарк")
        notebook.add(config_tab, text="Конфигурации тел")

        self._build_simulation_tab(sim_tab)
        self._build_benchmark_tab(bench_tab)
        self._build_config_tab(config_tab)
        self._build_log()

    def _build_simulation_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        row = 0
        ttk.Label(parent, text="Метод").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.sim_method, values=list(benchmark.METHODS),
                     state="readonly", width=16).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Сценарий").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Combobox(parent, textvariable=self.sim_scenario,
                     values=["auto", "random", "sun-earth-moon", "solar-system", "body-file"],
                     state="readonly", width=20).grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="N").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_n).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="dt, s").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Entry(parent, textvariable=self.sim_dt).grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="T, hours").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_t_hours).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="OpenMP threads").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Entry(parent, textvariable=self.sim_threads).grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="SYCL device").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.sim_device, values=["auto", "cpu", "gpu"],
                     state="readonly", width=16).grid(row=row, column=1, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="Файл тел").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_body_file).grid(row=row, column=1, columnspan=2,
                                                                sticky="ew", pady=4)
        ttk.Button(parent, text="Выбрать", command=lambda: self._pick_file(self.sim_body_file)).grid(
            row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Label(parent, text="CSV результатов").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_csv).grid(row=row, column=1, columnspan=2,
                                                          sticky="ew", pady=4)
        ttk.Button(parent, text="Сохранить как", command=lambda: self._pick_save_file(
            self.sim_csv, [("CSV", "*.csv"), ("All files", "*.*")]
        )).grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Checkbutton(parent, text="Записывать шаги",
                        variable=self.sim_write_trajectory).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_trajectory).grid(row=row, column=1, columnspan=2,
                                                                 sticky="ew", pady=4)
        ttk.Button(parent, text="Сохранить как", command=lambda: self._pick_save_file(
            self.sim_trajectory,
            self._trajectory_filetypes(self.sim_trajectory_format.get()),
            self._trajectory_extension(self.sim_trajectory_format.get()),
        )).grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Label(parent, text="Формат шагов").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.sim_trajectory_format,
                     values=["csv", "binary"], state="readonly", width=16).grid(
            row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Поля шагов").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Combobox(parent, textvariable=self.sim_trajectory_fields,
                     values=["positions", "state", "full"], state="readonly", width=16).grid(
            row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="Шаг записи").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_trajectory_stride).grid(row=row, column=1, sticky="ew", pady=4)

        row += 1
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Button(button_frame, text="Собрать выбранный метод",
                   command=self.build_for_single_run).pack(side="left")
        ttk.Button(button_frame, text="Запустить",
                   command=self.run_single_simulation).pack(side="left", padx=(8, 0))

    def _build_benchmark_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        row = 0
        ttk.Label(parent, text="Методы").grid(row=row, column=0, sticky="nw", pady=4)
        methods_frame = ttk.Frame(parent)
        methods_frame.grid(row=row, column=1, columnspan=3, sticky="w", pady=4)
        for method in benchmark.METHODS:
            ttk.Checkbutton(methods_frame, text=method, variable=self.method_vars[method]).pack(
                side="left", padx=(0, 14))

        row += 1
        ttk.Label(parent, text="N values").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_n_values).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="T hours").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Entry(parent, textvariable=self.bench_times).grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="dt, s").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_dt).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Сценарий").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Combobox(parent, textvariable=self.bench_scenario,
                     values=["auto-by-n", "auto", "random", "sun-earth-moon", "solar-system", "body-file"],
                     state="readonly").grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="OpenMP threads").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_threads).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="SYCL device").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Combobox(parent, textvariable=self.bench_device, values=["auto", "cpu", "gpu"],
                     state="readonly").grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="Файл тел").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_body_file).grid(row=row, column=1, columnspan=2,
                                                                  sticky="ew", pady=4)
        ttk.Button(parent, text="Выбрать", command=lambda: self._pick_file(self.bench_body_file)).grid(
            row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Label(parent, text="CSV результатов").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_csv).grid(row=row, column=1, columnspan=2,
                                                            sticky="ew", pady=4)
        ttk.Button(parent, text="Сохранить как", command=lambda: self._pick_save_file(
            self.bench_csv, [("CSV", "*.csv"), ("All files", "*.*")]
        )).grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Label(parent, text="Папка графиков").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_plots).grid(row=row, column=1, columnspan=2,
                                                              sticky="ew", pady=4)
        ttk.Button(parent, text="Выбрать", command=lambda: self._pick_directory(self.bench_plots)).grid(
            row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Checkbutton(parent, text="Записывать шаги",
                        variable=self.bench_write_trajectory).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_trajectory).grid(row=row, column=1, columnspan=2,
                                                                   sticky="ew", pady=4)
        ttk.Button(parent, text="Выбрать", command=lambda: self._pick_directory(self.bench_trajectory)).grid(
            row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Label(parent, text="Формат шагов").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.bench_trajectory_format,
                     values=["csv", "binary"], state="readonly", width=16).grid(
            row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Поля шагов").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Combobox(parent, textvariable=self.bench_trajectory_fields,
                     values=["positions", "state", "full"], state="readonly", width=16).grid(
            row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="Шаг записи").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_trajectory_stride).grid(row=row, column=1, sticky="ew", pady=4)

        row += 1
        options = ttk.Frame(parent)
        options.grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 4))
        ttk.Checkbutton(options, text="Перезаписать CSV", variable=self.bench_force).pack(side="left")
        ttk.Checkbutton(options, text="Строить графики", variable=self.bench_make_plots).pack(
            side="left", padx=(18, 0))
        ttk.Checkbutton(options, text="Пропускать долгие случаи",
                        variable=self.bench_default_skips).pack(side="left", padx=(18, 0))

        row += 1
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Button(button_frame, text="Собрать методы", command=self.build_for_benchmark).pack(side="left")
        ttk.Button(button_frame, text="Запустить бенчмарк", command=self.run_benchmark).pack(
            side="left", padx=(8, 0))
        ttk.Button(button_frame, text="Только графики", command=self.plot_benchmark).pack(
            side="left", padx=(8, 0))
        ttk.Button(button_frame, text="Сохранить JSON", command=self.save_benchmark_config).pack(
            side="left", padx=(22, 0))
        ttk.Button(button_frame, text="Загрузить JSON", command=self.load_benchmark_config).pack(
            side="left", padx=(8, 0))

    def _build_config_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

        row = 0
        ttk.Label(parent, text="N").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.gen_n).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Seed").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Entry(parent, textvariable=self.gen_seed).grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="Total mass, kg").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.gen_total_mass).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Radius, m").grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        ttk.Entry(parent, textvariable=self.gen_radius).grid(row=row, column=3, sticky="ew", pady=4)

        row += 1
        ttk.Label(parent, text="Файл").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.gen_output).grid(row=row, column=1, columnspan=2,
                                                             sticky="ew", pady=4)
        ttk.Button(parent, text="Сохранить как", command=lambda: self._pick_save_file(
            self.gen_output, [("Body CSV", "*.bodies.csv"), ("CSV", "*.csv"), ("All files", "*.*")]
        )).grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Button(button_frame, text="Создать случайный файл",
                   command=self.generate_body_config).pack(side="left")
        ttk.Button(button_frame, text="В симуляцию",
                   command=lambda: self._use_generated_file(self.sim_body_file, self.sim_scenario)).pack(
            side="left", padx=(8, 0))
        ttk.Button(button_frame, text="В бенчмарк",
                   command=lambda: self._use_generated_file(self.bench_body_file, self.bench_scenario)).pack(
            side="left", padx=(8, 0))

    def _build_log(self):
        frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="Журнал").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.status_text).grid(row=0, column=1, sticky="e", padx=(12, 8))
        self.activity = ttk.Progressbar(header, mode="indeterminate", length=150)
        self.activity.grid(row=0, column=2, sticky="e")
        self.activity.grid_remove()

        self.log = tk.Text(frame, height=12, wrap="word")
        self.log.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _pick_file(self, variable):
        path = filedialog.askopenfilename(initialdir=str(ROOT))
        if path:
            variable.set(path)

    def _pick_save_file(self, variable, filetypes, defaultextension=None):
        path = filedialog.asksaveasfilename(
            initialdir=str(ROOT),
            filetypes=filetypes,
            defaultextension=defaultextension,
        )
        if path:
            variable.set(path)

    def _pick_directory(self, variable):
        path = filedialog.askdirectory(initialdir=str(ROOT))
        if path:
            variable.set(path)

    def _trajectory_extension(self, trajectory_format):
        return ".bin" if trajectory_format == "binary" else ".csv"

    def _trajectory_filetypes(self, trajectory_format):
        if trajectory_format == "binary":
            return [("Binary trajectory", "*.bin"), ("CSV", "*.csv"), ("All files", "*.*")]
        return [("CSV", "*.csv"), ("Binary trajectory", "*.bin"), ("All files", "*.*")]

    def _default_trajectory_file(self, trajectory_format):
        return RESULTS_DIR / f"trajectory{self._trajectory_extension(trajectory_format)}"

    def _single_trajectory_path(self, trajectory_format):
        path = self.sim_trajectory.get().strip()
        default_csv = str(self._default_trajectory_file("csv"))
        default_bin = str(self._default_trajectory_file("binary"))
        if not path or path in {default_csv, default_bin}:
            path = str(self._default_trajectory_file(trajectory_format))
            self.sim_trajectory.set(path)
        return path

    def _append_log(self, text):
        chunks = str(text).split("\r")
        self.log.insert("end", chunks[0])
        for chunk in chunks[1:]:
            self.log.delete("end-1c linestart", "end-1c")
            self.log.insert("end", chunk)
        self.log.see("end")

    def _format_elapsed(self):
        if self.run_started_at is None:
            return "00:00"
        elapsed = int(time.monotonic() - self.run_started_at)
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _short_command(self, command, limit=90):
        text = shlex.join([str(part) for part in command])
        if len(text) <= limit:
            return text
        return text[:limit - 1] + "…"

    def _update_running_status(self):
        if not self.running:
            self.status_after_id = None
            return
        self.status_text.set(f"Выполняется {self._format_elapsed()}: {self.active_command}")
        self.status_after_id = self.root.after(1000, self._update_running_status)

    def _start_running_status(self, command):
        self.run_started_at = time.monotonic()
        self.active_command = self._short_command(command)
        self.status_text.set(f"Запуск: {self.active_command}")
        self.activity.grid()
        self.activity.start(12)
        if self.status_after_id is not None:
            self.root.after_cancel(self.status_after_id)
        self.status_after_id = self.root.after(1000, self._update_running_status)
        self.root.update_idletasks()

    def _finish_running_status(self, returncode):
        if self.status_after_id is not None:
            self.root.after_cancel(self.status_after_id)
            self.status_after_id = None
        self.activity.stop()
        self.activity.grid_remove()
        self.status_text.set(f"Завершено за {self._format_elapsed()} · код {returncode}")
        self.run_started_at = None
        self.active_command = ""

    def _poll_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item[0] in {"line", "output"}:
                    self._append_log(item[1])
                elif item[0] == "complete":
                    _, returncode, output, callback = item
                    self.running = False
                    self._finish_running_status(returncode)
                    if callback:
                        callback(returncode, output)
                    self._append_log(f"\nProcess finished with code {returncode}\n")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _run_process(self, command, *, env=None, env_factory=None, callback=None):
        if self.running:
            messagebox.showwarning("Процесс уже идет", "Дождись завершения текущего запуска.")
            return
        self.running = True
        self._start_running_status(command)
        self._append_log("\n$ " + shlex.join([str(part) for part in command]) + "\n")

        def worker():
            output_parts = []
            try:
                process_env = env_factory() if env_factory is not None else env
                process = subprocess.Popen(
                    [str(part) for part in command],
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    env=process_env,
                )
                assert process.stdout is not None
                decoder = codecs.getincrementaldecoder("utf-8")("replace")
                while True:
                    raw_chunk = os.read(process.stdout.fileno(), 4096)
                    if not raw_chunk:
                        break
                    text_chunk = decoder.decode(raw_chunk)
                    if text_chunk:
                        output_parts.append(text_chunk)
                        self.log_queue.put(("output", text_chunk))
                tail = decoder.decode(b"", final=True)
                if tail:
                    output_parts.append(tail)
                    self.log_queue.put(("output", tail))
                returncode = process.wait()
            except Exception as exc:
                output_parts.append(f"{exc}\n")
                self.log_queue.put(("output", f"{exc}\n"))
                returncode = 1
            self.log_queue.put(("complete", returncode, "".join(output_parts), callback))

        threading.Thread(target=worker, daemon=True).start()

    def _int_value(self, variable, name, minimum=1):
        try:
            value = int(variable.get())
        except ValueError as exc:
            raise ValueError(f"{name}: нужно целое число") from exc
        if value < minimum:
            raise ValueError(f"{name}: значение должно быть не меньше {minimum}")
        return value

    def _float_value(self, variable, name, minimum=0.0):
        try:
            value = float(variable.get())
        except ValueError as exc:
            raise ValueError(f"{name}: нужно число") from exc
        if value <= minimum:
            raise ValueError(f"{name}: значение должно быть больше {minimum}")
        return value

    def _number_list(self, variable, cast, name):
        try:
            values = [cast(item.strip()) for item in variable.get().split(",") if item.strip()]
        except ValueError as exc:
            raise ValueError(f"{name}: проверь список через запятую") from exc
        if not values:
            raise ValueError(f"{name}: список не должен быть пустым")
        return values

    def _selected_benchmark_methods(self):
        methods = [method for method, var in self.method_vars.items() if var.get()]
        if not methods:
            raise ValueError("Выбери хотя бы один метод")
        return methods

    def _build_command_for_methods(self, methods):
        return ["make", "all-sycl" if "sycl" in methods else "all"]

    def build_for_single_run(self):
        self._run_process(self._build_command_for_methods([self.sim_method.get()]))

    def build_for_benchmark(self):
        try:
            methods = self._selected_benchmark_methods()
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return
        self._run_process(self._build_command_for_methods(methods))

    def _scenario_and_body_file(self, scenario_var, body_file_var):
        scenario = scenario_var.get()
        body_file = body_file_var.get().strip()
        if scenario == "body-file":
            if not body_file:
                raise ValueError("Для сценария body-file нужен файл тел")
            return "auto", body_file
        return scenario, None

    def run_single_simulation(self):
        try:
            method = self.sim_method.get()
            n_bodies = self._int_value(self.sim_n, "N")
            dt_s = self._float_value(self.sim_dt, "dt")
            t_hours = self._float_value(self.sim_t_hours, "T")
            threads = self._int_value(self.sim_threads, "OpenMP threads")
            scenario, body_file = self._scenario_and_body_file(self.sim_scenario, self.sim_body_file)
            trajectory_format = self.sim_trajectory_format.get()
            trajectory_fields = self.sim_trajectory_fields.get()
            trajectory_stride = self._int_value(self.sim_trajectory_stride, "Шаг записи")
            trajectory_file = self._single_trajectory_path(trajectory_format) if self.sim_write_trajectory.get() else ""
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return

        exe_path = benchmark.find_executable(benchmark.METHODS[method])
        if exe_path is None:
            messagebox.showerror("Бинарник не найден", "Сначала собери выбранный метод.")
            return

        command = [exe_path, n_bodies, dt_s, t_hours * 3600.0]
        if method == "openmp":
            command.append(threads)
        command.append(scenario)
        if body_file:
            command.extend(["--bodies", body_file])
        if method == "sycl":
            command.extend(["--device", self.sim_device.get()])
        if trajectory_file:
            command.extend(["--trajectory", trajectory_file])
            command.extend(["--trajectory-format", trajectory_format])
            command.extend(["--trajectory-fields", trajectory_fields])
            command.extend(["--trajectory-stride", trajectory_stride])

        env_factory = benchmark.load_oneapi_env if method == "sycl" else None
        self._run_process(
            command,
            env_factory=env_factory,
            callback=lambda returncode, output: self._save_single_run(
                returncode, output, method, n_bodies, dt_s, t_hours, threads,
                scenario, body_file, trajectory_file, trajectory_format,
                trajectory_fields, trajectory_stride, command
            ),
        )

    def _save_single_run(self, returncode, output, method, n_bodies, dt_s, t_hours,
                         threads, scenario, body_file, trajectory_file, trajectory_format,
                         trajectory_fields, trajectory_stride, command):
        if returncode != 0:
            return
        csv_path = self.sim_csv.get().strip()
        if not csv_path:
            return
        try:
            metrics = benchmark.parse_metrics(output)
            actual_n = count_body_rows(body_file) if body_file else n_bodies
            reported_threads = metrics.get("threads", 0)
            if method == "serial":
                reported_threads = 1
            elif method == "openmp" and reported_threads == 0:
                reported_threads = threads

            row = {
                "timestamp": datetime.datetime.now().isoformat(),
                "method": method,
                "executable": benchmark.METHODS[method],
                "n_bodies": actual_n,
                "scenario": benchmark.scenario_display_name(actual_n, scenario, body_file),
                "body_config_file": body_file or "",
                "t_hours": t_hours,
                "dt_s": dt_s,
                "t_max_s": t_hours * 3600.0,
                "execution_time_s": metrics["execution_time_s"],
                "gflops": metrics["gflops"],
                "energy_error": metrics["energy_error"],
                "steps_completed": metrics["steps_completed"],
                "threads": reported_threads,
                "compute_units": metrics.get("compute_units", 0),
                "device_type": metrics.get("device_type", ""),
                "device_name": metrics.get("device_name", ""),
                "trajectory_file": trajectory_file,
                "trajectory_format": trajectory_format if trajectory_file else "",
                "trajectory_fields": trajectory_fields if trajectory_file else "",
                "trajectory_stride": trajectory_stride if trajectory_file else "",
                "command": " ".join(str(part) for part in command),
            }
            benchmark.save_results([row], csv_path)
            self._append_log(f"Saved run metrics to {csv_path}\n")
        except Exception as exc:
            messagebox.showerror("CSV не сохранен", str(exc))

    def _benchmark_config_from_ui(self):
        methods = self._selected_benchmark_methods()
        scenario_choice = self.bench_scenario.get()
        scenario = None
        body_file = None
        if scenario_choice == "body-file":
            body_file = self.bench_body_file.get().strip()
            if not body_file:
                raise ValueError("Для сценария body-file нужен файл тел")
            scenario = "auto"
        elif scenario_choice != "auto-by-n":
            scenario = scenario_choice

        config = {
            "methods": methods,
            "n_values": self._number_list(self.bench_n_values, int, "N values"),
            "times_hours": self._number_list(self.bench_times, float, "T hours"),
            "dt_s": self._float_value(self.bench_dt, "dt"),
            "scenario": scenario,
            "scenario_by_n": {str(key): value for key, value in benchmark.SCENARIO_BY_N.items()},
            "body_file": body_file,
            "openmp_threads": self._int_value(self.bench_threads, "OpenMP threads"),
            "device": self.bench_device.get(),
            "results_csv": self.bench_csv.get().strip(),
            "plots_dir": self.bench_plots.get().strip(),
            "trajectory_dir": self.bench_trajectory.get().strip() if self.bench_write_trajectory.get() else None,
            "trajectory_format": self.bench_trajectory_format.get(),
            "trajectory_fields": self.bench_trajectory_fields.get(),
            "trajectory_stride": self._int_value(self.bench_trajectory_stride, "Шаг записи"),
            "use_default_skips": self.bench_default_skips.get(),
        }
        return benchmark.normalize_benchmark_config(config)

    def _write_temp_benchmark_config(self):
        config = self._benchmark_config_from_ui()
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        temp = tempfile.NamedTemporaryFile("w", suffix=".json", prefix="gui_benchmark_",
                                           dir=str(RESULTS_DIR), delete=False, encoding="utf-8")
        with temp:
            json.dump(config, temp, indent=2, ensure_ascii=False)
        return temp.name

    def run_benchmark(self):
        try:
            config_path = self._write_temp_benchmark_config()
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return

        command = [sys.executable, "-u", ROOT / "benchmark.py", "--config", config_path, "--run"]
        if self.bench_make_plots.get():
            command.append("--plot")
        if self.bench_force.get():
            command.append("--force")
        self._run_process(command)

    def plot_benchmark(self):
        try:
            config_path = self._write_temp_benchmark_config()
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return
        self._run_process([sys.executable, "-u", ROOT / "benchmark.py", "--config", config_path, "--plot"])

    def save_benchmark_config(self):
        try:
            config = self._benchmark_config_from_ui()
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            initialdir=str(CONFIG_DIR),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        with Path(path).open("w", encoding="utf-8") as config_file:
            json.dump(config, config_file, indent=2, ensure_ascii=False)
        self._append_log(f"Saved benchmark configuration to {path}\n")

    def load_benchmark_config(self):
        path = filedialog.askopenfilename(
            initialdir=str(CONFIG_DIR),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            config = benchmark.normalize_benchmark_config(benchmark.load_benchmark_config(path))
            for method, variable in self.method_vars.items():
                variable.set(method in config["methods"])
            self.bench_n_values.set(",".join(str(value) for value in config["n_values"]))
            self.bench_times.set(",".join(str(value) for value in config["times_hours"]))
            self.bench_dt.set(str(config["dt_s"]))
            self.bench_threads.set(str(config["openmp_threads"]))
            self.bench_device.set(config["device"])
            self.bench_csv.set(config["results_csv"])
            self.bench_plots.set(config["plots_dir"])
            self.bench_write_trajectory.set(bool(config.get("trajectory_dir")))
            self.bench_trajectory_format.set(config.get("trajectory_format", "csv"))
            self.bench_trajectory_fields.set(config.get("trajectory_fields", "full"))
            self.bench_trajectory_stride.set(str(config.get("trajectory_stride", 1)))
            if config.get("trajectory_dir"):
                self.bench_trajectory.set(config["trajectory_dir"])
            self.bench_default_skips.set(config["use_default_skips"])
            if config.get("body_file"):
                self.bench_scenario.set("body-file")
                self.bench_body_file.set(config["body_file"])
            elif config.get("scenario"):
                self.bench_scenario.set(config["scenario"])
            else:
                self.bench_scenario.set("auto-by-n")
            self._append_log(f"Loaded benchmark configuration from {path}\n")
        except Exception as exc:
            messagebox.showerror("JSON не загружен", str(exc))

    def generate_body_config(self):
        try:
            n_bodies = self._int_value(self.gen_n, "N")
            seed = self._int_value(self.gen_seed, "Seed", minimum=0)
            radius = self._float_value(self.gen_radius, "Radius")
            if self.gen_total_mass.get().strip():
                total_mass = self._float_value(self.gen_total_mass, "Total mass")
            else:
                total_mass = SOLAR_MASS * 0.01 * n_bodies
            output = self.gen_output.get().strip()
            if not output:
                output = str(CONFIG_DIR / f"random_{n_bodies}_seed_{seed}.bodies.csv")
                self.gen_output.set(output)
            write_random_body_file(output, n_bodies, total_mass, radius, seed)
            self._append_log(f"Saved body configuration to {output}\n")
        except Exception as exc:
            messagebox.showerror("Файл не создан", str(exc))

    def _use_generated_file(self, body_file_var, scenario_var):
        path = self.gen_output.get().strip()
        if path:
            body_file_var.set(path)
            scenario_var.set("body-file")


def main():
    if TKINTER_IMPORT_ERROR is not None:
        print("Tkinter is not installed. Install python3-tk to use the windowed launcher.")
        print(f"Import error: {TKINTER_IMPORT_ERROR}")
        return 1

    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    NBodyGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
