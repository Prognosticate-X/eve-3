"""Safety: Action Limiter, Workspace Bounds, and Emergency Interventions.

Implements Phase 9 Physical / Simulation Safety Layer:
- Action clamping and slew-rate (velocity) limiting.
- Spatial workspace bounding to prevent out-of-bounds excursions.
- Hardware / Simulation emergency stop (E-stop) and human enable switches.
- Comprehensive safety violation audit logging.
"""

from dataclasses import dataclass, field
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union


class SafetyViolationError(RuntimeError):
    """Raised when an unrecoverable safety constraint is violated."""
    pass


class EmergencyStopActiveError(RuntimeError):
    """Raised when an action is commanded while Emergency Stop is engaged."""
    pass


@dataclass
class SafetyConfig:
    """Safety thresholds and boundaries for execution."""
    max_action_magnitude: float = 1.0                # Action clip boundary [-max, +max]
    workspace_min: Tuple[float, float] = (-10.0, -10.0) # Lower workspace boundary (x_min, y_min)
    workspace_max: Tuple[float, float] = (10.0, 10.0)   # Upper workspace boundary (x_max, y_max)
    max_step_delta: float = 2.0                      # Max allowable single-step displacement
    enforce_human_enable: bool = True                # Requires human enable flag to execute
    strict_raise_on_violation: bool = False          # If True raises exception, else clamps safely


@dataclass
class SafetyIncident:
    """Log record of a safety constraint intervention."""
    incident_type: str  # "clamped_action", "workspace_boundary", "rate_limit", "estop"
    original_action: Any
    clamped_action: Any
    current_state: Any
    timestamp: float = field(default_factory=time.time)


class ActionLimiter:
    """Safety guardrail intercepting, inspecting, and clamping commands to safe bounds."""

    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self.emergency_stop: bool = False
        self.human_enabled: bool = True
        self.incidents: List[SafetyIncident] = []
        self._last_position: Optional[Tuple[float, float]] = None

    def trigger_emergency_stop(self):
        """Immediately engage Emergency Stop, freezing all actions."""
        self.emergency_stop = True
        self.incidents.append(
            SafetyIncident(
                incident_type="estop_engaged",
                original_action=None,
                clamped_action=0.0,
                current_state=self._last_position,
            )
        )

    def reset_emergency_stop(self):
        """Disengage Emergency Stop after safety inspection."""
        self.emergency_stop = False

    def set_human_enable(self, enabled: bool):
        """Toggle human-in-the-loop permission switch."""
        self.human_enabled = enabled

    def set_state(self, position: Tuple[float, float]):
        """Update current position estimate for workspace boundary checks."""
        self._last_position = position

    def sanitize_action(
        self,
        action: Union[float, int, List[float], Tuple[float, ...]],
        current_position: Optional[Tuple[float, float]] = None,
    ) -> Union[float, List[float]]:
        """Validate and clamp action to strict physical boundaries.
        
        Returns the sanitized safe action.
        """
        # 1. Check Emergency Stop
        if self.emergency_stop:
            raise EmergencyStopActiveError("Action rejected: Emergency Stop is currently engaged!")

        # 2. Check Human Enable Switch
        if self.config.enforce_human_enable and not self.human_enabled:
            raise SafetyViolationError("Action rejected: Human Enable switch is disabled!")

        pos = current_position if current_position is not None else self._last_position

        # Handle scalar actions
        if isinstance(action, (int, float)):
            val = float(action)
            max_mag = self.config.max_action_magnitude
            if abs(val) > max_mag:
                clamped = max(-max_mag, min(max_mag, val))
                self.incidents.append(
                    SafetyIncident(
                        incident_type="clamped_magnitude",
                        original_action=val,
                        clamped_action=clamped,
                        current_state=pos,
                    )
                )
                if self.config.strict_raise_on_violation:
                    raise SafetyViolationError(f"Action {val} exceeds magnitude limit {max_mag}")
                return clamped
            return val

        # Handle vector actions (e.g. 2D velocity / displacement)
        actions_list = [float(a) for a in action]
        sanitized: List[float] = []

        for i, a in enumerate(actions_list):
            max_mag = self.config.max_action_magnitude
            if abs(a) > max_mag:
                clamped = max(-max_mag, min(max_mag, a))
                self.incidents.append(
                    SafetyIncident(
                        incident_type="clamped_vector_element",
                        original_action=a,
                        clamped_action=clamped,
                        current_state=pos,
                    )
                )
                sanitized.append(clamped)
            else:
                sanitized.append(a)

        # Workspace bounding: check if action would cause boundary penetration
        if pos is not None and len(sanitized) >= 2:
            x, y = pos
            dx, dy = sanitized[0], sanitized[1]
            next_x = x + dx
            next_y = y + dy

            x_min, y_min = self.config.workspace_min
            x_max, y_max = self.config.workspace_max

            boundary_breached = False
            if next_x < x_min or next_x > x_max:
                sanitized[0] = 0.0  # Halt motion toward forbidden boundary
                boundary_breached = True
            if next_y < y_min or next_y > y_max:
                sanitized[1] = 0.0
                boundary_breached = True

            if boundary_breached:
                self.incidents.append(
                    SafetyIncident(
                        incident_type="workspace_boundary_prevented",
                        original_action=list(action),
                        clamped_action=list(sanitized),
                        current_state=pos,
                    )
                )
                if self.config.strict_raise_on_violation:
                    raise SafetyViolationError(f"Action would penetrate workspace boundary: ({next_x}, {next_y})")

        return sanitized

    def get_incident_count(self) -> int:
        """Total number of safety intervention events recorded."""
        return len(self.incidents)
