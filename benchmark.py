#!/usr/bin/env python3
"""Benchmark runner and plotter for N-body implementations.

Usage:
  python benchmark.py --run   # run benchmarks and save CSV
  python benchmark.py --plot  # load CSV and draw graphs
  python benchmark.py         # run and plot if possible
"""

import argparse
import codecs
import csv
import datetime
import json
import math
import os
import re
import shutil
import shlex
import subprocess
import threading
import time
from pathlib import Path

_MPLCONFIGDIR = Path.cwd() / "benchmark_results" / "matplotlib_cache"
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR.resolve()))
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator

# Benchmark configuration
FIXED_DT = 3600.0  # seconds (1 hour)
NS = [3, 10, 100, 1000]
# Total simulation times in hours. Эта сетка задаёт размер эксперимента по времени.
TIMES_HOURS = [24, 168, 720, 8760]  # 1 day, 7 days, 30 days, 365 days
SKIPPED_BENCHMARKS = {
    ("serial", 1000, 8760): "serial N=1000 T=8760h is too slow for routine benchmark runs",
}

METHODS = {
    "serial": "nbody_serial",
    "openmp": "nbody_openmp",
    "sycl": "nbody_sycl",
    "two-body": "two_body_solver",
}
TWO_BODY_METHOD = "two-body"
METHOD_ALIASES = {
    "twobody": TWO_BODY_METHOD,
    "two_body": TWO_BODY_METHOD,
    "two_body_solver": TWO_BODY_METHOD,
}

SCENARIO_BY_N = {
    3: "sun-earth-moon",
    10: "solar-system",
    100: "random",
    1000: "random",
}

CSV_HEADERS = [
    "timestamp",
    "method",
    "executable",
    "n_bodies",
    "scenario",
    "body_config_file",
    "t_hours",
    "dt_s",
    "t_max_s",
    "execution_time_s",
    "gflops",
    "energy_error",
    "steps_completed",
    "threads",
    "compute_units",
    "device_type",
    "device_name",
    "trajectory_file",
    "trajectory_format",
    "command",
]
RESOURCE_HEADERS = [
    "run_id",
    "timestamp",
    "method",
    "n_bodies",
    "t_hours",
    "elapsed_s",
    "progress_pct",
    "cpu_percent",
    "gpu_percent",
]

RESULTS_DIR = Path("benchmark_results")
RUNS_DIR = RESULTS_DIR / "runs"
PLOTS_DIR = RESULTS_DIR / "plots"
ACPP_CACHE_DIR = RESULTS_DIR / "acpp_cache"
CSV_PATH = RESULTS_DIR / "benchmark_results.csv"
RESOURCE_CSV_PATH = RESULTS_DIR / "resource_usage.csv"
LATEST_RUN_FILE = RESULTS_DIR / "latest_run.txt"
DEFAULT_ONEAPI_SETVARS = Path("/opt/intel/oneapi/setvars.sh")
_ONEAPI_ENV_CACHE = None
FLOAT_PATTERN = r"[-+]?(?:nan|inf|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"

OUTPUT_PATTERNS = {
    "execution_time_s": re.compile(rf"Execution time:\s*({FLOAT_PATTERN})\s*seconds", re.IGNORECASE),
    "gflops": re.compile(rf"Performance:\s*({FLOAT_PATTERN})\s*GFLOP/s", re.IGNORECASE),
    "energy_error": re.compile(rf"Energy error:\s*({FLOAT_PATTERN})", re.IGNORECASE),
    "steps_completed": re.compile(r"Steps completed:\s*(\d+)"),
}
OPTIONAL_PATTERNS = {
    "threads": re.compile(r"(?:Number\s+of\s+threads|Threads):\s*(\d+)", re.IGNORECASE),
    "compute_units": re.compile(r"Compute\s+Units:\s*(\d+)", re.IGNORECASE),
    "device_type": re.compile(r"Device\s+Type:\s*(.+)", re.IGNORECASE),
    "device_name": re.compile(r"Device\s+Name:\s*(.+)", re.IGNORECASE),
}

DEFAULT_BENCHMARK_CONFIG = {
    "methods": ["serial", "openmp"],
    "n_values": NS,
    "times_hours": TIMES_HOURS,
    "dt_s": FIXED_DT,
    "scenario": None,
    "scenario_by_n": {str(key): value for key, value in SCENARIO_BY_N.items()},
    "body_file": None,
    "openmp_threads": os.cpu_count() or 1,
    "device": "auto",
    "output_dir": None,
    "results_csv": None,
    "plots_dir": None,
    "trajectory_dir": None,
    "trajectory_format": "csv",
    "use_default_skips": True,
    "monitor_resources": False,
    "monitor_interval_s": 0.5,
    "resource_csv": None,
}

METHOD_COLORS = {
    "serial": "#1f77b4",
    "openmp": "#ff7f0e",
    "sycl": "#2ca02c",
    TWO_BODY_METHOD: "#9467bd",
}
METHOD_MARKERS = {
    "serial": "o",
    "openmp": "s",
    "sycl": "^",
    TWO_BODY_METHOD: "D",
}
METHOD_LABELS = {
    "serial": "Последовательный",
    "openmp": "OpenMP",
    "sycl": "SYCL",
    TWO_BODY_METHOD: "Два тела",
}
TIME_LINESTYLES = ["-", "--", "-.", ":"]
METHOD_ORDER = {method: index for index, method in enumerate(METHODS)}
RESOURCE_PROGRESS_TICKS = list(range(0, 101, 10))


def parse_csv_values(value, cast):
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return [cast(item) for item in items]


