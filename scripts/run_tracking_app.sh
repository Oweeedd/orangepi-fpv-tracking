#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${TRACKING_VENV:-$REPO_DIR/.venv}"
CONFIG="${TRACKING_CONFIG:-config/tracking_crsf_direct_config.yaml}"
CAMERA_DEV="${TRACKING_CAMERA:-/dev/video1}"
CHECK_INTERVAL="${TRACKING_CAMERA_RETRY_SEC:-3}"
EXTRA_READY_DELAY="${TRACKING_CAMERA_READY_DELAY_SEC:-5}"

export PYTHONUNBUFFERED=1
export QT_X11_NO_MITSHM=1
export DISPLAY="${DISPLAY:-:0.0}"

cd "$REPO_DIR"

echo "[APP] repo=$REPO_DIR"
echo "[APP] DISPLAY=$DISPLAY"
echo "[APP] waiting for camera device: $CAMERA_DEV"

while [[ ! -e "$CAMERA_DEV" ]]; do
  echo "[APP] camera device not found: $CAMERA_DEV, retry in ${CHECK_INTERVAL}s..."
  sleep "$CHECK_INTERVAL"
done

while true; do
  if v4l2-ctl -d "$CAMERA_DEV" --list-formats-ext >/tmp/tracking_camera_formats.log 2>&1; then
    echo "[APP] camera formats detected"
    break
  fi
  echo "[APP] camera exists, but v4l2 is not ready yet, retry in ${CHECK_INTERVAL}s..."
  sleep "$CHECK_INTERVAL"
done

sleep "$EXTRA_READY_DELAY"
cat /tmp/tracking_camera_formats.log || true

if fuser "$CAMERA_DEV" >/tmp/tracking_camera_users.log 2>&1; then
  echo "[APP] WARNING: camera may be busy:"
  cat /tmp/tracking_camera_users.log || true
fi

if [[ -x "$REPO_DIR/scripts/prepare_servo_pwm.sh" ]]; then
  echo "[APP] preparing servo PWM..."
  sudo -n "$REPO_DIR/scripts/prepare_servo_pwm.sh" || echo "[APP] WARNING: PWM preparation failed"
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[APP] ERROR: venv not found at $VENV. Run ./scripts/install.sh first." >&2
  exit 2
fi

if [[ ! -e "$CONFIG" ]]; then
  echo "[APP] ERROR: config not found: $CONFIG" >&2
  exit 2
fi

exec "$VENV/bin/python" tracking_crsf_lab_direct.py --config "$CONFIG"
