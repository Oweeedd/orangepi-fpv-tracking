#!/usr/bin/env bash
set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
warn(){ echo "[WARN] $*"; }
ok(){ echo "[ OK ] $*"; }
fail(){ echo "[FAIL] $*"; FAIL=1; }

echo "== OS / kernel =="
uname -a
if uname -v | grep -q PREEMPT_RT; then ok "PREEMPT_RT kernel"; else warn "kernel is not PREEMPT_RT"; fi
if [[ -r /sys/kernel/realtime ]]; then echo "realtime=$(cat /sys/kernel/realtime)"; fi

echo
echo "== UART =="
for dev in /dev/ttyS2 /dev/ttyS6; do
  [[ -c "$dev" ]] && ok "$dev exists" || fail "$dev missing"
done
id -nG | tr ' ' '\n' | grep -qx dialout && ok "user is in dialout" || warn "user is not in dialout"

echo
echo "== camera =="
CAMERA="${TRACKING_CAMERA:-/dev/video1}"
[[ -e "$CAMERA" ]] && ok "$CAMERA exists" || warn "$CAMERA missing"
command -v v4l2-ctl >/dev/null && ok "v4l2-ctl installed" || fail "v4l2-ctl missing"

echo
echo "== PWM =="
[[ -d /sys/class/pwm/pwmchip1 ]] && ok "pwmchip1 exists" || warn "pwmchip1 missing"

echo
echo "== model / Python =="
MODEL_DIR="$REPO_DIR/models/yolov8n_416_rknn_model"
find "$MODEL_DIR" -maxdepth 1 -name '*.rknn' -print -quit 2>/dev/null | grep -q . && ok "RKNN model found" || warn "RKNN model not found in $MODEL_DIR"
[[ -x "$REPO_DIR/.venv/bin/python" ]] && ok "venv exists" || warn "run ./scripts/install.sh"

echo
echo "== X11 kiosk tools =="
for cmd in xdpyinfo xdotool wmctrl xset; do
  command -v "$cmd" >/dev/null && ok "$cmd" || fail "$cmd missing"
done

exit "$FAIL"