def count_body_rows(path):
    rows = 0
    with Path(path).open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(line for line in csvfile if not line.lstrip().startswith("#"))
        for row in reader:
            if not row:
                continue
            try:
                float(row[0])
            except (TypeError, ValueError):
                continue
            rows += 1
    if rows < 1:
        raise ValueError(f"Body CSV does not contain any body rows: {path}")
    return rows


def normalize_method_name(method):
    method = str(method).lower()
    return METHOD_ALIASES.get(method, method)


def sanitize_path_token(value):
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip())
    return token.strip("-") or "all"


def benchmark_output_name(config):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    methods = sanitize_path_token("-".join(config.get("methods") or ["methods"]))
    n_values = sanitize_path_token("-".join(str(value) for value in config.get("n_values") or ["n"]))
    return f"{timestamp}_{methods}_n{n_values}"


def latest_run_dir():
    try:
        value = LATEST_RUN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def remember_latest_run(output_dir):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_RUN_FILE.write_text(str(Path(output_dir)), encoding="utf-8")


def path_in_output_dir(output_dir, configured_path, default_name):
    if configured_path:
        configured = Path(configured_path)
        if configured.is_absolute():
            return configured
        return Path(output_dir) / configured
    return Path(output_dir) / default_name


def resolve_benchmark_output_paths(config, *, for_run=False, for_plot=False):
    explicit_paths = any(config.get(key) for key in ("results_csv", "plots_dir", "resource_csv"))
    output_dir = Path(config["output_dir"]) if config.get("output_dir") else None

    if output_dir is None and not explicit_paths:
        if for_run:
            output_dir = RUNS_DIR / benchmark_output_name(config)
        elif for_plot:
            output_dir = latest_run_dir()
            if output_dir is None and CSV_PATH.exists():
                output_dir = RESULTS_DIR

    if output_dir is not None:
        config["output_dir"] = str(output_dir)
        config["results_csv"] = str(path_in_output_dir(output_dir, config.get("results_csv"), "benchmark_results.csv"))
        config["plots_dir"] = str(path_in_output_dir(output_dir, config.get("plots_dir"), "plots"))
        config["resource_csv"] = str(path_in_output_dir(output_dir, config.get("resource_csv"), "resource_usage.csv"))
        if config.get("trajectory_dir"):
            config["trajectory_dir"] = str(path_in_output_dir(output_dir, config["trajectory_dir"], "trajectories"))
        return config

    config["results_csv"] = str(config.get("results_csv") or CSV_PATH)
    config["plots_dir"] = str(config.get("plots_dir") or PLOTS_DIR)
    config["resource_csv"] = str(config.get("resource_csv") or RESOURCE_CSV_PATH)
    return config


def normalize_benchmark_config(raw_config=None):
    config = dict(DEFAULT_BENCHMARK_CONFIG)
    if raw_config:
        config.update(raw_config)

    methods = config.get("methods") or []
    if isinstance(methods, str):
        methods = parse_csv_values(methods, str)
    config["methods"] = [
        normalized for method in methods
        if (normalized := normalize_method_name(method)) in METHODS
    ]
    if not config["methods"]:
        raise ValueError("Benchmark configuration must include at least one known method")

    n_values = config.get("n_values", NS)
    if isinstance(n_values, str):
        n_values = parse_csv_values(n_values, int)
    config["n_values"] = [int(value) for value in n_values]

    times_hours = config.get("times_hours", TIMES_HOURS)
    if isinstance(times_hours, str):
        times_hours = parse_csv_values(times_hours, float)
    config["times_hours"] = [float(value) for value in times_hours]

    config["dt_s"] = float(config.get("dt_s", FIXED_DT))
    config["openmp_threads"] = int(config.get("openmp_threads") or (os.cpu_count() or 1))
    config["device"] = (config.get("device") or "auto").lower()
    if config["device"] not in {"auto", "cpu", "gpu"}:
        raise ValueError("SYCL device must be auto, cpu, or gpu")

    scenario = config.get("scenario")
    config["scenario"] = scenario if scenario else None
    config["scenario_by_n"] = config.get("scenario_by_n") or {
        str(key): value for key, value in SCENARIO_BY_N.items()
    }
    config["body_file"] = str(config["body_file"]) if config.get("body_file") else None
    config["output_dir"] = str(config["output_dir"]) if config.get("output_dir") else None
    config["results_csv"] = str(config["results_csv"]) if config.get("results_csv") else None
    config["plots_dir"] = str(config["plots_dir"]) if config.get("plots_dir") else None
    config["trajectory_dir"] = str(config["trajectory_dir"]) if config.get("trajectory_dir") else None
    config["trajectory_format"] = (config.get("trajectory_format") or "csv").lower()
    if config["trajectory_format"] not in {"csv", "binary", "bin"}:
        raise ValueError("Trajectory format must be csv or binary")
    if config["trajectory_format"] == "bin":
        config["trajectory_format"] = "binary"
    config["use_default_skips"] = bool(config.get("use_default_skips", True))
    config["monitor_resources"] = bool(config.get("monitor_resources", False))
    config["monitor_interval_s"] = max(0.1, float(config.get("monitor_interval_s") or 0.5))
    config["resource_csv"] = str(config["resource_csv"]) if config.get("resource_csv") else None
    return config


def load_benchmark_config(config_path):
    with Path(config_path).open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def resolve_scenario(n_bodies, scenario=None, scenario_by_n=None):
    if scenario:
        return scenario
    mapping = scenario_by_n or SCENARIO_BY_N
    return mapping.get(str(n_bodies)) or mapping.get(n_bodies) or "random"


def scenario_display_name(n_bodies, scenario, body_file=None):
    if body_file:
        return f"Body file: {Path(body_file).name}"
    labels = {
        "auto": scenario_label(n_bodies),
        "sun-earth": "Sun-Earth analytical",
        "two-body": "Sun-Earth analytical",
        "elliptical": "Elliptical two-body",
        "sun-earth-moon": "Sun-Earth-Moon",
        "solar-system": "Solar system + Pluto",
        "random": f"Random test ({n_bodies} bodies)",
    }
    return labels.get(scenario, scenario)


