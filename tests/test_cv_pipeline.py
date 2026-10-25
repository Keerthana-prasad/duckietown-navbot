"""Unit tests for Computer Vision Pipeline, Object Detector, Lane Detector, and Obstacle Checks."""

import pytest
import numpy as np
from computer_vision import VisionPipeline, ObjectDetector, LaneDetector, ObstacleDetector
from computer_vision.schemas import BoundingBox, DetectedObject

TEST_CV_CONFIG = {
    "computer_vision": {
        "model_type": "mock",
        "confidence_threshold": 0.4,
        "lane_detection": {
            "enabled": True,
            "roi_top_ratio": 0.5,
            "lane_width_nominal_px": 240
        },
        "obstacle_detection": {
            "min_distance_meters": 0.22,
            "caution_distance_meters": 0.45,
            "bounding_box_area_stop": 0.25,
            "bounding_box_area_caution": 0.12
        }
    }
}


@pytest.fixture
def vision_pipeline():
    return VisionPipeline(TEST_CV_CONFIG)


def test_missing_or_none_frame(vision_pipeline):
    """Test handling of None or empty frame."""
    res = vision_pipeline.process(None)
    assert res.status == "no_frame"
    assert len(res.detections) == 0

    empty_arr = np.zeros((0, 0, 3), dtype=np.uint8)
    res_empty = vision_pipeline.process(empty_arr)
    assert res_empty.status == "no_frame"


def test_object_detection_mock(vision_pipeline):
    """Test object detector generates structured detections with normalized bboxes."""
    dummy_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
    res = vision_pipeline.process(dummy_frame, target_filter="bottle")
    
    assert res.status == "ok"
    assert len(res.detections) > 0
    det = res.detections[0]
    assert isinstance(det, DetectedObject)
    assert det.bbox.x1 >= 0.0 and det.bbox.x2 <= 1.0
    assert det.bbox.y1 >= 0.0 and det.bbox.y2 <= 1.0
    assert det.confidence > 0.0


def test_lane_detection_on_synthetic_road():
    """Test lane detector computes center offset from lane lines."""
    lane_detector = LaneDetector(TEST_CV_CONFIG)
    # Create synthetic frame: yellow on left, white on right
    frame = np.full((480, 640, 3), 40, dtype=np.uint8)
    # Yellow center line at x=200
    frame[240:, 190:210] = [0, 215, 255]
    # White right line at x=500
    frame[240:, 490:510] = [255, 255, 255]

    lane = lane_detector.detect(frame)
    assert lane.detected is True
    assert lane.confidence > 0.5
    assert -1.0 <= lane.center_offset_normalized <= 1.0


def test_obstacle_detection_tof():
    """Test obstacle detector triggers BLOCKED on close ToF distance."""
    obs_detector = ObstacleDetector(TEST_CV_CONFIG)
    
    # 0.15m is below 0.22m minimum stop distance
    is_blocked, dist, risk = obs_detector.evaluate(detections=[], tof_distance_m=0.15)
    assert is_blocked is True
    assert dist == 0.15
    assert risk == "BLOCKED"

    # 1.0m is clear
    is_blocked_clear, dist_clear, risk_clear = obs_detector.evaluate(detections=[], tof_distance_m=1.0)
    assert is_blocked_clear is False
    assert risk_clear == "CLEAR"


def test_visualizer_annotation(vision_pipeline):
    """Test annotated frame produces valid JPEG bytes."""
    frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    res = vision_pipeline.process(frame, target_filter="bottle")
    jpeg_bytes = vision_pipeline.render_annotated_jpeg(
        frame=frame,
        vision_result=res,
        state_text="NAVIGATING",
        goal_text="laboratory",
        mode="SIMULATION"
    )
    assert isinstance(jpeg_bytes, bytes)
    assert len(jpeg_bytes) > 500
    # Check JPEG magic bytes: 0xFF, 0xD8
    assert jpeg_bytes[:2] == b'\xff\xd8'
