"""Safety Supervisor: Enforces speed limits, obstacle interlocks, and sensor watchdogs."""

import time
import logging
from typing import Dict, Any, Tuple, Optional
import numpy as np

from navigation.state_machine import NavigationState, NavigationStateMachine

logger = logging.getLogger(__name__)


class SafetySupervisor:
    """Supervises robot motion and sensor health to guarantee physical safety."""

    def __init__(self, config: Dict[str, Any], state_machine: NavigationStateMachine):
        self.config = config
        self.nav_cfg = config.get("navigation", {})
        self.safety_cfg = config.get("safety", {})
        self.state_machine = state_machine

        # Limits
        self.max_v = float(self.nav_cfg.get("max_linear_velocity", 0.22))
        self.max_omega = float(self.nav_cfg.get("max_angular_velocity", 2.2))
        self.camera_timeout_s = float(self.safety_cfg.get("camera_timeout_seconds", 2.0))
        self.auto_stop_on_camera_loss = bool(self.safety_cfg.get("auto_stop_on_camera_loss", True))
        self.max_run_time_s = float(self.safety_cfg.get("max_continuous_run_time_s", 180.0))

        # Watchdogs
        self._last_camera_frame_time = time.time()
        self._nav_start_time = 0.0

    def register_camera_heartbeat(self):
        """Called whenever a valid camera frame is received."""
        self._last_camera_frame_time = time.time()

    def filter_velocity(
        self,
        requested_v: float,
        requested_omega: float,
        is_blocked: bool = False,
        tof_distance_m: Optional[float] = None
    ) -> Tuple[float, float, Optional[str]]:
        """Validates and clamps requested velocities through safety rules.
        
        Returns:
            Tuple of (safe_linear_v, safe_angular_omega, safety_event_reason)
        """
        current_state = self.state_machine.current_state

        # 1. State check: Motion is only permitted in NAVIGATING state
        if current_state not in (NavigationState.NAVIGATING,):
            return 0.0, 0.0, f"Movement inhibited in state {current_state.value}"

        # 2. Obstacle check: If forward path is blocked, halt immediately
        if is_blocked:
            self.state_machine.transition_to(NavigationState.BLOCKED, "Obstacle in driving corridor")
            return 0.0, 0.0, "Obstacle collision prevention triggered"

        # 3. Sensor loss check: Has camera disconnected?
        if self.auto_stop_on_camera_loss:
            stale_s = time.time() - self._last_camera_frame_time
            if stale_s > self.camera_timeout_s:
                self.state_machine.transition_to(NavigationState.ERROR, f"Camera frame timeout ({stale_s:.1f}s)")
                return 0.0, 0.0, "Camera stream stale or disconnected"

        # 4. Maximum run time watchdog (prevent battery drain)
        if self.state_machine.current_state == NavigationState.NAVIGATING:
            if self.state_machine.state_duration > self.max_run_time_s:
                self.state_machine.transition_to(NavigationState.IDLE, "Max continuous navigation time reached")
                return 0.0, 0.0, "Auto-idle timeout exceeded"

        # 5. Enforce strict physical velocity clamping
        safe_v = float(np.clip(requested_v, -self.max_v, self.max_v))
        safe_omega = float(np.clip(requested_omega, -self.max_omega, self.max_omega))

        return safe_v, safe_omega, None
