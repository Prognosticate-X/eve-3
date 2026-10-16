"""Tests for ExplorationPolicy and policy-driven replay simulation."""

import unittest

from eve3.discovery.policy import ExplorationPolicy
from eve3.discovery.tree import DiscoveryTree, ReplaySimulator


class TestPolicy(unittest.TestCase):

    def test_policy_scoring(self):
        pol = ExplorationPolicy(
            probe_cost_penalty_lambda=0.1,
            verification_priority_weight=5.0,
            probe_priority_weight=1.0,
            proposal_priority_weight=0.5,
        )

        score_v = pol.score_node("verify", cost=1.0)
        score_p = pol.score_node("probe", cost=1.0)
        score_prop = pol.score_node("propose", cost=1.0)

        self.assertGreater(score_v, score_p)
        self.assertGreater(score_p, score_prop)

    def test_simulator_policy_evaluation(self):
        tree = DiscoveryTree("test_pol_eval")
        r = tree.add_node("propose", payload={}, cost=1.0)
        p = tree.add_node("probe", payload={}, parent_id=r, cost=0.5)
        v = tree.add_node("verify", payload={}, parent_id=p, cost=0.2, outcome="verified")

        pol = ExplorationPolicy()
        sim = ReplaySimulator(tree)
        result = sim.evaluate_policy(pol)

        self.assertTrue(result["found_verified"])
        self.assertEqual(result["simulated_steps"], 3)
        self.assertAlmostEqual(result["causal_path_cost"], 1.7)


if __name__ == "__main__":
    unittest.main()
