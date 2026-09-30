# Autostart and recovery

The original recovered `tracking-stand.service` used `Restart=no`. Its log showed that if `/dev/video1` disappeared during operation, OpenCV stopped reading frames, the application exited and the kiosk wrapper ended.

The Git-ready service template changes this to:

```ini
Restart=always
RestartSec=3
```

This is intentional for appliance/kiosk operation: if the tracking process exits because the capture device or application fails, systemd starts the wrapper again, and the wrapper waits until the camera is available.

Because of `Restart=always`, pressing `q` in the GUI will also lead to a restart while the service remains active. To stop it intentionally:

```bash
systemctl --user stop tracking-stand.service
```

The wrapper itself performs these steps:

1. wait for an X display;
2. disable screen blanking/DPMS;
3. start `run_tracking_app.sh`;
4. wait for the OpenCV window named `TrackingCamera`;
5. apply fullscreen/always-on-top with `wmctrl`/`xdotool`;
6. wait for the application and return its exit status.

`run_tracking_app.sh` waits for the V4L2 device and for `v4l2-ctl` to successfully enumerate formats, prepares PWM, validates the venv and launches the direct RKNN application.