def benchmark_trajectory_path(trajectory_dir, method, n_bodies, t_hours, trajectory_format="csv"):
    if not trajectory_dir:
        return None
    t_label = str(t_hours).replace(".", "p")
    extension = "bin" if trajectory_format == "binary" else "csv"
    output_dir = Path(trajectory_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{method}_n{n_bodies}_t{t_label}h.{extension}"


def benchmark_n_values_for_method(method, n_values, body_file=None):
    if method == TWO_BODY_METHOD:
        return [2]
    if body_file:
        return [count_body_rows(body_file)]
    return n_values


def scenario_label(n):
    if n == 3:
        return "Sun-Earth-Moon"
    if n == 10:
        return "Solar system + Pluto"
    if n == 100:
        return "Random test (100 bodies)"
    if n == 1000:
        return "Random test (1000 bodies)"
    return f"N={n}"


def find_executable(exe_name: str) -> Path | None:
    root = Path.cwd()
    candidates = [root / exe_name, root / "build" / exe_name, root / "bin" / exe_name]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


def load_oneapi_env():
    """Return an environment with Intel oneAPI variables loaded."""
    global _ONEAPI_ENV_CACHE
    if _ONEAPI_ENV_CACHE is not None:
        return _ONEAPI_ENV_CACHE

    env = os.environ.copy()
    ACPP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    env.setdefault("ACPP_APPDB_DIR", str(ACPP_CACHE_DIR.resolve()))
    env.setdefault("MPLCONFIGDIR", str((RESULTS_DIR / "matplotlib_cache").resolve()))
    setvars_path = Path(os.environ.get("ONEAPI_SETVARS", DEFAULT_ONEAPI_SETVARS))
    if not setvars_path.exists():
        print(f"Warning: oneAPI setvars not found at {setvars_path}; running SYCL with current environment.")
        _ONEAPI_ENV_CACHE = env
        return _ONEAPI_ENV_CACHE

    command = f"source {shlex.quote(str(setvars_path))} >/dev/null 2>&1 && env -0"
    process = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        env=env,
    )
    if process.returncode != 0:
        print(f"Warning: failed to source {setvars_path}; running SYCL with current environment.")
        _ONEAPI_ENV_CACHE = env
        return _ONEAPI_ENV_CACHE

    for item in process.stdout.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        env[key.decode("utf-8", "surrogateescape")] = value.decode("utf-8", "surrogateescape")

    _ONEAPI_ENV_CACHE = env
    return _ONEAPI_ENV_CACHE


def read_cpu_times():
    try:
        with Path("/proc/stat").open("r", encoding="utf-8") as stat_file:
            parts = stat_file.readline().split()
    except OSError:
        return None
    if not parts or parts[0] != "cpu":
        return None
    values = [float(value) for value in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0.0)
    total = sum(values)
    return idle, total


def cpu_percent_between(previous, current):
    if previous is None or current is None:
        return None
    idle_delta = current[0] - previous[0]
    total_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))


def detect_gpu_probe():
    if shutil.which("nvidia-smi"):
        return "nvidia-smi"
    if shutil.which("rocm-smi"):
        return "rocm-smi"
    return None


def read_gpu_percent(probe):
    if probe == "nvidia-smi":
        command = [
            "nvidia-smi",
            "--query-gpu=utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    elif probe == "rocm-smi":
        command = ["rocm-smi", "--showuse"]
    else:
        return None

    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    if process.returncode != 0:
        return None

    values = []
    for line in process.stdout.splitlines():
        if probe == "nvidia-smi":
            match = re.search(r"(\d+(?:\.\d+)?)", line)
        else:
            match = re.search(r"GPU\s+use.*?(\d+(?:\.\d+)?)", line, re.IGNORECASE)
            if not match:
                match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
        if match:
            values.append(float(match.group(1)))
    if not values:
        return None
    return max(0.0, min(100.0, sum(values) / len(values)))


class ResourceSampler:
    def __init__(self, run_context, interval_s=0.5):
        self.run_context = run_context
        self.interval_s = interval_s
        self.samples = []
        self._stop = threading.Event()
        self._thread = None
        self._start_time = None
        self._previous_cpu = None
        self._gpu_probe = detect_gpu_probe()

    def start(self):
        self._start_time = time.monotonic()
        self._previous_cpu = read_cpu_times()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s + 1.0)
        total_duration = max(time.monotonic() - self._start_time, 1e-9)
        self._sample(elapsed_s=total_duration)
        for sample in self.samples:
            sample["progress_pct"] = min(100.0, 100.0 * sample["elapsed_s"] / total_duration)
        return self.samples

    def _loop(self):
        while not self._stop.wait(self.interval_s):
            self._sample()

    def _sample(self, elapsed_s=None):
        current_cpu = read_cpu_times()
        cpu_percent = cpu_percent_between(self._previous_cpu, current_cpu)
        self._previous_cpu = current_cpu
        if elapsed_s is None:
            elapsed_s = time.monotonic() - self._start_time
        sample = dict(self.run_context)
        sample.update({
            "timestamp": datetime.datetime.now().isoformat(),
            "elapsed_s": elapsed_s,
            "progress_pct": 0.0,
            "cpu_percent": cpu_percent,
            "gpu_percent": read_gpu_percent(self._gpu_probe),
        })
        self.samples.append(sample)


