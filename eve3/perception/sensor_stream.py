"""L4 Redundant Sensor Stream & Cross-Verification Fusion.

Implements Phase 11 L4 Sensor Substrate:
- Streaming real-world time-series sensory observations with Gaussian variance.
- Redundant multi-sensor cross-verification (Primary Sensor vs Redundant Audit Sensor).
- Disparity discrepancy detection for hardware sensor failure, drift, and spoofing protection.
- Automatic gating: triggers diffuse null hypothesis h_empty and ActionLimiter freeze when disparity exceeds tolerance.
"""

from dataclasses import dataclass, field
import math
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SensorReading:
    """Single observation record from a hardware or simulated sensor."""
    sensor_id: str
    modality: str                               # e.g., "odometry", "vision", "proximity", "rangefinder"
    value: Tuple[float, ...]                    # Continuous scalar or vector observation
    variance: float = 0.01                      # Measurement error variance sigma^2
    timestamp: float = field(default_factory=time.time)


@dataclass
class FusedSensorState:
    """State resulting from multi-sensor Bayesian fusion with audit verification."""
    fused_value: Tuple[float, ...]
    fused_variance: float
    disparity: float                            # ||value_primary - value_audit||
    sensor_fault_detected: bool
    is_safe_to_actuate: bool
    details: Dict[str, Any] = field(default_factory=dict)


class RedundantSensorStream:
    """Manages dual-channel sensory streams and enforces cross-verification safety."""

    def __init__(
        self,
        max_disparity_threshold: float = 0.35,
        stale_data_timeout_sec: float = 1.0,
    ):
        self.max_disparity = max_disparity_threshold
        self.stale_timeout = stale_data_timeout_sec
        self.history: List[FusedSensorState] = []

    def fuse_and_verify(
        self,
        primary: SensorReading,
        audit: SensorReading,
        current_time: Optional[float] = None,
    ) -> FusedSensorState:
        """Cross-verify primary and audit readings and produce Bayesian fused estimate.
        
        If disparity exceeds threshold, declares sensor fault and blocks actuation.
        """
        now = current_time if current_time is not None else time.time()

        # 1. Staleness check
        if (now - primary.timestamp > self.stale_timeout) or (now - audit.timestamp > self.stale_timeout):
            state = FusedSensorState(
                fused_value=primary.value,
                fused_variance=1e6,
                disparity=float("inf"),
                sensor_fault_detected=True,
                is_safe_to_actuate=False,
                details={"error": "stale_sensor_reading"},
            )
            self.history.append(state)
            return state

        # 2. Dimension check
        if len(primary.value) != len(audit.value):
            state = FusedSensorState(
                fused_value=primary.value,
                fused_variance=1e6,
                disparity=float("inf"),
                sensor_fault_detected=True,
                is_safe_to_actuate=False,
                details={"error": "mismatched_sensor_dimensions"},
            )
            self.history.append(state)
            return state

        # 3. Compute Euclidean disparity
        dim = len(primary.value)
        sq_dist = sum((primary.value[i] - audit.value[i]) ** 2 for i in range(dim))
        disparity = math.sqrt(sq_dist)

        # 4. Disparity threshold gating
        fault_detected = disparity > self.max_disparity
        is_safe = not fault_detected

        # 5. Bayesian 1D/Multi-D Gaussian fusion
        # Weights inversely proportional to variance
        var1 = max(1e-6, primary.variance)
        var2 = max(1e-6, audit.variance)
        w1 = 1.0 / var1
        w2 = 1.0 / var2
        w_sum = w1 + w2

        fused_val = tuple((w1 * primary.value[i] + w2 * audit.value[i]) / w_sum for i in range(dim))
        fused_var = 1.0 / w_sum

        state = FusedSensorState(
            fused_value=fused_val,
            fused_variance=fused_var,
            disparity=disparity,
            sensor_fault_detected=fault_detected,
            is_safe_to_actuate=is_safe,
            details={
                "primary_id": primary.sensor_id,
                "audit_id": audit.sensor_id,
                "confidence": max(0.01, 1.0 - (disparity / (self.max_disparity * 2.0))),
            },
        )
        self.history.append(state)
        return state

    def get_recent_fault_rate(self, window: int = 20) -> float:
        """Compute fault frequency over recent readings."""
        if not self.history:
            return 0.0
        recent = self.history[-window:]
        faults = sum(1 for s in recent if s.sensor_fault_detected)
        return faults / len(recent)
