# Deployment checklist

- [ ] Debian/Orange Pi userspace boots reliably.
- [ ] `/dev/ttyS2` and `/dev/ttyS6` exist.
- [ ] `serial-getty` is disabled on both tracking UARTs.
- [ ] Current user is in `dialout`.
- [ ] Receiver and FC roles match `serial.rx_port` / `serial.fc_port`.
- [ ] Camera is the expected `/dev/video*` device and provides the configured format.
- [ ] `.rknn` production model is present under `models/yolov8n_416_rknn_model/`.
- [ ] `pwmchip1/pwm0` exists and servo limits are safe.
- [ ] `./scripts/verify_system.sh` has no unexpected failures.
- [ ] Tracking works with `mixing.enabled: false`.
- [ ] AUX3 and AUX4 positions are verified on screen.
- [ ] Yaw/pitch correction signs are verified before enabling mixing.
- [ ] User systemd service starts in the intended X session.
- [ ] Camera disconnect/reconnect recovery is tested.
- [ ] If RT kernel is required, `/sys/kernel/realtime` reports `1` and `cyclictest` is re-run on the actual final image.
