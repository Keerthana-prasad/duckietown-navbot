"""Navigation State Machine.

Implements explicit operating states:
IDLE -> VALIDATING_REQUEST -> PLANNING -> NAVIGATING -> GOAL_REACHED
as well as:
PAUSED, BLOCKED, ERROR, EMERGENCY_STOP.
"""

from enum import Enum
import time
import logging
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NavigationState(str, Enum):
    IDLE = "IDLE"
    VALIDATING_REQUEST = "VALIDATING_REQUEST"
    PLANNING = "PLANNING"
    NAVIGATING = "NAVIGATING"
    GOAL_REACHED = "GOAL_REACHED"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class StateTransitionRecord(BaseModel):
    from_state: NavigationState
    to_state: NavigationState
    timestamp: float = Field(default_factory=time.time)
    reason: str = ""


class NavigationStateMachine:
    """Manages explicit operating states and validates state transitions."""

    # Allowed state transition graph
    VALID_TRANSITIONS: Dict[NavigationState, List[NavigationState]] = {
        NavigationState.IDLE: [
            NavigationState.VALIDATING_REQUEST,
            NavigationState.EMERGENCY_STOP,
            NavigationState.ERROR
        ],
        NavigationState.VALIDATING_REQUEST: [
            NavigationState.PLANNING,
            NavigationState.IDLE,
            NavigationState.ERROR,
            NavigationState.EMERGENCY_STOP
        ],
        NavigationState.PLANNING: [
            NavigationState.NAVIGATING,
            NavigationState.PAUSED,
            NavigationState.BLOCKED,
            NavigationState.ERROR,
            NavigationState.EMERGENCY_STOP,
            NavigationState.IDLE
        ],
        NavigationState.NAVIGATING: [
            NavigationState.GOAL_REACHED,
            NavigationState.PAUSED,
            NavigationState.BLOCKED,
            NavigationState.ERROR,
            NavigationState.EMERGENCY_STOP,
            NavigationState.IDLE
        ],
        NavigationState.PAUSED: [
            NavigationState.NAVIGATING,
            NavigationState.IDLE,
            NavigationState.ERROR,
            NavigationState.EMERGENCY_STOP
        ],
        NavigationState.BLOCKED: [
            NavigationState.NAVIGATING,
            NavigationState.PAUSED,
            NavigationState.IDLE,
            NavigationState.ERROR,
            NavigationState.EMERGENCY_STOP
        ],
        NavigationState.GOAL_REACHED: [
            NavigationState.IDLE,
            NavigationState.VALIDATING_REQUEST,
            NavigationState.EMERGENCY_STOP
        ],
        NavigationState.ERROR: [
            NavigationState.IDLE,
            NavigationState.EMERGENCY_STOP
        ],
        NavigationState.EMERGENCY_STOP: [
            NavigationState.IDLE  # Must explicitly reset to IDLE after clearing E-stop
        ]
    }

    def __init__(self, initial_state: NavigationState = NavigationState.IDLE):
        self._current_state = initial_state
        self._previous_state = initial_state
        self._state_start_time = time.time()
        self._history: List[StateTransitionRecord] = []
        self._last_error_message: Optional[str] = None

    @property
    def current_state(self) -> NavigationState:
        return self._current_state

    @property
    def state_duration(self) -> float:
        return time.time() - self._state_start_time

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error_message

    def transition_to(self, new_state: NavigationState, reason: str = "") -> bool:
        """Attempt to transition to a new state.
        
        Transitions to EMERGENCY_STOP or ERROR are always permitted from any state.
        """
        # Always allow emergency stop or unexpected error
        if new_state in (NavigationState.EMERGENCY_STOP, NavigationState.ERROR):
            return self._apply_transition(new_state, reason)

        allowed = self.VALID_TRANSITIONS.get(self._current_state, [])
        if new_state in allowed:
            return self._apply_transition(new_state, reason)
        else:
            logger.warning(
                f"Invalid state transition rejected: {self._current_state.value} -> {new_state.value} "
                f"(Reason: {reason})"
            )
            return False

    def _apply_transition(self, new_state: NavigationState, reason: str) -> bool:
        record = StateTransitionRecord(
            from_state=self._current_state,
            to_state=new_state,
            timestamp=time.time(),
            reason=reason
        )
        self._history.append(record)
        self._previous_state = self._current_state
        self._current_state = new_state
        self._state_start_time = time.time()

        if new_state == NavigationState.ERROR:
            self._last_error_message = reason

        logger.info(
            f"State changed: {self._previous_state.value} -> {self._current_state.value} "
            f"[{reason if reason else 'No reason given'}]"
        )
        return True

    def get_recent_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return [
            {
                "from": r.from_state.value,
                "to": r.to_state.value,
                "timestamp": r.timestamp,
                "reason": r.reason
            }
            for r in self._history[-limit:]
        ]
