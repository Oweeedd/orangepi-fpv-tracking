# CRSF Stack Next

Модульный bridge для Orange Pi 5 Ultra:
- CRSF bridge между ELRS и FC
- HC-SR04 через libgpiod
- HOLD / LAND
- TUI monitor через unix socket
- runtime config без пересборки
- AUX2-включаемое CSV логирование

## Сборка

```bash
sudo apt update
sudo apt install -y build-essential libgpiod-dev python3-pandas python3-matplotlib
make clean
make
```

## Конфиг

По умолчанию программа пытается читать:
1. `/etc/crsf-stack.conf`
2. `./crsf-stack.conf`
3. иначе использует defaults

Скопировать пример:

```bash
sudo cp crsf-stack.conf /etc/crsf-stack.conf
sudo nano /etc/crsf-stack.conf
```

## Запуск

```bash
sudo ./crsf_stack /dev/ttyS6 /dev/ttyS2 --verbose
```

или с явным конфигом:

```bash
sudo ./crsf_stack /dev/ttyS6 /dev/ttyS2 --config /etc/crsf-stack.conf --verbose
```

Отдельно монитор:

```bash
./monitor
```

## Логирование на AUX2

Если `AUX2 >= aux2_log_high_min`, начинается запись CSV в `log_dir`.
По умолчанию:

```text
/home/orangepi/crsf_logs
```

В лог пишутся:
- mode
- aux2/aux3
- sensor_cm
- target_cm
- vertical_speed_cms
- throttle live/base/out/corr
- battery
- attitude
- baro
- frame counters

## Построение графиков

```bash
python3 tools/plot_log.py /home/orangepi/crsf_logs/<file>.csv
```

## Полезные параметры для тюнинга

- `hold_kp` — основная чувствительность по ошибке высоты
- `hold_ki` — компенсация постоянной ошибки тяги
- `hold_kd` — демпфирование по изменению ошибки
- `vel_k` — отдельное демпфирование по вертикальной скорости
- `throttle_slew_up_per_sec` — скорость добавления газа
- `throttle_slew_down_per_sec` — скорость уменьшения газа
- `land_descent_rate_cm_per_sec` — скорость снижения цели в LAND
- `near_ground_*` — более мягкое управление у земли
