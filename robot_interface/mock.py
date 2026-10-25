"""Mock Robot Interface: High-fidelity simulation for development and testing."""

import time
import math
import logging
from typing import Optional, Dict, Any
import numpy as np

from robot_interface.base import BaseRobotInterface, RobotTelemetry

logger = logging.getLogger(__name__)


class MockRobotInterface(BaseRobotInterface):
    """Simulates Duckiebot DB21J behavior, camera feed, and sensor telemetry."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.robot_cfg = config.get("robot", {})
        self.hostname = self.robot_cfg.get("hostname", "entebot209.local")
        
        # State tracking
        self._connected = True
        self._linear_v = 0.0
        self._angular_omega = 0.0
        self._battery_pct = 95
        self._battery_voltage = 12.4
        self._left_ticks = 100
        self._right_ticks = 100
        self._tof_distance_m = 1.20
        self._emergency_stop = False
        self._frame_counter = 0
        self._last_cmd_time = time.time()
        self._sim_x = 0.0
        self._sim_theta = 0.0

        # Cached synthetic frame
        self._current_frame: Optional[np.ndarray] = None
        self._generate_synthetic_frame()

    def connect(self) -> bool:
        logger.info(f"[MOCK] Connected to simulated Duckiebot ({self.hostname}).")
        self._connected = True
        return True

    def disconnect(self) -> None:
        logger.info("[MOCK] Disconnecting simulated Duckiebot.")
        self.emergency_stop()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Returns synthetically rendered Duckietown road scene."""
        self._frame_counter += 1
        self._generate_synthetic_frame()
        return self._current_frame

    def get_telemetry(self) -> RobotTelemetry:
        """Returns simulated telemetry with encoder ticks, voltage, and ToF."""
        # Simulated slow battery decay
        if self._frame_counter % 200 == 0 and self._battery_pct > 15:
            self._battery_pct -= 1
            self._battery_voltage = 11.0 + (self._battery_pct / 100.0) * 1.4

        return RobotTelemetry(
            timestamp=time.time(),
            connected=self._connected,
            mode="simulation",
            hostname=self.hostname,
            battery_voltage=round(self._battery_voltage, 2),
            battery_percentage=self._battery_pct,
            camera_fps=15.0,
            camera_connected=True,
            tof_distance_m=round(self._tof_distance_m, 2),
            tof_sensor_connected=True,
            linear_velocity=round(self._linear_v, 3),
            angular_velocity=round(self._angular_omega, 3),
            left_wheel_ticks=self._left_ticks,
            right_wheel_ticks=self._right_ticks,
            last_command_time=self._last_cmd_time,
            emergency_stopped=self._emergency_stop,
            diagnostics={
                "motor_driver": "OK (Simulated)",
                "camera_node": "OK (640x480 @ 15fps)",
                "jetson_temperature_c": 41.5,
                "ram_usage_mb": "1280 / 3956 MB",
                "ros_master": "ros1_noetic (Mock Core)",
            }
        )

    def send_twist(self, linear_v: float, angular_omega: float) -> bool:
        """Simulates wheel response and encoder updates."""
        if self._emergency_stop:
            logger.warning("[MOCK] Movement command rejected: Emergency Stop is active.")
            return False

        self._linear_v = linear_v
        self._angular_omega = angular_omega
        self._last_cmd_time = time.time()

        # Update simulated encoders and odometry
        dt = 0.1
        self._sim_theta += angular_omega * dt
        self._sim_x += linear_v * math.cos(self._sim_theta) * dt
        
        # Approximate wheel ticks (DB21J has ~135 ticks/revolution)
        ticks_delta = int(linear_v * 150 * dt)
        turn_delta = int(angular_omega * 30 * dt)
        self._left_ticks += max(0, ticks_delta - turn_delta)
        self._right_ticks += max(0, ticks_delta + turn_delta)

        # Simulate ToF range response based on motion
        if abs(linear_v) > 0.01:
            self._tof_distance_m = max(0.20, 1.20 - (abs(self._sim_x) % 1.0))
        return True

    def emergency_stop(self) -> None:
        """Halts simulation immediately."""
        self._linear_v = 0.0
        self._angular_omega = 0.0
        self._emergency_stop = True
        logger.info("[MOCK] Emergency stop engaged. Velocities set to 0.0.")

    def clear_emergency_stop(self) -> None:
        self._emergency_stop = False
        logger.info("[MOCK] Emergency stop cleared.")

    def _generate_synthetic_frame(self, width: int = 640, height: int = 480) -> None:
        """Generate a realistic synthetic image of a Duckietown road scene."""
        # Dark road asphalt background
        frame = np.full((height, width, 3), 45, dtype=np.uint8)

        # Simulated road horizon and perspective
        horizon = int(height * 0.40)
        # Off-road area above horizon (light gray lab floor)
        frame[0:horizon, :] = 160

        # Yellow dashed center line (Duckietown center marking)
        # Yellow in BGR is (0, 215, 255)
        center_x = int(width * 0.40 + 20 * math.sin(self._frame_counter * 0.05))
        for y in range(horizon, height, 40):
            y_end = min(height, y + 25)
            # Perspective width increases toward bottom
            w_line = int(4 + 8 * (y - horizon) / (height - horizon))
            x_line = int(center_x + (y - horizon) * 0.2)
            frame[y:y_end, max(0, x_line - w_line):min(width, x_line + w_line)] = [0, 215, 255]

        # White solid right lane line (Duckietown right boundary)
        # White in BGR is (255, 255, 255)
        right_x = int(width * 0.75)
        for y in range(horizon, height, 2):
            w_line = int(5 + 10 * (y - horizon) / (height - horizon))
            x_line = int(right_x + (y - horizon) * 0.35)
            frame[y:y+2, max(0, x_line - w_line):min(width, x_line + w_line)] = [255, 255, 255]

        # White solid left curb line
        left_x = int(width * 0.15)
        for y in range(horizon, height, 2):
            w_line = int(5 + 10 * (y - horizon) / (height - horizon))
            x_line = int(left_x - (y - horizon) * 0.3)
            frame[y:y+2, max(0, x_line - w_line):min(width, x_line + w_line)] = [255, 255, 255]

        # Occasionally draw a synthetic target landmark (e.g. blue bottle or yellow duckie)
        obj_x = int(width * 0.52 + 15 * math.cos(self._frame_counter * 0.08))
        obj_y = int(height * 0.50)
        obj_size = 28
        # Blue bottle in BGR: (220, 50, 30)
        frame[obj_y:obj_y+obj_size, obj_x:obj_x+obj_size//2] = [220, 50, 30]

        self._current_frame = frame
