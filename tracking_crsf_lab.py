import argparse
import csv
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import serial
import yaml
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


CRSF_FRAMETYPE_RC_CHANNELS_PACKED = 0x16
CRSF_PAYLOAD_SIZE_RC_CHANNELS = 22
CRSF_CHANNEL_COUNT = 16

CRSF_RAW_MIN = 172
CRSF_RAW_MID = 992
CRSF_RAW_MAX = 1811


def crc8_dvb_s2(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0xD5) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def raw_to_us(raw: int) -> int:
    return int(round(988 + (raw - CRSF_RAW_MIN) * (2012 - 988) / (CRSF_RAW_MAX - CRSF_RAW_MIN)))


def us_to_raw(us: int) -> int:
    raw = int(round(CRSF_RAW_MIN + (us - 988) * (CRSF_RAW_MAX - CRSF_RAW_MIN) / (2012 - 988)))
    return max(CRSF_RAW_MIN, min(CRSF_RAW_MAX, raw))


def raw_to_norm(raw: int, throttle: bool = False) -> float:
    if throttle:
        return max(0.0, min(1.0, (raw - CRSF_RAW_MIN) / (CRSF_RAW_MAX - CRSF_RAW_MIN)))

    if raw >= CRSF_RAW_MID:
        return max(0.0, min(1.0, (raw - CRSF_RAW_MID) / (CRSF_RAW_MAX - CRSF_RAW_MID)))
    return -max(0.0, min(1.0, (CRSF_RAW_MID - raw) / (CRSF_RAW_MID - CRSF_RAW_MIN)))


def norm_to_raw(norm: float, throttle: bool = False) -> int:
    if throttle:
        norm = max(0.0, min(1.0, norm))
        return int(round(CRSF_RAW_MIN + norm * (CRSF_RAW_MAX - CRSF_RAW_MIN)))

    norm = max(-1.0, min(1.0, norm))
    if norm >= 0:
        return int(round(CRSF_RAW_MID + norm * (CRSF_RAW_MAX - CRSF_RAW_MID)))
    return int(round(CRSF_RAW_MID + norm * (CRSF_RAW_MID - CRSF_RAW_MIN)))


def unpack_channels(payload: bytes) -> List[int]:
    if len(payload) != CRSF_PAYLOAD_SIZE_RC_CHANNELS:
        raise ValueError(f"Bad RC payload size: {len(payload)}")

    bit_buffer = int.from_bytes(payload, byteorder="little")
    return [(bit_buffer >> (11 * i)) & 0x7FF for i in range(CRSF_CHANNEL_COUNT)]


def pack_channels(channels: List[int]) -> bytes:
    if len(channels) != CRSF_CHANNEL_COUNT:
        raise ValueError("Need 16 channels")

    bit_buffer = 0
    for i, ch in enumerate(channels):
        ch = max(0, min(0x7FF, int(ch)))
        bit_buffer |= ch << (11 * i)

    return bit_buffer.to_bytes(CRSF_PAYLOAD_SIZE_RC_CHANNELS, byteorder="little")


def rebuild_frame_with_payload(raw_frame: bytes, new_payload: bytes) -> bytes:
    addr = raw_frame[0]
    length = len(new_payload) + 2
    frame_type = raw_frame[2]
    crc = crc8_dvb_s2(bytes([frame_type]) + new_payload)
    return bytes([addr, length, frame_type]) + new_payload + bytes([crc])


@dataclass
class CRSFFrame:
    addr: int
    length: int
    frame_type: int
    payload: bytes
    crc: int
    raw: bytes


class CRSFParser:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes) -> List[CRSFFrame]:
        self.buf.extend(data)
        frames = []

        while True:
            if len(self.buf) < 2:
                break

            length = self.buf[1]
            if length < 2 or length > 64:
                self.buf.pop(0)
                continue

            total_len = 2 + length
            if len(self.buf) < total_len:
                break

            raw = bytes(self.buf[:total_len])
            del self.buf[:total_len]

            addr = raw[0]
            frame_type = raw[2]
            payload = raw[3:-1]
            crc = raw[-1]

            crc_calc = crc8_dvb_s2(bytes([frame_type]) + payload)
            if crc != crc_calc:
                continue

            frames.append(
                CRSFFrame(
                    addr=addr,
                    length=length,
                    frame_type=frame_type,
                    payload=payload,
                    crc=crc,
                    raw=raw,
                )
            )

        return frames


