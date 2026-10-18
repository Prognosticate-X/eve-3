"""Unit test running Phase 9 Simulated Environments & Statistical Falsification Experiment."""

import unittest

from experiments.run_env_simulation import run_env_simulation_experiment


class TestEnvSimulationExperiment(unittest.TestCase):
    """Verifies that Phase 9 L1/L2 Environments, ActionLimiter, and Statistical Falsification pass."""

    def test_env_simulation_meets_preregistered_criteria(self):
        results = run_env_simulation_experiment()

        # 1. L1 Discrete Perception Suite: 100.0% Pass Rate
        self.assertEqual(results["l1_pass_rate"], 1.0)
        self.assertEqual(results["l1_false_verif_rate"], 0.0)

        # 2. L2 Physical Simulation: Navigation Success Rate >= 90.0%
        self.assertGreaterEqual(results["l2_nav_success_rate"], 0.90)

        # 3. Safety Layer: Exactly zero action limiter penetrations (Rate == 0.00%)
        self.assertEqual(results["safety_penetration_rate"], 0.0)
        self.assertGreater(results["attempted_violations"], 0)

        # 4. Statistical Calibration: ECE <= 0.05
        self.assertLessEqual(results["s2_ece"], 0.05)
        self.assertTrue(results["is_calibrated"])
        # S1 Naive Bayes must fail calibration under noise
        self.assertGreater(results["s1_ece"], 0.20)

        # 5. SPRT Statistical Hypothesis Discrimination: 100.0% Resolved
        self.assertTrue(results["wrong_hypotheses_falsified"])
        self.assertTrue(results["true_hypothesis_survived"])

        # 6. Null Hypothesis h_empty Fallback: Dominates (>90%) on unmodeled anomalies
        self.assertTrue(results["null_hyp_detected"])
        self.assertGreaterEqual(results["null_hyp_belief"], 0.90)

        # 7. Strict Zero False Verification Rate: == 0.00%
        self.assertEqual(results["false_verification_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
