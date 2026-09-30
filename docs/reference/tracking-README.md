# Tracking Stand

## Состав

- `tracking_crsf_lab_direct.py` — основной запуск RKNN/NPU-детектора, трекера, AUX3/AUX4 и сервы.
- `tracking_crsf_lab.py` — базовый CRSF-мост, общий цикл обработки кадра и отрисовка интерфейса.
- `rknn_yolo_detector.py` — прямой RKNNLite YOLO-детектор без Ultralytics в рабочем контуре.
- `servo_pwm_sysfs.py` — управление SG90 через sysfs PWM.
- `tracking_crsf_direct_config.yaml` — основной конфиг стенда.
- `prepare_servo_pwm.sh` — подготовка PWM перед запуском.
- `kiosk/run_tracking_app.sh` — запуск приложения с ожиданием камеры.
- `kiosk/start_tracking_fullscreen.sh` — запуск в текущей X-сессии и перевод окна `TrackingCamera` в fullscreen.
- `systemd/tracking-stand.service` — пример user-service для автозапуска.
- `sudoers.d/tracking-servo-pwm` — пример правила sudo без пароля для подготовки PWM.

## Ручной запуск

```bash
cd /home/orangepi/yolo/yolo-opi/tracking_stand/kiosk
./start_tracking_fullscreen.sh
```

## Автозапуск

```bash
mkdir -p /home/orangepi/.config/systemd/user
cp systemd/tracking-stand.service /home/orangepi/.config/systemd/user/tracking-stand.service
sudo cp sudoers.d/tracking-servo-pwm /etc/sudoers.d/tracking-servo-pwm
sudo chmod 440 /etc/sudoers.d/tracking-servo-pwm

systemctl --user daemon-reload
systemctl --user enable tracking-stand.service
systemctl --user start tracking-stand.service
```

## Проверка

```bash
systemctl --user status tracking-stand.service
journalctl --user -u tracking-stand.service -f
tail -f /home/orangepi/yolo/yolo-opi/tracking_stand/autostart.log
```

## Управление

- ЛКМ — выбрать цель.
- ПКМ или `c` — сбросить цель.
- `b` — включить/выключить debug overlay.
- `g` — включить/выключить CRSF-панель.
- `v` — запись видео и CSV.
- `s` — скриншот.
- `q` — выход.
- `1`, `2`, `3` — ручные положения сервы для проверки.

## AUX-логика

- AUX3 low/mid/high — положения сервы 0°/45°/90°.
- AUX4 low — сброс цели и отключение сопровождения.
- AUX4 mid — захват ближайшего к центру объекта, сопровождение без подмешивания CRSF.
- AUX4 high — сопровождение с CRSF mixing.