@dataclass
class Detection:
    cls_id: int
    cls_name: str
    conf: float
    xyxy: Tuple[int, int, int, int]

    @property
    def center(self) -> Tuple[int, int]:
        x1, y1, x2, y2 = self.xyxy
        return int((x1 + x2) / 2), int((y1 + y2) / 2)

    def contains(self, x: int, y: int) -> bool:
        x1, y1, x2, y2 = self.xyxy
        return x1 <= x <= x2 and y1 <= y <= y2


@dataclass
class ControlState:
    target_locked: bool = False
    target_index: Optional[int] = None
    target_class: str = ""
    target_conf: float = 0.0

    error_x_norm: float = 0.0
    error_y_norm: float = 0.0

    auto_yaw_cmd: float = 0.0
    auto_pitch_cmd: float = 0.0

    yaw_smoothed: float = 0.0
    pitch_smoothed: float = 0.0


@dataclass
class RCState:
    roll_raw: int = CRSF_RAW_MID
    pitch_raw: int = CRSF_RAW_MID
    throttle_raw: int = CRSF_RAW_MIN
    yaw_raw: int = CRSF_RAW_MID
    aux3_raw: int = CRSF_RAW_MIN
    aux4_raw: int = CRSF_RAW_MIN

    roll_us: int = 1500
    pitch_us: int = 1500
    throttle_us: int = 988
    yaw_us: int = 1500
    aux3_us: int = 1000
    aux4_us: int = 1000

    roll_norm: float = 0.0
    pitch_norm: float = 0.0
    throttle_norm: float = 0.0
    yaw_norm: float = 0.0

    aux3_pos: int = 0
    aux4_on: bool = False

    final_roll_norm: float = 0.0
    final_pitch_norm: float = 0.0
    final_yaw_norm: float = 0.0
    final_throttle_norm: float = 0.0

    rc_rate_hz: float = 0.0
    frame_count: int = 0


class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.control = ControlState()
        self.rc = RCState()
        self.running = True