def parse_metrics(output: str):
    data = {}
    for key, pattern in OUTPUT_PATTERNS.items():
        match = pattern.search(output)
        if not match:
            raise ValueError(f"Unable to parse '{key}' from output")
        value = match.group(1)
        data[key] = float(value) if key != "steps_completed" else int(value)

    for key, pattern in OPTIONAL_PATTERNS.items():
        match = pattern.search(output)
        if key in {"threads", "compute_units"}:
            data[key] = int(match.group(1)) if match else 0
        else:
            data[key] = match.group(1).strip() if match else ""

    return data


def run_simulation(
    method: str,
    n_bodies: int,
    t_hours: float,
    device_choice: str,
    *,
    dt_s: float = FIXED_DT,
    scenario: str | None = None,
    scenario_by_n: dict | None = None,
    body_file: str | None = None,
    openmp_threads: int | None = None,
    use_default_skips: bool = True,
    trajectory_dir: str | None = None,
    trajectory_format: str = "csv",
    monitor_resources: bool = False,
    monitor_interval_s: float = 0.5,
    resource_samples: list | None = None,
):
    if method not in METHODS:
        raise ValueError(f"Unknown benchmark method: {method}")

    effective_n_bodies = 2 if method == TWO_BODY_METHOD else n_bodies
    skip_reason = SKIPPED_BENCHMARKS.get((method, effective_n_bodies, int(t_hours))) if use_default_skips else None
    if skip_reason:
        print(f"Skipping {method} | N={effective_n_bodies} | T={t_hours}h: {skip_reason}", flush=True)
        return None

    exe_name = METHODS[method]
    exe_path = find_executable(exe_name)
    if exe_path is None:
        print(f"Warning: executable for method '{method}' not found. Skipping.", flush=True)
        return None

    t_max_s = t_hours * 3600.0
    if method == TWO_BODY_METHOD:
        selected_scenario = scenario if scenario in {"sun-earth", "two-body", "elliptical"} else "sun-earth"
        command = [str(exe_path), str(dt_s), str(t_max_s), "--scenario", selected_scenario]
    else:
        selected_scenario = resolve_scenario(n_bodies, scenario, scenario_by_n)
        command = [str(exe_path), str(n_bodies), str(dt_s), str(t_max_s)]
    requested_threads = 0

    if method == "openmp":
        requested_threads = int(openmp_threads or (os.cpu_count() or 1))
        command.append(str(requested_threads))

    if method != TWO_BODY_METHOD:
        command.append(selected_scenario)
    if body_file and method != TWO_BODY_METHOD:
        command.extend(["--bodies", str(body_file)])
    if method == "sycl":
        command.extend(["--device", device_choice])
    trajectory_file = benchmark_trajectory_path(
        trajectory_dir,
        method,
        effective_n_bodies,
        t_hours,
        trajectory_format,
    )
    if trajectory_file is not None:
        command.extend(["--trajectory", str(trajectory_file)])
        command.extend(["--trajectory-format", trajectory_format])

    print(f"Running {method} | N={effective_n_bodies} | T={t_hours}h | cmd={command}", flush=True)
    env = load_oneapi_env() if method == "sycl" else None
    output_parts = []
    run_id = (
        f"{method}_n{effective_n_bodies}_t{str(t_hours).replace('.', 'p')}_"
        f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )
    sampler = None
    if monitor_resources:
        sampler = ResourceSampler(
            {
                "run_id": run_id,
                "method": method,
                "n_bodies": effective_n_bodies,
                "t_hours": t_hours,
            },
            interval_s=monitor_interval_s,
        )
        sampler.start()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        env=env,
    )
    assert process.stdout is not None
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while True:
        raw_chunk = os.read(process.stdout.fileno(), 4096)
        if not raw_chunk:
            break
        chunk = decoder.decode(raw_chunk)
        if chunk:
            output_parts.append(chunk)
            print(chunk, end="", flush=True)
    tail = decoder.decode(b"", final=True)
    if tail:
        output_parts.append(tail)
        print(tail, end="", flush=True)
    returncode = process.wait()
    if sampler is not None:
        samples = sampler.stop()
        if resource_samples is not None:
            resource_samples.extend(samples)
    output = "".join(output_parts)
    if returncode != 0:
        raise RuntimeError(
            f"Benchmark failed for {exe_name} N={effective_n_bodies} T={t_hours}h\n"
            f"output:\n{output}"
        )

    metrics = parse_metrics(output)
    reported_threads = metrics.get("threads", 0)
    if method in {"serial", TWO_BODY_METHOD}:
        reported_threads = 1
    elif method == "openmp" and reported_threads == 0:
        reported_threads = requested_threads

    metrics.update({
        "timestamp": datetime.datetime.now().isoformat(),
        "method": method,
        "executable": exe_name,
        "n_bodies": effective_n_bodies,
        "scenario": scenario_display_name(
            effective_n_bodies,
            selected_scenario,
            body_file if method != TWO_BODY_METHOD else None,
        ),
        "body_config_file": body_file if method != TWO_BODY_METHOD and body_file else "",
        "t_hours": t_hours,
        "dt_s": dt_s,
        "t_max_s": t_max_s,
        "threads": reported_threads,
        "compute_units": metrics.get("compute_units", 0),
        "device_type": metrics.get("device_type", ""),
        "device_name": metrics.get("device_name", ""),
        "trajectory_file": str(trajectory_file or ""),
        "trajectory_format": trajectory_format if trajectory_file is not None else "",
        "command": " ".join(command),
    })
    return metrics


def save_results(rows, csv_path=CSV_PATH):
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    fieldnames = CSV_HEADERS
    if not write_header:
        with csv_path.open("r", newline="", encoding="utf-8") as csvfile:
            existing_header = next(csv.reader(csvfile), None)
            if existing_header:
                fieldnames = existing_header
    with csv_path.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    print(f"Saved {len(rows)} rows to {csv_path}")


