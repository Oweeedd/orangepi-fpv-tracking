from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from rknnlite.api import RKNNLite


COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
    "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop",
    "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]


class RKNNYoloDetector:
    def __init__(
        self,
        model_path: str,
        imgsz: int = 416,
        conf: float = 0.30,
        iou: float = 0.45,
        max_det: int = 30,
        class_names: Optional[Sequence[str]] = None,
        core: str = "all",
    ):
        self.model_path = self._find_rknn_model(model_path)
        self.imgsz = int(imgsz)
        self.conf = float(conf)
        self.iou = float(iou)
        self.max_det = int(max_det)

        self.class_names = list(class_names) if class_names else COCO_NAMES

        print(f"[RKNN-DETECTOR] model: {self.model_path}")
        print(f"[RKNN-DETECTOR] imgsz={self.imgsz}, conf={self.conf}, iou={self.iou}, max_det={self.max_det}")
        print(f"[RKNN-DETECTOR] classes={len(self.class_names)}")

        self.rknn = RKNNLite()

        ret = self.rknn.load_rknn(self.model_path)
        if ret != 0:
            raise RuntimeError(f"load_rknn failed: {ret}")

        if core == "all":
            ret = self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
        elif core == "0":
            ret = self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0)
        elif core == "1":
            ret = self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_1)
        elif core == "2":
            ret = self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_2)
        else:
            ret = self.rknn.init_runtime()

        if ret != 0:
            raise RuntimeError(f"init_runtime failed: {ret}")

        self._printed_output_shape = False

    @staticmethod
    def _find_rknn_model(path: str) -> str:
        p = Path(path)

        if p.is_file() and p.suffix == ".rknn":
            return str(p)

        if p.is_dir():
            models = sorted(p.glob("*.rknn"))
            if not models:
                raise FileNotFoundError(f"No .rknn file found in {p}")
            return str(models[0])

        raise FileNotFoundError(path)

    @staticmethod
    def letterbox(image, new_shape: Tuple[int, int], color=(114, 114, 114)):
        h, w = image.shape[:2]
        new_h, new_w = new_shape

        scale = min(new_w / w, new_h / h)

        resized_w = int(round(w * scale))
        resized_h = int(round(h * scale))

        dw = new_w - resized_w
        dh = new_h - resized_h
        dw /= 2
        dh /= 2

        resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)

        top = int(round(dh - 0.1))
        bottom = int(round(dh + 0.1))
        left = int(round(dw - 0.1))
        right = int(round(dw + 0.1))

        out = cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=color,
        )

        return out, scale, left, top

    @staticmethod
    def xywh_to_xyxy(xywh: np.ndarray) -> np.ndarray:
        x, y, w, h = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
        x1 = x - w / 2
        y1 = y - h / 2
        x2 = x + w / 2
        y2 = y + h / 2
        return np.stack([x1, y1, x2, y2], axis=1)

    @staticmethod
    def nms_numpy(boxes: np.ndarray, scores: np.ndarray, iou_thres: float, max_det: int):
        if len(boxes) == 0:
            return []

        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]

        areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
        order = scores.argsort()[::-1]

        keep = []

        while order.size > 0 and len(keep) < max_det:
            i = order[0]
            keep.append(i)

            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            inter = w * h

            union = areas[i] + areas[order[1:]] - inter + 1e-6
            iou = inter / union

            inds = np.where(iou <= iou_thres)[0]
            order = order[inds + 1]

        return keep

    def detect(self, frame) -> List[Dict]:
        orig_h, orig_w = frame.shape[:2]

        img, scale, pad_x, pad_y = self.letterbox(frame, (self.imgsz, self.imgsz))
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        inp = np.expand_dims(img_rgb, 0)

        outputs = self.rknn.inference(inputs=[inp])

        if not self._printed_output_shape:
            print("[RKNN-DETECTOR] output tensors:")
            for i, out in enumerate(outputs):
                arr = np.asarray(out)
                print(f"  output[{i}]: shape={arr.shape}, dtype={arr.dtype}")
            self._printed_output_shape = True

        return self.decode(
            outputs,
            scale=scale,
            pad_x=pad_x,
            pad_y=pad_y,
            orig_w=orig_w,
            orig_h=orig_h,
        )

    def decode(self, outputs, scale: float, pad_x: float, pad_y: float, orig_w: int, orig_h: int) -> List[Dict]:
        out = np.asarray(outputs[0])

        if out.ndim == 3:
            out = out[0]

        # Expected exported Ultralytics RKNN format:
        # (4 + nc, N) or (N, 4 + nc)
        if out.shape[0] < out.shape[1]:
            pred = out.T
        else:
            pred = out

        if pred.shape[1] < 5:
            return []

        boxes_xywh = pred[:, :4]
        class_scores = pred[:, 4:]

        if class_scores.shape[1] <= 0:
            return []

        cls_ids = np.argmax(class_scores, axis=1)
        scores = class_scores[np.arange(class_scores.shape[0]), cls_ids]

        mask = scores >= self.conf

        boxes_xywh = boxes_xywh[mask]
        scores = scores[mask]
        cls_ids = cls_ids[mask]

        if len(scores) == 0:
            return []

        boxes = self.xywh_to_xyxy(boxes_xywh)

        # Undo letterbox
        boxes[:, [0, 2]] -= pad_x
        boxes[:, [1, 3]] -= pad_y
        boxes[:, :4] /= scale

        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, orig_w - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, orig_h - 1)

        final_dets = []

        for cls in np.unique(cls_ids):
            idxs = np.where(cls_ids == cls)[0]
            keep = self.nms_numpy(boxes[idxs], scores[idxs], self.iou, self.max_det)

            for k in keep:
                real_idx = idxs[k]
                cls_id = int(cls_ids[real_idx])

                if cls_id < len(self.class_names):
                    cls_name = self.class_names[cls_id]
                else:
                    cls_name = str(cls_id)

                final_dets.append({
                    "cls_id": cls_id,
                    "cls_name": cls_name,
                    "conf": float(scores[real_idx]),
                    "xyxy": tuple(boxes[real_idx].astype(int).tolist()),
                })

        final_dets.sort(key=lambda d: d["conf"], reverse=True)
        return final_dets[: self.max_det]

    def release(self):
        try:
            self.rknn.release()
        except Exception:
            pass