class CRSFBridgeThread(threading.Thread):
    def __init__(self, cfg: Dict[str, Any], shared: SharedState):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.shared = shared

        self.rx_port = cfg["serial"]["rx_port"]
        self.fc_port = cfg["serial"]["fc_port"]
        self.baudrate = int(cfg["serial"].get("baudrate", 420000))

        self.ch_cfg = cfg["channels"]
        self.aux_cfg = cfg["aux"]
        self.mixing_cfg = cfg["mixing"]

        self.parser = CRSFParser()

        self.rx_ser = None
        self.fc_ser = None

        self.rate_window_start = time.monotonic()
        self.rate_window_count = 0

    def open_serials(self):
        self.rx_ser = serial.Serial(
            port=self.rx_port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.02,
            write_timeout=0.02,
            exclusive=True,
        )

        self.fc_ser = serial.Serial(
            port=self.fc_port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.02,
            write_timeout=0.02,
            exclusive=True,
        )

        print(f"[CRSF] RX: {self.rx_port}")
        print(f"[CRSF] FC: {self.fc_port}")
        print(f"[CRSF] baudrate: {self.baudrate}")

    def close_serials(self):
        for ser in [self.rx_ser, self.fc_ser]:
            try:
                if ser:
                    ser.close()
            except Exception:
                pass

    def get_indices(self):
        return (
            int(self.ch_cfg["roll"]),
            int(self.ch_cfg["pitch"]),
            int(self.ch_cfg["throttle"]),
            int(self.ch_cfg["yaw"]),
            int(self.ch_cfg.get("aux3", 6)),
            int(self.ch_cfg["aux4"]),
        )

    def update_rc_state_from_channels(self, channels: List[int], final_channels: List[int]):
        roll_i, pitch_i, throttle_i, yaw_i, aux3_i, aux4_i = self.get_indices()
        aux3_us = raw_to_us(channels[aux3_i])
        aux4_us = raw_to_us(channels[aux4_i])
        aux4_on = aux4_us >= int(self.aux_cfg.get("aux4_on_threshold_us", 1700))

        if aux3_us < 1300:
            aux3_pos = 0
        elif aux3_us < 1700:
            aux3_pos = 1
        else:
            aux3_pos = 2

        now = time.monotonic()
        self.rate_window_count += 1
        elapsed = now - self.rate_window_start

        rc_rate = None
        if elapsed >= 1.0:
            rc_rate = self.rate_window_count / elapsed
            self.rate_window_count = 0
            self.rate_window_start = now

        with self.shared.lock:
            rc = self.shared.rc

            rc.roll_raw = channels[roll_i]
            rc.pitch_raw = channels[pitch_i]
            rc.throttle_raw = channels[throttle_i]
            rc.yaw_raw = channels[yaw_i]
            rc.aux3_raw = channels[aux3_i]
            rc.aux4_raw = channels[aux4_i]

            rc.roll_us = raw_to_us(channels[roll_i])
            rc.pitch_us = raw_to_us(channels[pitch_i])
            rc.throttle_us = raw_to_us(channels[throttle_i])
            rc.yaw_us = raw_to_us(channels[yaw_i])
            rc.aux3_us = aux3_us
            rc.aux4_us = aux4_us

            rc.roll_norm = raw_to_norm(channels[roll_i])
            rc.pitch_norm = raw_to_norm(channels[pitch_i])
            rc.throttle_norm = raw_to_norm(channels[throttle_i], throttle=True)
            rc.yaw_norm = raw_to_norm(channels[yaw_i])
            rc.aux3_pos = aux3_pos
            rc.aux4_on = aux4_on

            rc.final_roll_norm = raw_to_norm(final_channels[roll_i])
            rc.final_pitch_norm = raw_to_norm(final_channels[pitch_i])
            rc.final_yaw_norm = raw_to_norm(final_channels[yaw_i])
            rc.final_throttle_norm = raw_to_norm(final_channels[throttle_i], throttle=True)

            rc.frame_count += 1
            if rc_rate is not None:
                rc.rc_rate_hz = rc_rate

    def build_mixed_channels(self, channels: List[int]) -> List[int]:
        final_channels = list(channels)

        roll_i, pitch_i, throttle_i, yaw_i, aux3_i, aux4_i = self.get_indices()

        aux4_us = raw_to_us(channels[aux4_i])
        aux4_on = aux4_us >= int(self.aux_cfg.get("aux4_on_threshold_us", 1700))

        with self.shared.lock:
            control = self.shared.control

            auto_yaw = control.auto_yaw_cmd
            auto_pitch = control.auto_pitch_cmd
            target_locked = control.target_locked

        mixing_enabled = bool(self.mixing_cfg.get("enabled", False))

        max_auto_yaw = float(self.mixing_cfg.get("max_auto_yaw", 0.25))
        max_auto_pitch = float(self.mixing_cfg.get("max_auto_pitch", 0.20))

        auto_yaw = max(-max_auto_yaw, min(max_auto_yaw, auto_yaw))
        auto_pitch = max(-max_auto_pitch, min(max_auto_pitch, auto_pitch))

        pilot_yaw = raw_to_norm(channels[yaw_i])
        pilot_pitch = raw_to_norm(channels[pitch_i])

        # Если пилот активно двигает стик, можно ослабить автокоррекцию.
        override_thr = float(self.mixing_cfg.get("pilot_override_threshold", 0.60))
        override_factor = float(self.mixing_cfg.get("pilot_override_factor", 0.40))

        if abs(pilot_yaw) > override_thr:
            auto_yaw *= override_factor

        if abs(pilot_pitch) > override_thr:
            auto_pitch *= override_factor

        if mixing_enabled and aux4_on and target_locked:
            final_yaw = max(-1.0, min(1.0, pilot_yaw + auto_yaw))
            final_pitch = max(-1.0, min(1.0, pilot_pitch + auto_pitch))

            final_channels[yaw_i] = norm_to_raw(final_yaw)
            final_channels[pitch_i] = norm_to_raw(final_pitch)

        return final_channels

    def run(self):
        print("[CRSF] Starting bridge thread...")
        self.open_serials()

        try:
            while True:
                with self.shared.lock:
                    if not self.shared.running:
                        break

                try:
                    data = self.rx_ser.read(256)
                except serial.SerialException as e:
                    print(f"[CRSF] RX error: {e}")
                    time.sleep(0.1)
                    continue

                if not data:
                    continue

                frames = self.parser.feed(data)

                for frame in frames:
                    out_raw = frame.raw

                    if frame.frame_type == CRSF_FRAMETYPE_RC_CHANNELS_PACKED and len(frame.payload) == CRSF_PAYLOAD_SIZE_RC_CHANNELS:
                        channels = unpack_channels(frame.payload)
                        final_channels = self.build_mixed_channels(channels)
                        self.update_rc_state_from_channels(channels, final_channels)

                        new_payload = pack_channels(final_channels)
                        out_raw = rebuild_frame_with_payload(frame.raw, new_payload)

                    try:
                        self.fc_ser.write(out_raw)
                    except serial.SerialException as e:
                        print(f"[CRSF] FC write error: {e}")

        finally:
            self.close_serials()
            print("[CRSF] Bridge stopped")


