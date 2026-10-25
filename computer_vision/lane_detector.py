"""Lane Detector: Classical Duckietown yellow/white line detection."""

import logging
from typing import Dict, Any, Optional
import numpy as np

from computer_vision.schemas import LaneObservation

logger = logging.getLogger(__name__)

# Check if cv2 is available
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class LaneDetector:
    """Detects yellow dashed center lines and white solid border lines for Duckietown roads."""

    def __init__(self, config: Dict[str, Any]):
        lane_cfg = config.get("computer_vision", {}).get("lane_detection", {})
        self.enabled = lane_cfg.get("enabled", True)
        self.hsv_yellow_low = np.array(lane_cfg.get("hsv_yellow_low", [20, 90, 90]), dtype=np.uint8)
        self.hsv_yellow_high = np.array(lane_cfg.get("hsv_yellow_high", [35, 255, 255]), dtype=np.uint8)
        self.hsv_white_low = np.array(lane_cfg.get("hsv_white_low", [0, 0, 180]), dtype=np.uint8)
        self.hsv_white_high = np.array(lane_cfg.get("hsv_white_high", [180, 60, 255]), dtype=np.uint8)
        self.roi_top_ratio = float(lane_cfg.get("roi_top_ratio", 0.55))
        self.lane_width_nominal_px = float(lane_cfg.get("lane_width_nominal_px", 240))

    def detect(self, frame: Optional[np.ndarray]) -> LaneObservation:
        """Detect lanes in the given BGR frame."""
        if not self.enabled or frame is None or frame.size == 0:
            return LaneObservation(detected=False)

        h, w = frame.shape[:2]
        roi_y = int(h * self.roi_top_ratio)
        roi = frame[roi_y:, :]

        if HAS_CV2:
            return self._detect_cv2(roi, w, h - roi_y)
        else:
            return self._detect_numpy(roi, w, h - roi_y)

    def _detect_cv2(self, roi: np.ndarray, w: int, h: int) -> LaneObservation:
        """Lane detection using OpenCV HSV thresholding and moments."""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Yellow center lane mask
        mask_yellow = cv2.inRange(hsv, self.hsv_yellow_low, self.hsv_yellow_high)
        # White outer lane mask
        mask_white = cv2.inRange(hsv, self.hsv_white_low, self.hsv_white_high)

        m_yellow = cv2.moments(mask_yellow)
        m_white = cv2.moments(mask_white)

        has_yellow = m_yellow["m00"] > 400
        has_white = m_white["m00"] > 400

        cx_yellow = (m_yellow["m10"] / m_yellow["m00"]) if has_yellow else None
        cx_white = (m_white["m10"] / m_white["m00"]) if has_white else None

        img_center_x = w / 2.0

        if has_yellow and has_white and cx_yellow is not None and cx_white is not None:
            # Ideal target is midpoint between yellow and white lines
            lane_center = (cx_yellow + cx_white) / 2.0
            offset = (img_center_x - lane_center) / (w / 2.0)
            confidence = 0.90
        elif has_yellow and cx_yellow is not None:
            # In Duckietown, robot drives in the right lane, ~120px to the right of yellow line
            estimated_center = cx_yellow + (self.lane_width_nominal_px / 2.0)
            offset = (img_center_x - estimated_center) / (w / 2.0)
            confidence = 0.70
        elif has_white and cx_white is not None:
            # Robot drives ~120px to the left of the white outer line
            estimated_center = cx_white - (self.lane_width_nominal_px / 2.0)
            offset = (img_center_x - estimated_center) / (w / 2.0)
            confidence = 0.70
        else:
            return LaneObservation(detected=False, confidence=0.0)

        # Clamp offset between -1.0 (drifted left) and 1.0 (drifted right)
        offset_norm = float(np.clip(offset, -1.0, 1.0))
        heading_deg = float(offset_norm * 25.0) # Approx heading angle proportional to offset

        return LaneObservation(
            detected=True,
            center_offset_normalized=round(offset_norm, 3),
            heading_angle_deg=round(heading_deg, 2),
            confidence=confidence,
            white_lane_detected=has_white,
            yellow_lane_detected=has_yellow,
        )

    def _detect_numpy(self, roi: np.ndarray, w: int, h: int) -> LaneObservation:
        """Numpy-only fallback when OpenCV is not installed."""
        # Simple intensity and color channel analysis
        b, g, r = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
        
        # Yellow: high R, high G, low B
        yellow_mask = (r > 150) & (g > 140) & (b < 100)
        # White: high R, high G, high B
        white_mask = (r > 190) & (g > 190) & (b > 190)

        yellow_pts = np.argwhere(yellow_mask)
        white_pts = np.argwhere(white_mask)

        has_yellow = len(yellow_pts) > 200
        has_white = len(white_pts) > 200

        img_center_x = w / 2.0

        if has_yellow and has_white:
            cy_yellow = np.mean(yellow_pts[:, 1])
            cy_white = np.mean(white_pts[:, 1])
            lane_center = (cy_yellow + cy_white) / 2.0
            offset = (img_center_x - lane_center) / (w / 2.0)
            confidence = 0.85
        elif has_yellow:
            cy_yellow = np.mean(yellow_pts[:, 1])
            lane_center = cy_yellow + (self.lane_width_nominal_px / 2.0)
            offset = (img_center_x - lane_center) / (w / 2.0)
            confidence = 0.65
        elif has_white:
            cy_white = np.mean(white_pts[:, 1])
            lane_center = cy_white - (self.lane_width_nominal_px / 2.0)
            offset = (img_center_x - lane_center) / (w / 2.0)
            confidence = 0.65
        else:
            return LaneObservation(detected=False, confidence=0.0)

        offset_norm = float(np.clip(offset, -1.0, 1.0))
        return LaneObservation(
            detected=True,
            center_offset_normalized=round(offset_norm, 3),
            heading_angle_deg=round(offset_norm * 25.0, 2),
            confidence=confidence,
            white_lane_detected=has_white,
            yellow_lane_detected=has_yellow,
        )
