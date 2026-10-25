"""Object Detector: YOLOv11 / YOLOv8 integration with Mock and Jetson Nano fallback."""

import logging
import time
from typing import List, Dict, Any, Optional
import numpy as np

from computer_vision.schemas import DetectedObject, BoundingBox

logger = logging.getLogger(__name__)


class ObjectDetector:
    """Detects objects and landmarks for Duckiebot navigation."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("computer_vision", {})
        self.model_type = self.config.get("model_type", "yolo")
        self.model_name = self.config.get("model_name", "yolov8n.pt")
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.40))
        self.iou_threshold = float(self.config.get("iou_threshold", 0.45))
        self.device = self.config.get("device", "cpu")
        
        self.model = None
        self._mock_counter = 0
        self._init_model()

    def _init_model(self):
        """Initialize Ultralytics YOLO model or set up mock detector."""
        if self.model_type == "mock":
            logger.info("ObjectDetector configured in mock mode.")
            return

        try:
            from ultralytics import YOLO
            logger.info(f"Loading YOLO model '{self.model_name}' on {self.device}...")
            self.model = YOLO(self.model_name)
            logger.info("YOLO model loaded successfully.")
        except Exception as e:
            logger.warning(
                f"Could not load YOLO model ({e}). Using robust simulation detector."
            )
            self.model = None

    def detect(self, frame: Optional[np.ndarray], target_filter: Optional[str] = None) -> List[DetectedObject]:
        """Run detection on an image frame.
        
        Args:
            frame: BGR numpy image array (H, W, 3) or None.
            target_filter: Optional class label or landmark to prioritize.
        
        Returns:
            List of DetectedObject.
        """
        if frame is None or frame.size == 0:
            return []

        if self.model is not None:
            return self._detect_yolo(frame, target_filter)
        else:
            return self._detect_simulated(frame, target_filter)

    def _detect_yolo(self, frame: np.ndarray, target_filter: Optional[str] = None) -> List[DetectedObject]:
        """Run real inference using Ultralytics YOLO."""
        h, w = frame.shape[:2]
        results = self.model.predict(
            source=frame,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False
        )

        detections: List[DetectedObject] = []
        if not results:
            return detections

        first_res = results[0]
        boxes = first_res.boxes
        names = first_res.names

        for idx, box in enumerate(boxes):
            cls_id = int(box.cls[0].item())
            label = names.get(cls_id, str(cls_id)).lower()
            conf = float(box.conf[0].item())
            
            # Normalised coordinates [0.0, 1.0]
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = xyxy
            norm_box = BoundingBox(
                x1=float(np.clip(x1 / w, 0.0, 1.0)),
                y1=float(np.clip(y1 / h, 0.0, 1.0)),
                x2=float(np.clip(x2 / w, 0.0, 1.0)),
                y2=float(np.clip(y2 / h, 0.0, 1.0)),
            )

            # Lateral offset from optical center: -1.0 (far left) to +1.0 (far right)
            cx, cy = norm_box.center
            lateral_offset = (cx - 0.5) * 2.0

            # Distance estimate from geometric height ratio (calibrated approx)
            box_h = norm_box.height
            estimated_distance = 0.5 / max(box_h, 0.05) if box_h > 0.01 else 2.0
            
            # Obstacle criteria: if box occupies large bottom region
            is_obstacle = norm_box.y2 > 0.65 and norm_box.area > 0.08

            det = DetectedObject(
                id=f"det_{idx}_{int(time.time()*1000)%10000}",
                label=label,
                confidence=round(conf, 3),
                bbox=norm_box,
                estimated_distance_m=round(estimated_distance, 2),
                lateral_offset=round(lateral_offset, 2),
                is_obstacle=is_obstacle,
            )
            detections.append(det)

        return detections

    def _detect_simulated(self, frame: np.ndarray, target_filter: Optional[str] = None) -> List[DetectedObject]:
        """Realistic simulated detector for offline development, tests, and mock mode."""
        self._mock_counter += 1
        h, w = frame.shape[:2]
        detections: List[DetectedObject] = []

        # If a target filter is provided (e.g. "bottle", "laboratory", "red object")
        # simulate encountering it in the scene with realistic drift
        sim_target = target_filter.lower() if target_filter else "bottle"
        if "lab" in sim_target or "bottle" in sim_target:
            label = "bottle"
        elif "entrance" in sim_target or "box" in sim_target:
            label = "box"
        elif "pickup" in sim_target or "cup" in sim_target:
            label = "cup"
        elif "duckie" in sim_target:
            label = "duckie"
        else:
            label = "bottle"

        # Simulate periodic target appearance (e.g. robot turns and acquires it)
        # Bounding box slowly approaches as robot navigates
        t = (self._mock_counter % 60) / 60.0
        # Simulated approach: area increases from 0.04 to 0.22
        scale = 0.12 + 0.10 * np.sin(t * np.pi)
        cx = 0.5 + 0.15 * np.cos(self._mock_counter * 0.1)
        cy = 0.55

        x1 = max(0.0, cx - scale / 2)
        x2 = min(1.0, cx + scale / 2)
        y1 = max(0.0, cy - scale)
        y2 = min(1.0, cy + scale)

        bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
        cx_box, _ = bbox.center
        lat_offset = (cx_box - 0.5) * 2.0
        est_dist = round(0.5 / max(bbox.height, 0.05), 2)

        det = DetectedObject(
            id=f"sim_{self._mock_counter}",
            label=label,
            confidence=0.91,
            bbox=bbox,
            estimated_distance_m=est_dist,
            lateral_offset=round(lat_offset, 2),
            is_obstacle=False,
            color="blue" if label == "bottle" else "red"
        )
        detections.append(det)

        # Occasionally add an obstacle or duckie crossing
        if (self._mock_counter // 40) % 2 == 1:
            obs_box = BoundingBox(x1=0.42, y1=0.68, x2=0.58, y2=0.92)
            detections.append(
                DetectedObject(
                    id=f"obs_{self._mock_counter}",
                    label="duckie",
                    confidence=0.88,
                    bbox=obs_box,
                    estimated_distance_m=0.32,
                    lateral_offset=0.0,
                    is_obstacle=True,
                    color="yellow"
                )
            )

        return detections
