"""Unit test running Phase 7 Autonomous Curriculum & Exploration experiment."""

import unittest

from experiments.run_autonomous_curriculum import run_autonomous_curriculum_experiment


class TestAutonomousCurriculumExperiment(unittest.TestCase):
    """Verifies that Arm A5 meets pre-registered Phase 7 criteria."""

    def test_autonomous_curriculum_meets_preregistered_criteria(self):
        results = run_autonomous_curriculum_experiment()

        metrics = results["metrics"]
        a5 = results["a5_autonomous_curriculum"]
        a4 = results["a4_external_only"]

        # 1. Held-out transfer pass rate should be >= external-only benchmark training
        self.assertGreaterEqual(a5["held_out_pass_rate"], a4["held_out_pass_rate"])

        # 2. Coverage entropy must be above collapse threshold
        self.assertTrue(metrics["entropy_healthy"])
        self.assertGreaterEqual(a5["avg_entropy"], 0.40)

        # 3. Synthetic ratio must be <= 60%
        self.assertTrue(metrics["synthetic_ratio_compliant"])
        self.assertLessEqual(a5["synthetic_ratio"], 0.60)

        # 4. Strict zero false verification
        self.assertTrue(metrics["zero_false_verification"])
        self.assertEqual(a5["false_verification_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
