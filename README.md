# N-Body Problem Numerical Solution

Проект численного решения задачи N тел в гравитационном поле с использованием различных параллельных технологий.

## 📋 Описание проекта

Проект реализует численное решение задачи N тел для гравитационного взаимодействия. Включает несколько реализаций:

- **Последовательная версия** (Serial) - базовая реализация на CPU
- **OpenMP версия** - параллельная реализация с использованием OpenMP
- **SYCL версия** - гетерогенная реализация для GPU/CPU с использованием SYCL
- **Аналитическое решение задачи двух тел** - для сравнения и валидации

### Метод интегрирования

Используется **Velocity Verlet** метод (Störmer-Verlet с явными скоростями) второго порядка точности O(Δt²). Это симплектический метод, который хорошо сохраняет интегралы движения (энергию, момент импульса).

### Начальные условия

- **N=3**: Солнце-Земля-Луна с реальными массами и орбитами
- **N=10**: Солнечная система (Солнце + 9 планет включая Плутон)
- **N=100, 1000**: Случайные тела в сфере с вириальным равновесием

## 🏗️ Структура проекта

```
├── Common/                          # Общие компоненты
│   ├── include/
│   │   ├── body.h                  # Класс Body и SystemState
│   │   ├── common.h                # Константы и структуры
│   │   └── vector3.h               # 3D векторная математика
│   └── src/
│       ├── body.cpp                # Реализация тел и начальных условий
│       └── Vector3.cpp             # Векторные операции
├── The N-body Problem Numerical Solution/
│   ├── include/                    # Заголовки N-body (пусто)
│   └── src/
│       ├── nbody_serial.cpp        # Последовательная версия
│       ├── nbody_openmp.cpp        # OpenMP версия
│       └── nbody_sycl.cpp          # SYCL версия
├── The Two-body Problem Analytical Solution/
│   ├── include/
│   │   └── two_body_solver.h       # Аналитическое решение
│   └── src/
│       ├── two_body_solver.cpp     # Реализация аналитики
│       └── test_main.cpp           # Тестовый main
├── benchmark.py                    # Скрипт для бенчмаркинга
├── run_benchmarks.sh               # Быстрый запуск бенчмарков
├── Makefile                        # Сборка проекта
├── CMakeLists.txt                  # Альтернативная сборка
└── BUILD.md                        # Инструкции по сборке
```

## 🔧 Зависимости

### Обязательные
- **C++17 компилятор** (GCC 7+, Clang 5+, MSVC 2017+)
- **CMake 3.15+** (для альтернативной сборки)
- **Python 3.6+** с matplotlib (для графиков бенчмарков)
- **python3-tk** (для оконного запускателя `nbody_gui.py`)

### Для OpenMP версии
- **OpenMP 3.0+** (обычно включен в GCC/Clang)

### Для SYCL версии
- **Intel oneAPI** или **DPC++ компилятор**
- Поддержка SYCL устройств (GPU/CPU)

### Для графиков
```bash
pip install matplotlib numpy
```

### Для оконного запускателя
```bash
sudo apt-get install python3-tk
```

## ⚙️ Установка Intel oneAPI (для SYCL/GPU)

### Linux (Ubuntu/Debian)

```bash
# 1. Обновление системы
sudo apt-get update
sudo apt-get install -y wget gpg

# 2. Добавление GPG ключа Intel
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | \
  gpg --dearmor | \
  sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null

# 3. Добавление репозитория Intel oneAPI
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | \
  sudo tee /etc/apt/sources.list.d/oneAPI.list

# 4. Обновление списка пакетов
sudo apt-get update

# 5. Установка Intel oneAPI Base Kit
sudo apt-get install -y intel-basekit

# Альтернатива: установка только компилятора HPC Kit (меньше и быстрее)
# sudo apt-get install -y intel-hpckit
```

### Активация oneAPI в текущей сессии
```bash
source /opt/intel/oneapi/setvars.sh
```

### Автоматическая активация при каждом запуске
Добавьте в `~/.bashrc`:
```bash
echo 'source /opt/intel/oneapi/setvars.sh > /dev/null 2>&1' >> ~/.bashrc
source ~/.bashrc
```

Или добавьте строку напрямую:
```bash
source /opt/intel/oneapi/setvars.sh > /dev/null 2>&1
```

## 🚀 Быстрый старт

### 1. Клонирование и сборка
```bash
git clone <repository-url>
cd "The-N-body-Problem"
make all          # Собрать основные версии (serial, OpenMP)
make all-sycl     # Собрать включая SYCL (требует Intel oneAPI)
```

