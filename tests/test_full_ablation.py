"""Tests verifying 4-regime ablation pipeline and metric consistency."""

import unittest

from experiments.run_full_ablation import run_full_ablation


class TestFullAblation(unittest.TestCase):

    def test_run_full_ablation_pipeline(self):
        output = run_full_ablation()
        summary = output["metrics_summary"]

        self.assertIn("Baseline_A_Naive", summary)
        self.assertIn("Baseline_B_FalsifyOnly", summary)
        self.assertIn("Baseline_C_Library", summary)
        self.assertIn("Full_System", summary)

        # Critical metric: False verification rate MUST be 0.0%
        for name, m in summary.items():
            self.assertEqual(
                m["false_verification_rate"],
                0.0,
                f"Regime {name} reported non-zero false verification rate!",
            )
            self.assertGreaterEqual(m["hidden_test_pass_rate"], 0.8)


if __name__ == "__main__":
    unittest.main()
