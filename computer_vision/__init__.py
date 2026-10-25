"""Computer Vision module for Duckiebot."""

from computer_vision.schemas import (
    BoundingBox,
    DetectedObject,
    LaneObservation,
    VisionFrameResult
)
from computer_vision.detector import ObjectDetector
from computer_vision.lane_detector import LaneDetector
from computer_vision.obstacle_detector import ObstacleDetector
from computer_vision.visualization import Visualizer
from computer_vision.pipeline import VisionPipeline

__all__ = [
    "BoundingBox",
    "DetectedObject",
    "LaneObservation",
    "VisionFrameResult",
    "ObjectDetector",
    "LaneDetector",
    "ObstacleDetector",
    "Visualizer",
    "VisionPipeline",
]
