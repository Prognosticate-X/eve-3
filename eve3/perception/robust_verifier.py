"""Robust Perception Verifier: Perception-to-Symbolic Reasoning with h_empty Anomaly Gating.

Implements Phase 10 Neurosymbolic Bridge:
- Evaluates candidate policies and programs on perceived SceneGraphs rather than raw oracle states.
- Propagates perceptual uncertainties and node/edge confidences into predicate truth degrees.
- Activates diffuse null hypothesis h_empty when perceptual corruption exceeds safety thresholds,
  preventing false positive library crystallization.
- Quantifies the degradation curve of task success rate under increasing perceptual noise epsilon.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from eve3.envs.grid_tasks import Grid
from eve3.perception.encoder import PerceptionEncoder, PerceptionNoiseConfig
from eve3.perception.symbolic_state import PredicateState, SceneGraph


@dataclass
class PerceivedVerificationResult:
    """Outcome of program verification over perceived sensory states."""
    success: bool
    is_corrupted: bool
    confidence: float
    fallback_to_null: bool
    predicates: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


class RobustPerceptionVerifier:
    """Verifies programs and policies against SceneGraphs with h_empty anomaly shielding."""

    def __init__(
        self,
        confidence_rejection_threshold: float = 0.50,
        graph_distance_threshold: float = 0.20,
    ):
        self.rejection_threshold = confidence_rejection_threshold
        self.graph_distance_threshold = graph_distance_threshold

    def verify_grid_transformation(
        self,
        grid_input: Grid,
        grid_expected_output: Grid,
        transform_fn: Callable[[Grid], Grid],
        encoder: PerceptionEncoder,
    ) -> PerceivedVerificationResult:
        """Verify grid transformation program via perceived scene graphs of input and output."""
        # 1. Encode input scene graph
        sg_in, corrupted_in = encoder.encode_grid(grid_input, scene_id="input_scene")

        # 2. Execute program
        try:
            grid_actual_output = transform_fn(grid_input)
        except Exception as e:
            return PerceivedVerificationResult(
                success=False,
                is_corrupted=False,
                confidence=0.0,
                fallback_to_null=False,
                details={"error": str(e)},
            )

        # 3. Encode expected and actual output scene graphs
        sg_expected, corrupted_exp = encoder.encode_grid(grid_expected_output, scene_id="expected_output")
        sg_actual, corrupted_act = encoder.encode_grid(grid_actual_output, scene_id="actual_output")

        is_corrupted = corrupted_in or corrupted_exp or corrupted_act

        # 4. If perceptual corruption is triggered, fallback to null hypothesis h_empty
        if is_corrupted:
            return PerceivedVerificationResult(
                success=False,
                is_corrupted=True,
                confidence=0.05,  # Diffuse null likelihood
                fallback_to_null=True,
                details={"reason": "perceptual_noise_exceeded_threshold"},
            )

        # 5. Robust graph comparison
        graph_distance = sg_actual.compute_graph_distance(sg_expected)
        is_success = (graph_distance <= self.graph_distance_threshold)

        # Mean confidence across nodes
        all_confs = [n.confidence for n in sg_actual.nodes.values()] + [n.confidence for n in sg_expected.nodes.values()]
        avg_conf = sum(all_confs) / len(all_confs) if all_confs else 1.0

        return PerceivedVerificationResult(
            success=is_success,
            is_corrupted=False,
            confidence=avg_conf,
            fallback_to_null=False,
            details={"graph_distance": graph_distance},
        )

    def verify_nav_trajectory(
        self,
        trajectory: List[Any],
        target_pos: Tuple[float, float],
        encoder: PerceptionEncoder,
    ) -> PerceivedVerificationResult:
        """Verify physical navigation rollout through perceived final scene graph."""
        if not trajectory:
            return PerceivedVerificationResult(
                success=False, is_corrupted=False, confidence=0.0, fallback_to_null=False
            )

        final_step = trajectory[-1]
        final_pos = (final_step.state[0], final_step.state[1])

        sg_final, is_corrupted = encoder.encode_sim_state(
            agent_pos=final_pos,
            target_pos=target_pos,
            scene_id="final_step_scene",
        )

        if is_corrupted:
            return PerceivedVerificationResult(
                success=False,
                is_corrupted=True,
                confidence=0.05,
                fallback_to_null=True,
                details={"reason": "sim_perception_corrupted"},
            )

        pred_state = sg_final.evaluate_predicate_state()
        goal_reached = pred_state.is_satisfied("goal_reached", threshold=self.rejection_threshold)
        conf = pred_state.soft_confidences.get("goal_reached", 0.8)

        return PerceivedVerificationResult(
            success=goal_reached,
            is_corrupted=False,
            confidence=conf,
            fallback_to_null=False,
            predicates=dict(pred_state.predicates),
        )

    def quantify_noise_impact(
        self,
        eval_fn: Callable[[PerceptionEncoder], PerceivedVerificationResult],
        noise_levels: List[float],
        trials_per_level: int = 20,
    ) -> Dict[str, Any]:
        """Quantify how task success rate and h_empty fallbacks vary as perceptual noise scales."""
        noise_results: List[Dict[str, Any]] = []

        for noise_scale in noise_levels:
            successes = 0
            corruptions = 0
            null_fallbacks = 0
            confidences: List[float] = []

            for trial in range(trials_per_level):
                encoder = PerceptionEncoder(seed=trial * 100 + int(noise_scale * 1000))
                encoder.set_noise_level(noise_scale)

                res = eval_fn(encoder)
                if res.success:
                    successes += 1
                if res.is_corrupted:
                    corruptions += 1
                if res.fallback_to_null:
                    null_fallbacks += 1
                confidences.append(res.confidence)

            pass_rate = successes / trials_per_level
            fallback_rate = null_fallbacks / trials_per_level
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

            noise_results.append({
                "noise_level": noise_scale,
                "pass_rate": pass_rate,
                "corruption_rate": corruptions / trials_per_level,
                "null_fallback_rate": fallback_rate,
                "avg_confidence": avg_conf,
            })

        return {"levels": noise_results}
