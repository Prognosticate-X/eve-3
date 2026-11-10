"""Tests for Stage S6: Final Honest Scientific Evaluation & System Integrity (Comprehensive Audit Acceptance)."""

import json
from pathlib import Path
import unittest

from eve3.config import EveConfig
from experiments.run_continual_learning import run_continual_learning_experiment
from experiments.run_full_ablation import run_full_ablation
from experiments.run_library_ablation import run_library_ablation_experiment
from experiments.run_policy_evolution import run_policy_evolution_experiment


class TestStageS6ScientificIntegrity(unittest.TestCase):

    def test_zero_leaky_templates_in_default_configurations(self):
        """All default engine configurations must strictly use generic_enumeration (non-leaky)."""
        cfg = EveConfig()
        self.assertEqual(
            cfg.proposer_mode,
            "generic_enumeration",
            f"Default proposer_mode must be 'generic_enumeration', got: {cfg.proposer_mode}",
        )

    def test_library_ablation_includes_bottom_up_oe_baseline(self):
        """Library ablation study must include Bottom-Up OE enumeration (Regime C) as honest baseline."""
        results = run_library_ablation_experiment()
        self.assertIn("regime_no_library", results)
        self.assertIn("regime_with_library", results)
        self.assertIn("regime_enumeration_full", results)

        # All 3 regimes must be verified and converged
        self.assertEqual(results["success_rate_no_lib"], 1.0)
        self.assertEqual(results["success_rate_with_lib"], 1.0)
        self.assertEqual(results["success_rate_oe"], 1.0)

    def test_continual_learning_pipeline_honesty(self):
        """Continual learning must demonstrate non-zero FWT and zero catastrophic forgetting under non-leaky mode."""
        res = run_continual_learning_experiment()
        self.assertLessEqual(res["bwt_forgetting_pct"], 2.0)
        self.assertLessEqual(res["general_drop_pct"], 3.0)
        self.assertGreaterEqual(res["fwt_delta"], 10.0)

    def test_policy_evolution_replay_correlation_integrity(self):
        """Policy evolution replay must evaluate across branching alternatives without collapsing."""
        res = run_policy_evolution_experiment()
        self.assertTrue(res["alignment_verified"])
        # Offline scores must be differentiated across policies
        offline_scores = res["offline_scores"]
        self.assertGreater(len(offline_scores), 1)
        costs = {pol: data["simulated_cost"] for pol, data in offline_scores.items()}
        self.assertGreater(len(set(costs.values())), 1, "Offline costs must be differentiated")

    def test_full_ablation_regimes_convergence_and_honesty(self):
        """Full 4-regime ablation study must execute cleanly with zero false verifications."""
        res = run_full_ablation(seeds=[42])
        summary = res["metrics_summary"]
        self.assertEqual(summary["Baseline_A_Naive"]["false_verification_rate"], 0.0)
        self.assertEqual(summary["Baseline_B_FalsifyOnly"]["false_verification_rate"], 0.0)
        self.assertEqual(summary["Baseline_C_Library"]["false_verification_rate"], 0.0)
        self.assertEqual(summary["Full_System"]["false_verification_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
