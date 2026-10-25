"""Goal-oriented Navigation Planner: Combines LLM intent, CV detections, lane offset, and safety."""

import time
import logging
from typing import Dict, Any, Optional, Tuple
import numpy as np

from llm.schemas import InterpretedGoal, NavigationIntent
from computer_vision.schemas import VisionFrameResult, DetectedObject
from navigation.state_machine import NavigationState, NavigationStateMachine
from navigation.safety import SafetySupervisor
from robot_interface.base import BaseRobotInterface

logger = logging.getLogger(__name__)


class NavigationPlanner:
    """Coordinates task execution, visual servoeing, and Duckiebot movement."""

    def __init__(
        self,
        config: Dict[str, Any],
        robot_interface: BaseRobotInterface,
        state_machine: NavigationStateMachine,
        safety_supervisor: SafetySupervisor
    ):
        self.config = config
        self.nav_cfg = config.get("navigation", {})
        self.robot = robot_interface
        self.sm = state_machine
        self.safety = safety_supervisor

        # Navigation tuning parameters
        self.cruise_v = float(self.nav_cfg.get("default_cruise_velocity", 0.15))
        self.turn_speed = float(self.nav_cfg.get("turn_speed", 1.0))
        self.kp_lane = float(self.nav_cfg.get("kp_lane_centering", 0.75))
        self.goal_bbox_ratio = float(self.nav_cfg.get("goal_reached_bbox_ratio", 0.25))

        # Current active task
        self.active_goal: Optional[InterpretedGoal] = None
        self.task_id: Optional[str] = None
        self._search_spin_counter = 0

    def set_goal(self, goal: InterpretedGoal, task_id: str) -> bool:
        """Assign and validate a new goal."""
        logger.info(f"Setting goal for task {task_id}: intent={goal.intent.value}, target={goal.target}")

        if goal.requires_clarification or goal.intent == NavigationIntent.UNSUPPORTED:
            self.sm.transition_to(NavigationState.ERROR, f"Unsupported or ambiguous goal: {goal.clarification_message}")
            return False

        self.active_goal = goal
        self.task_id = task_id
        self._search_spin_counter = 0

        # Transition IDLE -> VALIDATING_REQUEST -> PLANNING
        self.sm.transition_to(NavigationState.VALIDATING_REQUEST, "Validating goal feasibility")
        self.sm.transition_to(NavigationState.PLANNING, f"Planned trajectory for '{goal.target}'")
        return True

    def start_navigation(self) -> bool:
        """Explicit action required to begin physical or simulated motion."""
        if self.sm.current_state in (NavigationState.PLANNING, NavigationState.PAUSED):
            return self.sm.transition_to(NavigationState.NAVIGATING, "User confirmed task execution")
        else:
            logger.warning(f"Cannot start navigation from state {self.sm.current_state.value}")
            return False

    def pause_navigation(self) -> bool:
        """Temporarily pause motion."""
        if self.sm.current_state == NavigationState.NAVIGATING:
            self.robot.send_twist(0.0, 0.0)
            return self.sm.transition_to(NavigationState.PAUSED, "Task paused by user")
        return False

    def resume_navigation(self) -> bool:
        """Resume paused motion."""
        if self.sm.current_state in (NavigationState.PAUSED, NavigationState.BLOCKED):
            return self.sm.transition_to(NavigationState.NAVIGATING, "Task resumed by user")
        return False

    def stop_navigation(self, reason: str = "Stopped by user") -> bool:
        """Gracefully halt navigation and return to IDLE."""
        self.robot.send_twist(0.0, 0.0)
        self.active_goal = None
        return self.sm.transition_to(NavigationState.IDLE, reason)

    def step(self, vision_result: VisionFrameResult) -> Tuple[float, float, str]:
        """Executes one control iteration based on latest vision observations.
        
        Returns:
            Tuple of (commanded_v, commanded_omega, status_summary)
        """
        # Register camera heartbeat with safety supervisor
        if vision_result.status == "ok":
            self.safety.register_camera_heartbeat()

        current_state = self.sm.current_state

        # If not actively navigating, ensure motors remain halted
        if current_state != NavigationState.NAVIGATING:
            self.robot.send_twist(0.0, 0.0)
            return 0.0, 0.0, f"Holding {current_state.value}"

        if not self.active_goal:
            self.stop_navigation("No active goal")
            return 0.0, 0.0, "No active goal"

        # Check for forward obstacles
        if vision_result.obstacle_detected:
            safe_v, safe_omega, _ = self.safety.filter_velocity(0.0, 0.0, is_blocked=True)
            self.robot.send_twist(safe_v, safe_omega)
            return safe_v, safe_omega, "BLOCKED by obstacle"

        # Plan motion according to intent
        v_req, omega_req, action_desc = self._compute_motion(vision_result)

        # Pass requested velocities through safety supervisor
        safe_v, safe_omega, safety_event = self.safety.filter_velocity(
            requested_v=v_req,
            requested_omega=omega_req,
            is_blocked=False,
            tof_distance_m=vision_result.closest_obstacle_distance_m
        )

        if safety_event and self.sm.current_state != NavigationState.GOAL_REACHED:
            action_desc = f"Safety Override: {safety_event}"

        # Send movement commands through supported Duckietown control interface
        self.robot.send_twist(safe_v, safe_omega)

        return safe_v, safe_omega, action_desc

    def _compute_motion(self, vision: VisionFrameResult) -> Tuple[float, float, str]:
        """Calculates trajectory based on intent, detected objects, and road lanes."""
        intent = self.active_goal.intent

        # 1. STOP intent
        if intent == NavigationIntent.STOP:
            self.sm.transition_to(NavigationState.GOAL_REACHED, "Stop command executed")
            return 0.0, 0.0, "Goal reached: Robot halted"

        # 2. FOLLOW_LANE or EXPLORE
        if intent in (NavigationIntent.FOLLOW_LANE, NavigationIntent.EXPLORE):
            return self._compute_lane_following(vision)

        # 3. NAVIGATE_TO_LANDMARK or SEARCH_FOR_OBJECT
        target_indicator = (self.active_goal.visual_indicator or "").lower()
        matched_detection: Optional[DetectedObject] = None

        for det in vision.detections:
            det_label = det.label.lower()
            if target_indicator in det_label or det_label in target_indicator:
                matched_detection = det
                break

        if matched_detection:
            # Target acquired visually!
            cx_offset = matched_detection.lateral_offset
            box_h = matched_detection.bbox.height
            dist = matched_detection.estimated_distance_m

            # Check goal arrival condition
            # Goal reached if target occupies > 25% frame height and is centered, or distance <= 0.28m
            is_close = (box_h >= self.goal_bbox_ratio) or (dist is not None and dist <= 0.28)
            if is_close and abs(cx_offset) < 0.40:
                logger.info(f"Target '{matched_detection.label}' reached! (h={box_h:.2f}, dist={dist})")
                self.sm.transition_to(NavigationState.GOAL_REACHED, f"Arrived at {self.active_goal.target}")
                return 0.0, 0.0, f"Goal reached: At {self.active_goal.target}"

            # Visual servoing toward target
            # Steer toward center of target: negative offset means target is left -> turn left (positive omega)
            steering = -cx_offset * self.turn_speed * 1.5
            forward_speed = self.cruise_v * (0.8 if abs(cx_offset) > 0.3 else 1.0)
            return forward_speed, float(np.clip(steering, -1.8, 1.8)), f"Tracking target '{matched_detection.label}'"

        else:
            # Target not yet visible: follow road lanes while searching
            if vision.lane.detected:
                v, omega, _ = self._compute_lane_following(vision)
                return v, omega, f"Following lane while searching for '{self.active_goal.target}'"
            else:
                # If neither lane nor target is found, gently search/scan
                self._search_spin_counter += 1
                spin_omega = 0.5 if (self._search_spin_counter // 25) % 2 == 0 else -0.5
                return 0.04, spin_omega, f"Searching for '{self.active_goal.target}'"

    def _compute_lane_following(self, vision: VisionFrameResult) -> Tuple[float, float, str]:
        """Standard Duckietown proportional lane following."""
        if vision.lane.detected:
            # Proportional steering from lane center offset
            # In our lane detector: positive offset means robot is shifted right -> steer left (+omega)
            offset = vision.lane.center_offset_normalized
            omega = offset * self.kp_lane * 2.0
            omega_clamped = float(np.clip(omega, -1.5, 1.5))
            return self.cruise_v, omega_clamped, f"Lane centering (offset={offset:.2f})"
        else:
            # Lane markings temporarily lost; crawl forward cautiously
            return self.cruise_v * 0.5, 0.0, "Caution: Lane markers not visible"
