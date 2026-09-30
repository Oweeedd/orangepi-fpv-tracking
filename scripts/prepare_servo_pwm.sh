#!/usr/bin/env bash
set -euo pipefail

PWMCHIP="${PWMCHIP:-/sys/class/pwm/pwmchip1}"
CHANNEL="${PWM_CHANNEL:-0}"
PERIOD_NS="${PWM_PERIOD_NS:-20000000}"
CENTER_US="${PWM_CENTER_US:-1500}"
TARGET_USER="${SUDO_USER:-${USER:-orangepi}}"
PWM="$PWMCHIP/pwm$CHANNEL"

if [[ $EUID -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi

if [[ ! -d "$PWMCHIP" ]]; then
  echo "[PWM] ERROR: $PWMCHIP not found" >&2
  exit 1
fi

echo "[PWM] preparing $PWMCHIP channel $CHANNEL"

if [[ ! -d "$PWM" ]]; then
  echo "$CHANNEL" > "$PWMCHIP/export"
  sleep 0.2
fi

echo 0 > "$PWM/enable" 2>/dev/null || true
echo "$PERIOD_NS" > "$PWM/period"

POLARITY="$(cat "$PWM/polarity")"
PERIOD="$(cat "$PWM/period")"

echo "[PWM] polarity=$POLARITY"
echo "[PWM] period=$PERIOD"

PULSE_NS=$((CENTER_US * 1000))
if [[ "$POLARITY" == "inversed" ]]; then
  DUTY=$((PERIOD_NS - PULSE_NS))
else
  DUTY=$PULSE_NS
fi

echo "$DUTY" > "$PWM/duty_cycle"
echo 1 > "$PWM/enable"

REAL_PWM="$(readlink -f "$PWM")"
if id "$TARGET_USER" >/dev/null 2>&1; then
  chown -R "$TARGET_USER:$TARGET_USER" "$REAL_PWM"
  chmod -R u+rw "$REAL_PWM"
fi

echo "[PWM] ready"
echo "[PWM] final:"
echo "polarity=$(cat "$PWM/polarity")"
echo "period=$(cat "$PWM/period")"
echo "duty_cycle=$(cat "$PWM/duty_cycle")"
echo "enable=$(cat "$PWM/enable")"

if [[ -r /sys/kernel/debug/pwm ]]; then
  cat /sys/kernel/debug/pwm || true
fi
