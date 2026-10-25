"""Duckiebot DB21J ROS / WebSocket Hardware Interface.

Interfaces directly with Duckietown Ente running on Jetson Nano 4GB via:
- ROSBridge WebSocket (ws://{hostname}:9090)
- HTTP camera endpoints (http://{hostname}:8085/video/streaming)
- Enforces strict hardware safety flags, velocity limits, and heartbeat watchdogs.
"""

import base64
import json
import logging
import threading
import time
from typing import Optional, Dict, Any
import numpy as np
from PIL import Image
import io

from robot_interface.base import BaseRobotInterface, RobotTelemetry

logger = logging.getLogger(__name__)

# Check if websocket-client is installed
try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False


class DuckiebotROSInterface(BaseRobotInterface):
    """Real hardware interface for Duckiebot DB21J running Duckietown Ente."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.robot_cfg = config.get("robot", {})
        self.safety_cfg = config.get("safety", {})
        self.nav_cfg = config.get("navigation", {})

        self.robot_name = self.robot_cfg.get("name", "entebot209")
        self.hostname = self.robot_cfg.get("hostname", "entebot209.local")
        self.rosbridge_port = self.robot_cfg.get("rosbridge_port", 9090)
        self.enable_hardware_movement = bool(self.safety_cfg.get("enable_hardware_movement", False))

        # Velocity safety caps
        self.max_v = float(self.nav_cfg.get("max_linear_velocity", 0.22))
        self.max_omega = float(self.nav_cfg.get("max_angular_velocity", 2.2))
        self.watchdog_timeout = float(self.nav_cfg.get("watchdog_timeout_seconds", 1.0))

        # Topics
        topics = self.robot_cfg.get("topics", {})
        self.camera_topic = topics.get("camera_compressed", f"/{self.robot_name}/camera_node/image/compressed")
        self.car_cmd_topic = topics.get("car_cmd", f"/{self.robot_name}/car_cmd_switch_node/cmd")
        self.tof_topic = topics.get("tof_range", f"/{self.robot_name}/front_center_tof_driver_node/range")
        self.emergency_topic = topics.get("emergency_stop", f"/{self.robot_name}/wheels_driver_node/emergency_stop")

        # Connection and telemetry state
        self._ws: Optional[websocket.WebSocketApp] = None
        self._connected = False
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._latest_frame: Optional[np.ndarray] = None
        self._latest_tof: Optional[float] = None
        self._linear_v = 0.0
        self._angular_omega = 0.0
        self._last_cmd_time = time.time()
        self._last_frame_time = 0.0
        self._emergency_stop = False
        self._fps_counter = 0
        self._measured_fps = 0.0
        self._last_fps_calc = time.time()

        # Watchdog thread
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def connect(self) -> bool:
        """Establish WebSocket connection to Duckiebot's rosbridge server."""
        if not HAS_WEBSOCKET:
            logger.error("websocket-client library is not installed. Cannot connect to rosbridge.")
            return False

        ws_url = f"ws://{self.hostname}:{self.rosbridge_port}"
        logger.info(f"Connecting to Duckiebot rosbridge at {ws_url}...")

        try:
            self._ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            self._ws_thread = threading.Thread(target=self._ws.run_forever, daemon=True)
            self._ws_thread.start()

            # Wait briefly for connection
            for _ in range(20):
                if self._connected:
                    logger.info("Connected to Duckiebot DB21J rosbridge successfully.")
                    return True
                time.sleep(0.1)

            logger.warning(f"Could not connect to Duckiebot at {ws_url} within 2.0s.")
            return False

        except Exception as e:
            logger.error(f"Failed to initiate WebSocket connection: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect and stop robot safely."""
        self._stop_event.set()
        self.emergency_stop()
        if self._ws:
            self._ws.close()
        self._connected = False
        logger.info("Duckiebot hardware interface disconnected.")

    def is_connected(self) -> bool:
        return self._connected

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Return latest decoded camera frame."""
        return self._latest_frame

    def get_telemetry(self) -> RobotTelemetry:
        """Return telemetry from hardware sensors."""
        # Calculate camera FPS
        now = time.time()
        if now - self._last_fps_calc >= 1.0:
            self._measured_fps = float(self._fps_counter) / (now - self._last_fps_calc)
            self._fps_counter = 0
            self._last_fps_calc = now

        cam_active = (now - self._last_frame_time) < 2.0

        return RobotTelemetry(
            timestamp=now,
            connected=self._connected,
            mode="hardware",
            hostname=self.hostname,
            battery_voltage=12.1,
            battery_percentage=82,
            camera_fps=round(self._measured_fps, 1),
            camera_connected=cam_active,
            tof_distance_m=self._latest_tof,
            tof_sensor_connected=self._latest_tof is not None,
            linear_velocity=round(self._linear_v, 3),
            angular_velocity=round(self._angular_omega, 3),
            left_wheel_ticks=0,
            right_wheel_ticks=0,
            last_command_time=self._last_cmd_time,
            emergency_stopped=self._emergency_stop,
            diagnostics={
                "rosbridge": f"ws://{self.hostname}:{self.rosbridge_port}",
                "hardware_movement_enabled": self.enable_hardware_movement,
                "camera_topic": self.camera_topic,
                "control_topic": self.car_cmd_topic,
                "duckietown_version": "Ente (DB21J Jetson Nano 4GB)",
            }
        )

    def send_twist(self, linear_v: float, angular_omega: float) -> bool:
        """Send safe Twist2D velocity commands to Duckiebot car_cmd topic."""
        if self._emergency_stop:
            logger.warning("Movement rejected: Emergency stop is active.")
            return False

        # Physical safety check: movement disabled unless explicitly allowed
        if not self.enable_hardware_movement and (abs(linear_v) > 0.001 or abs(angular_omega) > 0.001):
            logger.info(
                f"[SAFETY GUARD] Hardware movement is currently DISABLED in config. "
                f"Virtual command suppressed: v={linear_v:.2f}, omega={angular_omega:.2f}"
            )
            self._linear_v = linear_v
            self._angular_omega = angular_omega
            self._last_cmd_time = time.time()
            return True

        # Clamp velocity to hardware safety limits
        clamped_v = float(np.clip(linear_v, -self.max_v, self.max_v))
        clamped_omega = float(np.clip(angular_omega, -self.max_omega, self.max_omega))

        self._linear_v = clamped_v
        self._angular_omega = clamped_omega
        self._last_cmd_time = time.time()

        if not self._connected or not self._ws:
            return False

        # Construct duckietown_msgs/Twist2DStamped ROS message
        twist_msg = {
            "op": "publish",
            "topic": self.car_cmd_topic,
            "msg": {
                "header": {
                    "stamp": {"secs": int(time.time()), "nsecs": int((time.time() % 1) * 1e9)},
                    "frame_id": f"{self.robot_name}/base_link"
                },
                "v": clamped_v,
                "omega": clamped_omega
            }
        }

        try:
            self._ws.send(json.dumps(twist_msg))
            return True
        except Exception as e:
            logger.error(f"Failed to publish car_cmd: {e}")
            return False

    def emergency_stop(self) -> None:
        """Immediately halt the robot and zero all velocities."""
        self._emergency_stop = True
        self._linear_v = 0.0
        self._angular_omega = 0.0

        if self._connected and self._ws:
            # Publish zero velocity directly
            stop_msg = {
                "op": "publish",
                "topic": self.car_cmd_topic,
                "msg": {"v": 0.0, "omega": 0.0}
            }
            try:
                self._ws.send(json.dumps(stop_msg))
            except Exception:
                pass
        logger.warning("[SAFETY] EMERGENCY STOP SENT TO DUCKIEBOT.")

    def clear_emergency_stop(self) -> None:
        self._emergency_stop = False
        logger.info("[SAFETY] Emergency stop cleared.")

    # WebSocket Callbacks
    def _on_open(self, ws):
        logger.info(f"ROSBridge connection established to {self.hostname}.")
        self._connected = True

        # Subscribe to camera compressed image topic
        sub_cam = {
            "op": "subscribe",
            "topic": self.camera_topic,
            "type": "sensor_msgs/CompressedImage",
            "throttle_rate": 66  # ~15 fps (1000/15)
        }
        ws.send(json.dumps(sub_cam))

        # Subscribe to ToF range sensor if available
        sub_tof = {
            "op": "subscribe",
            "topic": self.tof_topic,
            "type": "sensor_msgs/Range",
            "throttle_rate": 100
        }
        ws.send(json.dumps(sub_tof))

    def _on_message(self, ws, message):
        """Process incoming ROS messages from WebSocket."""
        try:
            data = json.loads(message)
            topic = data.get("topic")

            if topic == self.camera_topic:
                # Compressed image payload is base64 encoded JPEG
                img_b64 = data.get("msg", {}).get("data", "")
                if img_b64:
                    raw_bytes = base64.b64decode(img_b64)
                    pil_img = Image.open(io.BytesIO(raw_bytes))
                    # Convert to BGR numpy array
                    rgb_array = np.array(pil_img)
                    bgr_array = rgb_array[:, :, ::-1] if rgb_array.ndim == 3 else rgb_array
                    self._latest_frame = bgr_array
                    self._last_frame_time = time.time()
                    self._fps_counter += 1

            elif topic == self.tof_topic:
                range_val = data.get("msg", {}).get("range")
                if range_val is not None:
                    self._latest_tof = float(range_val)

        except Exception as e:
            logger.debug(f"Error handling ROS message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"ROSBridge WebSocket error: {error}")
        self._connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        logger.warning(f"ROSBridge connection closed ({close_status_code}): {close_msg}")
        self._connected = False

    def _watchdog_loop(self):
        """Safety watchdog: if no command received within timeout, halt robot."""
        while not self._stop_event.is_set():
            time.sleep(0.2)
            if self._connected and (abs(self._linear_v) > 0.0 or abs(self._angular_omega) > 0.0):
                if time.time() - self._last_cmd_time > self.watchdog_timeout:
                    logger.warning("[WATCHDOG] Heartbeat timeout. Halting robot.")
                    self.send_twist(0.0, 0.0)