### 2. Запуск тестов

#### С GPU (рекомендуется - автоматически активирует oneAPI):
```bash
make run-sycl     # GPU через Makefile
# или
./nbody_gpu.sh 1000 3600 86400  # Wrapper скрипт (не требует ручной активации)
```

#### На CPU:
```bash
make run-serial   # Последовательная версия
make run-openmp   # OpenMP версия
```

### 3. Запуск бенчмарков
```bash
make benchmark-full     # Полный цикл через Makefile
./run_benchmarks.sh     # Интерактивный скрипт с проверками
./test_gpu.sh 100       # Сравнение GPU vs CPU vs OpenMP
```

## 📊 Бенчмаркинг

### Быстрый запуск всех бенчмарков
```bash
make benchmark-full
```

Это выполнит:
1. Сборку всех доступных версий
2. Запуск симуляций для N=[3,10,100,1000] и T=[24,168,720,8760] часов
3. Сохранение результатов в `benchmark_results/benchmark_results.csv`
4. Построение графиков производительности

### Интерактивный скрипт бенчмаркинга
```bash
./run_benchmarks.sh              # Полный цикл с проверкой зависимостей
./run_benchmarks.sh --force      # Принудительный перезапуск
./run_benchmarks.sh --plot-only  # Только построение графиков
./run_benchmarks.sh --with-sycl  # Включить SYCL версию
./run_benchmarks.sh --help       # Показать справку
```

Скрипт автоматически:
- Проверяет наличие всех зависимостей (компиляторы, Python, matplotlib)
- Собирает необходимые версии (с или без SYCL)
- Запускает бенчмарки
- Строит графики
- Показывает сводку результатов

### Ручной запуск бенчмарков
```bash
# Только запуск бенчмарков
python3 benchmark.py --run

# Только построение графиков (если CSV уже есть)
python3 benchmark.py --plot

# Принудительный перезапуск
python3 benchmark.py --force
```

### Оконный запускатель
```bash
make gui        # открыть окно в текущем терминале
make gui-bg     # открыть окно в фоне и сразу вернуть терминал

# или без сборки
python3 nbody_gui.py
```

Окно позволяет запускать одиночные симуляции, выбирать методы бенчмарка,
задавать `N`, `dt`, время моделирования, OpenMP-потоки и SYCL-устройство,
сохранять/загружать JSON-конфиги бенчмарков, выбирать CSV и папку графиков.
Сборку можно запускать кнопками внутри окна: если выбран SYCL, будет использован
`make all-sycl`, иначе `make all`.
Во вкладке конфигураций можно создать воспроизводимый файл начальных тел
`*.bodies.csv` для случайного случая и затем использовать его в serial,
OpenMP и SYCL через сценарий `body-file`.
Пример JSON-конфига лежит в `configs/default_benchmark.json`.

Те же возможности доступны из CLI:
```bash
python3 benchmark.py --config configs/my_benchmark.json --run --plot --force
python3 benchmark.py --methods serial,openmp --n-values 100,1000 --times-hours 24,168 \
  --results-csv benchmark_results/custom.csv --plots-dir benchmark_results/custom_plots
```

### Графики производительности
- **execution_time_vs_n.png** - Время выполнения vs количество тел
- **gflops_vs_n.png** - Производительность GFLOP/s vs количество тел
- **energy_error_vs_n.png** - Ошибка энергии vs количество тел
- **speedup_openmp_vs_serial.png** - Ускорение OpenMP над Serial
- **efficiency_vs_n.png** - Эффективность параллелизации

## 🎯 Использование

### Ручной запуск симуляций

#### Последовательная версия
```bash
./nbody_serial N DT T_MAX [SCENARIO] [--bodies PATH]
# Пример: ./nbody_serial 100 3600 86400 random
```

#### OpenMP версия
```bash
./nbody_openmp N DT T_MAX [THREADS] [SCENARIO] [--bodies PATH]
# Пример: ./nbody_openmp 1000 3600 86400 8 random
```

#### SYCL версия (GPU)
```bash
# Способ 1: Wrapper скрипт (рекомендуется - не требует ручной активации oneAPI)
./nbody_gpu.sh N DT T_MAX [SCENARIO]
# Пример: ./nbody_gpu.sh 1000 3600 86400 solar-system

# Способ 2: Через Makefile (также автоматически активирует oneAPI)
make run-sycl

# Способ 3: Прямой запуск (требует ручной активации oneAPI)
./nbody_sycl N DT T_MAX [SCENARIO] [--bodies PATH] [--device auto|cpu|gpu]
# Пример: ./nbody_sycl 1000 3600 86400 solar-system
```

