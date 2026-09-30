# Installation on Orange Pi 5 Ultra

This is a deployment guide for the recovered working layout. It assumes Debian 12 / Orange Pi userspace and a graphical X11 session because the application opens an OpenCV window and the kiosk wrapper uses X11 tools.

## 1. Clone/copy repository

Example:

```bash
cd ~
git clone <YOUR_REPOSITORY_URL> orangepi-fpv-tracking
cd orangepi-fpv-tracking
```

## 2. Install runtime dependencies

```bash
chmod +x scripts/*.sh
./scripts/install.sh
```

The installer creates a repo-local `.venv`, installs the minimal direct-RKNN Python requirements, adds the user to `dialout`, installs a restricted sudoers rule for PWM setup and generates the user systemd unit using the actual repository path.

After group membership changes, log out and log in again.

## 3. Configure UARTs

Read `hardware-and-io.md`, enable `uart2-m0 uart6-m1` in `/boot/orangepiEnv.txt`, then run:

```bash
./scripts/configure_uart.sh
sudo reboot
```

After reboot:

```bash
ls -l /dev/ttyS2 /dev/ttyS6
```

## 4. Install RKNN model

Place the production `.rknn` file here:

```text
models/yolov8n_416_rknn_model/
```

The actual model was not included in the supplied archives, so this repository deliberately contains only the expected directory and documentation.

## 5. Verify device/config values

Edit:

```text
config/tracking_crsf_direct_config.yaml
```

At minimum verify camera device, receiver/FC UART roles, channel indices, image orientation and servo angles.

Run:

```bash
./scripts/verify_system.sh
```

## 6. Manual run

From an active graphical session:

```bash
./scripts/start_tracking_fullscreen.sh
```

For a console-visible run without fullscreen wrapper:

```bash
./scripts/run_tracking_app.sh
```

## 7. Enable autostart

```bash
systemctl --user enable --now tracking-stand.service
systemctl --user status tracking-stand.service
```

The service template is generated during `install.sh`. To install and enable it in one pass on a fresh clone, use:

```bash
./scripts/install.sh --enable
```

## 8. Logs

```bash
journalctl --user -u tracking-stand.service -f
tail -f logs/autostart.log
```

## LightDM / autologin

The recovered working machine had LightDM enabled. The tracking service is a **user graphical-session service**, so fully unattended boot requires that the intended user session actually starts (typically by LightDM autologin). The exact local LightDM autologin override was not present in the supplied files, therefore this repository does not fabricate or automatically overwrite it.
