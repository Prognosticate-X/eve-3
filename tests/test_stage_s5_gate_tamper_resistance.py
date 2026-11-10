"""Tests for Stage S5 Task S5.2: Regression Gate Tamper-Resistance & Immutable Config (H17)."""

from dataclasses import FrozenInstanceError
import unittest

from eve3.discovery.tree import DiscoveryTree
from eve3.plasticity.adapter_bank import AdapterBank
from eve3.plasticity.consolidator import Consolidator
from eve3.plasticity.regression_gate import RegressionGate, RegressionGateConfig


class TestStageS5GateTamperResistance(unittest.TestCase):

    def test_regression_gate_config_is_strictly_immutable(self):
        """Modifying RegressionGateConfig attributes at runtime must raise FrozenInstanceError."""
        cfg = RegressionGateConfig()
        with self.assertRaises(FrozenInstanceError):
            cfg.max_family_regression_pct = 99.0  # Attempt tamper

        with self.assertRaises(FrozenInstanceError):
            cfg.max_general_drop_pct = 50.0

        with self.assertRaises(FrozenInstanceError):
            cfg.min_overall_accuracy = 0.10

    def test_preregistration_hash_and_validity_check(self):
        """Pre-registered hash must be reproducible and invalid configurations detected."""
        default_cfg = RegressionGateConfig()
        h1 = default_cfg.compute_preregistration_hash()
        h2 = default_cfg.compute_preregistration_hash()
        self.assertEqual(h1, h2)
        self.assertTrue(default_cfg.is_preregistered_valid())

        # Config violating preregistered bounds
        tampered_cfg = RegressionGateConfig(max_family_regression_pct=50.0)
        self.assertFalse(tampered_cfg.is_preregistered_valid())

        gate = RegressionGate(tampered_cfg)
        res = gate.evaluate_metrics(
            candidate_family_scores={"list_mapping": 1.0},
            historical_family_scores={},
            general_probe_score=1.0,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("pre-registered" in reason.lower() for reason in res.rejection_reasons))

    def test_consolidator_uses_real_tree_performance_not_hardcoded_pass(self):
        """When eval_fn is None, Consolidator must evaluate tree empirical pass rate, rejecting failing trees."""
        bank = AdapterBank(db_path=":memory:")
        gate = RegressionGate()
        consolidator = Consolidator(adapter_bank=bank, regression_gate=gate)

        # Build a discovery tree where 2 succeeded but 8 failed (20% pass rate, well below 80% min_accuracy)
        failing_tree = DiscoveryTree(task_id="failing_family_task")
        r = failing_tree.add_node("propose", {}, cost=1.0)
        failing_tree.add_node("verify", {"code": "x"}, parent_id=r, cost=1.0, outcome="verified")
        failing_tree.add_node("verify", {"code": "y"}, parent_id=r, cost=1.0, outcome="verified")
        for _ in range(8):
            failing_tree.add_node("falsify", {}, parent_id=r, cost=1.0, outcome="falsified")

        # Sleep cycle on poorly performing tree must be rejected by regression gate!
        res = consolidator.run_sleep_cycle(
            target_family="list_filtering",
            tree=failing_tree,
        )
        self.assertFalse(res.success)
        self.assertTrue(
            "rejected" in res.message.lower() or "failed" in res.message.lower(),
            f"Expected rejection or failure message, got: {res.message}",
        )

        bank.close()


if __name__ == "__main__":
    unittest.main()
