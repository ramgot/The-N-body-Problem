#!/usr/bin/env python3
"""Benchmark runner and plotter for N-body implementations.

Usage:
  python benchmark.py --run   # run benchmarks and save CSV
  python benchmark.py --plot  # load CSV and draw graphs
  python benchmark.py         # run and plot if possible
"""

import argparse
import csv
import datetime
import math
import os
import re
import shlex
import subprocess
from pathlib import Path

_MPLCONFIGDIR = Path.cwd() / "benchmark_results" / "matplotlib_cache"
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR.resolve()))
import matplotlib.pyplot as plt

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
    "command",
]

RESULTS_DIR = Path("benchmark_results")
PLOTS_DIR = RESULTS_DIR / "plots"
ACPP_CACHE_DIR = RESULTS_DIR / "acpp_cache"
CSV_PATH = RESULTS_DIR / "benchmark_results.csv"
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


def run_simulation(method: str, n_bodies: int, t_hours: float, device_choice: str):
    skip_reason = SKIPPED_BENCHMARKS.get((method, n_bodies, int(t_hours)))
    if skip_reason:
        print(f"Skipping {method} | N={n_bodies} | T={t_hours}h: {skip_reason}")
        return None

    exe_name = METHODS[method]
    exe_path = find_executable(exe_name)
    if exe_path is None:
        print(f"Warning: executable for method '{method}' not found. Skipping.")
        return None

    t_max_s = t_hours * 3600.0
    scenario = SCENARIO_BY_N.get(n_bodies, "random")
    command = [str(exe_path), str(n_bodies), str(FIXED_DT), str(t_max_s)]
    requested_threads = 0

    if method == "openmp":
        requested_threads = os.cpu_count() or 1
        command.append(str(requested_threads))

    command.append(scenario)
    if method == "sycl":
        command.extend(["--device", device_choice])

    print(f"Running {method} | N={n_bodies} | T={t_hours}h | cmd={command}")
    env = load_oneapi_env() if method == "sycl" else None
    process = subprocess.run(command, capture_output=True, text=True, env=env)
    if process.returncode != 0:
        raise RuntimeError(
            f"Benchmark failed for {exe_name} N={n_bodies} T={t_hours}h\n"
            f"stdout:\n{process.stdout}\n"
            f"stderr:\n{process.stderr}"
        )

    metrics = parse_metrics(process.stdout)
    reported_threads = metrics.get("threads", 0)
    if method == "serial":
        reported_threads = 1
    elif method == "openmp" and reported_threads == 0:
        reported_threads = requested_threads

    metrics.update({
        "timestamp": datetime.datetime.now().isoformat(),
        "method": method,
        "executable": exe_name,
        "n_bodies": n_bodies,
        "scenario": scenario_label(n_bodies),
        "t_hours": t_hours,
        "dt_s": FIXED_DT,
        "t_max_s": t_max_s,
        "threads": reported_threads,
        "compute_units": metrics.get("compute_units", 0),
        "device_type": metrics.get("device_type", ""),
        "device_name": metrics.get("device_name", ""),
        "command": " ".join(command),
    })
    return metrics


def save_results(rows):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_HEADERS})
    print(f"Saved {len(rows)} rows to {CSV_PATH}")


def load_results():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Benchmark CSV not found: {CSV_PATH}")
    rows = []
    with CSV_PATH.open("r", newline="", encoding="utf-8") as csvfile:
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


def plot_line(rows, x_key, y_key, title, ylabel, filename, logx=False, logy=False, group_by="method"):
    groups = {}
    for row in rows:
        if group_by == "method_t_hours":
            label = f"{row['method']} T={int(row['t_hours'])}h"
        else:
            label = row[group_by]
        groups.setdefault(label, []).append(row)

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted_any = False

    for label, group_rows in sorted(groups.items()):
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
        ax.plot(xs, ys, marker="o", label=label)
        plotted_any = True

    if not plotted_any:
        plt.close(fig)
        print(f"Skipping plot {filename}: no finite positive data for requested scale")
        return None

    ax.set_title(title)
    ax.set_xlabel("Number of bodies (N)" if x_key == "n_bodies" else x_key)
    ax.set_ylabel(ylabel)
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(fontsize="small", loc="best")
    fig.tight_layout()
    filepath = PLOTS_DIR / filename
    fig.savefig(filepath)
    print(f"Saved plot {filepath}")
    return fig


