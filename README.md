# N-body Problem

Учебный проект для численного моделирования гравитационной задачи N тел.
В репозитории есть последовательная версия, OpenMP-версия, SYCL-версия на
AdaptiveCpp, аналитический двухтельный пример, бенчмаркинг и Tkinter-интерфейс
для запуска симуляций и просмотра траекторий.

## Состав проекта

- `Common/` - общие типы: `Body`, `Vector3`, сценарии начальных тел,
  чтение CSV-конфигураций и запись траекторий.
- `N-body-Numerical-Solution/` - численные реализации N-body:
  `nbody_serial`, `nbody_openmp`, `nbody_sycl`.
- `Two-body-Analytical-Solution/` - аналитическое решение двух тел и CLI-вход
  для запуска/бенчмаркинга.
- `benchmark.py` - запуск серий экспериментов, CSV-таблица результатов,
  графики и опциональная запись траекторий.
- `nbody_gui.py` - окно для одиночных запусков, бенчмарков, генерации файлов
  тел и просмотра траекторий.
- `trajectory_viewer.py` - отдельный просмотрщик CSV и binary-траекторий.
- `run_benchmarks.sh` - быстрый shell-раннер с проверкой зависимостей.
- `configs/` - JSON-конфиги бенчмарков и CSV-файлы начальных тел, если они
  создаются через GUI.

## Требования

Базовая сборка:

- Linux/WSL;
- `g++` с C++17;
- OpenMP для `nbody_openmp`;
- Python 3, `numpy`, `matplotlib`;
- `python3-tk` для GUI и viewer.

SYCL-сборка:

- AdaptiveCpp;
- по умолчанию Makefile ищет компилятор в `/opt/adaptivecpp/bin/acpp`;
- путь можно переопределить через `CXX_SYCL=/path/to/acpp`.

## Быстрый старт

```bash
make all
./nbody_serial 3 3600 86400 sun-earth-moon
./nbody_openmp 10 3600 86400 8 solar-system
./two_body_solver 3600 31557600
```

Сборка SYCL:

```bash
make all-sycl
./nbody_sycl 1000 3600 86400 random --device auto
```

Полезные Makefile-цели:

```bash
make all                  # serial, OpenMP, two-body
make all-sycl             # всё плюс SYCL
make run-serial
make run-openmp
make run-sycl
make run-twobody
make check-compilers
make check-acpp
make print-acpp-config
make clean
```

## Сценарии и входные тела

Исполняемые файлы принимают общий набор параметров:

```bash
./nbody_serial N DT T_MAX [SCENARIO] [--bodies PATH] [--trajectory PATH] [--trajectory-format csv|binary]
./nbody_openmp N DT T_MAX [THREADS] [SCENARIO] [--bodies PATH] [--trajectory PATH] [--trajectory-format csv|binary]
./nbody_sycl N DT T_MAX [SCENARIO] [--bodies PATH] [--device auto|cpu|gpu] [--trajectory PATH] [--trajectory-format csv|binary]
./two_body_solver [dt] [t_max] [--scenario auto|sun-earth|elliptical] [--trajectory PATH] [--trajectory-format csv|binary]
```

Сценарии:

- `sun-earth-moon` - 3 тела;
- `solar-system` - Солнце, планеты и Плутон;
- `random` - случайная система на `N` тел;
- `auto` - выбор сценария по `N`.

Файл `--bodies` должен быть CSV с колонками:

```text
mass,x,y,z,vx,vy,vz
```

## Траектории

Траектория записывается только если передан `--trajectory`.
Форматы:

- `csv` - удобно смотреть и отлаживать, но файл крупнее;
- `binary` - компактнее и быстрее для больших запусков, расширение `.bin`.

Пример:

```bash
./nbody_serial 3 3600 86400 sun-earth-moon \
  --trajectory benchmark_results/trajectory.bin \
  --trajectory-format binary
```

Просмотр:

```bash
make viewer
python3 trajectory_viewer.py benchmark_results/trajectory.bin
```

Viewer показывает фактически загруженное число тел отдельно от лимита загрузки.
Поле лимита нужно только для больших файлов, чтобы не пытаться отрисовать сразу
тысячи тел и кадров.

