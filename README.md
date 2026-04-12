# Запуск проекта через PowerShell и WSL

Проект собирается через GNU Make внутри Linux/WSL. Самый простой и надёжный сценарий такой: открыть обычный PowerShell в корне репозитория, зайти в Ubuntu внутри WSL и уже там выполнить `make`.

## 1. Открыть PowerShell в корне проекта

Если PowerShell уже открыт не в той папке, сначала перейдите в каталог репозитория:

```powershell
cd "C:\path\to\The-N-body-Problem"
```

Проверить, что вы в нужной папке:

```powershell
Get-Location
Get-ChildItem
```

## 2. Проверить, какая WSL-дистрибуция установлена

В PowerShell выполните:

```powershell
wsl -l -v
```

Нормальный вариант для сборки этого проекта: `Ubuntu` или другая обычная Linux-дистрибуция для разработки.

Если у вас есть только `Docker Desktop`, установите Ubuntu:

```powershell
wsl --install -d Ubuntu
```

Если Ubuntu уже установлена, но `wsl` по умолчанию открывает не её, сделайте Ubuntu дистрибуцией по умолчанию:

```powershell
wsl --set-default Ubuntu
```

Разово можно запускать нужную дистрибуцию и без смены default:

```powershell
wsl -d Ubuntu
```

## 3. Зайти в Ubuntu из PowerShell

Рекомендуемая команда:

```powershell
wsl -d Ubuntu
```

Если PowerShell был открыт в корне репозитория, WSL обычно откроется сразу в этой же папке, только уже в Linux-пути. Проверить это можно так:

```bash
pwd
ls
```

Если вы оказались не в корне проекта, перейдите туда вручную из Linux-shell.

## 4. Установить инструменты сборки в WSL

В Ubuntu выполните:

```bash
sudo apt update
sudo apt install -y build-essential make
```

Это поставит `g++`, стандартные библиотеки и `make`.

Если хотите запускать benchmark-скрипты и строить графики, дополнительно установите Python-пакеты:

```bash
sudo apt install -y python3 python3-pip
python3 -m pip install --user matplotlib numpy
```

## 5. Собрать проект

Основная сборка:

```bash
make all
```

После успешной сборки в корне проекта появятся исполняемые файлы:

- `nbody_serial`
- `nbody_openmp`
- `two_body_solver`

Полезные варианты:

```bash
make clean
make BUILD_MODE=Debug all
make help
```

Опциональная SYCL-сборка:

```bash
make all-sycl
```

Она имеет смысл только если у вас уже установлен Intel oneAPI и доступен компилятор `icpx`.

## 6. Запустить программы

Минимальный запуск:

```bash
./nbody_serial
./nbody_openmp
./two_body_solver
```

Примеры запуска с параметрами:

```bash
./nbody_serial 10 3600 86400 solar-system
./nbody_openmp 1000 3600 86400 8 random
./two_body_solver
```

Где:

- `N` — количество тел
- `DT` — шаг по времени в секундах
- `T_MAX` — общее время моделирования в секундах
- `THREADS` — число потоков OpenMP
- `SCENARIO` — `auto`, `sun-earth-moon`, `solar-system` или `random`

## 7. Вернуться в PowerShell

Когда закончите работу в WSL:

```bash
exit
```

## 8. Частые проблемы

- `wsl` открывает `Docker Desktop`, а не Ubuntu.
  Используйте `wsl -d Ubuntu` или выполните `wsl --set-default Ubuntu`.

- Ошибка `g++: not found`.
  Внутри Ubuntu не установлен toolchain. Повторите шаг 4.

- Ошибка `make: command not found`.
  Внутри Ubuntu не установлен `make`. Повторите шаг 4.

- Ошибка `icpx: not found`.
  Не запускайте `make all-sycl`, если Intel oneAPI не установлен. Для обычной сборки достаточно `make all`.

- PowerShell открыт не в каталоге проекта.
  Сначала выполните `cd "C:\path\to\The-N-body-Problem"`, а потом снова заходите в WSL.
