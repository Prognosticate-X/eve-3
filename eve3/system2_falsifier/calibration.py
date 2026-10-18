"""Calibration: Expected Calibration Error (ECE) and Adaptive Temperature Controller.

Implements Phase 9 Calibration Substrate:
- Partitioning predictions into M probability bins to compute Expected Calibration Error (ECE).
- Adaptive temperature tuning: automatically increases temperature T when posterior
  becomes overconfident / poorly calibrated under noise.
- Enforces pre-registered target threshold: ECE <= 0.05.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CalibrationBin:
    """Statistics for an individual confidence interval bin."""
    bin_idx: int
    lower_bound: float
    upper_bound: float
    sample_count: int = 0
    accuracy: float = 0.0
    confidence: float = 0.0


@dataclass
class CalibrationReport:
    """Comprehensive calibration evaluation result."""
    ece: float
    is_calibrated: bool  # True if ECE <= 0.05
    total_samples: int
    overconfidence_bias: float  # Avg (confidence - accuracy)
    recommended_temperature: float
    bins: List[CalibrationBin] = field(default_factory=list)


class CalibrationTracker:
    """Calculates ECE and dynamically adapts posterior temperature T."""

    def __init__(
        self,
        num_bins: int = 10,
        target_ece: float = 0.05,
        adaptation_rate: float = 2.0,
        min_temperature: float = 1.0,
        max_temperature: float = 5.0,
    ):
        self.num_bins = num_bins
        self.target_ece = target_ece
        self.adaptation_rate = adaptation_rate
        self.min_temperature = min_temperature
        self.max_temperature = max_temperature

        self.current_temperature: float = 1.0
        self.history_confidences: List[float] = []
        self.history_accuracies: List[bool] = []

    def record_prediction(self, confidence: float, correct: bool):
        """Record a single prediction confidence and empirical ground-truth correctness."""
        c = max(0.0, min(1.0, float(confidence)))
        self.history_confidences.append(c)
        self.history_accuracies.append(bool(correct))

    def compute_ece(
        self,
        confidences: Optional[List[float]] = None,
        accuracies: Optional[List[bool]] = None,
    ) -> CalibrationReport:
        """Compute Expected Calibration Error (ECE) across M equal-width probability bins."""
        confs = confidences if confidences is not None else self.history_confidences
        accs = accuracies if accuracies is not None else self.history_accuracies

        N = len(confs)
        if N == 0:
            return CalibrationReport(
                ece=0.0,
                is_calibrated=True,
                total_samples=0,
                overconfidence_bias=0.0,
                recommended_temperature=self.current_temperature,
                bins=[],
            )

        bin_size = 1.0 / self.num_bins
        bins: List[CalibrationBin] = []
        total_ece = 0.0
        total_bias = 0.0

        for m in range(self.num_bins):
            lo = m * bin_size
            hi = (m + 1) * bin_size

            # In-bin indices
            in_bin = [
                i for i, c in enumerate(confs)
                if (lo <= c < hi) or (m == self.num_bins - 1 and lo <= c <= hi)
            ]
            bin_count = len(in_bin)

            if bin_count > 0:
                bin_acc = sum(1.0 for i in in_bin if accs[i]) / bin_count
                bin_conf = sum(confs[i] for i in in_bin) / bin_count
                bin_diff = abs(bin_acc - bin_conf)
                total_ece += (bin_count / N) * bin_diff
                total_bias += (bin_count / N) * (bin_conf - bin_acc)

                bins.append(
                    CalibrationBin(
                        bin_idx=m,
                        lower_bound=lo,
                        upper_bound=hi,
                        sample_count=bin_count,
                        accuracy=bin_acc,
                        confidence=bin_conf,
                    )
                )

        # Dynamic temperature adjustment
        # If overconfident (confidence > accuracy) and ECE > target_ece: increase T
        if total_ece > self.target_ece and total_bias > 0.0:
            adjustment = 1.0 + self.adaptation_rate * total_ece
            self.current_temperature = min(self.max_temperature, self.current_temperature * adjustment)
        elif total_ece <= self.target_ece:
            # Gradually anneal temperature towards 1.0 when well-calibrated
            self.current_temperature = max(self.min_temperature, self.current_temperature * 0.95)

        is_calibrated = total_ece <= self.target_ece

        return CalibrationReport(
            ece=total_ece,
            is_calibrated=is_calibrated,
            total_samples=N,
            overconfidence_bias=total_bias,
            recommended_temperature=self.current_temperature,
            bins=bins,
        )

    def get_temperature(self) -> float:
        """Fetch current adapted temperature T."""
        return self.current_temperature
