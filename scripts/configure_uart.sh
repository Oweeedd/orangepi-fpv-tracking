#!/usr/bin/env bash
set -euo pipefail

TARGET_USER="${SUDO_USER:-${USER:-orangepi}}"

echo "[UART] disabling serial getty on ttyS2/ttyS6"
sudo systemctl disable --now serial-getty@ttyS2.service 2>/dev/null || true
sudo systemctl disable --now serial-getty@ttyS6.service 2>/dev/null || true

if id "$TARGET_USER" >/dev/null 2>&1; then
  sudo usermod -aG dialout "$TARGET_USER"
  echo "[UART] added $TARGET_USER to dialout (re-login required)"
fi

echo "[UART] current devices:"
ls -l /dev/ttyS2 /dev/ttyS6 2>/dev/null || true

echo "[UART] NOTE: UART overlays must also be enabled in /boot/orangepiEnv.txt."
echo "[UART] See docs/hardware-and-io.md before rebooting."
