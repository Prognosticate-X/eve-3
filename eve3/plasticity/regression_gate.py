"""Automated Regression Gate for Continual Learning & Weight Consolidation.

Enforces pre-registered safety criteria:
1. Historical task family retention: no family drops > max_family_regression_pct (default 2.0%).
2. General coding capability retention: score drop <= max_general_drop_pct (default 3.0%).
3. False verification rate: strictly 0.0%.
4. Minimum overall accuracy threshold.
"""

from dataclasses import dataclass, field
import datetime
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RegressionGateConfig:
    """Configuration parameters for the regression gate."""
    max_family_regression_pct: float = 2.0     # Max allowable drop per family (%)
    max_general_drop_pct: float = 3.0          # Max allowable drop on general probe (%)
    max_false_verification_rate: float = 0.0   # Strict zero false verification
    min_overall_accuracy: float = 0.80         # Minimum overall accuracy across families


@dataclass
class FamilyEvaluationResult:
    """Evaluation result for an individual task family."""
    family_name: str
    passed_count: int
    total_count: int
    accuracy: float
    false_verification_count: int = 0
    avg_runtime_ms: float = 0.0


@dataclass
class GateResult:
    """Summary result produced by evaluating a candidate against the Regression Gate."""
    passed: bool
    family_scores: Dict[str, float]
    historical_family_scores: Dict[str, float]
    family_regressions: Dict[str, float]
    general_probe_score: float
    baseline_general_probe_score: float
    false_verification_rate: float
    overall_accuracy: float
    rejection_reasons: List[str] = field(default_factory=list)
    evaluated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "family_scores": self.family_scores,
            "historical_family_scores": self.historical_family_scores,
            "family_regressions": self.family_regressions,
            "general_probe_score": self.general_probe_score,
            "baseline_general_probe_score": self.baseline_general_probe_score,
            "false_verification_rate": self.false_verification_rate,
            "overall_accuracy": self.overall_accuracy,
            "rejection_reasons": self.rejection_reasons,
            "evaluated_at": self.evaluated_at,
        }


