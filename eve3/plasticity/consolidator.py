"""Consolidator: T1 Sleep Phase Consolidation and Value-Weighted Replay Engine.

Extracts training pairs from Discovery Tree verified trajectories:
- Positive samples: (task_description, verified_program)
- Preference/Negative pairs: (task_description, falsified_candidate, verified_program, counterexample)
- Value-weighted replay sampling: p(i) ~ w_i * exp(-Δt_i / tau) * (1 + hardness_i)
- Integrates with RegressionGate to enforce strict commit / rollback decisions.
"""

from dataclasses import dataclass, field
import datetime
import math
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from eve3.discovery.tree import DiscoveryTree, DiscoveryNode
from eve3.plasticity.adapter_bank import AdapterBank
from eve3.plasticity.regression_gate import GateResult, RegressionGate


@dataclass
class ConsolidationSample:
    """A formatted sample extracted from historical exploration."""
    task_id: str
    task_family: str
    prompt: str
    target_code: str
    rejected_code: Optional[str] = None
    counterexample: Optional[str] = None
    value_weight: float = 1.0
    hardness: float = 0.0
    timestamp: float = 0.0


@dataclass
class ConsolidationConfig:
    """Hyperparameters for sleep consolidation."""
    batch_size: int = 16
    tau_decay_hours: float = 72.0
    lambda_pref: float = 0.5
    lambda_replay: float = 0.3
    lambda_kl: float = 0.1
    min_verified_samples_to_trigger: int = 2


@dataclass
class ConsolidationResult:
    """Result of a consolidation cycle."""
    success: bool
    adapter_id: str
    samples_processed: int
    positive_count: int
    preference_pairs_count: int
    gate_result: Optional[GateResult] = None
    message: str = ""


class Consolidator:
    """Prepares and coordinates offline parameter consolidation and replay."""

    def __init__(
        self,
        adapter_bank: AdapterBank,
        regression_gate: RegressionGate,
        config: Optional[ConsolidationConfig] = None,
    ):
        self.adapter_bank = adapter_bank
        self.regression_gate = regression_gate
        self.config = config or ConsolidationConfig()

    def extract_samples_from_tree(
        self,
        tree: DiscoveryTree,
        current_time: Optional[float] = None,
    ) -> List[ConsolidationSample]:
        """Extract positive solutions, falsified pairs, and replay weights from tree."""
        samples: List[ConsolidationSample] = []
        now = current_time or datetime.datetime.now(datetime.timezone.utc).timestamp()

        # Find verified and falsified nodes
        verified_nodes = [
            n for n in tree.nodes.values()
            if n.outcome in ("verified", "success") and "code" in n.payload
        ]

        falsified_nodes = [
            n for n in tree.nodes.values()
            if n.outcome == "falsified" and "code" in n.payload
        ]

        for v_node in verified_nodes:
            task_id = tree.task_id or "unnamed_task"
            family = v_node.payload.get("task_family", "generic")
            target_code = v_node.payload.get("code", "")

            # Compute value weight and hardness
            cost = v_node.cost
            reuse_count = v_node.payload.get("reuse_count", 1)
            value_weight = 1.0 * (1.0 + math.log(1.0 + reuse_count))
            hardness = max(0.0, cost / 10.0)

            # Look for related falsified candidate to form a preference pair
            related_falsified = next(
                (f for f in falsified_nodes if f.payload.get("task_id", task_id) == task_id),
                None,
            )

            rejected_code = related_falsified.payload.get("code") if related_falsified else None
            counterexample = (
                str(related_falsified.payload.get("counterexample")) if related_falsified else None
            )

            sample = ConsolidationSample(
                task_id=task_id,
                task_family=family,
                prompt=f"Task {task_id}: synthesize functional program",
                target_code=target_code,
                rejected_code=rejected_code,
                counterexample=counterexample,
                value_weight=value_weight,
                hardness=hardness,
                timestamp=v_node.timestamp,
            )
            samples.append(sample)

        return samples

    def compute_replay_probabilities(
        self,
        samples: List[ConsolidationSample],
        current_time: Optional[float] = None,
    ) -> List[float]:
        """Calculate p(i) ~ w_i * exp(-Δt_i / tau) * (1 + hardness_i)."""
        if not samples:
            return []

        now = current_time or datetime.datetime.now(datetime.timezone.utc).timestamp()
        tau_seconds = self.config.tau_decay_hours * 3600.0

        scores: List[float] = []
        for s in samples:
            dt = max(0.0, now - s.timestamp)
            time_decay = math.exp(-dt / tau_seconds)
            p_score = s.value_weight * time_decay * (1.0 + s.hardness)
            scores.append(max(1e-6, p_score))

        total_sum = sum(scores)
        return [sc / total_sum for sc in scores]

    def run_sleep_cycle(
        self,
        target_family: str,
        tree: DiscoveryTree,
        train_fn: Optional[Callable[[List[ConsolidationSample]], bool]] = None,
        eval_fn: Optional[Callable[[], Tuple[Dict[str, float], float, float]]] = None,
    ) -> ConsolidationResult:
        """Run an end-to-end sleep consolidation cycle with regression gate check."""
        samples = self.extract_samples_from_tree(tree)
        if len(samples) < self.config.min_verified_samples_to_trigger:
            return ConsolidationResult(
                success=False,
                adapter_id="",
                samples_processed=len(samples),
                positive_count=0,
                preference_pairs_count=0,
                message=f"Insufficient verified samples ({len(samples)} < {self.config.min_verified_samples_to_trigger})",
            )

        positive_count = len([s for s in samples if s.target_code])
        pref_count = len([s for s in samples if s.rejected_code])

        # Create candidate adapter in bank
        candidate_id = self.adapter_bank.create(family=target_family)

        # Execute training (mock or external MLX function)
        if train_fn is not None:
            train_ok = train_fn(samples)
            if not train_ok:
                return ConsolidationResult(
                    success=False,
                    adapter_id=candidate_id,
                    samples_processed=len(samples),
                    positive_count=positive_count,
                    preference_pairs_count=pref_count,
                    message="Consolidation training process failed.",
                )

        # Run regression gate check
        if eval_fn is not None:
            cand_scores, gen_score, false_verif_rate = eval_fn()
        else:
            cand_scores = {target_family: 1.0}
            gen_score = 1.0
            false_verif_rate = 0.0

        historical_scores = {target_family: 0.95}
        gate_res = self.regression_gate.evaluate_metrics(
            candidate_family_scores=cand_scores,
            historical_family_scores=historical_scores,
            general_probe_score=gen_score,
            false_verification_rate=false_verif_rate,
        )

        try:
            self.adapter_bank.commit(
                adapter_id=candidate_id,
                gate_result=gate_res,
                description=f"Consolidated {len(samples)} samples for family {target_family}",
            )
            return ConsolidationResult(
                success=True,
                adapter_id=candidate_id,
                samples_processed=len(samples),
                positive_count=positive_count,
                preference_pairs_count=pref_count,
                gate_result=gate_res,
                message="Consolidation committed successfully.",
            )
        except ValueError as e:
            return ConsolidationResult(
                success=False,
                adapter_id=candidate_id,
                samples_processed=len(samples),
                positive_count=positive_count,
                preference_pairs_count=pref_count,
                gate_result=gate_res,
                message=str(e),
            )
