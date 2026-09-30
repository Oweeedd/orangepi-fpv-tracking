# Recovered RKNN benchmark notes

Two supplied logs contain a 580-frame YOLO11n RKNN 640×640 video test on aarch64. This is **not** the production 416×416 model used by `tracking_crsf_lab_direct.py`; it is retained only as evidence of an earlier RKNN performance experiment.

| Run | Frames | Mean inference | Median | 95th percentile | Max |
|---|---:|---:|---:|---:|---:|
| no-save | 580 | 65.89 ms | 65.35 ms | 77.10 ms | 90.40 ms |
| save | 580 | 62.64 ms | 61.60 ms | 73.40 ms | 86.60 ms |

The logs report `rknn-toolkit-lite2 2.3.2`, model toolkit version 2.3.2, target `rk3588 / RKNPU v2`, and `librknnrt 1.5.2`, with a warning that model and runtime versions do not match. Both supplied runs completed all 580 frames; the save run also reports an output directory.

Do not interpret the difference between the two single runs as a reliable effect of video saving.
