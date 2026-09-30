# Configuration reference

Primary configuration: `config/tracking_crsf_direct_config.yaml`.

## Detector

- `model_path` — `.rknn` file or directory containing one `.rknn` model.
- `imgsz` — model input side; the working tracking configuration uses 416.
- `conf`, `iou`, `max_det` — confidence threshold, NMS IoU threshold and maximum detections.
- `detector.core` — `all`, `0`, `1` or `2` to select RKNN NPU core mask.
- `classes.allowed` — optional allow-list of class names.

## Tracker

- `same_class_only` — refuse class changes during matching.
- `max_center_dist` — normal matching search radius in pixels.
- `iou_weight`, `center_weight` — scoring weights before target loss.
- `min_match_score` — minimum normal match score.
- `memory_frames` — how long target memory is kept.
- `control_lost_frames` — number of lost frames over which command decay may continue.
- `lost_expand_per_frame` — search-radius growth during target loss.
- `reacquire_max_center_dist` — maximum expanded radius.
- `reacquire_min_match_score` — relaxed score threshold after loss.
- `click_nearest_max_dist` — maximum click-to-object distance if click is outside all boxes.

## AUX4 state machine

The direct runtime treats AUX4 as a 3-position mode switch:

```text
LOW  (< capture threshold) -> OFF: clear target, no tracking
MID  -> CAPTURE: choose nearest-to-center target and track, no CRSF mixing
HIGH (>= mix threshold) -> MIX: track and permit CRSF yaw/pitch mixing
```

Defaults:

```yaml
aux:
  aux4_capture_threshold_us: 1300
  aux4_mix_threshold_us: 1700
```

## Controller and mixing

`control.kp_yaw` / `control.kp_pitch` scale image error. Dead zones suppress small errors; `max_yaw` / `max_pitch` bound the command; `alpha` smooths it.

`mixing.max_auto_yaw` / `max_auto_pitch` impose an additional cap on what can be added to pilot input. `pilot_override_threshold` and `pilot_override_factor` reduce automatic correction when the pilot commands a large stick deflection.

The Git-ready default has `mixing.enabled: false`. The recovered working snapshot is kept as `config/tracking_crsf_direct_config.working-reference.yaml` and had mixing enabled. Enable it only after verifying channel order, directions and preview behavior.

## Servo

`servo_pwm` configures the sysfs PWM device, pulse range and three AUX3 positions. The prep script establishes the 20 ms period and center pulse before the application starts.