def save_resource_samples(samples, csv_path=RESOURCE_CSV_PATH):
    if not samples:
        print("No resource usage samples collected")
        return
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=RESOURCE_HEADERS)
        if write_header:
            writer.writeheader()
        for sample in samples:
            writer.writerow({key: sample.get(key, "") for key in RESOURCE_HEADERS})
    print(f"Saved {len(samples)} resource usage samples to {csv_path}")


def load_results(csv_path=CSV_PATH):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Benchmark CSV not found: {csv_path}")
    rows = []
    with csv_path.open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            row["n_bodies"] = int(row["n_bodies"])
            row["t_hours"] = float(row["t_hours"])
            row["dt_s"] = float(row["dt_s"])
            row["t_max_s"] = float(row["t_max_s"])
            row["execution_time_s"] = float(row["execution_time_s"])
            row["gflops"] = float(row["gflops"])
            row["energy_error"] = float(row["energy_error"])
            row["steps_completed"] = int(row["steps_completed"])
            row["threads"] = int(row["threads"]) if row.get("threads") else 0
            row["compute_units"] = int(row["compute_units"]) if row.get("compute_units") else 0
            row["device_type"] = row.get("device_type", "")
            row["device_name"] = row.get("device_name", "")
            rows.append(row)
    return rows


def load_resource_samples(csv_path=RESOURCE_CSV_PATH):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return []
    rows = []
    with csv_path.open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                row["n_bodies"] = int(row["n_bodies"])
                row["t_hours"] = float(row["t_hours"])
                row["elapsed_s"] = float(row["elapsed_s"])
                row["progress_pct"] = float(row["progress_pct"])
                row["cpu_percent"] = float(row["cpu_percent"]) if row.get("cpu_percent") else math.nan
                row["gpu_percent"] = float(row["gpu_percent"]) if row.get("gpu_percent") else math.nan
            except (TypeError, ValueError):
                continue
            rows.append(row)
    return rows


def method_sort_key(method):
    return (METHOD_ORDER.get(method, len(METHOD_ORDER)), method)


def format_hours(hours):
    return f"{int(hours)} ч" if float(hours).is_integer() else f"{hours:g} ч"


def format_plain_number(value, _position=None):
    if not math.isfinite(value):
        return ""
    return f"{value:g}"


def method_display_name(method):
    return METHOD_LABELS.get(method, method)


def style_for_t_hours(t_hours):
    values = sorted(TIMES_HOURS)
    try:
        index = values.index(int(t_hours) if float(t_hours).is_integer() else t_hours)
    except ValueError:
        index = len(values)
    return TIME_LINESTYLES[index % len(TIME_LINESTYLES)]


def method_from_label(label):
    return str(label).split()[0]


def finite_positive(value, *, positive=False):
    return math.isfinite(value) and (value > 0 if positive else True)


def plot_line(rows, x_key, y_key, title, ylabel, filename, plots_dir=PLOTS_DIR,
              logx=False, logy=False, group_by="method"):
    groups = {}
    for row in rows:
        if group_by == "method_t_hours":
            key = (row["method"], row["t_hours"])
        else:
            key = (row[group_by], None)
        groups.setdefault(key, []).append(row)

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted_any = False

    for (method, t_hours), group_rows in sorted(
        groups.items(),
        key=lambda item: (method_sort_key(item[0][0]), item[0][1] or 0),
    ):
        sorted_rows = sorted(group_rows, key=lambda x: (x["n_bodies"], x["t_hours"]))
        xs = []
        ys = []
        for row in sorted_rows:
            x = row[x_key]
            y = row[y_key]
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            if logx and x <= 0:
                continue
            if logy and y <= 0:
                continue
            xs.append(x)
            ys.append(y)
        if not xs:
            continue
        color = METHOD_COLORS.get(method)
        linestyle = style_for_t_hours(t_hours) if group_by == "method_t_hours" else "-"
        marker = METHOD_MARKERS.get(method, "o")
        label = method_display_name(method)
        if group_by == "method_t_hours":
            label = f"{label}, {format_hours(t_hours)}"
        ax.plot(xs, ys, marker=marker, linestyle=linestyle, color=color, label=label)
        plotted_any = True

    if not plotted_any:
        plt.close(fig)
        print(f"Skipping plot {filename}: no finite positive data for requested scale")
        return None

    ax.set_title(title)
    ax.set_xlabel("Количество тел (N)" if x_key == "n_bodies" else x_key)
    ax.set_ylabel(ylabel)
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(fontsize="small", loc="best")
    fig.tight_layout()
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)
    filepath = plots_dir / filename
    fig.savefig(filepath)
    print(f"Saved plot {filepath}")
    return fig


def plot_speedup(rows, filename, plots_dir=PLOTS_DIR, methods=("openmp",)):
    serial_map = {
        (r["n_bodies"], r["t_hours"]): r
        for r in rows
        if r["method"] == "serial"
    }
    method_maps = {
        method: {
            (r["n_bodies"], r["t_hours"]): r
            for r in rows
            if r["method"] == method
        }
        for method in methods
    }

    fig, ax = plt.subplots(figsize=(9, 5))
    plotted_any = False

    for method in sorted(methods, key=method_sort_key):
        method_map = method_maps.get(method, {})
        if not method_map:
            continue
        for t_hours in sorted({r["t_hours"] for r in rows}):
            x = []
            y = []
            for n in sorted({r["n_bodies"] for r in rows}):
                key = (n, t_hours)
                if key not in serial_map or key not in method_map:
                    continue
                srow = serial_map[key]
                mrow = method_map[key]
                serial_time = srow["execution_time_s"]
                method_time = mrow["execution_time_s"]
                if not finite_positive(serial_time, positive=True) or not finite_positive(method_time, positive=True):
                    continue
                x.append(n)
                y.append(serial_time / method_time)
            if x:
                ax.plot(
                    x,
                    y,
                    marker=METHOD_MARKERS.get(method, "o"),
                    linestyle=style_for_t_hours(t_hours),
                    color=METHOD_COLORS.get(method),
                    label=f"{method_display_name(method)}, {format_hours(t_hours)}",
                )
                plotted_any = True

    if not plotted_any:
        print("Нет данных для расчёта speedup")
        return

    ax.axhline(1.0, color="#666666", linewidth=1.0, linestyle=":", label="Уровень последовательной версии")
    ax.set_title("Ускорение относительно последовательной версии")
    ax.set_xlabel("Количество тел (N)")
    ax.set_ylabel("Ускорение, раз")
    ax.set_xscale("log")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(fontsize="small", loc="best")
    fig.tight_layout()
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)
    filepath = plots_dir / filename
    fig.savefig(filepath)
    print(f"Saved plot {filepath}")
    return fig


