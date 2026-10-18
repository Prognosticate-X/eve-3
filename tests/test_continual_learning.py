"""Tests for Phase 6 Continual Learning, Backward Retention (BWT), and Forward Transfer (FWT)."""

import unittest

from experiments.run_continual_learning import run_continual_learning_experiment
from eve3.plasticity.adapter_bank import AdapterBank
from eve3.plasticity.regression_gate import GateResult, RegressionGate


class TestContinualLearning(unittest.TestCase):

    def test_continual_learning_pipeline_metrics(self):
        """Run continual learning experiment and verify pre-registered thresholds."""
        results = run_continual_learning_experiment()

        # 1. Backward Transfer (BWT) Forgetting <= 2.0%
        self.assertLessEqual(
            results["bwt_forgetting_pct"],
            2.0,
            f"BWT forgetting {results['bwt_forgetting_pct']:.2f}% exceeds max allowed 2.0%",
        )

        # 2. General Coding Capability Retention Drop <= 3.0%
        self.assertLessEqual(
            results["general_drop_pct"],
            3.0,
            f"General coding drop {results['general_drop_pct']:.2f}% exceeds max allowed 3.0%",
        )

        # 3. Forward Transfer Gain >= +10.0%
        self.assertGreaterEqual(
            results["fwt_delta"],
            10.0,
            f"FWT delta {results['fwt_delta']:.2f}% is below target +10.0%",
        )

        # 4. Retention matrix diagonal must be 1.0 (all learned tasks solved)
        matrix = results["retention_matrix"]
        for i in range(len(matrix)):
            self.assertEqual(matrix[i][i], 1.0)

    def test_regression_gate_rollback_under_catastrophic_failure(self):
        """Verify that an adversarial / regressed adapter is rejected and safely rolled back."""
        bank = AdapterBank(db_path=":memory:")
        gate = RegressionGate()

        # Step 1: Good base state with list_mapping active
        ad1 = bank.create(family="list_mapping")
        pass_gate1 = gate.evaluate_metrics(
            candidate_family_scores={"list_mapping": 1.0},
            historical_family_scores={},
            general_probe_score=1.0,
        )
        snap1 = bank.commit(ad1, pass_gate1, description="Mapping family activated")
        self.assertEqual(bank.get_active_adapter("list_mapping").adapter_id, ad1)

        # Step 2: Adversarial adapter for list_filtering causes list_mapping to crash to 0.2
        ad2 = bank.create(family="list_filtering")
        fail_gate = gate.evaluate_metrics(
            candidate_family_scores={"list_mapping": 0.2, "list_filtering": 1.0},
            historical_family_scores={"list_mapping": 1.0},
            general_probe_score=0.90,  # 10% drop on general probe
        )
        self.assertFalse(fail_gate.passed)

        # Commit must raise ValueError
        with self.assertRaises(ValueError):
            bank.commit(ad2, fail_gate)

        # Adapter status must be reverted
        meta2 = bank.get_adapter(ad2)
        self.assertEqual(meta2.status, "reverted")

        # Rollback confirms state restored to snap1
        rollback_ok = bank.rollback(snap1.version_id)
        self.assertTrue(rollback_ok)
        self.assertEqual(bank.get_active_adapter("list_mapping").adapter_id, ad1)
        self.assertIsNone(bank.get_active_adapter("list_filtering"))

        bank.close()


if __name__ == "__main__":
    unittest.main()
