"""Abstract base class and models for Robot Hardware Interface."""

from abc import ABC, abstractmethod
import time
from typing import Optional, Dict, Any
import numpy as np
from pydantic import BaseModel, Field


class RobotTelemetry(BaseModel):
    """Real-time robot telemetry data."""
    timestamp: float = Field(default_factory=time.time)
    connected: bool = Field(default=False)
    mode: str = Field(default="simulation")  # "simulation" or "hardware"
    hostname: str = Field(default="entebot209.local")
    battery_voltage: float = Field(default=12.2)  # DB21J LiPo nominal voltage ~11.1V - 12.6V
    battery_percentage: int = Field(default=88)
    camera_fps: float = Field(default=0.0)
    camera_connected: bool = Field(default=False)
    tof_distance_m: Optional[float] = Field(default=None)
    tof_sensor_connected: bool = Field(default=False)
    linear_velocity: float = Field(default=0.0)   # v in m/s
    angular_velocity: float = Field(default=0.0)  # omega in rad/s
    left_wheel_ticks: int = Field(default=0)
    right_wheel_ticks: int = Field(default=0)
    last_command_time: float = Field(default=0.0)
    emergency_stopped: bool = Field(default=False)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class BaseRobotInterface(ABC):
    """Abstract interface defining required contract for Duckiebot interactions."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection with robot hardware or simulation engine."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Safely disconnect and halt all movement."""
        pass

    @abstractmethod
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Retrieve most recent camera frame as BGR numpy array."""
        pass

    @abstractmethod
    def get_telemetry(self) -> RobotTelemetry:
        """Retrieve latest sensor readings, connectivity status, and diagnostics."""
        pass

    @abstractmethod
    def send_twist(self, linear_v: float, angular_omega: float) -> bool:
        """Send velocity command (linear v in m/s, angular omega in rad/s)."""
        pass

    @abstractmethod
    def emergency_stop(self) -> None:
        """Immediately command zero velocity and engage hardware brake."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connection to robot or simulation is alive."""
        pass