def plot_efficiency(rows, filename, plots_dir=PLOTS_DIR):
    serial_map = {(r["n_bodies"], r["t_hours"]): r for r in rows if r["method"] == "serial"}
    fig, ax = plt.subplots(figsize=(9, 5))
    plotted_any = False

    for method in sorted(set(r["method"] for r in rows if r["method"] != "serial"), key=method_sort_key):
        for t_hours in sorted({r["t_hours"] for r in rows}):
            x = []
            y = []
            for n in sorted({r["n_bodies"] for r in rows}):
                key = (n, t_hours)
                if key in serial_map:
                    srow = serial_map[key]
                    mrow = next((r for r in rows if r["method"] == method and r["n_bodies"] == n and r["t_hours"] == t_hours), None)
                    if not mrow:
                        continue
                    resource_count = mrow.get("threads") or mrow.get("compute_units") or 1
                    if resource_count <= 0:
                        continue
                    if not math.isfinite(srow["execution_time_s"]) or not math.isfinite(mrow["execution_time_s"]):
                        continue
                    if srow["execution_time_s"] <= 0 or mrow["execution_time_s"] <= 0:
                        continue
                    speedup = srow["execution_time_s"] / mrow["execution_time_s"]
                    x.append(n)
                    y.append(speedup / resource_count)
            if x:
                ax.plot(
                    x,
                    y,
                    marker=METHOD_MARKERS.get(method, "o"),
                    linestyle=style_for_t_hours(t_hours),
                    color=METHOD_COLORS.get(method),
                    label=f"{method_display_name(method)}, {format_hours(t_hours)}",
                )
                plotted_any = True

    if not plotted_any:
        print("Нет данных для расчёта эффективности")
        return

    ax.set_title("Эффективность распараллеливания")
    ax.set_xlabel("Количество тел (N)")
    ax.set_ylabel("Эффективность (ускорение / ресурсы)")
    ax.set_xscale("log")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(fontsize="small", loc="best")
    fig.tight_layout()
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)
    filepath = plots_dir / filename
    fig.savefig(filepath)
    print(f"Saved plot {filepath}")
    return fig


def plot_execution_time_vs_duration_for_n(rows, n_values, title, filename, plots_dir=PLOTS_DIR):
    rows_by_n = {
        n: [row for row in rows if row["n_bodies"] == n]
        for n in n_values
    }
    available = [n for n in n_values if rows_by_n[n]]
    if not available:
        print(f"Skipping plot {filename}: no rows for N={n_values}")
        return None

    fig, axes = plt.subplots(
        1,
        len(available),
        figsize=(6.4 * len(available), 4.8),
        squeeze=False,
        sharey=True,
    )
    plotted_any = False

    for ax, n in zip(axes[0], available):
        n_rows = rows_by_n[n]
        x_ticks = sorted({
            row["t_hours"]
            for row in n_rows
            if finite_positive(row["t_hours"], positive=True)
        })
        for method in sorted({row["method"] for row in n_rows}, key=method_sort_key):
            method_rows = sorted(
                [row for row in n_rows if row["method"] == method],
                key=lambda row: row["t_hours"],
            )
            xs = []
            ys = []
            for row in method_rows:
                t_hours = row["t_hours"]
                execution_time = row["execution_time_s"]
                if not finite_positive(t_hours, positive=True) or not finite_positive(execution_time, positive=True):
                    continue
                xs.append(t_hours)
                ys.append(execution_time)
            if not xs:
                continue
            ax.plot(
                xs,
                ys,
                marker=METHOD_MARKERS.get(method, "o"),
                linestyle="-",
                color=METHOD_COLORS.get(method),
                label=method_display_name(method),
            )
            plotted_any = True
        ax.set_title(f"{title} для N = {n}")
        ax.set_xlabel("Длительность симуляции, часы")
        ax.set_xscale("log")
        if x_ticks:
            ax.xaxis.set_major_locator(FixedLocator(x_ticks))
            ax.xaxis.set_major_formatter(FuncFormatter(format_plain_number))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=4))
        ax.yaxis.set_minor_locator(NullLocator())
        ax.grid(True, which="major", linestyle="--", alpha=0.32)
        ax.legend(fontsize="small", loc="best")

    if not plotted_any:
        plt.close(fig)
        print(f"Skipping plot {filename}: no finite positive execution time data")
        return None

    axes[0][0].set_ylabel("Время выполнения, с")
    fig.tight_layout()
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)
    filepath = plots_dir / filename
    fig.savefig(filepath)
    print(f"Saved plot {filepath}")
    return fig


def collapse_progress_points(points):
    buckets = {}
    for progress, value in points:
        buckets.setdefault(progress, []).append(value)
    return sorted(
        (progress, sum(values) / len(values))
        for progress, values in buckets.items()
    )


