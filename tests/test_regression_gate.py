"""Tests for Automated Regression Gatekeeper and Safety Criteria."""

from pathlib import Path
import unittest

from eve3.plasticity.regression_gate import (
    RegressionGate,
    RegressionGateConfig,
)


class TestRegressionGate(unittest.TestCase):

    def setUp(self):
        self.config = RegressionGateConfig(
            max_family_regression_pct=2.0,
            max_general_drop_pct=3.0,
            max_false_verification_rate=0.0,
            min_overall_accuracy=0.80,
        )
        self.gate = RegressionGate(config=self.config)

    def test_gate_passes_when_metrics_improve_or_stay_stable(self):
        historical = {
            "list_mapping": 0.95,
            "list_filtering": 0.90,
            "list_reduction": 0.85,
        }
        candidate = {
            "list_mapping": 0.96,   # improved
            "list_filtering": 0.90,  # identical
            "list_reduction": 0.84,  # dropped by 1.0% (<= 2.0% allowed)
        }
        res = self.gate.evaluate_metrics(
            candidate_family_scores=candidate,
            historical_family_scores=historical,
            general_probe_score=0.99,
            baseline_general_probe_score=1.00,  # 1% drop <= 3% allowed
            false_verification_rate=0.0,
        )
        self.assertTrue(res.passed)
        self.assertEqual(len(res.rejection_reasons), 0)

    def test_gate_rejects_when_historical_family_regresses_beyond_threshold(self):
        historical = {"list_mapping": 0.95, "list_filtering": 0.90}
        candidate = {
            "list_mapping": 0.91,  # dropped by 4.0% (> 2.0% limit)
            "list_filtering": 0.90,
        }
        res = self.gate.evaluate_metrics(
            candidate_family_scores=candidate,
            historical_family_scores=historical,
            general_probe_score=1.00,
            baseline_general_probe_score=1.00,
            false_verification_rate=0.0,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("regressed by 4.00%" in r for r in res.rejection_reasons))

    def test_gate_rejects_when_general_probe_drops_beyond_threshold(self):
        historical = {"list_mapping": 0.95}
        candidate = {"list_mapping": 0.95}
        # Baseline = 1.0, current = 0.95 -> 5% drop (> 3% allowed)
        res = self.gate.evaluate_metrics(
            candidate_family_scores=candidate,
            historical_family_scores=historical,
            general_probe_score=0.95,
            baseline_general_probe_score=1.00,
            false_verification_rate=0.0,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("General coding probe dropped" in r for r in res.rejection_reasons))

    def test_gate_rejects_strictly_on_false_verification(self):
        historical = {"list_mapping": 0.95}
        candidate = {"list_mapping": 0.98}
        res = self.gate.evaluate_metrics(
            candidate_family_scores=candidate,
            historical_family_scores=historical,
            general_probe_score=1.0,
            baseline_general_probe_score=1.0,
            false_verification_rate=0.02,  # > 0.0%
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("False verification rate" in r for r in res.rejection_reasons))

    def test_gate_general_coding_probe_reference_evaluation(self):
        score = self.gate.run_general_coding_probe_evaluation()
        self.assertEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
