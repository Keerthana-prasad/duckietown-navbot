"""Data models for Computer Vision detections and observations."""

import time
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Bounding box coordinates [x1, y1, x2, y2] normalized (0.0 - 1.0) or in pixels."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)


class DetectedObject(BaseModel):
    """Structured information about a detected object or landmark."""
    id: str = Field(description="Unique detection ID")
    label: str = Field(description="Class label (e.g., duckie, bottle, cup, box, traffic_light)")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence score")
    bbox: BoundingBox = Field(description="Normalized bounding box (0.0 to 1.0)")
    estimated_distance_m: Optional[float] = Field(
        default=None,
        description="Calibrated or ToF-fused physical distance in meters"
    )
    lateral_offset: float = Field(
        default=0.0,
        description="Normalized horizontal offset from camera optical center (-1.0 to 1.0)"
    )
    color: Optional[str] = Field(default=None, description="Dominant recognized color if available")
    is_obstacle: bool = Field(default=False, description="Whether this object presents a collision risk")


class LaneObservation(BaseModel):
    """Structured information extracted from Duckietown road lane detection."""
    detected: bool = Field(default=False, description="True if lane markings were found")
    center_offset_normalized: float = Field(
        default=0.0,
        description="Offset from lane center (-1.0 is far left, +1.0 is far right)"
    )
    heading_angle_deg: float = Field(
        default=0.0,
        description="Estimated heading deviation from lane centerline in degrees"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    white_lane_detected: bool = Field(default=False, description="Right continuous lane marker")
    yellow_lane_detected: bool = Field(default=False, description="Center dashed lane marker")


class VisionFrameResult(BaseModel):
    """Complete vision processing result for a single frame."""
    timestamp: float = Field(default_factory=time.time)
    frame_index: int = Field(default=0)
    width: int = Field(default=640)
    height: int = Field(default=480)
    detections: List[DetectedObject] = Field(default_factory=list)
    lane: LaneObservation = Field(default_factory=LaneObservation)
    obstacle_detected: bool = Field(default=False)
    closest_obstacle_distance_m: Optional[float] = Field(default=None)
    status: str = Field(default="ok", description="Status string: 'ok', 'degraded', 'no_frame', 'camera_disconnected'")
    latency_ms: float = Field(default=0.0)
