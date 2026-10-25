"""Factory for instantiating the appropriate Robot Interface."""

import logging
from typing import Dict, Any

from robot_interface.base import BaseRobotInterface
from robot_interface.mock import MockRobotInterface
from robot_interface.duckiebot_ros import DuckiebotROSInterface

logger = logging.getLogger(__name__)


def create_robot_interface(config: Dict[str, Any]) -> BaseRobotInterface:
    """Create robot interface based on system mode in configuration."""
    mode = config.get("system", {}).get("mode", "simulation").lower()

    if mode == "hardware":
        logger.info("Initializing physical Duckiebot ROS/WebSocket interface...")
        interface = DuckiebotROSInterface(config)
        # Attempt connection; if hardware unreachable, log warning and allow fallback
        connected = interface.connect()
        if not connected:
            logger.warning(
                "Physical Duckiebot unreachable at configured hostname. "
                "Retaining hardware interface instance (can be reconnected from dashboard)."
            )
        return interface
    else:
        logger.info("Initializing MockRobotInterface for simulation/testing...")
        mock = MockRobotInterface(config)
        mock.connect()
        return mock
