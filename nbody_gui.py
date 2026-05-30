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

if TKINTER_IMPORT_ERROR is None:
    from trajectory_viewer import TrajectoryViewerFrame
else:
    TrajectoryViewerFrame = None

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
        self._updating_sim_trajectory = False
        self.sim_trajectory_auto_path = True

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
        self.sim_trajectory.trace_add("write", self._on_sim_trajectory_changed)
        self.sim_trajectory_format = tk.StringVar(value="csv")
        self.sim_trajectory_format.trace_add("write", self._on_sim_trajectory_format_changed)

        self.method_vars = {
            method: tk.BooleanVar(value=method in {"serial", "openmp"})
            for method in benchmark.METHODS
        }
        self.bench_n_values = tk.StringVar(value="3,10,100,1000")
        self.bench_times = tk.StringVar(value="24,168,720,8760")
        self.bench_dt = tk.StringVar(value="3600")
        self.bench_scenario = tk.StringVar(value="auto-by-n")
        self.bench_body_file = tk.StringVar(value="")
        self.bench_threads = tk.StringVar(value=cpu_count)
        self.bench_device = tk.StringVar(value="auto")
        self.bench_output_dir = tk.StringVar(value="")
        self.bench_write_trajectory = tk.BooleanVar(value=False)
        self.bench_trajectory_format = tk.StringVar(value="csv")
        self.bench_force = tk.BooleanVar(value=True)
        self.bench_make_plots = tk.BooleanVar(value=True)
        self.bench_default_skips = tk.BooleanVar(value=True)
        self.bench_monitor_resources = tk.BooleanVar(value=False)
        self.bench_monitor_interval = tk.StringVar(value="0.5")
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
        visualization_tab = ttk.Frame(notebook, padding=12)
        notebook.add(sim_tab, text="Симуляция")
        notebook.add(bench_tab, text="Бенчмарк")
        notebook.add(config_tab, text="Конфигурации тел")
        notebook.add(visualization_tab, text="Визуализация")

        self._build_simulation_tab(sim_tab)
        self._build_benchmark_tab(bench_tab)
        self._build_config_tab(config_tab)
        self._build_visualization_tab(visualization_tab)
        self._build_log()
        self._bind_dynamic_ui()
        self._refresh_dynamic_ui()

    def _build_simulation_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)
        self.sim_rows = {}

        row = 0
        method_label = ttk.Label(parent, text="Метод")
        method_label.grid(row=row, column=0, sticky="w", pady=4)
        self.sim_method_combo = ttk.Combobox(parent, textvariable=self.sim_method, values=list(benchmark.METHODS),
                                             state="readonly", width=16)
        self.sim_method_combo.grid(row=row, column=1, sticky="ew", pady=4)
        scenario_label = ttk.Label(parent, text="Сценарий")
        scenario_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.sim_scenario_combo = ttk.Combobox(
            parent,
            textvariable=self.sim_scenario,
            values=["auto", "random", "sun-earth-moon", "solar-system", "body-file"],
            state="readonly",
            width=20,
        )
        self.sim_scenario_combo.grid(row=row, column=3, sticky="ew", pady=4)
        self.sim_rows["scenario"] = [scenario_label, self.sim_scenario_combo]

        row += 1
        n_label = ttk.Label(parent, text="N")
        n_label.grid(row=row, column=0, sticky="w", pady=4)
        n_entry = ttk.Entry(parent, textvariable=self.sim_n)
        n_entry.grid(row=row, column=1, sticky="ew", pady=4)
        dt_label = ttk.Label(parent, text="dt, s")
        dt_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        dt_entry = ttk.Entry(parent, textvariable=self.sim_dt)
        dt_entry.grid(row=row, column=3, sticky="ew", pady=4)
        self.sim_rows["n"] = [n_label, n_entry]
        self.sim_rows["dt"] = [dt_label, dt_entry]

        row += 1
        ttk.Label(parent, text="T, hours").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_t_hours).grid(row=row, column=1, sticky="ew", pady=4)
        threads_label = ttk.Label(parent, text="OpenMP threads")
        threads_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        threads_entry = ttk.Entry(parent, textvariable=self.sim_threads)
        threads_entry.grid(row=row, column=3, sticky="ew", pady=4)
        self.sim_rows["openmp"] = [threads_label, threads_entry]

        row += 1
        sycl_label = ttk.Label(parent, text="SYCL device")
        sycl_label.grid(row=row, column=0, sticky="w", pady=4)
        sycl_combo = ttk.Combobox(parent, textvariable=self.sim_device, values=["auto", "cpu", "gpu"],
                                  state="readonly", width=16)
        sycl_combo.grid(row=row, column=1, sticky="ew", pady=4)
        self.sim_rows["sycl"] = [sycl_label, sycl_combo]

        row += 1
        body_file_label = ttk.Label(parent, text="Файл тел")
        body_file_label.grid(row=row, column=0, sticky="w", pady=4)
        body_file_entry = ttk.Entry(parent, textvariable=self.sim_body_file)
        body_file_entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        body_file_button = ttk.Button(parent, text="Выбрать", command=lambda: self._pick_file(self.sim_body_file))
        body_file_button.grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=4)
        self.sim_rows["body_file"] = [body_file_label, body_file_entry, body_file_button]

        row += 1
        ttk.Label(parent, text="Таблица результатов (CSV)").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_csv).grid(row=row, column=1, columnspan=2,
                                                          sticky="ew", pady=4)
        ttk.Button(parent, text="Сохранить как", command=lambda: self._pick_results_csv(
            self.sim_csv
        )).grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Checkbutton(parent, text="Записывать траекторию",
                        variable=self.sim_write_trajectory).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.sim_trajectory).grid(row=row, column=1, columnspan=2,
                                                                 sticky="ew", pady=4)
        ttk.Button(parent, text="Сохранить как", command=self._pick_single_trajectory_file).grid(
            row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Label(parent, text="Формат траектории").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.sim_trajectory_format,
                     values=["csv", "binary"], state="readonly", width=16).grid(
            row=row, column=1, sticky="ew", pady=4)

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
        self.bench_rows = {}

        row = 0
        ttk.Label(parent, text="Методы").grid(row=row, column=0, sticky="nw", pady=4)
        methods_frame = ttk.Frame(parent)
        methods_frame.grid(row=row, column=1, columnspan=3, sticky="w", pady=4)
        for method in benchmark.METHODS:
            ttk.Checkbutton(methods_frame, text=method, variable=self.method_vars[method]).pack(
                side="left", padx=(0, 14))

        row += 1
        bench_n_label = ttk.Label(parent, text="N values")
        bench_n_label.grid(row=row, column=0, sticky="w", pady=4)
        bench_n_entry = ttk.Entry(parent, textvariable=self.bench_n_values)
        bench_n_entry.grid(row=row, column=1, sticky="ew", pady=4)
        bench_times_label = ttk.Label(parent, text="T hours")
        bench_times_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        bench_times_entry = ttk.Entry(parent, textvariable=self.bench_times)
        bench_times_entry.grid(row=row, column=3, sticky="ew", pady=4)
        self.bench_rows["n_values"] = [bench_n_label, bench_n_entry]
        self.bench_rows["times"] = [bench_times_label, bench_times_entry]

        row += 1
        ttk.Label(parent, text="dt, s").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_dt).grid(row=row, column=1, sticky="ew", pady=4)
        bench_scenario_label = ttk.Label(parent, text="Сценарий")
        bench_scenario_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        self.bench_scenario_combo = ttk.Combobox(
            parent,
            textvariable=self.bench_scenario,
            values=["auto-by-n", "auto", "random", "sun-earth-moon", "solar-system", "body-file"],
            state="readonly",
        )
        self.bench_scenario_combo.grid(row=row, column=3, sticky="ew", pady=4)
        self.bench_rows["scenario"] = [bench_scenario_label, self.bench_scenario_combo]

        row += 1
        bench_threads_label = ttk.Label(parent, text="OpenMP threads")
        bench_threads_label.grid(row=row, column=0, sticky="w", pady=4)
        bench_threads_entry = ttk.Entry(parent, textvariable=self.bench_threads)
        bench_threads_entry.grid(row=row, column=1, sticky="ew", pady=4)
        bench_device_label = ttk.Label(parent, text="SYCL device")
        bench_device_label.grid(row=row, column=2, sticky="w", padx=(16, 0), pady=4)
        bench_device_combo = ttk.Combobox(parent, textvariable=self.bench_device, values=["auto", "cpu", "gpu"],
                                          state="readonly")
        bench_device_combo.grid(row=row, column=3, sticky="ew", pady=4)
        self.bench_rows["openmp"] = [bench_threads_label, bench_threads_entry]
        self.bench_rows["sycl"] = [bench_device_label, bench_device_combo]

        row += 1
        bench_body_file_label = ttk.Label(parent, text="Файл тел")
        bench_body_file_label.grid(row=row, column=0, sticky="w", pady=4)
        bench_body_file_entry = ttk.Entry(parent, textvariable=self.bench_body_file)
        bench_body_file_entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        bench_body_file_button = ttk.Button(
            parent,
            text="Выбрать",
            command=lambda: self._pick_file(self.bench_body_file),
        )
        bench_body_file_button.grid(row=row, column=3, sticky="ew", padx=(8, 0), pady=4)
        self.bench_rows["body_file"] = [
            bench_body_file_label,
            bench_body_file_entry,
            bench_body_file_button,
        ]

        row += 1
        ttk.Label(parent, text="Папка прогона").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.bench_output_dir).grid(row=row, column=1, columnspan=2,
                                                                   sticky="ew", pady=4)
        ttk.Button(parent, text="Выбрать", command=lambda: self._pick_directory(self.bench_output_dir)).grid(
            row=row, column=3, sticky="ew", padx=(8, 0), pady=4)

        row += 1
        ttk.Checkbutton(parent, text="Записывать траектории",
                        variable=self.bench_write_trajectory).grid(row=row, column=0, sticky="w", pady=4)

        row += 1
        ttk.Label(parent, text="Формат траекторий").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.bench_trajectory_format,
                     values=["csv", "binary"], state="readonly", width=16).grid(
            row=row, column=1, sticky="ew", pady=4)

        row += 1
        options = ttk.Frame(parent)
        options.grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 4))
        ttk.Checkbutton(options, text="Перезаписать таблицу", variable=self.bench_force).pack(side="left")
        ttk.Checkbutton(options, text="Строить графики", variable=self.bench_make_plots).pack(
            side="left", padx=(18, 0))
        ttk.Checkbutton(options, text="Пропускать долгие случаи",
                        variable=self.bench_default_skips).pack(side="left", padx=(18, 0))
        ttk.Checkbutton(options, text="Мониторинг ресурсов",
                        variable=self.bench_monitor_resources).pack(side="left", padx=(18, 0))
        self.bench_monitor_interval_label = ttk.Label(options, text="Интервал, s")
        self.bench_monitor_interval_label.pack(side="left", padx=(18, 4))
        self.bench_monitor_interval_entry = ttk.Entry(options, textvariable=self.bench_monitor_interval, width=6)
        self.bench_monitor_interval_entry.pack(side="left")

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

    def _build_visualization_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.trajectory_viewer = TrajectoryViewerFrame(
            parent,
            initial_path=self.sim_trajectory.get(),
            initial_format="auto",
        )
        self.trajectory_viewer.grid(row=0, column=0, sticky="nsew")

    def _bind_dynamic_ui(self):
        self.sim_method.trace_add("write", lambda *_args: self._refresh_simulation_fields())
        self.sim_scenario.trace_add("write", lambda *_args: self._refresh_simulation_fields())
        self.bench_scenario.trace_add("write", lambda *_args: self._refresh_benchmark_fields())
        self.bench_monitor_resources.trace_add("write", lambda *_args: self._refresh_benchmark_fields())
        for variable in self.method_vars.values():
            variable.trace_add("write", lambda *_args: self._refresh_benchmark_fields())

    def _refresh_dynamic_ui(self):
        self._refresh_simulation_fields()
        self._refresh_benchmark_fields()

    def _set_widgets_visible(self, widgets, visible):
        for widget in widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _fixed_n_for_scenario(self, scenario):
        if scenario == "sun-earth-moon":
            return 3
        if scenario == "solar-system":
            return 10
        return None

    def _scenario_uses_n_field(self, scenario):
        return scenario in {"auto", "random"}

    def _refresh_simulation_fields(self):
        method = self.sim_method.get()
        scenario = self.sim_scenario.get()
        is_two_body = method == benchmark.TWO_BODY_METHOD

        self._set_widgets_visible(self.sim_rows["scenario"], not is_two_body)
        self._set_widgets_visible(
            self.sim_rows["n"],
            not is_two_body and self._scenario_uses_n_field(scenario),
        )
        self._place_simulation_dt(not is_two_body and self._scenario_uses_n_field(scenario))
        self._set_widgets_visible(self.sim_rows["openmp"], method == "openmp")
        self._set_widgets_visible(self.sim_rows["sycl"], method == "sycl")
        self._set_widgets_visible(self.sim_rows["body_file"], not is_two_body and scenario == "body-file")

    def _place_simulation_dt(self, n_visible):
        label, entry = self.sim_rows["dt"]
        if n_visible:
            label.grid_configure(column=2, sticky="w", padx=(16, 0))
            entry.grid_configure(column=3, sticky="ew")
        else:
            label.grid_configure(column=0, sticky="w", padx=(0, 0))
            entry.grid_configure(column=1, sticky="ew")

    def _selected_benchmark_methods(self, allow_empty=False):
        methods = [method for method, var in self.method_vars.items() if var.get()]
        if not methods and not allow_empty:
            raise ValueError("Выбери хотя бы один метод")
        return methods

    def _benchmark_has_nbody_method(self, methods):
        return any(method != benchmark.TWO_BODY_METHOD for method in methods)

    def _refresh_benchmark_fields(self):
        methods = self._selected_benchmark_methods(allow_empty=True)
        has_nbody_method = self._benchmark_has_nbody_method(methods)
        uses_body_file = has_nbody_method and self.bench_scenario.get() == "body-file"
        show_n_values = has_nbody_method and not uses_body_file

        self._set_widgets_visible(self.bench_rows["n_values"], show_n_values)
        self._place_benchmark_times(show_n_values)
        self._set_widgets_visible(self.bench_rows["scenario"], has_nbody_method)
        self._set_widgets_visible(self.bench_rows["body_file"], uses_body_file)
        self._set_widgets_visible(self.bench_rows["openmp"], "openmp" in methods)
        self._set_widgets_visible(self.bench_rows["sycl"], "sycl" in methods)
        if self.bench_monitor_resources.get():
            self.bench_monitor_interval_label.pack(side="left", padx=(18, 4))
            self.bench_monitor_interval_entry.pack(side="left")
        else:
            self.bench_monitor_interval_label.pack_forget()
            self.bench_monitor_interval_entry.pack_forget()

    def _place_benchmark_times(self, n_values_visible):
        label, entry = self.bench_rows["times"]
        if n_values_visible:
            label.grid_configure(column=2, sticky="w", padx=(16, 0))
            entry.grid_configure(column=3, sticky="ew")
        else:
            label.grid_configure(column=0, sticky="w", padx=(0, 0))
            entry.grid_configure(column=1, sticky="ew")

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

    def _pick_results_csv(self, variable):
        path = filedialog.asksaveasfilename(
            initialdir=str(ROOT),
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
            defaultextension=".csv",
        )
        if path:
            variable.set(self._path_with_suffix(path, ".csv"))

    def _pick_single_trajectory_file(self):
        trajectory_format = self.sim_trajectory_format.get()
        path = filedialog.asksaveasfilename(
            initialdir=str(ROOT),
            filetypes=self._trajectory_filetypes(trajectory_format),
            defaultextension=self._trajectory_extension(trajectory_format),
        )
        if path:
            self._set_sim_trajectory_path(
                self._trajectory_path_with_format_extension(path, trajectory_format),
                auto=False,
            )

    def _pick_directory(self, variable):
        path = filedialog.askdirectory(initialdir=str(ROOT))
        if path:
            variable.set(path)

    def _trajectory_extension(self, trajectory_format):
        return ".bin" if trajectory_format == "binary" else ".csv"

    def _trajectory_filetypes(self, trajectory_format):
        if trajectory_format == "binary":
            return [("Binary trajectory", "*.bin"), ("All files", "*.*")]
        return [("CSV trajectory", "*.csv"), ("All files", "*.*")]

    def _default_trajectory_file(self, trajectory_format):
        return RESULTS_DIR / f"trajectory{self._trajectory_extension(trajectory_format)}"

    def _path_with_suffix(self, path, extension):
        path = str(path).strip()
        if not path:
            return ""
        path_obj = Path(path)
        if path_obj.suffix.lower() != extension:
            path_obj = path_obj.with_suffix(extension)
        return str(path_obj)

    def _trajectory_path_with_format_extension(self, path, trajectory_format):
        return self._path_with_suffix(path, self._trajectory_extension(trajectory_format))

    def _on_sim_trajectory_format_changed(self, *_args):
        trajectory_format = self.sim_trajectory_format.get()
        path = self.sim_trajectory.get().strip() or str(self._default_trajectory_file(trajectory_format))
        normalized = self._trajectory_path_with_format_extension(path, trajectory_format)
        if normalized != path:
            self._set_sim_trajectory_path(normalized, auto=self.sim_trajectory_auto_path)

    def _on_sim_trajectory_changed(self, *_args):
        if not self._updating_sim_trajectory:
            self.sim_trajectory_auto_path = False

    def _set_sim_trajectory_path(self, path, auto=None):
        self._updating_sim_trajectory = True
        try:
            self.sim_trajectory.set(str(path))
        finally:
            self._updating_sim_trajectory = False
        if auto is not None:
            self.sim_trajectory_auto_path = auto

    def _safe_filename_part(self, value):
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value))
        cleaned = "_".join(part for part in cleaned.split("_") if part)
        return cleaned or "run"

    def _resolved_single_scenario_name(self, n_bodies, scenario, body_file):
        if body_file:
            return Path(body_file).stem
        if scenario == "sun-earth":
            return "sun-earth"
        if scenario == "auto":
            return benchmark.SCENARIO_BY_N.get(n_bodies, "random")
        return scenario

    def _generated_single_trajectory_file(self, trajectory_format, method, n_bodies, t_hours, scenario, body_file):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        scenario_name = self._safe_filename_part(
            self._resolved_single_scenario_name(n_bodies, scenario, body_file)
        )
        t_part = self._safe_filename_part(f"{t_hours:g}h")
        extension = self._trajectory_extension(trajectory_format)
        filename = f"single_{method}_{scenario_name}_n{n_bodies}_t{t_part}_{timestamp}{extension}"
        return RESULTS_DIR / "trajectories" / filename

    def _single_trajectory_path(self, trajectory_format, method, n_bodies, t_hours, scenario, body_file):
        path = self.sim_trajectory.get().strip()
        default_csv = str(self._default_trajectory_file("csv"))
        default_bin = str(self._default_trajectory_file("binary"))
        if self.sim_trajectory_auto_path or not path or path in {default_csv, default_bin}:
            path = str(self._generated_single_trajectory_file(
                trajectory_format, method, n_bodies, t_hours, scenario, body_file
            ))
            self._set_sim_trajectory_path(path, auto=True)
        normalized = self._trajectory_path_with_format_extension(path, trajectory_format)
        if normalized != path:
            self._set_sim_trajectory_path(normalized, auto=self.sim_trajectory_auto_path)
            path = normalized
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

    def _single_run_body_count(self, scenario, body_file):
        if body_file:
            body_count = count_body_rows(body_file)
            if body_count < 1:
                raise ValueError("Файл тел не содержит ни одного тела")
            return body_count
        fixed_count = self._fixed_n_for_scenario(scenario)
        if fixed_count is not None:
            return fixed_count
        return self._int_value(self.sim_n, "N")

    def run_single_simulation(self):
        try:
            method = self.sim_method.get()
            dt_s = self._float_value(self.sim_dt, "dt")
            t_hours = self._float_value(self.sim_t_hours, "T")
            threads = self._int_value(self.sim_threads, "OpenMP threads") if method == "openmp" else 1
            if method == benchmark.TWO_BODY_METHOD:
                n_bodies = 2
                scenario, body_file = "sun-earth", None
            else:
                scenario, body_file = self._scenario_and_body_file(self.sim_scenario, self.sim_body_file)
                n_bodies = self._single_run_body_count(scenario, body_file)
            trajectory_format = self.sim_trajectory_format.get()
            trajectory_file = self._single_trajectory_path(
                trajectory_format, method, n_bodies, t_hours, scenario, body_file
            ) if self.sim_write_trajectory.get() else ""
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return

        exe_path = benchmark.find_executable(benchmark.METHODS[method])
        if exe_path is None:
            messagebox.showerror("Бинарник не найден", "Сначала собери выбранный метод.")
            return

        if method == benchmark.TWO_BODY_METHOD:
            command = [exe_path, dt_s, t_hours * 3600.0, "--scenario", scenario]
        else:
            command = [exe_path, n_bodies, dt_s, t_hours * 3600.0]
        if method == "openmp":
            command.append(threads)
        if method != benchmark.TWO_BODY_METHOD:
            command.append(scenario)
        if body_file and method != benchmark.TWO_BODY_METHOD:
            command.extend(["--bodies", body_file])
        if method == "sycl":
            command.extend(["--device", self.sim_device.get()])
        if trajectory_file:
            command.extend(["--trajectory", trajectory_file])
            command.extend(["--trajectory-format", trajectory_format])

        env_factory = benchmark.load_oneapi_env if method == "sycl" else None
        self._run_process(
            command,
            env_factory=env_factory,
            callback=lambda returncode, output: self._save_single_run(
                returncode, output, method, n_bodies, dt_s, t_hours, threads,
                scenario, body_file, trajectory_file, trajectory_format, command
            ),
        )

    def _save_single_run(self, returncode, output, method, n_bodies, dt_s, t_hours,
                         threads, scenario, body_file, trajectory_file, trajectory_format, command):
        if returncode != 0:
            return
        csv_path = self._path_with_suffix(self.sim_csv.get(), ".csv")
        if not csv_path:
            return
        if csv_path != self.sim_csv.get().strip():
            self.sim_csv.set(csv_path)
        try:
            metrics = benchmark.parse_metrics(output)
            actual_n = self._actual_body_count(method, n_bodies, scenario, body_file)
            reported_threads = metrics.get("threads", 0)
            if method in {"serial", benchmark.TWO_BODY_METHOD}:
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
                "command": " ".join(str(part) for part in command),
            }
            benchmark.save_results([row], csv_path)
            self._append_log(f"Saved run metrics to {csv_path}\n")
            if trajectory_file and hasattr(self, "trajectory_viewer"):
                self.trajectory_viewer.set_path(trajectory_file, trajectory_format)
        except Exception as exc:
            messagebox.showerror("CSV не сохранен", str(exc))

    def _actual_body_count(self, method, n_bodies, scenario, body_file):
        if method == benchmark.TWO_BODY_METHOD:
            return 2
        if body_file:
            return count_body_rows(body_file)
        resolved = benchmark.SCENARIO_BY_N.get(n_bodies, "random") if scenario == "auto" else scenario
        if resolved == "sun-earth-moon":
            return 3
        if resolved == "solar-system":
            return 10
        return n_bodies

    def _benchmark_config_from_ui(self):
        methods = self._selected_benchmark_methods()
        has_nbody_method = self._benchmark_has_nbody_method(methods)
        scenario_choice = self.bench_scenario.get()
        scenario = None
        body_file = None
        if has_nbody_method and scenario_choice == "body-file":
            body_file = self.bench_body_file.get().strip()
            if not body_file:
                raise ValueError("Для сценария body-file нужен файл тел")
            scenario = "auto"
        elif has_nbody_method and scenario_choice != "auto-by-n":
            scenario = scenario_choice

        config = {
            "methods": methods,
            "n_values": (
                [count_body_rows(body_file)] if body_file else
                self._number_list(self.bench_n_values, int, "N values") if has_nbody_method else
                [2]
            ),
            "times_hours": self._number_list(self.bench_times, float, "T hours"),
            "dt_s": self._float_value(self.bench_dt, "dt"),
            "scenario": scenario,
            "scenario_by_n": {str(key): value for key, value in benchmark.SCENARIO_BY_N.items()},
            "body_file": body_file,
            "openmp_threads": (
                self._int_value(self.bench_threads, "OpenMP threads")
                if "openmp" in methods else (os.cpu_count() or 1)
            ),
            "device": self.bench_device.get(),
            "output_dir": self.bench_output_dir.get().strip() or None,
            "results_csv": None,
            "plots_dir": None,
            "resource_csv": None,
            "trajectory_dir": "trajectories" if self.bench_write_trajectory.get() else None,
            "trajectory_format": self.bench_trajectory_format.get(),
            "use_default_skips": self.bench_default_skips.get(),
            "monitor_resources": self.bench_monitor_resources.get(),
            "monitor_interval_s": self._float_value(self.bench_monitor_interval, "Интервал мониторинга"),
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
            self.bench_output_dir.set(config.get("output_dir") or "")
            self.bench_write_trajectory.set(bool(config.get("trajectory_dir")))
            self.bench_trajectory_format.set(config.get("trajectory_format", "csv"))
            self.bench_default_skips.set(config["use_default_skips"])
            self.bench_monitor_resources.set(config["monitor_resources"])
            self.bench_monitor_interval.set(str(config["monitor_interval_s"]))
            if config.get("body_file"):
                self.bench_scenario.set("body-file")
                self.bench_body_file.set(config["body_file"])
            elif config.get("scenario"):
                self.bench_scenario.set(config["scenario"])
            else:
                self.bench_scenario.set("auto-by-n")
            self._refresh_dynamic_ui()
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
            self._refresh_dynamic_ui()


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
