"""Unit tests for Navigation State Machine, Safety Supervisor, and Planner."""

import pytest
import time
from navigation.state_machine import NavigationState, NavigationStateMachine
from navigation.safety import SafetySupervisor
from navigation.planner import NavigationPlanner
from robot_interface.mock import MockRobotInterface
from llm.schemas import InterpretedGoal, NavigationIntent, Constraints
from computer_vision.schemas import VisionFrameResult, DetectedObject, BoundingBox

TEST_NAV_CONFIG = {
    "system": {"mode": "simulation"},
    "robot": {"hostname": "entebot209.local"},
    "navigation": {
        "max_linear_velocity": 0.22,
        "max_angular_velocity": 2.2,
        "default_cruise_velocity": 0.15,
        "turn_speed": 1.0,
        "goal_reached_bbox_ratio": 0.25,
        "watchdog_timeout_seconds": 1.0
    },
    "safety": {
        "enable_hardware_movement": False,
        "auto_stop_on_camera_loss": True,
        "camera_timeout_seconds": 1.5,
        "max_continuous_run_time_s": 100.0
    }
}


def test_state_machine_valid_workflow():
    """Test standard progression: IDLE -> VALIDATING_REQUEST -> PLANNING -> NAVIGATING -> GOAL_REACHED."""
    sm = NavigationStateMachine(NavigationState.IDLE)
    assert sm.current_state == NavigationState.IDLE

    assert sm.transition_to(NavigationState.VALIDATING_REQUEST) is True
    assert sm.transition_to(NavigationState.PLANNING) is True
    assert sm.transition_to(NavigationState.NAVIGATING) is True
    assert sm.transition_to(NavigationState.GOAL_REACHED) is True
    assert sm.transition_to(NavigationState.IDLE) is True


def test_state_machine_invalid_transition():
    """Test invalid direct state jump (e.g. IDLE directly to GOAL_REACHED)."""
    sm = NavigationStateMachine(NavigationState.IDLE)
    assert sm.transition_to(NavigationState.GOAL_REACHED) is False
    assert sm.current_state == NavigationState.IDLE


def test_emergency_stop_from_any_state():
    """Test that EMERGENCY_STOP can be triggered from any state."""
    sm = NavigationStateMachine(NavigationState.NAVIGATING)
    assert sm.transition_to(NavigationState.EMERGENCY_STOP, "User hit e-stop") is True
    assert sm.current_state == NavigationState.EMERGENCY_STOP

    # Reset from e-stop must go to IDLE
    assert sm.transition_to(NavigationState.IDLE) is True


def test_safety_speed_clamping():
    """Test safety supervisor clamps velocities that exceed physical limits."""
    sm = NavigationStateMachine(NavigationState.NAVIGATING)
    safety = SafetySupervisor(TEST_NAV_CONFIG, sm)
    safety.register_camera_heartbeat()

    # Request excessive linear velocity (1.5 m/s > 0.22 cap)
    safe_v, safe_omega, _ = safety.filter_velocity(1.5, 5.0)
    assert safe_v <= 0.22
    assert safe_omega <= 2.2


def test_safety_stops_motion_when_not_navigating():
    """Test safety supervisor halts movement when state is IDLE or PAUSED."""
    sm = NavigationStateMachine(NavigationState.IDLE)
    safety = SafetySupervisor(TEST_NAV_CONFIG, sm)

    safe_v, safe_omega, reason = safety.filter_velocity(0.15, 0.5)
    assert safe_v == 0.0
    assert safe_omega == 0.0
    assert "inhibited" in reason


def test_planner_arrives_at_goal():
    """Test that planner recognizes goal arrival when target occupies central frame."""
    robot = MockRobotInterface(TEST_NAV_CONFIG)
    sm = NavigationStateMachine(NavigationState.IDLE)
    safety = SafetySupervisor(TEST_NAV_CONFIG, sm)
    planner = NavigationPlanner(TEST_NAV_CONFIG, robot, sm, safety)

    goal = InterpretedGoal(
        intent=NavigationIntent.NAVIGATE_TO_LANDMARK,
        target="laboratory",
        visual_indicator="bottle",
        constraints=Constraints()
    )
    planner.set_goal(goal, "test_task_1")
    planner.start_navigation()
    assert sm.current_state == NavigationState.NAVIGATING

    # Simulate vision frame with large, centered target object (arrival criteria)
    target_det = DetectedObject(
        id="det_target",
        label="bottle",
        confidence=0.95,
        bbox=BoundingBox(x1=0.35, y1=0.30, x2=0.65, y2=0.75), # height = 0.45 > 0.25 threshold
        estimated_distance_m=0.25,
        lateral_offset=0.0
    )
    vis = VisionFrameResult(detections=[target_det], status="ok")

    v, omega, desc = planner.step(vis)
    assert sm.current_state == NavigationState.GOAL_REACHED
    assert v == 0.0
    assert omega == 0.0
    assert "Goal reached" in desc
