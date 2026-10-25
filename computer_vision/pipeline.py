"""Integrated Computer Vision Pipeline."""

import time
import logging
from typing import Dict, Any, Optional, Tuple
import numpy as np

from computer_vision.schemas import VisionFrameResult
from computer_vision.detector import ObjectDetector
from computer_vision.lane_detector import LaneDetector
from computer_vision.obstacle_detector import ObstacleDetector
from computer_vision.visualization import Visualizer

logger = logging.getLogger(__name__)


class VisionPipeline:
    """End-to-end vision processing pipeline for Duckiebot."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.detector = ObjectDetector(config)
        self.lane_detector = LaneDetector(config)
        self.obstacle_detector = ObstacleDetector(config)
        self.visualizer = Visualizer()
        self.frame_count = 0

    def process(
        self,
        frame: Optional[np.ndarray],
        target_filter: Optional[str] = None,
        tof_distance_m: Optional[float] = None
    ) -> VisionFrameResult:
        """Processes an image frame and produces structured vision results."""
        start_time = time.time()
        self.frame_count += 1

        if frame is None or frame.size == 0:
            return VisionFrameResult(
                timestamp=time.time(),
                frame_index=self.frame_count,
                status="no_frame",
                latency_ms=0.0
            )

        h, w = frame.shape[:2]

        # 1. Detect objects & landmarks
        detections = self.detector.detect(frame, target_filter=target_filter)

        # 2. Detect road lanes
        lane = self.lane_detector.detect(frame)

        # 3. Detect obstacles & collision risks
        is_blocked, closest_dist, risk_level = self.obstacle_detector.evaluate(
            detections=detections,
            tof_distance_m=tof_distance_m
        )

        latency = (time.time() - start_time) * 1000.0

        return VisionFrameResult(
            timestamp=time.time(),
            frame_index=self.frame_count,
            width=w,
            height=h,
            detections=detections,
            lane=lane,
            obstacle_detected=is_blocked,
            closest_obstacle_distance_m=closest_dist,
            status="ok",
            latency_ms=round(latency, 2)
        )

    def render_annotated_jpeg(
        self,
        frame: Optional[np.ndarray],
        vision_result: VisionFrameResult,
        state_text: str = "IDLE",
        goal_text: Optional[str] = None,
        mode: str = "SIMULATION"
    ) -> bytes:
        """Produce annotated JPEG bytes suitable for MJPEG web streaming."""
        return self.visualizer.annotate_frame(
            frame=frame,
            detections=vision_result.detections,
            lane=vision_result.lane,
            state_text=state_text,
            goal_text=goal_text,
            is_blocked=vision_result.obstacle_detected,
            mode=mode
        )
