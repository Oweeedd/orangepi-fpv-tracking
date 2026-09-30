# Troubleshooting

## `/dev/ttyS2` or `/dev/ttyS6` missing

Check `/boot/orangepiEnv.txt` for `overlays=uart2-m0 uart6-m1`, reboot, then inspect:

```bash
dmesg | grep -Ei 'ttyS2|ttyS6|serial'
ls -l /dev/ttyS2 /dev/ttyS6
```

## Permission denied on UART

```bash
groups
sudo usermod -aG dialout "$USER"
```

Log out and back in.

## UART is busy / CRSF does not start

Check that serial getty is disabled:

```bash
systemctl status serial-getty@ttyS2.service
systemctl status serial-getty@ttyS6.service
```

Use `./scripts/configure_uart.sh` if needed.

Also check for an older bridge process using the same UARTs:

```bash
sudo fuser -v /dev/ttyS2 /dev/ttyS6
pgrep -af 'crsf|tracking'
```

Do not run the legacy C++ bridge and the Python visual-tracking bridge on the same UARTs at the same time.

## Camera exists but cannot be opened

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video1 --list-formats-ext
fuser -v /dev/video1
```