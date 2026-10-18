"""Tests for AdapterBank Routing, Versioning, and Rollback."""

import unittest

from eve3.plasticity.adapter_bank import AdapterBank
from eve3.plasticity.regression_gate import GateResult


class TestAdapterBankRollback(unittest.TestCase):

    def setUp(self):
        self.bank = AdapterBank(db_path=":memory:")

    def tearDown(self):
        self.bank.close()

    def test_routing_by_hint_and_semantics(self):
        # Register and commit an adapter for list_mapping
        ad_id = self.bank.create(family="list_mapping")
        pass_gate = GateResult(
            passed=True,
            family_scores={"list_mapping": 1.0},
            historical_family_scores={},
            family_regressions={},
            general_probe_score=1.0,
            baseline_general_probe_score=1.0,
            false_verification_rate=0.0,
            overall_accuracy=1.0,
        )
        self.bank.commit(ad_id, pass_gate)

        # Route by explicit hint
        routed_1 = self.bank.route("arbitrary prompt", family_hint="list_mapping")
        self.assertEqual(routed_1, ad_id)

        # Route by semantic keywords
        routed_2 = self.bank.route("Increment each element in list by one")
        self.assertEqual(routed_2, ad_id)

        # Unmatched returns None (falls back to base model)
        routed_none = self.bank.route("some random text", family_hint="unknown_family")
        self.assertIsNone(routed_none)

    def test_commit_failure_when_gate_rejected(self):
        ad_id = self.bank.create(family="list_filtering")
        fail_gate = GateResult(
            passed=False,
            family_scores={"list_filtering": 0.5},
            historical_family_scores={"list_filtering": 0.9},
            family_regressions={"list_filtering": 40.0},
            general_probe_score=1.0,
            baseline_general_probe_score=1.0,
            false_verification_rate=0.0,
            overall_accuracy=0.5,
            rejection_reasons=["Severe regression on list_filtering"],
        )
        with self.assertRaises(ValueError):
            self.bank.commit(ad_id, fail_gate)

        meta = self.bank.get_adapter(ad_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.status, "reverted")

    def test_snapshot_and_rollback_flow(self):
        # Step 1: Base snapshot is version 1
        initial_snap = self.bank.snapshot(description="Base checkpoint")
        initial_ver = initial_snap.version_id

        # Step 2: Add and activate adapter A
        ad_a = self.bank.create(family="list_reduction")
        pass_gate = GateResult(
            passed=True,
            family_scores={"list_reduction": 1.0},
            historical_family_scores={},
            family_regressions={},
            general_probe_score=1.0,
            baseline_general_probe_score=1.0,
            false_verification_rate=0.0,
            overall_accuracy=1.0,
        )
        snap_after_a = self.bank.commit(ad_a, pass_gate)
        self.assertEqual(self.bank.get_active_adapter("list_reduction").adapter_id, ad_a)

        # Step 3: Rollback to initial snapshot
        success = self.bank.rollback(initial_ver)
        self.assertTrue(success)

        # After rollback, no active adapter for list_reduction
        self.assertIsNone(self.bank.get_active_adapter("list_reduction"))
        meta_a = self.bank.get_adapter(ad_a)
        self.assertEqual(meta_a.status, "reverted")


if __name__ == "__main__":
    unittest.main()
