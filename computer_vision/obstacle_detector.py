"""Obstacle Detector: Fuses 2D bounding boxes, vertical position, and optional ToF sensor data."""

import logging
from typing import List, Optional, Tuple, Dict, Any
from computer_vision.schemas import DetectedObject

logger = logging.getLogger(__name__)


class ObstacleDetector:
    """Detects collision risks in the forward path of the Duckiebot."""

    def __init__(self, config: Dict[str, Any]):
        obs_cfg = config.get("computer_vision", {}).get("obstacle_detection", {})
        self.min_dist_m = float(obs_cfg.get("min_distance_meters", 0.22))
        self.caution_dist_m = float(obs_cfg.get("caution_distance_meters", 0.45))
        self.bbox_area_stop = float(obs_cfg.get("bounding_box_area_stop", 0.28))
        self.bbox_area_caution = float(obs_cfg.get("bounding_box_area_caution", 0.14))

    def evaluate(
        self,
        detections: List[DetectedObject],
        tof_distance_m: Optional[float] = None
    ) -> Tuple[bool, Optional[float], str]:
        """Evaluate forward collision risk.
        
        Args:
            detections: List of DetectedObject from current frame.
            tof_distance_m: Range reading from hardware ToF sensor if available (in meters).
            
        Returns:
            Tuple of (is_blocked: bool, closest_distance_m: float, risk_level: str)
            risk_level can be: "CLEAR", "CAUTION", "BLOCKED"
        """
        closest_distance = 999.0
        risk_level = "CLEAR"
        is_blocked = False

        # 1. Sensor check: Hardware ToF range sensor (highest reliability if present on DB21J)
        if tof_distance_m is not None and tof_distance_m > 0.02:
            closest_distance = min(closest_distance, tof_distance_m)
            if tof_distance_m <= self.min_dist_m:
                logger.warning(f"ToF Sensor Emergency Obstacle at {tof_distance_m:.2f}m")
                return True, round(tof_distance_m, 2), "BLOCKED"
            elif tof_distance_m <= self.caution_dist_m:
                risk_level = "CAUTION"

        # 2. Vision check: Evaluate detected objects directly in driving path
        for det in detections:
            # Check if object is in central driving corridor (lateral offset between -0.55 and +0.55)
            in_corridor = abs(det.lateral_offset) < 0.55
            if not in_corridor and not det.is_obstacle:
                continue

            area = det.bbox.area
            bottom_y = det.bbox.y2

            # Estimate distance if provided by calibration/sensor
            if det.estimated_distance_m:
                closest_distance = min(closest_distance, det.estimated_distance_m)

            # If an object is marked as obstacle or occupies critical foreground region
            if det.is_obstacle or (bottom_y > 0.70 and area > self.bbox_area_stop):
                is_blocked = True
                risk_level = "BLOCKED"
                logger.warning(
                    f"Visual Obstacle detected in path: '{det.label}', area={area:.3f}, bottom={bottom_y:.2f}"
                )
                break
            elif bottom_y > 0.60 and area > self.bbox_area_caution:
                risk_level = "CAUTION"

        final_dist = closest_distance if closest_distance < 900.0 else None
        return is_blocked, (round(final_dist, 2) if final_dist is not None else None), risk_level
