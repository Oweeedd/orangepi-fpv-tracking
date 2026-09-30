# Operator guide

## Keyboard and mouse

- Left click — select a detection as the target.
- Right click or `c` — clear the target.
- Space — pause/unpause frame acquisition.
- `b` — toggle debug overlay.
- `g` — toggle CRSF panel.
- `v` — start/stop video + CSV recording.
- `s` — save screenshot.
- `1`, `2`, `3` — manually command the three configured servo positions.
- `q` — quit the application. If the systemd kiosk service is running, it will restart the application; stop the service first for a persistent shutdown.

## AUX4 modes

| Position | Behavior |
|---|---|
| Low | Clears target and disables tracking action |
| Mid | Captures the detection nearest the frame center and tracks it; no CRSF mixing |
| High | Tracks and permits yaw/pitch CRSF mixing if `mixing.enabled: true` |

## AUX3 servo

AUX3 low/mid/high maps to the three configured servo angles. Manual keys `1`/`2`/`3` are available for bench validation.

## First-flight / bench procedure

1. Keep `mixing.enabled: false`.
2. Verify live RC values and AUX switching in the on-screen panel.
3. Confirm the target is selected/reacquired as expected.
4. Verify the sign of `auto_yaw_cmd` and `auto_pitch_cmd` while moving a target around the image.
5. Verify servo limits without mechanical binding.
6. Only then enable mixing and start with conservative `max_auto_yaw` / `max_auto_pitch`.
