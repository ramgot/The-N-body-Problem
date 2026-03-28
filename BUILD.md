# Сборка проекта с CMake

CMake - это кроссплатформенная система сборки, которая работает на Windows, WSL и Linux.

## 🚀 Быстрый старт

### Windows (PowerShell)

```powershell
# Первая сборка
cmake -B build
cmake --build build

# Запуск программ
.\build\nbody_serial.exe
.\build\nbody_openmp.exe
.\build\two_body_solver.exe
```

### WSL/Linux (Bash)

```bash
# Первая сборка
cmake -B build
cmake --build build

# Запуск программ
./build/nbody_serial
./build/nbody_openmp
./build/two_body_solver
```

## 📦 Установка CMake

### Windows

**Вариант 1: Chocolatey**
```powershell
choco install cmake
```

**Вариант 2: Скачать с сайта**
https://cmake.org/download/

### WSL/Linux

```bash
sudo apt-get update
sudo apt-get install cmake
```

## 🔨 Команды

### Построить проект

```bash
cmake -B build              # Генерирует файлы сборки в папку 'build'
cmake --build build         # Собирает проект
cmake --build build -j4     # Собирает с 4 потоками (быстрее)
```

### Откомпилировать целевой файл

```bash
cmake --build build --target nbody_serial
cmake --build build --target nbody_openmp
cmake --build build --target two_body_solver
```

### Очистить сборку

```bash
rm -r build                 # На Linux/WSL
rmdir /s /q build           # На Windows PowerShell
```

### Собрать с отладочной информацией

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build
```

## 🎯 SYCL поддержка (Intel oneAPI)

### Установка Intel oneAPI

**Windows:**
https://www.intel.com/content/www/en/en/developer/tools/oneapi/hpc-toolkit-download.html

**WSL/Ubuntu:**
```bash
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/oneAPI.list
sudo apt update
sudo apt install intel-oneapi-compiler-dpcpp-cpp
```

После установки:
```bash
source /opt/intel/oneapi/setvars.sh  # На Linux
# или используйте Intel oneAPI Command Prompt на Windows

cmake -B build
cmake --build build --target nbody_sycl
./build/nbody_sycl
```

## 📊 Проверить конфигурацию

```bash
cmake -B build     # Выведет информацию о том, какие модули найдены
```

Вы должны увидеть что-то вроде:
```
=== N-Body Problem Build Configuration ===
Build type: Release
C++ Standard: 17

Targets to build:
  ✓ nbody_serial      - Serial N-body simulation
  ✓ nbody_openmp      - Parallel N-body with OpenMP
  ✓ two_body_solver   - Two-body analytical solution
  ✓ nbody_sycl        - SYCL N-body (Intel oneAPI)  [если установлен]
```

## 💡 Полезные команды

| Команда | Описание |
|---------|---------|
| `cmake -B build` | Генерирует файлы сборки |
| `cmake --build build` | Строит проект |
| `cmake --build build -j4` | Строит с 4 потоками |
| `cmake --build build --target nbody_serial` | Создает только serial версию |
| `cmake -B build -DCMAKE_BUILD_TYPE=Debug` | Сборка с отладкой |
| `cmake -B build -DCMAKE_CXX_COMPILER=clang++` | Использует clang компилятор |

## ✅ Типичный рабочий процесс

```bash
# Первый раз
cmake -B build
cmake --build build

# Запуск
./build/nbody_serial
./build/nbody_openmp
./build/two_body_solver

# После изменения кода - просто пересобрать
cmake --build build

# Чистая сборка (если что-то не работает)
rm -r build
cmake -B build
cmake --build build
```