class RegressionGate:
    """Evaluates candidates against historical held-out suites and general coding probes."""

    def __init__(
        self,
        config: Optional[RegressionGateConfig] = None,
        benchmarks_dir: Optional[Path] = None,
    ):
        self.config = config or RegressionGateConfig()
        if benchmarks_dir is not None:
            self.benchmarks_dir = benchmarks_dir
        else:
            self.benchmarks_dir = Path(__file__).parent.parent.parent / "benchmarks"

    def evaluate_metrics(
        self,
        candidate_family_scores: Dict[str, float],
        historical_family_scores: Dict[str, float],
        general_probe_score: float,
        baseline_general_probe_score: float = 1.0,
        false_verification_rate: float = 0.0,
    ) -> GateResult:
        """Evaluate precomputed scores against pre-registered regression thresholds."""
        rejection_reasons: List[str] = []
        family_regressions: Dict[str, float] = {}

        # 1. Check family regressions
        for family, hist_score in historical_family_scores.items():
            curr_score = candidate_family_scores.get(family, 0.0)
            regression_drop = (hist_score - curr_score) * 100.0  # Percentage points
            family_regressions[family] = regression_drop

            if regression_drop > self.config.max_family_regression_pct + 1e-6:
                rejection_reasons.append(
                    f"Family '{family}' regressed by {regression_drop:.2f}% "
                    f"(exceeds max limit {self.config.max_family_regression_pct:.2f}%)"
                )

        # 2. Check general coding probe retention
        if baseline_general_probe_score > 0:
            general_drop = (
                (baseline_general_probe_score - general_probe_score)
                / baseline_general_probe_score
            ) * 100.0
        else:
            general_drop = 0.0

        if general_drop > self.config.max_general_drop_pct + 1e-6:
            rejection_reasons.append(
                f"General coding probe dropped by {general_drop:.2f}% "
                f"(exceeds max limit {self.config.max_general_drop_pct:.2f}%)"
            )

        # 3. Check false verification rate
        if false_verification_rate > self.config.max_false_verification_rate:
            rejection_reasons.append(
                f"False verification rate is {false_verification_rate:.4f} "
                f"(strict requirement is {self.config.max_false_verification_rate:.4f})"
            )

        # 4. Check overall accuracy across evaluated families
        if candidate_family_scores:
            overall_accuracy = sum(candidate_family_scores.values()) / len(candidate_family_scores)
        else:
            overall_accuracy = 0.0

        if overall_accuracy < self.config.min_overall_accuracy - 1e-6:
            rejection_reasons.append(
                f"Overall accuracy {overall_accuracy * 100:.1f}% is below minimum "
                f"threshold {self.config.min_overall_accuracy * 100:.1f}%"
            )

        passed = len(rejection_reasons) == 0

        return GateResult(
            passed=passed,
            family_scores=candidate_family_scores,
            historical_family_scores=historical_family_scores,
            family_regressions=family_regressions,
            general_probe_score=general_probe_score,
            baseline_general_probe_score=baseline_general_probe_score,
            false_verification_rate=false_verification_rate,
            overall_accuracy=overall_accuracy,
            rejection_reasons=rejection_reasons,
        )

    def load_family_benchmark(self, family_name: str) -> Optional[Dict[str, Any]]:
        """Load benchmark tasks for a given task family."""
        family_file = self.benchmarks_dir / "families" / f"{family_name}.json"
        if not family_file.exists():
            return None
        with open(family_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_general_coding_probes(self) -> List[Dict[str, Any]]:
        """Load general non-DSL algorithmic probes."""
        probe_file = self.benchmarks_dir / "general_coding_probe.json"
        if not probe_file.exists():
            return []
        with open(probe_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("probes", [])

    def run_general_coding_probe_evaluation(
        self,
        solver_fn: Optional[Callable[[str, Any], Any]] = None,
    ) -> float:
        """Evaluate pythonic algorithmic probes.
        
        If solver_fn is None, runs default reference solvers to establish baseline score (1.0).
        """
        probes = self.load_general_coding_probes()
        if not probes:
            return 1.0

        passed_probes = 0
        total_probes = len(probes)

        # Built-in reference implementations for general probes
        def default_solver(probe_id: str, inp: Any) -> Any:
            if probe_id == "probe_fibonacci":
                n = int(inp)
                if n <= 0:
                    return 0
                if n == 1:
                    return 1
                a, b = 0, 1
                for _ in range(2, n + 1):
                    a, b = b, a + b
                return b
            elif probe_id == "probe_is_palindrome":
                s = str(inp).lower()
                return s == s[::-1]
            elif probe_id == "probe_frequency_count":
                counts: Dict[str, int] = {}
                for item in inp:
                    key = str(item)
                    counts[key] = counts.get(key, 0) + 1
                return counts
            elif probe_id == "probe_valid_parentheses":
                pairs = {")": "(", "]": "[", "}": "{"}
                stack = []
                for ch in str(inp):
                    if ch in "([{":
                        stack.append(ch)
                    elif ch in ")]}":
                        if not stack or stack[-1] != pairs[ch]:
                            return False
                        stack.pop()
                return len(stack) == 0
            elif probe_id == "probe_binary_search_index":
                arr = inp.get("arr", [])
                target = inp.get("target")
                lo, hi = 0, len(arr) - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if arr[mid] == target:
                        return mid
                    elif arr[mid] < target:
                        lo = mid + 1
                    else:
                        hi = mid - 1
                return -1
            return None

        eval_fn = solver_fn or default_solver

        for probe in probes:
            probe_id = probe["probe_id"]
            test_cases = probe.get("test_cases", [])
            probe_passed = True
            for tc in test_cases:
                inp = tc["input"]
                expected = tc["expected"]
                try:
                    actual = eval_fn(probe_id, inp)
                    if actual != expected:
                        probe_passed = False
                        break
                except Exception:
                    probe_passed = False
                    break
            if probe_passed:
                passed_probes += 1

        return passed_probes / total_probes if total_probes > 0 else 1.0
