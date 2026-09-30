# Orange Pi FPV Tracking — RK3588 / RKNN / CRSF / PREEMPT_RT

Target detection and tracking on an Orange Pi 5 Ultra (RK3588), using direct RKNNLite inference on the NPU, a CRSF receiver-to-flight-controller bridge, bounded yaw/pitch assist, and a separate sysfs-PWM servo controlled by AUX3.

This repository was assembled from the recovered working Orange Pi project rather than from a generic template. It includes the tracking source, actual deployment scripts, UART/PWM notes, systemd kiosk setup, the working kernel configuration, and the documented PREEMPT_RT bring-up for Linux `6.1.99-rt36`.

The production `.rknn` model was not present in the supplied archives and is therefore not fabricated here. See `models/README.md`.

## Current data flow

```text
V4L2 camera -> RKNN NPU detector -> target tracker -> image-space controller
ELRS/CRSF -> ttyS2 -> CRSF parser/mixer -> ttyS6 -> flight controller
AUX3 -> sysfs PWM servo
AUX4 -> OFF / CAPTURE / MIX
```

Start with `docs/installation.md` and `docs/architecture.md`. The repository default keeps `mixing.enabled: false`; enable control mixing only after validating channel mapping and correction directions on the bench.