## 🎮 Запуск на GPU (Accelerators)

### ✅ Запуск SYCL версии на GPU

SYCL версия автоматически выбирает доступное GPU устройство.

**✅ Протестировано на:** AMD Radeon 780M (iGPU) - работает успешно!

#### Способ 1: Wrapper скрипт (рекомендуется - самый простой)
```bash
./nbody_gpu.sh 1000 3600 86400
```

#### Способ 2: Через Makefile (также автоматически активирует oneAPI)
```bash
make run-sycl
```

#### Способ 3: Ручной запуск с активацией oneAPI
```bash
source /opt/intel/oneapi/setvars.sh
./nbody_sycl 1000 3600 86400
```

### AMD GPU (CDNA/RDNA, Radeon)

#### ✅ Для встроенной видеокарты (iGPU) в AMD Ryzen процессорах

Интегрированная видеокарта автоматически поддерживается через Level Zero в Intel oneAPI. Просто запустите:

```bash
source /opt/intel/oneapi/setvars.sh
./nbody_sycl N DT T_MAX [SCENARIO]
```

**Пример для Radeon 780M:**
```bash
source /opt/intel/oneapi/setvars.sh
./nbody_sycl 1000 3600 86400        # Симуляция 1000 тел на 1 день
./nbody_sycl 100 3600 21600         # Быстрая симуляция 100 тел на 6 часов
```

#### Для дискретных AMD GPU (Radeon Pro, Instinct)

Требуется установка дополнительного софта:

```bash
# Установка ROCm
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
echo 'deb [arch=amd64] https://repo.radeon.com/rocm/apt/ubuntu $(lsb_release -sc) main' | \
  sudo tee /etc/apt/sources.list.d/rocm.list
sudo apt-get update
sudo apt-get install -y rocm-dkms

# Активировать oneAPI с HIP поддержкой
source /opt/intel/oneapi/setvars.sh
export ONEAPI_DEVICE_SELECTOR=hip

# Сборка и запуск
make clean
make run-sycl
```

### Intel GPU (Arc)

#### Собрать и запустить для Intel Arc GPU
```bash
# Активировать oneAPI
source /opt/intel/oneapi/setvars.sh
export ONEAPI_DEVICE_SELECTOR=level_zero

# Сборка и запуск
make run-sycl
```

### Nvidia GPU (CUDA) - Инструкция для других компьютеров

#### Требования
- **Nvidia GPU** (CUDA Compute Capability 5.0+)
- **Intel oneAPI** с CUDA поддержкой
- **CUDA Toolkit 11.8+** (некоторые версии)

#### Установка необходимых компонентов

```bash
# 1. Уже установлено: Intel oneAPI Base Kit
# (если нет, см. раздел выше: "Установка Intel oneAPI")

# 2. Убедитесь, что CUDA поддержка доступна в oneAPI
# Проверьте установленные компоненты:
ls /opt/intel/oneapi/ | grep -i dpc

# 3. Если нужна явная поддержка CUDA, установите NVIDIA CUDA Toolkit:
# (Приблизительная инструкция, версии могут отличаться)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-repo-ubuntu2204_12.4.1-1_amd64.deb
sudo dpkg -i cuda-repo-ubuntu2204_12.4.1-1_amd64.deb
sudo apt-get update
sudo apt-get install -y cuda-toolkit
```

#### Собрать и запустить для Nvidia GPU
```bash
# Активировать oneAPI с CUDA поддержкой
source /opt/intel/oneapi/setvars.sh
export ONEAPI_DEVICE_SELECTOR=cuda

# Пересборка SYCL версии (если нужна)
make clean
icpx -std=c++17 -Wall -Wextra -O2 -fsycl \
  -IN-body-Numerical-Solution/include -ICommon/include \
  N-body-Numerical-Solution/src/nbody_sycl.cpp \
  Common/src/body.cpp Common/src/Vector3.cpp \
  -o nbody_sycl

# Запуск
./nbody_sycl 1000 3600 86400
```

#### Проверка доступности CUDA в системе
```bash
which nvcc          # Проверить NVIDIA компилятор
nvidia-smi          # Информация о GPU
```

### CPU (если GPU недоступен)

```bash
# Использовать CPU как fallback
source /opt/intel/oneapi/setvars.sh
./nbody_sycl 1000 3600 86400

# Или явно выбрать CPU
ONEAPI_DEVICE_SELECTOR=cpu ./nbody_sycl 1000 3600 86400
```