## GUI

```bash
make gui
python3 nbody_gui.py
```

В GUI есть вкладки:

- одиночная симуляция;
- бенчмарк;
- генерация CSV-конфигураций тел;
- визуализация траекторий.

Таблица результатов всегда сохраняется как CSV. Формат `csv` или `binary`
относится только к файлам траекторий; GUI подставляет подходящее расширение
`.csv` или `.bin`.

## Бенчмарки

Быстрые команды:

```bash
make benchmark        # собрать базовые реализации и записать CSV
make benchmark-full   # записать CSV и построить графики
make plots            # построить графики из существующего CSV
./run_benchmarks.sh
./run_benchmarks.sh --with-sycl --device gpu
./run_benchmarks.sh --with-two-body
```

Прямой запуск Python-раннера:

```bash
python3 benchmark.py --run --force
python3 benchmark.py --plot
python3 benchmark.py --config configs/default_benchmark.json --run --plot --force
python3 benchmark.py --run --plot --force --monitor-resources
python3 benchmark.py --methods serial,openmp,two-body --n-values 3,10,100 --times-hours 24,168 \
  --output-dir benchmark_results/runs/custom_small
```

Метод `two-body` всегда записывает `n_bodies=2`; значение `--n-values` для него
игнорируется, чтобы аналитический solver не создавал ложные точки `N=3/10/...`.

Результаты:

Каждый запуск бенчмарка получает отдельную папку в `benchmark_results/runs/`.
Путь к последнему запуску хранится в `benchmark_results/latest_run.txt`.

- CSV-таблица: `<run-dir>/benchmark_results.csv`;
- снимок настроек: `<run-dir>/benchmark_config.json`;
- samples нагрузки CPU/GPU: `<run-dir>/resource_usage.csv`;
- графики: `<run-dir>/plots/`;
- опциональные траектории: `<run-dir>/trajectories/`.

Флаг `--output-dir` задаёт конкретную папку прогона. Без него `--run` создаёт
новую папку с timestamp, а `--plot` читает последний прогон.

Основные графики:

- `execution_time_vs_n.png`, `gflops_vs_n.png`, `energy_error_vs_n.png`;
- `execution_time_vs_duration_small_n.png` для `N=3,10`;
- `execution_time_vs_duration_large_n.png` для `N=100,1000`;
- `speedup_openmp_vs_serial.png`;
- `speedup_parallel_vs_serial.png` с OpenMP и SYCL относительно serial;
- `efficiency_vs_n.png`;
- `resource_usage_n<N>.png` при запуске с `--monitor-resources`.

Мониторинг ресурсов выключен по умолчанию. При `--monitor-resources` раннер
сэмплирует общую загрузку CPU через `/proc/stat`, GPU через `nvidia-smi` или
`rocm-smi`, если такая утилита доступна, а затем усредняет графики по каждому
`N` на оси X `0..100%` от времени выполнения запуска с шагом 10%.

`benchmark_results/` считается генерируемым каталогом. Его можно удалить через:

```bash
make clean-benchmark
```

## Конфиги бенчмарков

Минимальный JSON:

```json
{
  "methods": ["serial", "openmp"],
  "n_values": [3, 10, 100],
  "times_hours": [24, 168],
  "dt_s": 3600,
  "scenario": null,
  "openmp_threads": 8,
  "device": "auto",
  "output_dir": null,
  "results_csv": null,
  "plots_dir": null,
  "trajectory_dir": null,
  "trajectory_format": "csv",
  "use_default_skips": true,
  "monitor_resources": false,
  "monitor_interval_s": 0.5,
  "resource_csv": null
}
```

GUI умеет сохранять и загружать такие конфиги.

## Чистка

```bash
make clean             # удалить объектные файлы и исполняемые файлы
make clean-benchmark   # удалить benchmark_results
make clean-all         # оба действия
```

В рабочем дереве не нужны для сборки: `__pycache__/`, `benchmark_results/`,
локальные отчёты и временные траектории. Они не участвуют в запуске кода.