def interpolate_resource_value(points, target_progress):
    if not points:
        return math.nan
    if len(points) == 1:
        return points[0][1]
    if target_progress <= points[0][0]:
        return points[0][1]
    if target_progress >= points[-1][0]:
        return points[-1][1]

    for (left_progress, left_value), (right_progress, right_value) in zip(points, points[1:]):
        if right_progress == left_progress:
            continue
        if left_progress <= target_progress <= right_progress:
            fraction = (target_progress - left_progress) / (right_progress - left_progress)
            return left_value + fraction * (right_value - left_value)
    return points[-1][1]


def aggregate_resource_series(samples, n_bodies, metric_key, progress_ticks=RESOURCE_PROGRESS_TICKS):
    runs = {}
    for sample in samples:
        if sample["n_bodies"] != n_bodies:
            continue
        value = sample.get(metric_key, math.nan)
        progress = sample.get("progress_pct", math.nan)
        if not math.isfinite(value) or not math.isfinite(progress):
            continue
        run_id = sample.get("run_id") or f"{sample['method']}_n{n_bodies}_t{sample['t_hours']}"
        runs.setdefault((sample["method"], run_id), []).append((progress, value))

    buckets = {}
    for (method, _run_id), points in runs.items():
        normalized_points = collapse_progress_points(points)
        for progress_tick in progress_ticks:
            value = interpolate_resource_value(normalized_points, progress_tick)
            if math.isfinite(value):
                buckets.setdefault((method, progress_tick), []).append(value)

    series = {}
    for (method, progress_tick), values in buckets.items():
        series.setdefault(method, []).append((progress_tick, sum(values) / len(values)))
    for method in series:
        series[method].sort()
    return series


def plot_resource_usage(samples, plots_dir=PLOTS_DIR):
    if not samples:
        return
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)

    for n_bodies in sorted({sample["n_bodies"] for sample in samples}):
        cpu_series = aggregate_resource_series(samples, n_bodies, "cpu_percent")
        gpu_series = aggregate_resource_series(samples, n_bodies, "gpu_percent")
        if not cpu_series and not gpu_series:
            continue

        fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
        plotted_any = False
        for ax, metric_name, series in (
            (axes[0], "Загрузка CPU, %", cpu_series),
            (axes[1], "Загрузка GPU, %", gpu_series),
        ):
            for method in sorted(series, key=method_sort_key):
                points = series[method]
                if not points:
                    continue
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                color = METHOD_COLORS.get(method)
                ax.fill_between(xs, ys, 0, color=color, alpha=0.16, linewidth=0)
                ax.plot(
                    xs,
                    ys,
                    marker=METHOD_MARKERS.get(method, "o"),
                    color=color,
                    linewidth=1.8,
                    label=method_display_name(method),
                )
                plotted_any = True
            ax.set_ylabel(metric_name)
            ax.set_ylim(0, 100)
            ax.set_xlim(0, 100)
            ax.xaxis.set_major_locator(FixedLocator(RESOURCE_PROGRESS_TICKS))
            ax.yaxis.set_major_locator(FixedLocator([0, 20, 40, 60, 80, 100]))
            ax.xaxis.set_minor_locator(NullLocator())
            ax.yaxis.set_minor_locator(NullLocator())
            ax.grid(True, which="major", linestyle="--", alpha=0.32)
            if series:
                ax.legend(fontsize="small", loc="best")
            else:
                ax.text(0.5, 0.5, "Нет данных", transform=ax.transAxes, ha="center", va="center")

        if not plotted_any:
            plt.close(fig)
            continue
        axes[1].set_xlabel("Прогресс запуска, % времени")
        fig.suptitle(f"Профиль загрузки ресурсов для N = {n_bodies}")
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        filepath = plots_dir / f"resource_usage_n{n_bodies}.png"
        fig.savefig(filepath)
        print(f"Saved plot {filepath}")


def draw_plots(rows, plots_dir=PLOTS_DIR):
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)
    plot_line(
        rows,
        x_key="n_bodies",
        y_key="execution_time_s",
        title="Время выполнения от количества тел",
        ylabel="Время выполнения, с",
        filename="execution_time_vs_n.png",
        plots_dir=plots_dir,
        logx=True,
        logy=False,
        group_by="method_t_hours",
    )
    plot_line(
        rows,
        x_key="n_bodies",
        y_key="gflops",
        title="Производительность от количества тел",
        ylabel="Производительность, GFLOP/s",
        filename="gflops_vs_n.png",
        plots_dir=plots_dir,
        logx=True,
        logy=False,
        group_by="method_t_hours",
    )
    plot_line(
        rows,
        x_key="n_bodies",
        y_key="energy_error",
        title="Относительная ошибка энергии от количества тел",
        ylabel="Ошибка энергии",
        filename="energy_error_vs_n.png",
        plots_dir=plots_dir,
        logx=True,
        logy=True,
        group_by="method_t_hours",
    )
    plot_execution_time_vs_duration_for_n(
        rows,
        n_values=[3, 10],
        title="Время выполнения от длительности",
        filename="execution_time_vs_duration_small_n.png",
        plots_dir=plots_dir,
    )
    plot_execution_time_vs_duration_for_n(
        rows,
        n_values=[100, 1000],
        title="Время выполнения от длительности",
        filename="execution_time_vs_duration_large_n.png",
        plots_dir=plots_dir,
    )
    plot_speedup(rows, "speedup_openmp_vs_serial.png", plots_dir=plots_dir, methods=("openmp",))
    plot_speedup(rows, "speedup_parallel_vs_serial.png", plots_dir=plots_dir, methods=("openmp", "sycl"))
    plot_efficiency(rows, "efficiency_vs_n.png", plots_dir=plots_dir)
    if "agg" not in plt.get_backend().lower():
        plt.show()


