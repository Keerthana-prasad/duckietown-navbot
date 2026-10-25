"""Central System Manager: Coordinates Robot Interface, Vision Pipeline, LLM, and Navigation."""

import time
import uuid
import logging
import threading
from typing import Dict, Any, Optional, List, Generator
import yaml

from robot_interface import create_robot_interface, BaseRobotInterface, RobotTelemetry
from computer_vision import VisionPipeline, VisionFrameResult
from llm import IntentParser, InterpretedGoal, NavigationIntent
from navigation import NavigationStateMachine, NavigationState, SafetySupervisor, NavigationPlanner
from backend.schemas.api_models import TaskResponse, TaskStatus, LogMessage

logger = logging.getLogger(__name__)


class SystemManager:
    """Singleton service managing the entire Duckiebot AI Navigation lifecycle."""

    _instance: Optional["SystemManager"] = None

    @classmethod
    def get_instance(cls, config_path: str = "config/config.yaml") -> "SystemManager":
        if cls._instance is None:
            cls._instance = SystemManager(config_path)
        return cls._instance

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config = self._load_config(config_path)

        # In-memory logging ring buffer
        self._logs: List[LogMessage] = []
        self._log_lock = threading.Lock()
        self.log_info("Initializing Duckiebot AI Navigation System...")

        # 1. Initialize Robot Hardware / Simulation Interface
        self.robot: BaseRobotInterface = create_robot_interface(self.config)

        # 2. Initialize Computer Vision Pipeline
        self.vision = VisionPipeline(self.config)

        # 3. Initialize LLM Intent Parser
        self.intent_parser = IntentParser(self.config)

        # 4. Initialize State Machine, Safety Supervisor, and Navigation Planner
        self.state_machine = NavigationStateMachine(NavigationState.IDLE)
        self.safety = SafetySupervisor(self.config, self.state_machine)
        self.planner = NavigationPlanner(
            config=self.config,
            robot_interface=self.robot,
            state_machine=self.state_machine,
            safety_supervisor=self.safety
        )

        # Runtime state caching
        self.latest_frame = None
        self.latest_vision_result: VisionFrameResult = VisionFrameResult()
        self.latest_annotated_jpeg: bytes = b""
        self.active_task: Optional[TaskResponse] = None
        self.tasks_history: Dict[str, TaskResponse] = {}

        # Background processing loop
        self._stop_event = threading.Event()
        self._loop_thread = threading.Thread(target=self._navigation_loop, daemon=True)
        self._loop_thread.start()

        self.log_info(
            f"Duckiebot System initialized in [{self.config.get('system', {}).get('mode', 'simulation').upper()}] mode."
        )

    def _load_config(self, path: str) -> Dict[str, Any]:
        """Load YAML configuration with fallback defaults."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Could not load config file at '{path}': {e}. Using empty defaults.")
            return {}

    def log_info(self, message: str, source: str = "system"):
        self._add_log("INFO", message, source)

    def log_warning(self, message: str, source: str = "system"):
        self._add_log("WARNING", message, source)

    def log_error(self, message: str, source: str = "system"):
        self._add_log("ERROR", message, source)

    def _add_log(self, level: str, message: str, source: str):
        with self._log_lock:
            entry = LogMessage(
                timestamp=time.time(),
                level=level,
                source=source,
                message=message
            )
            self._logs.append(entry)
            if len(self._logs) > 200:
                self._logs.pop(0)

    def get_recent_logs(self, limit: int = 50) -> List[LogMessage]:
        with self._log_lock:
            return list(self._logs[-limit:])

    def create_task(self, prompt_text: str) -> TaskResponse:
        """Process natural language request via LLM and prepare navigation goal."""
        task_id = f"task_{str(uuid.uuid4())[:8]}"
        self.log_info(f"Received user task [{task_id}]: '{prompt_text}'", source="llm")

        # LLM Interpretation
        interpreted_goal: InterpretedGoal = self.intent_parser.parse(prompt_text)

        # Check for ambiguity or unsupported intent
        if interpreted_goal.requires_clarification or interpreted_goal.intent == NavigationIntent.UNSUPPORTED:
            status = TaskStatus.FAILED
            message = interpreted_goal.clarification_message or "Clarification required."
            self.log_warning(f"Task [{task_id}] rejected/unclear: {message}", source="llm")
        else:
            status = TaskStatus.PENDING
            message = f"Goal interpreted successfully for '{interpreted_goal.target}'."
            # Set goal into planner (transitions to PLANNING)
            self.planner.set_goal(interpreted_goal, task_id)
            self.log_info(f"Task [{task_id}] planned. Ready to start.", source="planner")

        task_response = TaskResponse(
            task_id=task_id,
            status=status,
            raw_query=prompt_text,
            interpreted_goal=interpreted_goal,
            navigation_state=self.state_machine.current_state,
            created_at=time.time(),
            message=message
        )

        self.active_task = task_response
        self.tasks_history[task_id] = task_response
        return task_response

    def start_active_task(self, task_id: Optional[str] = None) -> bool:
        """Confirm and begin active navigation task."""
        if not self.active_task:
            return False
        success = self.planner.start_navigation()
        if success:
            self.active_task.status = TaskStatus.IN_PROGRESS
            self.active_task.navigation_state = self.state_machine.current_state
            self.log_info(f"Navigation started for task [{self.active_task.task_id}].", source="navigation")
        return success

    def pause_active_task(self) -> bool:
        if not self.active_task:
            return False
        success = self.planner.pause_navigation()
        if success:
            self.active_task.status = TaskStatus.PAUSED
            self.active_task.navigation_state = self.state_machine.current_state
            self.log_info("Navigation paused.", source="navigation")
        return success

    def resume_active_task(self) -> bool:
        if not self.active_task:
            return False
        success = self.planner.resume_navigation()
        if success:
            self.active_task.status = TaskStatus.IN_PROGRESS
            self.active_task.navigation_state = self.state_machine.current_state
            self.log_info("Navigation resumed.", source="navigation")
        return success

    def stop_active_task(self, reason: str = "Stopped by user") -> bool:
        if self.active_task:
            self.active_task.status = TaskStatus.STOPPED
        success = self.planner.stop_navigation(reason)
        self.log_info(f"Navigation stopped: {reason}", source="navigation")
        return success

    def emergency_stop(self) -> None:
        """Trigger instant hardware and software emergency stop."""
        self.state_machine.transition_to(NavigationState.EMERGENCY_STOP, "User hit EMERGENCY STOP")
        self.robot.emergency_stop()
        if self.active_task:
            self.active_task.status = TaskStatus.STOPPED
        self.log_error("EMERGENCY STOP TRIGGERED. All motor movement halted.", source="safety")

    def clear_emergency_stop(self) -> None:
        """Reset emergency stop and return to IDLE."""
        if hasattr(self.robot, "clear_emergency_stop"):
            self.robot.clear_emergency_stop()
        self.state_machine.transition_to(NavigationState.IDLE, "Emergency stop reset by user")
        self.log_info("Emergency stop cleared. System is now IDLE.", source="safety")

    def get_telemetry(self) -> RobotTelemetry:
        return self.robot.get_telemetry()

    def get_latest_vision_result(self) -> VisionFrameResult:
        return self.latest_vision_result

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield multipart JPEG byte chunks for web streaming."""
        while not self._stop_event.is_set():
            if self.latest_annotated_jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + self.latest_annotated_jpeg + b"\r\n"
                )
            time.sleep(0.066)  # ~15 FPS

    def shutdown(self):
        """Clean shutdown of background threads and robot connection."""
        self._stop_event.set()
        self.robot.disconnect()
        self.log_info("Duckiebot System Manager shut down gracefully.")

    def _navigation_loop(self):
        """Periodic background navigation control loop (~15 Hz)."""
        target_period = 0.066  # ~15 fps
        while not self._stop_event.is_set():
            loop_start = time.time()
            try:
                # 1. Fetch camera frame from interface
                frame = self.robot.get_latest_frame()
                self.latest_frame = frame

                # 2. Get sensor reading (e.g. ToF range)
                telemetry = self.robot.get_telemetry()
                tof_dist = telemetry.tof_distance_m

                # 3. Target filter for CV detector if goal is active
                target_hint = None
                if self.planner.active_goal:
                    target_hint = self.planner.active_goal.visual_indicator or self.planner.active_goal.target

                # 4. Run Computer Vision Pipeline
                vision_res = self.vision.process(
                    frame=frame,
                    target_filter=target_hint,
                    tof_distance_m=tof_dist
                )
                self.latest_vision_result = vision_res

                # 5. Run Navigation Planner step
                v, omega, status_desc = self.planner.step(vision_res)

                # Check if goal was just reached
                if self.state_machine.current_state == NavigationState.GOAL_REACHED:
                    if self.active_task and self.active_task.status == TaskStatus.IN_PROGRESS:
                        self.active_task.status = TaskStatus.COMPLETED
                        self.active_task.navigation_state = NavigationState.GOAL_REACHED
                        self.log_info(f"Task [{self.active_task.task_id}] successfully completed!", source="planner")

                # 6. Render annotated frame for Web Dashboard
                goal_disp = self.planner.active_goal.target if self.planner.active_goal else None
                sys_mode = self.config.get("system", {}).get("mode", "simulation").upper()
                annotated_bytes = self.vision.render_annotated_jpeg(
                    frame=frame,
                    vision_result=vision_res,
                    state_text=self.state_machine.current_state.value,
                    goal_text=goal_disp,
                    mode=sys_mode
                )
                self.latest_annotated_jpeg = annotated_bytes

            except Exception as e:
                logger.error(f"Error in navigation control loop: {e}", exc_info=True)
                self.log_error(f"Control loop error: {str(e)}", source="system")

            elapsed = time.time() - loop_start
            sleep_time = max(0.005, target_period - elapsed)
            time.sleep(sleep_time)
