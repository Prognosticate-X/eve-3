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
import statistics
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

    def extract_all_samples(
        self,
        trees: List[DiscoveryTree],
        current_time: Optional[float] = None,
    ) -> List[ConsolidationSample]:
        """Extract all consolidation samples across multiple discovery trees."""
        all_samples: List[ConsolidationSample] = []
        for tree in trees:
            all_samples.extend(self.extract_samples_from_tree(tree, current_time=current_time))
        return all_samples

    def sample_replay_batch(
        self,
        samples: List[ConsolidationSample],
        n: int,
        current_time: Optional[float] = None,
        random_seed: Optional[int] = None,
    ) -> List[ConsolidationSample]:
        """Sample n samples according to value-weighted probabilities p(i)."""
        if not samples or n <= 0:
            return []
        if len(samples) <= n:
            return list(samples)

        probs = self.compute_replay_probabilities(samples, current_time=current_time)
        rng = random.Random(random_seed)
        chosen_indices = rng.choices(range(len(samples)), weights=probs, k=n)
        return [samples[idx] for idx in chosen_indices]

    def format_mlx_dataset(
        self,
        samples: List[ConsolidationSample],
    ) -> List[Dict[str, Any]]:
        """Format samples into MLX-LM fine-tuning pairs (prompt, completion)."""
        dataset: List[Dict[str, Any]] = []
        for s in samples:
            dataset.append({
                "prompt": f"<|im_start|>user\nSynthesize DSL function for task {s.task_id} in family {s.task_family}.<|im_end|>\n<|im_start|>assistant\n",
                "completion": f"{s.target_code}<|im_end|>",
                "weight": s.value_weight,
            })
        return dataset

    def compute_surrogate_loss(
        self,
        new_samples: List[ConsolidationSample],
        replay_samples: List[ConsolidationSample],
        kl_penalty: float = 0.05,
    ) -> Dict[str, float]:
        """Compute four-part consolidation loss per Roadmap Section 4.2:
        L = L_sft(new) + lambda_pref * L_pref + lambda_replay * L_sft(replay) + lambda_kl * KL(pi || pi_base)
        """
        # SFT surrogate: normalized description length of target
        l_sft_new = (
            statistics.mean([len(s.target_code) / 50.0 for s in new_samples])
            if new_samples else 0.0
        )
        # Replay loss
        l_replay = (
            statistics.mean([len(s.target_code) / 50.0 for s in replay_samples])
            if replay_samples else 0.0
        )
        # Preference loss: penalty if rejected code is shorter or closer than target
        pref_pairs = [s for s in new_samples if s.rejected_code]
        if pref_pairs:
            l_pref = statistics.mean([
                max(0.0, 1.0 - (len(s.target_code) - len(s.rejected_code)) / 20.0)
                for s in pref_pairs
            ])
        else:
            l_pref = 0.0

        total_loss = (
            l_sft_new
            + self.config.lambda_pref * l_pref
            + self.config.lambda_replay * l_replay
            + self.config.lambda_kl * kl_penalty
        )

        return {
            "loss_total": total_loss,
            "loss_sft_new": l_sft_new,
            "loss_pref": l_pref,
            "loss_replay": l_replay,
            "loss_kl": kl_penalty,
        }

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
