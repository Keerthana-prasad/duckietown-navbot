"""Pydantic schemas for LLM Destination Interpreter.

Ensures strict validation of LLM outputs for natural-language navigation tasks.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class NavigationIntent(str, Enum):
    NAVIGATE_TO_LANDMARK = "navigate_to_landmark"
    SEARCH_FOR_OBJECT = "search_for_object"
    STOP = "stop"
    FOLLOW_LANE = "follow_lane"
    EXPLORE = "explore"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class Constraints(BaseModel):
    avoid_obstacles: bool = Field(default=True, description="Enforce obstacle avoidance at all times")
    max_speed_ratio: float = Field(default=1.0, ge=0.0, le=1.0, description="Speed scaling factor (0.0 to 1.0)")
    stop_at_target: bool = Field(default=True, description="Halt robot when target reached")


class InterpretedGoal(BaseModel):
    intent: NavigationIntent = Field(description="Interpreted high-level task intent")
    target: Optional[str] = Field(default=None, description="Identified landmark, object label, or destination")
    target_attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Attributes such as color, size, relative position (e.g. {'color': 'red', 'position': 'near entrance'})"
    )
    constraints: Constraints = Field(default_factory=Constraints, description="Safety and movement constraints")
    requires_clarification: bool = Field(default=False, description="True if prompt is underspecified or ambiguous")
    clarification_message: Optional[str] = Field(
        default=None,
        description="Explanation or question to present to user if clarification or rejection is required"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in interpretation")
    raw_query: str = Field(default="", description="Original natural-language text entered by user")
    mapped_landmark: Optional[str] = Field(default=None, description="System-verified landmark identifier")
    visual_indicator: Optional[str] = Field(default=None, description="Expected visual detector class for target")


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"
    BLOCKED = "blocked"
    FAILED = "failed"
    STOPPED = "stopped"
