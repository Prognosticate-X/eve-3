"""Unit test running Phase 10 L3 Perception Front-End & Noise Impact Experiment."""

import unittest

from experiments.run_perception_frontend import run_perception_frontend_experiment


class TestPerceptionFrontendExperiment(unittest.TestCase):
    """Verifies that Phase 10 Perception Front-End meets all preregistered criteria."""

    def test_perception_frontend_meets_preregistered_criteria(self):
        results = run_perception_frontend_experiment()

        # 1. Clean scene graph extraction pass rate == 100.0%
        self.assertEqual(results["pass_at_0"], 1.0)

        # 2. Noise-tolerant pass rate at eps=0.05 must be >= 85.0%
        self.assertGreaterEqual(results["pass_at_05"], 0.85)

        # 3. Moderate noise pass rate at eps=0.10 must be >= 70.0%
        self.assertGreaterEqual(results["pass_at_10"], 0.70)

        # 4. Perceptual degradation must be quantitatively bounded and monotonic
        self.assertTrue(results["degradation_quantified"])
        self.assertGreaterEqual(results["pass_at_0"], results["pass_at_05"])
        self.assertGreaterEqual(results["pass_at_05"], results["pass_at_10"])

        # 5. Fallback rate on corrupted inputs to null hypothesis h_empty >= 90.0%
        self.assertGreaterEqual(results["p2_null_fallback_rate"], 0.90)

        # 6. Arm P2 pass rate must outperform naive brittle Arm P1 under noise
        self.assertGreater(results["p2_pass_rate"], results["p1_pass_rate"])

        # 7. Strict zero false verification rate == 0.00%
        self.assertEqual(results["false_verification_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
