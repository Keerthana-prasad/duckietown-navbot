"""Pydantic schemas for Backend REST API."""

import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from llm.schemas import InterpretedGoal, TaskStatus
from navigation.state_machine import NavigationState
from computer_vision.schemas import VisionFrameResult
from robot_interface.base import RobotTelemetry


class TaskCreateRequest(BaseModel):
    """User submission of a natural-language navigation instruction."""
    text: str = Field(..., min_length=1, max_length=500, description="Natural language prompt")


class TaskResponse(BaseModel):
    """Details of a registered navigation task."""
    task_id: str
    status: TaskStatus
    raw_query: str
    interpreted_goal: Optional[InterpretedGoal] = None
    navigation_state: NavigationState
    created_at: float = Field(default_factory=time.time)
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """System health and subsystem connectivity summary."""
    status: str = "ok"
    mode: str = "simulation"
    robot_connected: bool
    camera_connected: bool
    llm_cloud_ready: bool
    active_state: NavigationState
    timestamp: float = Field(default_factory=time.time)
    version: str = "1.0.0"


class LogMessage(BaseModel):
    """Structured log record for frontend dashboard."""
    timestamp: float = Field(default_factory=time.time)
    level: str = "INFO"
    source: str = "system"
    message: str


class ControlCommandRequest(BaseModel):
    """Manual direct velocity override request (subject to safety limits)."""
    linear_v: float = Field(..., ge=-0.3, le=0.3)
    angular_omega: float = Field(..., ge=-2.5, le=2.5)