def main():
    parser = argparse.ArgumentParser(description="Benchmark and plot N-body results")
    parser.add_argument("--run", action="store_true", help="Run benchmark suite")
    parser.add_argument("--plot", action="store_true", help="Plot results from CSV")
    parser.add_argument("--force", action="store_true", help="Force re-run and overwrite CSV file")
    parser.add_argument("--config", help="Load benchmark settings from a JSON configuration file")
    parser.add_argument("--methods", help="Comma-separated methods, e.g. serial,openmp,sycl,two-body")
    parser.add_argument("--n-values", help="Comma-separated body counts, e.g. 3,10,100")
    parser.add_argument("--times-hours", help="Comma-separated simulation durations in hours")
    parser.add_argument("--dt", type=float, help="Time step in seconds")
    parser.add_argument("--scenario", help="Scenario for all runs: auto, random, sun-earth-moon, solar-system")
    parser.add_argument("--body-file", help="CSV file with explicit initial bodies")
    parser.add_argument("--openmp-threads", type=int, help="OpenMP thread count")
    parser.add_argument("--output-dir", help="Benchmark run directory for CSV, plots, resource samples, and trajectories")
    parser.add_argument("--results-csv", help="Where to write/read benchmark CSV results")
    parser.add_argument("--plots-dir", help="Directory for generated plots")
    parser.add_argument("--resource-csv", help="Where to write/read resource usage samples")
    parser.add_argument("--trajectory-dir", help="Directory for per-run trajectory files")
    parser.add_argument(
        "--trajectory-format",
        choices=["csv", "binary", "bin"],
        help="Trajectory file format for --trajectory-dir",
    )
    parser.add_argument("--no-default-skips", action="store_true", help="Do not skip known slow default cases")
    parser.add_argument(
        "--monitor-resources",
        action="store_true",
        help="Sample CPU/GPU utilization during benchmark runs and plot normalized profiles",
    )
    parser.add_argument(
        "--monitor-interval",
        type=float,
        help="Resource monitoring interval in seconds",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        default=None,
        help="SYCL device for benchmark runs (serial/OpenMP are always CPU implementations)",
    )
    args = parser.parse_args()

    raw_config = {}
    if args.config:
        raw_config = load_benchmark_config(args.config)
    config = normalize_benchmark_config(raw_config)

    if args.methods:
        config["methods"] = parse_csv_values(args.methods, str)
    if args.n_values:
        config["n_values"] = parse_csv_values(args.n_values, int)
    if args.times_hours:
        config["times_hours"] = parse_csv_values(args.times_hours, float)
    if args.dt is not None:
        config["dt_s"] = args.dt
    if args.scenario:
        config["scenario"] = args.scenario
    if args.body_file:
        config["body_file"] = args.body_file
    if args.openmp_threads is not None:
        config["openmp_threads"] = args.openmp_threads
    if args.output_dir:
        config["output_dir"] = args.output_dir
    if args.results_csv:
        config["results_csv"] = args.results_csv
    if args.plots_dir:
        config["plots_dir"] = args.plots_dir
    if args.resource_csv:
        config["resource_csv"] = args.resource_csv
    if args.trajectory_dir:
        config["trajectory_dir"] = args.trajectory_dir
    if args.trajectory_format:
        config["trajectory_format"] = args.trajectory_format
    if args.device is not None:
        config["device"] = args.device
    if args.no_default_skips:
        config["use_default_skips"] = False
    if args.monitor_resources:
        config["monitor_resources"] = True
    if args.monitor_interval is not None:
        config["monitor_interval_s"] = args.monitor_interval
    config = normalize_benchmark_config(config)

    if not args.run and not args.plot:
        args.run = True
        args.plot = True

    config = resolve_benchmark_output_paths(config, for_run=args.run, for_plot=args.plot)
    csv_path = Path(config["results_csv"])
    plots_dir = Path(config["plots_dir"])
    resource_csv_path = Path(config["resource_csv"])

    if args.run:
        if config.get("output_dir"):
            output_dir = Path(config["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            remember_latest_run(config["output_dir"])
            (output_dir / "benchmark_config.json").write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Benchmark output directory: {output_dir}")
        if csv_path.exists() and args.force:
            csv_path.unlink()
        if config["monitor_resources"] and resource_csv_path.exists() and args.force:
            resource_csv_path.unlink()
        if csv_path.exists() and not args.force:
            print(f"CSV already exists at {csv_path}. Use --force to overwrite or delete manually.")
        else:
            benchmark_rows = []
            resource_samples = []
            for method in config["methods"]:
                for n_bodies in benchmark_n_values_for_method(method, config["n_values"], config["body_file"]):
                    for t_hours in config["times_hours"]:
                        row = run_simulation(
                            method,
                            n_bodies,
                            t_hours,
                            config["device"],
                            dt_s=config["dt_s"],
                            scenario=config["scenario"],
                            scenario_by_n=config["scenario_by_n"],
                            body_file=config["body_file"],
                            openmp_threads=config["openmp_threads"],
                            use_default_skips=config["use_default_skips"],
                            trajectory_dir=config["trajectory_dir"],
                            trajectory_format=config["trajectory_format"],
                            monitor_resources=config["monitor_resources"],
                            monitor_interval_s=config["monitor_interval_s"],
                            resource_samples=resource_samples,
                        )
                        if row is not None:
                            benchmark_rows.append(row)
            save_results(benchmark_rows, csv_path)
            if config["monitor_resources"]:
                save_resource_samples(resource_samples, resource_csv_path)

    if args.plot:
        rows = load_results(csv_path)
        draw_plots(rows, plots_dir)
        plot_resource_usage(load_resource_samples(resource_csv_path), plots_dir)


if __name__ == "__main__":
    main()