class TrackingCRSFLab:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.model_path = cfg["model_path"]
        self.source = cfg.get("source", 1)

        self.imgsz = int(cfg.get("imgsz", 480))
        self.conf = float(cfg.get("conf", 0.25))
        self.iou = float(cfg.get("iou", 0.45))
        self.max_det = int(cfg.get("max_det", 50))

        self.camera_cfg = cfg.get("camera", {})
        self.control_cfg = cfg.get("control", {})
        self.failsafe_cfg = cfg.get("failsafe", {})
        self.ui_cfg = cfg.get("ui", {})
        self.tracker_cfg = cfg.get("tracker", {})

        self.allowed_classes = set(cfg.get("classes", {}).get("allowed", []) or [])

        self.window_name = self.ui_cfg.get("window_name", "Tracking CRSF Lab")
        self.draw_all_boxes = bool(self.ui_cfg.get("draw_all_boxes", True))
        self.draw_debug = bool(self.ui_cfg.get("draw_debug", True))
        self.show_crsf_panel = bool(self.ui_cfg.get("draw_crsf_panel", True))

        self.shared = SharedState()
        self.latest_detections: List[Detection] = []

        self.paused = False
        self.recording = bool(self.ui_cfg.get("record_on_start", False))
        self.video_writer = None
        self.csv_file = None
        self.csv_writer = None

        self.frame_id = 0
        self.last_frame = None
        self.fps_smooth = 0.0
        self.last_time = time.time()

        if YOLO is None:
            raise RuntimeError("Ultralytics is not installed. Use tracking_crsf_lab_direct.py for RKNN mode.")

        print(f"[INFO] Loading model: {self.model_path}")
        self.model = YOLO(self.model_path, task="detect")
        print("[INFO] Model loaded")

        self.crsf_thread = CRSFBridgeThread(cfg, self.shared)

    @staticmethod
    def clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def apply_deadzone(value: float, deadzone: float) -> float:
        if abs(value) < deadzone:
            return 0.0
        return value

    def open_source(self):
        src = self.source
        if isinstance(src, str) and src.isdigit():
            src = int(src)

        print(f"[INFO] Opening source: {src}")
        use_v4l2 = isinstance(src, int) or (isinstance(src, str) and src.startswith("/dev/video"))
        cap = cv2.VideoCapture(src, cv2.CAP_V4L2 if use_v4l2 else 0)

        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {src}")

        if use_v4l2:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.camera_cfg.get("width", 640)))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.camera_cfg.get("height", 480)))
            cap.set(cv2.CAP_PROP_FPS, int(self.camera_cfg.get("fps", 30)))

        return cap

    def run_detector(self, frame) -> List[Detection]:
        results = self.model.predict(
            frame,
            imgsz=self.imgsz,
            conf=self.conf,
            iou=self.iou,
            max_det=self.max_det,
            verbose=False,
        )

        detections: List[Detection] = []
        if not results:
            return detections

        r = results[0]
        names = r.names

        if r.boxes is None:
            return detections

        for box in r.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_name = names.get(cls_id, str(cls_id))

            if self.allowed_classes and cls_name not in self.allowed_classes:
                continue

            detections.append(
                Detection(
                    cls_id=cls_id,
                    cls_name=cls_name,
                    conf=conf,
                    xyxy=(int(x1), int(y1), int(x2), int(y2)),
                )
            )

        return detections

    def select_target_by_click(self, x: int, y: int):
        if not self.latest_detections:
            print("[INFO] No detections to select")
            return

        inside = []
        for i, det in enumerate(self.latest_detections):
            if det.contains(x, y):
                cx, cy = det.center
                dist = math.hypot(cx - x, cy - y)
                inside.append((dist, i))

        with self.shared.lock:
            control = self.shared.control

            if inside:
                inside.sort(key=lambda t: t[0])
                control.target_index = inside[0][1]
                control.target_locked = True
                print(f"[INFO] Target selected: index={control.target_index}")
                return

            nearest = []
            for i, det in enumerate(self.latest_detections):
                cx, cy = det.center
                dist = math.hypot(cx - x, cy - y)
                nearest.append((dist, i))

            nearest.sort(key=lambda t: t[0])
            dist, idx = nearest[0]

            if dist < 120:
                control.target_index = idx
                control.target_locked = True
                print(f"[INFO] Target selected nearest: index={idx}, dist={dist:.1f}")
            else:
                print("[INFO] Click too far from detections")

    def clear_target(self):
        with self.shared.lock:
            self.shared.control = ControlState()
        print("[INFO] Target cleared")

    def update_control(self, frame, detections: List[Detection]) -> Optional[Detection]:
        h, w = frame.shape[:2]
        frame_cx = w / 2
        frame_cy = h / 2

        with self.shared.lock:
            control = self.shared.control
            target_index = control.target_index

        if target_index is None or target_index >= len(detections):
            lost_decay = float(self.failsafe_cfg.get("lost_target_decay", 0.85))

            with self.shared.lock:
                c = self.shared.control
                c.target_locked = False
                c.auto_yaw_cmd *= lost_decay
                c.auto_pitch_cmd *= lost_decay
                c.yaw_smoothed *= lost_decay
                c.pitch_smoothed *= lost_decay

            return None

        target = detections[target_index]
        tx, ty = target.center

        error_x = tx - frame_cx
        error_y = ty - frame_cy

        error_x_norm = error_x / frame_cx
        error_y_norm = error_y / frame_cy

        deadzone_x = float(self.control_cfg.get("deadzone_x", 0.05))
        deadzone_y = float(self.control_cfg.get("deadzone_y", 0.05))

        error_x_dz = self.apply_deadzone(error_x_norm, deadzone_x)
        error_y_dz = self.apply_deadzone(error_y_norm, deadzone_y)

        kp_yaw = float(self.control_cfg.get("kp_yaw", 0.35))
        kp_pitch = float(self.control_cfg.get("kp_pitch", 0.25))

        max_yaw = float(self.control_cfg.get("max_yaw", 0.30))
        max_pitch = float(self.control_cfg.get("max_pitch", 0.25))

        alpha = float(self.control_cfg.get("alpha", 0.30))

        yaw_raw = kp_yaw * error_x_dz
        pitch_raw = kp_pitch * error_y_dz

        if bool(self.control_cfg.get("invert_yaw", False)):
            yaw_raw *= -1.0

        if bool(self.control_cfg.get("invert_pitch", False)):
            pitch_raw *= -1.0

        with self.shared.lock:
            c = self.shared.control

            c.yaw_smoothed = alpha * yaw_raw + (1.0 - alpha) * c.yaw_smoothed
            c.pitch_smoothed = alpha * pitch_raw + (1.0 - alpha) * c.pitch_smoothed

            c.auto_yaw_cmd = self.clamp(c.yaw_smoothed, -max_yaw, max_yaw)
            c.auto_pitch_cmd = self.clamp(c.pitch_smoothed, -max_pitch, max_pitch)

            c.target_locked = True
            c.target_class = target.cls_name
            c.target_conf = target.conf
            c.error_x_norm = error_x_norm
            c.error_y_norm = error_y_norm

        return target

    def start_recording(self, frame):
        if self.video_writer is not None:
            return

        Path("recordings").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        video_path = Path("recordings") / f"tracking_crsf_{ts}.avi"
        csv_path = Path("logs") / f"tracking_crsf_{ts}.csv"

        h, w = frame.shape[:2]
        self.video_writer = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"XVID"),
            20.0,
            (w, h),
        )

        self.csv_file = open(csv_path, "w", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            "time", "frame_id",
            "target_locked", "target_index", "target_class", "target_conf",
            "error_x_norm", "error_y_norm",
            "auto_yaw_cmd", "auto_pitch_cmd",
            "roll_us", "pitch_us", "throttle_us", "yaw_us", "aux3_us", "aux3_pos", "aux4_us", "aux4_on",
            "final_pitch_norm", "final_yaw_norm",
            "fps", "rc_rate_hz",
        ])

        self.recording = True
        print(f"[INFO] Recording video: {video_path}")
        print(f"[INFO] Recording CSV:   {csv_path}")

    def stop_recording(self):
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None

        if self.csv_file is not None:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None

        self.recording = False

    def log_csv(self):
        if self.csv_writer is None:
            return

        with self.shared.lock:
            c = self.shared.control
            r = self.shared.rc

            self.csv_writer.writerow([
                time.time(),
                self.frame_id,
                int(c.target_locked),
                c.target_index,
                c.target_class,
                f"{c.target_conf:.4f}",
                f"{c.error_x_norm:.6f}",
                f"{c.error_y_norm:.6f}",
                f"{c.auto_yaw_cmd:.6f}",
                f"{c.auto_pitch_cmd:.6f}",
                r.roll_us,
                r.pitch_us,
                r.throttle_us,
                r.yaw_us,
                getattr(r, "aux3_us", 1000),
                getattr(r, "aux3_pos", 0),
                r.aux4_us,
                int(r.aux4_on),
                f"{r.final_pitch_norm:.6f}",
                f"{r.final_yaw_norm:.6f}",
                f"{self.fps_smooth:.3f}",
                f"{r.rc_rate_hz:.3f}",
            ])

    def draw_stick_box(self, frame, origin, title, pilot_x, pilot_y, final_x, final_y, assist_on):
        x0, y0 = origin
        size = 130
        half = size // 2

        cv2.rectangle(frame, (x0, y0), (x0 + size, y0 + size), (230, 230, 230), 1)
        cv2.line(frame, (x0 + half, y0), (x0 + half, y0 + size), (90, 90, 90), 1)
        cv2.line(frame, (x0, y0 + half), (x0 + size, y0 + half), (90, 90, 90), 1)

        cv2.putText(frame, title, (x0, y0 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)

        def map_point(nx, ny):
            px = int(x0 + half + self.clamp(nx, -1.0, 1.0) * half)
            py = int(y0 + half - self.clamp(ny, -1.0, 1.0) * half)
            return px, py

        pilot_pt = map_point(pilot_x, pilot_y)
        final_pt = map_point(final_x, final_y)

        cv2.circle(frame, pilot_pt, 6, (255, 130, 0), -1)
        cv2.putText(frame, "P", (pilot_pt[0] + 7, pilot_pt[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 130, 0), 1)

        cv2.drawMarker(frame, final_pt, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 14, 2)
        cv2.putText(frame, "F", (final_pt[0] + 7, final_pt[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)

        if assist_on:
            cv2.arrowedLine(frame, pilot_pt, final_pt, (0, 0, 255), 2, tipLength=0.25)

    def draw_crsf_panel(self, frame):
        if not self.show_crsf_panel:
            return

        h, w = frame.shape[:2]

        with self.shared.lock:
            rc = self.shared.rc
            c = self.shared.control
            mixing_enabled = bool(self.cfg.get("mixing", {}).get("enabled", False))

        panel_w = 330
        panel_h = 220
        x0 = max(0, w - panel_w - 10)
        y0 = max(0, h - panel_h - 10)

        overlay = frame.copy()
        cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        assist_color = (0, 255, 0) if rc.aux4_on else (120, 120, 120)
        mode_text = "MIX ACTIVE" if mixing_enabled and rc.aux4_on and c.target_locked else "PREVIEW/PASS"
        cv2.putText(frame, f"CRSF AUX4: {'ON' if rc.aux4_on else 'OFF'}  {mode_text}",
                    (x0 + 10, y0 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, assist_color, 2)

        thr_vis = rc.throttle_norm * 2.0 - 1.0
        final_thr_vis = rc.final_throttle_norm * 2.0 - 1.0

        self.draw_stick_box(
            frame,
            (x0 + 15, y0 + 58),
            "YAW / THR",
            rc.yaw_norm,
            thr_vis,
            rc.final_yaw_norm,
            final_thr_vis,
            rc.aux4_on,
        )

        self.draw_stick_box(
            frame,
            (x0 + 175, y0 + 58),
            "ROLL / PITCH",
            rc.roll_norm,
            rc.pitch_norm,
            rc.final_roll_norm,
            rc.final_pitch_norm,
            rc.aux4_on,
        )

        cv2.putText(frame, f"RC: {rc.rc_rate_hz:.1f}Hz  AUX3: {getattr(rc, 'aux3_us', 1000)}  AUX4: {rc.aux4_us}",
                    (x0 + 15, y0 + panel_h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

    def draw_overlay(self, frame, detections, target):
        h, w = frame.shape[:2]
        cx = int(w / 2)
        cy = int(h / 2)

        cv2.drawMarker(frame, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 24, 2)

        dzx = float(self.control_cfg.get("deadzone_x", 0.05))
        dzy = float(self.control_cfg.get("deadzone_y", 0.05))
        cv2.rectangle(
            frame,
            (cx - int((w / 2) * dzx), cy - int((h / 2) * dzy)),
            (cx + int((w / 2) * dzx), cy + int((h / 2) * dzy)),
            (180, 180, 180),
            1,
        )

        with self.shared.lock:
            c = self.shared.control
            rc = self.shared.rc

        if self.draw_all_boxes:
            for i, det in enumerate(detections):
                x1, y1, x2, y2 = det.xyxy
                color = (0, 180, 255)

                if c.target_locked and i == c.target_index:
                    color = (0, 255, 0)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{i}: {det.cls_name} {det.conf:.2f}",
                            (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        if target is not None:
            tx, ty = target.center
            cv2.circle(frame, (tx, ty), 5, (0, 255, 0), -1)
            cv2.line(frame, (cx, cy), (tx, ty), (0, 255, 0), 2)

            arrow_scale = 140
            end_x = int(cx + c.auto_yaw_cmd * arrow_scale)
            end_y = int(cy + c.auto_pitch_cmd * arrow_scale)
            cv2.arrowedLine(frame, (cx, cy), (end_x, end_y), (0, 0, 255), 3, tipLength=0.25)

        elif bool(self.tracker_cfg.get("draw_lost_bbox", True)):
            with self.shared.lock:
                lost_bbox = getattr(self.shared.control, "target_bbox", None)
                lost_frames = int(getattr(self.shared.control, "target_lost_frames", 0))

            if lost_bbox is not None and lost_frames > 0:
                lx1, ly1, lx2, ly2 = lost_bbox
                cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), (0, 0, 255), 2)
                cv2.putText(
                    frame,
                    f"LOST {lost_frames}",
                    (lx1, max(20, ly1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                )

        self.draw_crsf_panel(frame)

        if self.draw_debug:
            mixing_enabled = bool(self.cfg.get("mixing", {}).get("enabled", False))
            lines = [
                f"FPS: {self.fps_smooth:.1f}",
                f"RC Hz: {rc.rc_rate_hz:.1f}",
                f"Detections: {len(detections)}",
                f"Target: {c.target_locked} index={c.target_index}",
                f"Lost frames: {getattr(c, 'target_lost_frames', 0)}",
                f"Class: {c.target_class} conf={c.target_conf:.2f}",
                f"err_x: {c.error_x_norm:+.3f}",
                f"err_y: {c.error_y_norm:+.3f}",
                f"auto_yaw:   {c.auto_yaw_cmd:+.3f}",
                f"auto_pitch: {c.auto_pitch_cmd:+.3f}",
                f"pilot yaw/pitch: {rc.yaw_us}/{rc.pitch_us}",
                f"AUX3: {getattr(rc, 'aux3_us', 1000)} pos={getattr(rc, 'aux3_pos', 0)}",
                f"Servo: {getattr(getattr(self, 'servo_pwm', None), 'current_name', 'OFF')} angle={getattr(getattr(self, 'servo_pwm', None), 'current_angle', 0)}",
                f"AUX4: {rc.aux4_us} {'ON' if rc.aux4_on else 'OFF'}",
                f"mixing_enabled: {mixing_enabled}",
                f"recording: {self.recording}",
            ]

            x0, y0 = 10, 25
            for i, text in enumerate(lines):
                y = y0 + i * 22
                cv2.putText(frame, text, (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
                cv2.putText(frame, text, (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        return frame

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.select_target_by_click(x, y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.clear_target()

    def handle_key(self, key, frame):
        if key == -1:
            return True

        ch = chr(key & 0xFF)

        if ch == "q":
            return False
        elif ch == " ":
            self.paused = not self.paused
            print(f"[INFO] paused={self.paused}")
        elif ch == "c":
            self.clear_target()
        elif ch == "b":
            self.draw_debug = not self.draw_debug
        elif ch == "g":
            self.show_crsf_panel = not self.show_crsf_panel
        elif ch == "v":
            if self.recording:
                self.stop_recording()
            else:
                self.start_recording(frame)
        elif ch == "s":
            Path("screenshots").mkdir(exist_ok=True)
            p = Path("screenshots") / f"tracking_crsf_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
            cv2.imwrite(str(p), frame)
            print(f"[INFO] Screenshot: {p}")

        return True

    def run(self):
        cap = self.open_source()
        self.crsf_thread.start()

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1100, 780)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)

        print("")
        print("[INFO] Controls:")
        print("  left click  - select target")
        print("  right click - clear target")
        print("  q           - quit")
        print("  space       - pause")
        print("  c           - clear target")
        print("  b           - toggle debug")
        print("  g           - toggle CRSF panel")
        print("  v           - record on/off")
        print("  s           - screenshot")
        print("")
        print("[SAFETY] Start with mixing.enabled=false. Enable only after checking preview.")

        try:
            while True:
                if not self.paused or self.last_frame is None:
                    ok, frame = cap.read()
                    if not ok:
                        print("[WARN] Failed to read frame")
                        break

                    if bool(self.camera_cfg.get("rotate_180", False)):
                        frame = cv2.rotate(frame, cv2.ROTATE_180)

                    self.last_frame = frame
                else:
                    frame = self.last_frame.copy()

                detections = self.run_detector(frame)
                self.latest_detections = detections

                if hasattr(self, "handle_aux4_mode"):
                    self.handle_aux4_mode(frame, detections)

                target = self.update_control(frame, detections)

                if hasattr(self, "update_aux3_servo"):
                    self.update_aux3_servo()

                overlay = frame.copy()
                overlay = self.draw_overlay(overlay, detections, target)

                self.frame_id += 1

                now = time.time()
                dt = now - self.last_time
                self.last_time = now

                if dt > 0:
                    fps = 1.0 / dt
                    if self.fps_smooth == 0:
                        self.fps_smooth = fps
                    else:
                        self.fps_smooth = 0.9 * self.fps_smooth + 0.1 * fps

                if self.recording:
                    if self.video_writer is None:
                        self.start_recording(overlay)
                    self.video_writer.write(overlay)
                    self.log_csv()

                cv2.imshow(self.window_name, overlay)

                key = cv2.waitKey(1)
                if not self.handle_key(key, overlay):
                    break

        finally:
            with self.shared.lock:
                self.shared.running = False

            cap.release()
            self.stop_recording()
            if hasattr(self, "detector"):
                try:
                    self.detector.release()
                except Exception:
                    pass
            if hasattr(self, "servo_pwm") and self.servo_pwm is not None:
                self.servo_pwm.disable()
            cv2.destroyAllWindows()
            print("[INFO] Stopped")


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/tracking_crsf_ultralytics.example.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    app = TrackingCRSFLab(cfg)
    app.run()


if __name__ == "__main__":
    main()