def plot_speedup(rows, filename):
    serial_rows = [r for r in rows if r["method"] == "serial"]
    openmp_rows = [r for r in rows if r["method"] == "openmp"]
    serial_map = {(r["n_bodies"], r["t_hours"]): r for r in serial_rows}
    openmp_map = {(r["n_bodies"], r["t_hours"]): r for r in openmp_rows}

    fig, ax = plt.subplots(figsize=(9, 5))
    plotted_any = False

    for t_hours in sorted({r["t_hours"] for r in rows}):
        x = []
        y = []
        for n in sorted({r["n_bodies"] for r in rows}):
            key = (n, t_hours)
            if key in serial_map and key in openmp_map:
                srow = serial_map[key]
                orow = openmp_map[key]
                if not math.isfinite(srow["execution_time_s"]) or not math.isfinite(orow["execution_time_s"]):
                    continue
                if srow["execution_time_s"] <= 0 or orow["execution_time_s"] <= 0:
                    continue
                x.append(n)
                y.append(srow["execution_time_s"] / orow["execution_time_s"])
        if x:
            ax.plot(x, y, marker="o", linestyle="-", label=f"T={int(t_hours)}h")
            plotted_any = True

    if not plotted_any:
        print("Нет данных для расчёта speedup")
        return

    ax.set_title("Speedup of OpenMP over Serial")
    ax.set_xlabel("Number of bodies (N)")
    ax.set_ylabel("Speedup ratio")
    ax.set_xscale("log")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(fontsize="small", loc="best")
    fig.tight_layout()
    filepath = PLOTS_DIR / filename
    fig.savefig(filepath)
    print(f"Saved plot {filepath}")
    return fig


def plot_efficiency(rows, filename):
    serial_map = {(r["n_bodies"], r["t_hours"]): r for r in rows if r["method"] == "serial"}
    fig, ax = plt.subplots(figsize=(9, 5))
    plotted_any = False

    for method in sorted(set(r["method"] for r in rows if r["method"] != "serial")):
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
                ax.plot(x, y, marker="o", linestyle="-", label=f"{method} T={int(t_hours)}h")
                plotted_any = True

    if not plotted_any:
        print("Нет данных для расчёта эффективности")
        return

    ax.set_title("Parallel efficiency vs Number of bodies")
    ax.set_xlabel("Number of bodies (N)")
    ax.set_ylabel("Efficiency (speedup / resources)")
    ax.set_xscale("log")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(fontsize="small", loc="best")
    fig.tight_layout()
    filepath = PLOTS_DIR / filename
    fig.savefig(filepath)
    print(f"Saved plot {filepath}")
    return fig


def draw_plots(rows):
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_line(
        rows,
        x_key="n_bodies",
        y_key="execution_time_s",
        title="Execution time vs Number of bodies",
        ylabel="Execution time, s",
        filename="execution_time_vs_n.png",
        logx=True,
        logy=False,
        group_by="method_t_hours",
    )
    plot_line(
        rows,
        x_key="n_bodies",
        y_key="gflops",
        title="Achieved performance vs Number of bodies",
        ylabel="Performance, GFLOP/s",
        filename="gflops_vs_n.png",
        logx=True,
        logy=False,
        group_by="method_t_hours",
    )
    plot_line(
        rows,
        x_key="n_bodies",
        y_key="energy_error",
        title="Relative energy error vs Number of bodies",
        ylabel="Energy error",
        filename="energy_error_vs_n.png",
        logx=True,
        logy=True,
        group_by="method_t_hours",
    )
    plot_speedup(rows, "speedup_openmp_vs_serial.png")
    plot_efficiency(rows, "efficiency_vs_n.png")
    if "agg" not in plt.get_backend().lower():
        plt.show()


def main():
    parser = argparse.ArgumentParser(description="Benchmark and plot N-body results")
    parser.add_argument("--run", action="store_true", help="Run benchmark suite")
    parser.add_argument("--plot", action="store_true", help="Plot results from CSV")
    parser.add_argument("--force", action="store_true", help="Force re-run and overwrite CSV file")
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        default="auto",
        help="SYCL device for benchmark runs (serial/OpenMP are always CPU implementations)",
    )
    args = parser.parse_args()

    if not args.run and not args.plot:
        args.run = True
        args.plot = True

    if args.run:
        if CSV_PATH.exists() and args.force:
            CSV_PATH.unlink()
        if CSV_PATH.exists() and not args.force:
            print(f"CSV already exists at {CSV_PATH}. Use --force to overwrite or delete manually.")
        else:
            benchmark_rows = []
            for method in METHODS:
                for n_bodies in NS:
                    for t_hours in TIMES_HOURS:
                        row = run_simulation(method, n_bodies, t_hours, args.device)
                        if row is not None:
                            benchmark_rows.append(row)
            save_results(benchmark_rows)

    if args.plot:
        rows = load_results()
        draw_plots(rows)


if __name__ == "__main__":
    main()
