import argparse
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import yaml

from tracking_crsf_lab import (
    CRSFBridgeThread,
    Detection,
    ControlState,
    SharedState,
    TrackingCRSFLab,
)
from rknn_yolo_detector import RKNNYoloDetector
from servo_pwm_sysfs import SysfsServo, SysfsServoConfig


def box_iou_xyxy(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

    union = area_a + area_b - inter + 1e-6
    return inter / union


def box_center_xyxy(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


class TrackingCRSFLabDirect(TrackingCRSFLab):
    def __init__(self, cfg: Dict[str, Any]):
        # Base class loads Ultralytics; direct mode uses RKNNLite instead.
        self.cfg = cfg
        self.model_path = cfg["model_path"]
        self.source = cfg.get("source", 1)

        self.imgsz = int(cfg.get("imgsz", 416))
        self.conf = float(cfg.get("conf", 0.30))
        self.iou = float(cfg.get("iou", 0.45))
        self.max_det = int(cfg.get("max_det", 30))

        self.camera_cfg = cfg.get("camera", {})
        self.control_cfg = cfg.get("control", {})
        self.failsafe_cfg = cfg.get("failsafe", {})
        self.ui_cfg = cfg.get("ui", {})
        self.tracker_cfg = cfg.get("tracker", {})

        self.allowed_classes = set(cfg.get("classes", {}).get("allowed", []) or [])

        self.window_name = self.ui_cfg.get("window_name", "Tracking CRSF Lab Direct")
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

        class_names = cfg.get("detector", {}).get("class_names", None)
        core = cfg.get("detector", {}).get("core", "all")

        print("[INFO] Loading direct RKNN detector")
        self.detector = RKNNYoloDetector(
            model_path=self.model_path,
            imgsz=self.imgsz,
            conf=self.conf,
            iou=self.iou,
            max_det=self.max_det,
            class_names=class_names,
            core=core,
        )
        print("[INFO] Direct RKNN detector loaded")

        self.crsf_thread = CRSFBridgeThread(cfg, self.shared)

        servo_pwm_raw = cfg.get("servo_pwm", {}) or {}
        self.servo_pwm = SysfsServo(
            SysfsServoConfig(
                enabled=bool(servo_pwm_raw.get("enabled", False)),
                pwmchip=str(servo_pwm_raw.get("pwmchip", "/sys/class/pwm/pwmchip1")),
                channel=int(servo_pwm_raw.get("channel", 0)),
                period_ns=int(servo_pwm_raw.get("period_ns", 20_000_000)),
                min_us=int(servo_pwm_raw.get("min_us", 700)),
                max_us=int(servo_pwm_raw.get("max_us", 2300)),
                min_angle=float(servo_pwm_raw.get("min_angle", 0)),
                max_angle=float(servo_pwm_raw.get("max_angle", 180)),
                down_angle=float(servo_pwm_raw.get("down_angle", 0)),
                mid_angle=float(servo_pwm_raw.get("mid_angle", 45)),
                front_angle=float(servo_pwm_raw.get("front_angle", 90)),
                invert=bool(servo_pwm_raw.get("invert", False)),
            )
        )

    def run_detector(self, frame) -> List[Detection]:
        raw_dets = self.detector.detect(frame)

        detections: List[Detection] = []

        for d in raw_dets:
            cls_name = d["cls_name"]

            if self.allowed_classes and cls_name not in self.allowed_classes:
                continue

            detections.append(
                Detection(
                    cls_id=int(d["cls_id"]),
                    cls_name=cls_name,
                    conf=float(d["conf"]),
                    xyxy=tuple(map(int, d["xyxy"])),
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

        nearest = []
        for i, det in enumerate(self.latest_detections):
            cx, cy = det.center
            dist = math.hypot(cx - x, cy - y)
            nearest.append((dist, i))

        with self.shared.lock:
            control = self.shared.control

            if inside:
                inside.sort(key=lambda t: t[0])
                idx = inside[0][1]
            else:
                nearest.sort(key=lambda t: t[0])
                dist, idx = nearest[0]
                if dist > float(self.tracker_cfg.get("click_nearest_max_dist", 120)):
                    print("[INFO] Click too far from detections")
                    return

            det = self.latest_detections[idx]

            control.target_index = idx
            control.target_locked = True
            control.target_class = det.cls_name
            control.target_conf = det.conf

            control.target_bbox = det.xyxy
            control.target_cls_id = det.cls_id
            control.target_lost_frames = 0

            print(f"[INFO] Target selected: index={idx}, class={det.cls_name}, conf={det.conf:.2f}")

    def clear_target(self):
        with self.shared.lock:
            self.shared.control = ControlState()
        print("[INFO] Target cleared")

    def match_target(self, detections: List[Detection]) -> Tuple[Optional[int], Optional[Detection]]:
        with self.shared.lock:
            c = self.shared.control
            last_bbox = getattr(c, "target_bbox", None)
            target_cls_id = getattr(c, "target_cls_id", None)
            lost_frames = int(getattr(c, "target_lost_frames", 0))

        if last_bbox is None or target_cls_id is None:
            return None, None

        if not detections:
            return None, None

        last_cx, last_cy = box_center_xyxy(last_bbox)

        same_class_only = bool(self.tracker_cfg.get("same_class_only", True))

        base_center_dist = float(self.tracker_cfg.get("max_center_dist", 180.0))
        lost_expand_per_frame = float(self.tracker_cfg.get("lost_expand_per_frame", 8.0))
        reacquire_max_center_dist = float(self.tracker_cfg.get("reacquire_max_center_dist", 520.0))

        dynamic_center_dist = min(
            reacquire_max_center_dist,
            base_center_dist + lost_frames * lost_expand_per_frame,
        )

        iou_weight = float(self.tracker_cfg.get("iou_weight", 0.65))
        center_weight = float(self.tracker_cfg.get("center_weight", 0.35))

        if lost_frames > 0:
            min_score = float(self.tracker_cfg.get("reacquire_min_match_score", 0.05))
        else:
            min_score = float(self.tracker_cfg.get("min_match_score", 0.15))

        best_score = -1.0
        best_idx = None

        for i, det in enumerate(detections):
            if same_class_only and det.cls_id != target_cls_id:
                continue

            iou = box_iou_xyxy(last_bbox, det.xyxy)

            cx, cy = det.center
            dist = math.hypot(cx - last_cx, cy - last_cy)

            if dist > dynamic_center_dist:
                continue

            center_score = max(0.0, 1.0 - dist / dynamic_center_dist)

            if lost_frames > 0:
                score = 0.35 * iou + 0.65 * center_score
            else:
                score = iou_weight * iou + center_weight * center_score

            score += 0.05 * float(det.conf)

            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx is None or best_score < min_score:
            return None, None

        return best_idx, detections[best_idx]

    def update_control(self, frame, detections: List[Detection]) -> Optional[Detection]:
        h, w = frame.shape[:2]
        frame_cx = w / 2
        frame_cy = h / 2

        with self.shared.lock:
            control = self.shared.control
            has_target = getattr(control, "target_bbox", None) is not None

        if not has_target:
            with self.shared.lock:
                c = self.shared.control
                c.target_locked = False
                c.auto_yaw_cmd = 0.0
                c.auto_pitch_cmd = 0.0
            return None

        matched_idx, target = self.match_target(detections)

        if target is None:
            lost_decay = float(self.failsafe_cfg.get("lost_target_decay", 0.85))

            control_lost_frames = int(self.tracker_cfg.get("control_lost_frames", 8))
            memory_frames = int(self.tracker_cfg.get("memory_frames", 75))

            with self.shared.lock:
                c = self.shared.control

                lost = int(getattr(c, "target_lost_frames", 0)) + 1
                c.target_lost_frames = lost
                c.target_locked = False

                c.auto_yaw_cmd *= lost_decay
                c.auto_pitch_cmd *= lost_decay
                c.yaw_smoothed *= lost_decay
                c.pitch_smoothed *= lost_decay

                if lost >= control_lost_frames:
                    c.auto_yaw_cmd = 0.0
                    c.auto_pitch_cmd = 0.0
                    c.yaw_smoothed = 0.0
                    c.pitch_smoothed = 0.0

                if lost > memory_frames:
                    print("[TRACKER] Target memory expired")
                    self.shared.control = ControlState()

            return None

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

            was_lost = int(getattr(c, "target_lost_frames", 0)) > 0

            c.yaw_smoothed = alpha * yaw_raw + (1.0 - alpha) * c.yaw_smoothed
            c.pitch_smoothed = alpha * pitch_raw + (1.0 - alpha) * c.pitch_smoothed

            c.auto_yaw_cmd = self.clamp(c.yaw_smoothed, -max_yaw, max_yaw)
            c.auto_pitch_cmd = self.clamp(c.pitch_smoothed, -max_pitch, max_pitch)

            c.target_locked = True
            c.target_index = matched_idx
            c.target_class = target.cls_name
            c.target_conf = target.conf
            c.error_x_norm = error_x_norm
            c.error_y_norm = error_y_norm

            c.target_bbox = target.xyxy
            c.target_cls_id = target.cls_id
            c.target_lost_frames = 0

            if was_lost:
                print(f"[TRACKER] Target reacquired: class={target.cls_name}, conf={target.conf:.2f}")

        return target


    def aux4_position_from_us(self, aux4_us: int) -> int:
        """
        AUX4 three-position logic:
          0: OFF / clear target / no tracking
          1: CAPTURE+TRACK / no mixing
          2: MIX / track + CRSF mixing

        Default thresholds:
          <1300      -> pos 0
          1300..1699 -> pos 1
          >=1700     -> pos 2
        """
        aux_cfg = self.cfg.get("aux", {}) or {}

        capture_thr = int(aux_cfg.get("aux4_capture_threshold_us", 1300))
        mix_thr = int(aux_cfg.get("aux4_mix_threshold_us", aux_cfg.get("aux4_on_threshold_us", 1700)))

        if aux4_us < capture_thr:
            return 0
        elif aux4_us < mix_thr:
            return 1
        return 2

    def aux4_mode_name(self, pos: int) -> str:
        if pos == 0:
            return "OFF"
        if pos == 1:
            return "CAPTURE"
        return "MIX"

    def has_target_memory(self) -> bool:
        with self.shared.lock:
            c = self.shared.control
            return getattr(c, "target_bbox", None) is not None

    def select_target_nearest_center(self, frame, detections: List[Detection]) -> bool:
        """
        Selects the detection closest to the frame center.
        Used when AUX4 is switched to CAPTURE or MIX and no target is selected yet.
        """
        if not detections:
            return False

        h, w = frame.shape[:2]
        frame_cx = w / 2.0
        frame_cy = h / 2.0

        max_dist = float(self.tracker_cfg.get("aux4_capture_max_center_dist", 999999.0))

        best_idx = None
        best_dist = 1e18

        for i, det in enumerate(detections):
            cx, cy = det.center
            dist = math.hypot(cx - frame_cx, cy - frame_cy)

            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx is None:
            return False

        if best_dist > max_dist:
            print(f"[AUX4] nearest object too far from center: dist={best_dist:.1f}")
            return False

        det = detections[best_idx]

        with self.shared.lock:
            c = self.shared.control

            c.target_index = best_idx
            c.target_locked = True
            c.target_class = det.cls_name
            c.target_conf = det.conf
            c.target_bbox = det.xyxy
            c.target_cls_id = det.cls_id
            c.target_lost_frames = 0

            c.auto_yaw_cmd = 0.0
            c.auto_pitch_cmd = 0.0
            c.yaw_smoothed = 0.0
            c.pitch_smoothed = 0.0
            c.error_x_norm = 0.0
            c.error_y_norm = 0.0

        print(
            f"[AUX4] Auto target selected: index={best_idx}, "
            f"class={det.cls_name}, conf={det.conf:.2f}, dist={best_dist:.1f}"
        )

        return True

    def handle_aux4_mode(self, frame, detections: List[Detection]) -> int:
        """
        Handles operator control by AUX4:
          pos 0: clear target, no tracking
          pos 1: capture nearest to center and track
          pos 2: capture if needed, then allow mixing in CRSF thread
        """
        if not hasattr(self, "_last_aux4_pos"):
            self._last_aux4_pos = None

        with self.shared.lock:
            aux4_us = int(getattr(self.shared.rc, "aux4_us", 1000))
            had_target = getattr(self.shared.control, "target_bbox", None) is not None

        pos = self.aux4_position_from_us(aux4_us)

        if pos != self._last_aux4_pos:
            print(f"[AUX4] mode={self.aux4_mode_name(pos)} aux4_us={aux4_us}")
            self._last_aux4_pos = pos

        if pos == 0:
            if had_target:
                with self.shared.lock:
                    self.shared.control = ControlState()
                print("[AUX4] OFF: target cleared")
            return pos

        if not had_target:
            self.select_target_nearest_center(frame, detections)

        return pos


    def update_aux3_servo(self):
        if not hasattr(self, "servo_pwm") or self.servo_pwm is None:
            return

        with self.shared.lock:
            aux3_us = int(getattr(self.shared.rc, "aux3_us", 1000))

        self.servo_pwm.set_aux3_position(aux3_us)

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
            from pathlib import Path
            Path("screenshots").mkdir(exist_ok=True)
            p = Path("screenshots") / f"tracking_direct_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
            cv2.imwrite(str(p), frame)
            print(f"[INFO] Screenshot: {p}")
        elif ch == "1":
            if hasattr(self, "servo_pwm") and self.servo_pwm is not None:
                self.servo_pwm.set_angle(self.servo_pwm.cfg.down_angle, "DOWN")
                print("[SERVO-PWM] manual DOWN")
        elif ch == "2":
            if hasattr(self, "servo_pwm") and self.servo_pwm is not None:
                self.servo_pwm.set_angle(self.servo_pwm.cfg.mid_angle, "MID")
                print("[SERVO-PWM] manual MID")
        elif ch == "3":
            if hasattr(self, "servo_pwm") and self.servo_pwm is not None:
                self.servo_pwm.set_angle(self.servo_pwm.cfg.front_angle, "FRONT")
                print("[SERVO-PWM] manual FRONT")

        return True


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/tracking_crsf_direct_config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    app = TrackingCRSFLabDirect(cfg)
    app.run()


if __name__ == "__main__":
    main()