### Проверка доступных SYCL устройств

```bash
# Способ 1: Посмотреть сообщение о выборе устройства
source /opt/intel/oneapi/setvars.sh
./nbody_sycl 100 3600 21600 2>&1 | grep "Starting simulation on device"

# Способ 2: Попробовать разные селекторы
export ONEAPI_DEVICE_SELECTOR=cpu
./nbody_sycl 100 3600 21600 2>&1 | grep "device"

export ONEAPI_DEVICE_SELECTOR=gpu
./nbody_sycl 100 3600 21600 2>&1 | grep "device"
```

### Быстрое сравнение производительности CPU vs GPU

```bash
source /opt/intel/oneapi/setvars.sh

echo "=== Запуск на CPU ==="
ONEAPI_DEVICE_SELECTOR=cpu time ./nbody_sycl 1000 3600 21600

echo -e "\n=== Запуск на GPU (автоматический выбор) ==="
time ./nbody_sycl 1000 3600 21600

echo -e "\n=== OpenMP версия для сравнения ==="
time ./nbody_openmp 1000 3600 21600 8
```

### Параметры командной строки

- `N` - количество тел (3, 10, 100, 1000)
- `DT` - шаг по времени в секундах (обычно 3600 = 1 час)
- `T_MAX` - общее время симуляции в секундах
- `THREADS` - количество OpenMP потоков (только для OpenMP версии)
- `SCENARIO` - сценарий начальных условий:
  - `auto` - автоматический выбор по N
  - `sun-earth-moon` - Солнце-Земля-Луна
  - `solar-system` - Солнечная система
  - `random` - случайные тела
- `--bodies PATH` - загрузить начальные тела из CSV (`mass,x,y,z,vx,vy,vz`);
  удобно для воспроизводимых случайных конфигураций

### Примеры сценариев

```bash
# Солнечная система на 1 день
./nbody_serial 10 3600 86400 solar-system

# Случайные 1000 тел на 1 год
./nbody_openmp 1000 3600 31536000 16 random

# Солнце-Земля-Луна на GPU
./nbody_sycl 3 3600 86400 sun-earth-moon
```

## 🏭 Сборка

### Makefile (рекомендуется)
```bash
make help                    # Показать все доступные цели
make all                     # Собрать основные версии
make all-sycl                # Собрать включая SYCL
make benchmark-full          # Полный бенчмарк цикл
make quick-benchmark         # Быстрый бенчмарк (без SYCL)
make quick-benchmark-sycl    # Быстрый бенчмарк с SYCL
make clean                   # Очистить сборку
make clean-all               # Очистить всё включая бенчмарки
```

### CMake (альтернатива)
```bash
mkdir build && cd build
cmake ..
make
```

### Переменные сборки
```bash
make CXX=clang++ all          # Использовать Clang
make BUILD_MODE=Debug all     # Отладочная сборка
make SYCL_BACKEND=opencl all-sycl  # SYCL с OpenCL бэкендом
```

## 🔍 Архитектура кода

### Основные классы

#### `Body`
- Позиция, скорость, ускорение, масса
- Методы обновления по Velocity Verlet
- Вычисление сил и энергий

#### `SystemState`
- Состояние всей системы тел
- Вычисление консервативных величин (энергия, момент)

#### `NBodySimulation*`
- Основной класс симуляции
- Интегрирование по времени
- Метрики производительности

### Начальные условия (`InitialConditions` namespace)
- `sunEarthMoon()` - Реалистичные Солнце-Земля-Луна
- `solarSystem()` - Солнечная система с 9 планетами
- `randomSphere()` - Случайные тела в вириальном равновесии

### Метод интегрирования

```cpp
// Velocity Verlet схема
v(t + dt/2) = v(t) + 0.5*a(t)*dt
r(t + dt) = r(t) + v(t + dt/2)*dt
a(t + dt) = F(r(t + dt))/m
v(t + dt) = v(t + dt/2) + 0.5*a(t + dt)*dt
```

## 📈 Результаты бенчмаркинга

Типичные результаты на современном CPU (Intel i7-9700K):

| Метод | N=100 | N=1000 | GFLOP/s |
|-------|-------|--------|---------|
| Serial | ~50   | ~0.5   | ~2.5    |
| OpenMP | ~150  | ~15    | ~7.5    |
| SYCL   | ~200  | ~50    | ~25     |

*Результаты зависят от оборудования и могут отличаться.
