#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO_DIR/scripts/run_tracking_app.sh"
LOG_DIR="${TRACKING_LOG_DIR:-$REPO_DIR/logs}"
LOG="$LOG_DIR/autostart.log"
PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/tracking_stand_app.pid"
CAMERA_WINDOW_NAME="${TRACKING_WINDOW_NAME:-TrackingCamera}"

export DISPLAY="${DISPLAY:-:0.0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export QT_X11_NO_MITSHM=1
export PYTHONUNBUFFERED=1

mkdir -p "$LOG_DIR"

echo "[AUTO] DISPLAY=$DISPLAY" | tee -a "$LOG"
echo "[AUTO] XAUTHORITY=$XAUTHORITY" | tee -a "$LOG"

if pgrep -f "tracking_crsf_lab_direct.py" >/dev/null 2>&1; then
  echo "[AUTO] tracking app is already running, exit" | tee -a "$LOG"
  exit 0
fi

if [[ -f "$PIDFILE" ]]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "[AUTO] wrapper already running pid=$OLD_PID, exit" | tee -a "$LOG"
    exit 0
  fi
fi

echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

while ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; do
  echo "[AUTO] waiting for X display $DISPLAY..." | tee -a "$LOG"
  sleep 2
done

xset -dpms 2>/dev/null || true
xset s off 2>/dev/null || true
xset s noblank 2>/dev/null || true

"$APP" >> "$LOG" 2>&1 &
APP_PID=$!
echo "[AUTO] app pid=$APP_PID" | tee -a "$LOG"

WIN_ID=""
for i in $(seq 1 90); do
  sleep 1
  WIN_ID="$(xdotool search --name "^${CAMERA_WINDOW_NAME}$" 2>/dev/null | head -n 1 || true)"
  [[ -n "$WIN_ID" ]] && break
  echo "[AUTO] waiting for camera window '${CAMERA_WINDOW_NAME}'... $i/90" | tee -a "$LOG"
done

if [[ -n "$WIN_ID" ]]; then
  sleep 2
  wmctrl -ir "$WIN_ID" -b add,fullscreen 2>/dev/null || true
  wmctrl -ir "$WIN_ID" -b add,above 2>/dev/null || true
  xdotool windowmove "$WIN_ID" 0 0 2>/dev/null || true
  xdotool windowsize "$WIN_ID" 100% 100% 2>/dev/null || true
  xdotool windowraise "$WIN_ID" 2>/dev/null || true
  xdotool windowactivate "$WIN_ID" 2>/dev/null || true
  echo "[AUTO] camera window fullscreen applied" | tee -a "$LOG"
else
  echo "[AUTO] WARNING: camera window not found" | tee -a "$LOG"
  wmctrl -l | tee -a "$LOG" || true
fi

set +e
wait "$APP_PID"
STATUS=$?
set -e
echo "[AUTO] app exited status=$STATUS" | tee -a "$LOG"
exit "$STATUS"
