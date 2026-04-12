# Быстрый старт с GPU

## ✅ Для AMD Radeon 780M (встроенная видеокарта в AMD Ryzen)

### Способ 1: Через Makefile (рекомендуется)
```bash
make run-sycl           # Базовый запуск
```

### Способ 2: Через wrapper скрипт (самый простой)
```bash
./nbody_gpu.sh 100 3600 21600          # 100 тел, 6 часов
./nbody_gpu.sh 1000 3600 86400         # 1000 тел, 1 день
./nbody_gpu.sh 10 3600 86400 solar-system  # Солнечная система
```

### Способ 3: Ручной запуск (требует активации oneAPI)
```bash
# Один раз активировать (или добавить в .bashrc)
source /opt/intel/oneapi/setvars.sh

# Затем запустить
./nbody_sycl 1000 3600 86400
```

## 📊 Тестирование GPU vs CPU vs OpenMP

```bash
# Скрипт автоматически тестирует все версии
./test_gpu.sh 100      # Тест с 100 телами
./test_gpu.sh 1000     # Тест с 1000 телами
```

## 🔧 Установка oneAPI (если ещё не установлено)

```bash
sudo apt-get update && sudo apt-get install -y wget gpg

wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | \
  gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | \
  sudo tee /etc/apt/sources.list.d/oneAPI.list

sudo apt-get update
sudo apt-get install -y intel-basekit
```

## 📝 Автоматическая активация при каждом запуске

Добавьте в `~/.bashrc`:
```bash
source /opt/intel/oneapi/setvars.sh > /dev/null 2>&1
```

Или используйте команду:
```bash
echo 'source /opt/intel/oneapi/setvars.sh > /dev/null 2>&1' >> ~/.bashrc
source ~/.bashrc
```

## 🎯 Примеры конкретных сценариев

```bash
# Быстро: Солнце-Земля-Луна
./nbody_gpu.sh 3 3600 86400 sun-earth-moon

# Реалистично: Солнечная система на 1 день
./nbody_gpu.sh 10 3600 86400 solar-system

# Стресс-тест: 1000 тел на неделю
./nbody_gpu.sh 1000 3600 604800

# Сравнение: одна и та же симуляция на разных платформах
make run-serial          # CPU одно-поточный
make run-openmp          # CPU многопоточный
make run-sycl            # GPU (автоматически с oneAPI)
```

## 💡 Советы

- Первый запуск может быть медленнее (инициализация GPU)
- Для больших N (1000+) GPU даёт видимое ускорение
- Используйте test_gpu.sh для объективного сравнения производительности
