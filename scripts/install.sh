#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -eq 0 ]]; then
  echo "Run this installer as the target desktop user, without sudo. It invokes sudo only for system changes." >&2
  exit 2
fi

ENABLE_SERVICE=0
[[ "${1:-}" == "--enable" ]] && ENABLE_SERVICE=1

TARGET_USER="${SUDO_USER:-${USER}}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
VENV="$REPO_DIR/.venv"

echo "[INSTALL] repo=$REPO_DIR user=$TARGET_USER"

sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip \
  v4l-utils wmctrl xdotool x11-utils psmisc \
  libgl1 libglib2.0-0

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel setuptools
"$VENV/bin/python" -m pip install -r "$REPO_DIR/requirements.txt"

sudo usermod -aG dialout "$TARGET_USER"

# Restricted passwordless sudo only for the PWM preparation script.
SUDOERS=/etc/sudoers.d/tracking-servo-pwm
printf '%s ALL=(root) NOPASSWD: %s/scripts/prepare_servo_pwm.sh\n' "$TARGET_USER" "$REPO_DIR" | sudo tee "$SUDOERS" >/dev/null
sudo chmod 440 "$SUDOERS"
sudo visudo -cf "$SUDOERS"

mkdir -p "$TARGET_HOME/.config/systemd/user"
sed \
  -e "s|@REPO_DIR@|$REPO_DIR|g" \
  -e "s|@HOME@|$TARGET_HOME|g" \
  "$REPO_DIR/systemd/tracking-stand.service.in" \
  > "$TARGET_HOME/.config/systemd/user/tracking-stand.service"
chown "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.config/systemd/user/tracking-stand.service"

sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$TARGET_USER")" systemctl --user daemon-reload 2>/dev/null || true

cat <<EOF

[INSTALL] Base software installed.
Next:
  1. Read docs/hardware-and-io.md and enable uart2-m0 + uart6-m1.
  2. Run: ./scripts/configure_uart.sh
  3. Put the .rknn model under models/yolov8n_416_rknn_model/
  4. Verify config/tracking_crsf_direct_config.yaml
  5. Run: ./scripts/verify_system.sh
EOF

if [[ $ENABLE_SERVICE -eq 1 ]]; then
  echo "[INSTALL] enabling user service"
  sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$TARGET_USER")" systemctl --user enable tracking-stand.service || true
  echo "[INSTALL] Service enabled. Start it from the graphical user session or reboot after autologin is configured."
fi
