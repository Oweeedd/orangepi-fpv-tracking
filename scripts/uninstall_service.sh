#!/usr/bin/env bash
set -euo pipefail
systemctl --user disable --now tracking-stand.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/tracking-stand.service"
systemctl --user daemon-reload
sudo rm -f /etc/sudoers.d/tracking-servo-pwm
echo "Tracking user service and sudoers rule removed. Project files were not deleted."
