"""Tests for Discovery Tree and Replay Simulator (RSI)."""

import unittest

from eve3.discovery.tree import DiscoveryNode, DiscoveryTree, ReplaySimulator


class TestDiscoveryTree(unittest.TestCase):

    def test_discovery_tree_and_causal_replay(self):
        tree = DiscoveryTree(task_id="test_task_01")

        root_id = tree.add_node(
            action_type="propose",
            payload={"candidates": ["(reverse x)", "(map (lambda (a) (+ a 1)) x)"]},
            cost=1.0,
        )

        probe_id = tree.add_node(
            action_type="probe",
            payload={"probe": [1, 2], "observed": [2, 3]},
            parent_id=root_id,
            cost=0.5,
        )

        verify_id = tree.add_node(
            action_type="verify",
            payload={"code": "(map (lambda (a) (+ a 1)) x)"},
            parent_id=probe_id,
            cost=0.2,
            outcome="verified",
        )

        self.assertAlmostEqual(tree.total_cost(), 1.7)

        # Serialize & deserialize
        json_str = tree.to_json()
        reconstructed = DiscoveryTree.from_json(json_str)
        self.assertEqual(len(reconstructed.nodes), 3)

        # Replay simulation with causal dependencies:
        simulator = ReplaySimulator(tree)
        # Even if verification is assigned high priority, it cannot be reached without expanding root and probe first!
        res = simulator.evaluate_policy_sample_efficiency(
            policy_priority_fn=lambda node: 10.0 if node.action_type == "verify" else 1.0
        )
        self.assertTrue(res["found_verified"])
        # All 3 nodes along the path (root, probe, verify) must be expanded
        self.assertEqual(res["simulated_steps"], 3)
        self.assertAlmostEqual(res["simulated_cost"], 1.7)
        self.assertAlmostEqual(res["causal_path_cost"], 1.7)


if __name__ == "__main__":
    unittest.main()
