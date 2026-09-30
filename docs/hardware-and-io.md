# Hardware and I/O

## Confirmed platform

The recovered working system is an Orange Pi 5 Ultra (RK3588) running Debian 12 Bookworm. The current tracking configuration uses a V4L2 capture device, two hardware UARTs and Linux PWM sysfs.

## UART physical pins

From the project notes:

| UART | Orange Pi physical pin | Signal |
|---|---:|---|
| UART2 | 8 | TXD.2 |
| UART2 | 10 | RXD.2 |
| UART6 | 11 | RXD.6 |
| UART6 | 13 | TXD.6 |

Connect UART signal lines crosswise and use a common ground:

```text
Orange Pi TX -> device RX
Orange Pi RX <- device TX
Orange Pi GND -- device GND
```

### Current tracking assignment

The supplied working tracking config and logs use:

```text
ELRS / CRSF receiver -> /dev/ttyS2
Flight controller    -> /dev/ttyS6
```

Older `pilot-cumpot` notes used these roles in the opposite order. For this repository, `config/tracking_crsf_direct_config.yaml` is the source of truth. If your physical board is still wired according to the older layout, either swap the devices or swap `serial.rx_port` / `serial.fc_port` in the config.

## Enabling UART overlays

The recovered project notes used this `orangepiEnv.txt` pattern:

```ini
verbosity=1
bootlogo=true
extraargs=cma=128M
overlay_prefix=rk3588
fdtfile=rockchip/rk3588-orangepi-5-ultra.dtb
rootdev=UUID=<YOUR_ROOT_UUID>
rootfstype=ext4
console=display
overlays=uart2-m0 uart6-m1
```

Do **not** copy the old UUID. Keep the `rootdev` already present on your board and add/retain the two UART overlays.

After editing `/boot/orangepiEnv.txt`, reboot and verify:

```bash
ls -l /dev/ttyS2 /dev/ttyS6
dmesg | grep -Ei 'ttyS2|ttyS6|serial'
```

Free both UARTs from serial login services:

```bash
./scripts/configure_uart.sh
```

The working board had `/dev/ttyS2` and `/dev/ttyS6` owned by `root:dialout` with mode `0660`.

## CRSF baud rate

The current Python runtime uses `420000` baud as recorded in the tracking config. A separate older C++ experiment used custom `termios2` handling at `416666`; that value belongs to the legacy module and is not silently substituted into the current Python application.

## Camera

The current deployment expects:

```text
/dev/video1
640x480 @ 30 FPS
rotate_180: true
```

Inspect the real capture device with:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video1 --list-formats-ext
```

If enumeration changes, update `source:` in the YAML or set `TRACKING_CAMERA` for the launcher.

## PWM servo

The recovered system exposes:

```text
/sys/class/pwm/pwmchip0
/sys/class/pwm/pwmchip1
/sys/class/pwm/pwmchip2
```

The tracking servo uses `pwmchip1`, channel `0`, 20 ms period. The working log showed inverted polarity, and `prepare_servo_pwm.sh` handles either `normal` or `inversed` by reading the actual sysfs value before calculating `duty_cycle`.

AUX3 mapping in the current config:

| AUX3 pulse | Servo state | Configured angle |
|---:|---|---:|
| < 1300 µs | DOWN | 0° |
| 1300–1699 µs | MID | 45° |
| >= 1700 µs | FRONT | 90° |

The exact physical header pin for the servo PWM was not present in the recovered files, so this repository intentionally does not invent one. Verify the board overlay/pin mux used on your actual unit before rewiring hardware.
