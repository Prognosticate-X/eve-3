"""Tests for Stage S5 Task S5.1: Discovery Tree Support Coverage, Evaluatability, and Importance Sampling (H16)."""

import math
import unittest

from eve3.discovery.policy import ExplorationPolicy
from eve3.discovery.tree import DiscoveryNode, DiscoveryTree, ReplaySimulator


class TestStageS5TreeSupport(unittest.TestCase):

    def test_backward_compatibility_of_simulator_output_keys(self):
        """Ensure all pre-existing keys in evaluate_policy result dictionary are preserved."""
        tree = DiscoveryTree(task_id="compat_tree")
        r = tree.add_node("propose", {"candidates": ["x"]}, cost=1.0)
        v = tree.add_node("verify", {"code": "x"}, parent_id=r, cost=0.2, outcome="verified")

        sim = ReplaySimulator(tree)
        res = sim.evaluate_policy(ExplorationPolicy())

        # Original keys must exist and match expected types
        self.assertIn("found_verified", res)
        self.assertIn("simulated_cost", res)
        self.assertIn("simulated_steps", res)
        self.assertIn("causal_path_cost", res)
        self.assertIn("tree_total_cost", res)

        self.assertTrue(res["found_verified"])
        self.assertEqual(res["simulated_steps"], 2)
        self.assertAlmostEqual(res["simulated_cost"], 1.2)

        # Stage S5 new keys must exist
        self.assertIn("evaluatable", res)
        self.assertIn("status", res)
        self.assertIn("support_coverage", res)
        self.assertIn("is_weights", res)
        self.assertIn("effective_sample_size", res)
        self.assertIn("weight_variance", res)

    def test_unsupported_tree_without_verification_marked_out_of_support(self):
        """A linear tree with no verified node or missing policy preferred actions must be marked out_of_support."""
        tree = DiscoveryTree(task_id="unsupported_tree")
        r = tree.add_node("propose", {"candidates": ["x"]}, cost=1.0)
        p1 = tree.add_node("probe", {"input": 1}, parent_id=r, cost=0.5, outcome="falsified")
        p2 = tree.add_node("probe", {"input": 2}, parent_id=p1, cost=0.5, outcome="falsified")

        # Tree terminates without any verify node
        sim = ReplaySimulator(tree)
        # Policy specifically seeks verification
        pol = ExplorationPolicy(name="verify_seeker", verification_priority_weight=10.0)
        res = sim.evaluate_policy(pol)

        self.assertFalse(res["found_verified"])
        self.assertFalse(res["evaluatable"])
        self.assertEqual(res["status"], "out_of_support")
        self.assertLess(res["support_coverage"], 1.0)

    def test_branching_tree_produces_differentiated_policy_decisions(self):
        """On a tree with branching alternatives, different policies must make different choices and achieve different costs."""
        tree = DiscoveryTree(task_id="branching_tree")
        root_id = tree.add_node("propose", {"candidates": ["x", "(reverse x)"]}, cost=1.0)

        # Branch A: Verification-first path (direct verify node from root)
        v_direct = tree.add_node(
            "verify", {"code": "x"}, parent_id=root_id, cost=0.3, outcome="verified"
        )

        # Branch B: Probe-first path (probe from root, then verify)
        p_node = tree.add_node(
            "probe", {"input": [1, 2]}, parent_id=root_id, cost=0.8, outcome="success"
        )
        v_delayed = tree.add_node(
            "verify", {"code": "(reverse x)"}, parent_id=p_node, cost=0.2, outcome="verified"
        )

        # Policy 1: verification_first (strongly prefers verify over probe)
        pol_verify = ExplorationPolicy(
            name="verification_first",
            verification_priority_weight=10.0,
            probe_priority_weight=0.1,
        )

        # Policy 2: probe_first (prefers probing over verification)
        pol_probe = ExplorationPolicy(
            name="probe_first",
            verification_priority_weight=0.1,
            probe_priority_weight=10.0,
        )

        sim = ReplaySimulator(tree)
        res_verify = sim.evaluate_policy(pol_verify)
        res_probe = sim.evaluate_policy(pol_probe)

        # Both must find verified node and be evaluatable
        self.assertTrue(res_verify["found_verified"])
        self.assertTrue(res_verify["evaluatable"])
        self.assertEqual(res_verify["status"], "evaluatable")

        self.assertTrue(res_probe["found_verified"])
        self.assertTrue(res_probe["evaluatable"])
        self.assertEqual(res_probe["status"], "evaluatable")

        # The two policies must NOT have the exact same steps and cost!
        self.assertNotEqual(
            res_verify["simulated_cost"],
            res_probe["simulated_cost"],
            "Policies with opposing priorities must have different costs on a branching tree",
        )
        self.assertNotEqual(
            res_verify["simulated_steps"],
            res_probe["simulated_steps"],
            "Verification-first should take fewer steps (2) than probe-first (3)",
        )
        self.assertEqual(res_verify["simulated_steps"], 2)  # root -> v_direct
        self.assertEqual(res_probe["simulated_steps"], 3)   # root -> p_node -> v_delayed

    def test_importance_sampling_weights_and_ess_calculation(self):
        """Verify that IS weights and effective sample size (ESS) are mathematically sound."""
        tree = DiscoveryTree(task_id="is_tree")
        root_id = tree.add_node("propose", {}, cost=1.0)
        c1 = tree.add_node("verify", {}, parent_id=root_id, cost=0.5, outcome="verified")
        c2 = tree.add_node("probe", {}, parent_id=root_id, cost=0.5, outcome="success")

        sim = ReplaySimulator(tree)
        pol = ExplorationPolicy(verification_priority_weight=5.0, probe_priority_weight=1.0)
        res = sim.evaluate_policy(pol)

        # Decision at root has 2 candidates: c1 (verify, score ~5.0) and c2 (probe, score ~1.0)
        # Softmax p(verify) > 0.5. Behavior policy mu = 1/2 = 0.5.
        # Step weight w = p / mu = 2 * p > 1.0.
        self.assertGreater(len(res["is_weights"]), 0)
        for w in res["is_weights"]:
            self.assertGreater(w, 0.0)

        # ESS should be a positive finite float <= len(is_weights)
        self.assertGreater(res["effective_sample_size"], 0.0)
        self.assertFalse(math.isnan(res["effective_sample_size"]))
        self.assertFalse(math.isinf(res["effective_sample_size"]))


if __name__ == "__main__":
    unittest.main()
