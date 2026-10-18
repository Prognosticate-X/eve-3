"""Tests for Sleep Consolidation and Replay Distribution."""

import time
import unittest

from eve3.discovery.tree import DiscoveryTree
from eve3.plasticity.adapter_bank import AdapterBank
from eve3.plasticity.consolidator import Consolidator, ConsolidationConfig
from eve3.plasticity.regression_gate import RegressionGate


class TestConsolidator(unittest.TestCase):

    def setUp(self):
        self.bank = AdapterBank(db_path=":memory:")
        self.gate = RegressionGate()
        self.consolidator = Consolidator(
            adapter_bank=self.bank,
            regression_gate=self.gate,
            config=ConsolidationConfig(min_verified_samples_to_trigger=2),
        )

    def tearDown(self):
        self.bank.close()

    def test_extract_samples_and_replay_probabilities(self):
        tree = DiscoveryTree(task_id="task_inc")
        now = time.time()

        # Add node 1 (verified)
        n1_id = tree.add_node(
            action_type="verify",
            payload={"code": "(map (lambda (a) (+ a 1)) x)", "task_family": "list_mapping"},
            cost=1.5,
            outcome="verified",
        )
        tree.nodes[n1_id].timestamp = now - 3600  # 1 hour ago

        # Add node 2 (falsified on task_inc)
        tree.add_node(
            action_type="falsify",
            payload={
                "code": "(map (lambda (a) (+ a 2)) x)",
                "task_id": "task_inc",
                "counterexample": "[0] -> expected [1], actual [2]",
            },
            cost=1.0,
            outcome="falsified",
        )

        # Add node 3 (verified on another task)
        n3_id = tree.add_node(
            action_type="verify",
            payload={"code": "(filter (lambda (a) (is_even a)) x)", "task_family": "list_filtering"},
            cost=2.0,
            outcome="verified",
        )
        tree.nodes[n3_id].timestamp = now - 7200  # 2 hours ago

        samples = self.consolidator.extract_samples_from_tree(tree, current_time=now)
        self.assertEqual(len(samples), 2)  # Two verified nodes

        # Check preference pair linking
        sample_inc = next(s for s in samples if "(+ a 1)" in s.target_code)
        self.assertIsNotNone(sample_inc.rejected_code)
        self.assertIn("(+ a 2)", sample_inc.rejected_code)

        # Compute replay probabilities
        probs = self.consolidator.compute_replay_probabilities(samples, current_time=now)
        self.assertEqual(len(probs), 2)
        self.assertAlmostEqual(sum(probs), 1.0, places=4)
        for p in probs:
            self.assertGreater(p, 0.0)

    def test_run_sleep_cycle_end_to_end(self):
        tree = DiscoveryTree(task_id="task_reduction")
        tree.add_node(
            action_type="verify",
            payload={"code": "(sum x)", "task_family": "list_reduction"},
            cost=1.0,
            outcome="verified",
        )
        tree.add_node(
            action_type="verify",
            payload={"code": "(length x)", "task_family": "list_reduction"},
            cost=1.2,
            outcome="verified",
        )

        res = self.consolidator.run_sleep_cycle(
            target_family="list_reduction",
            tree=tree,
            eval_fn=lambda: ({"list_reduction": 1.0}, 1.0, 0.0),
        )
        self.assertTrue(res.success)
        self.assertTrue(res.gate_result.passed)
        self.assertIsNotNone(self.bank.get_active_adapter("list_reduction"))

    def test_sample_replay_batch_and_mlx_dataset_formatting(self):
        tree1 = DiscoveryTree(task_id="t1")
        tree1.add_node(
            action_type="verify",
            payload={"code": "(map inc x)", "task_family": "list_mapping"},
            outcome="verified",
        )
        tree2 = DiscoveryTree(task_id="t2")
        tree2.add_node(
            action_type="verify",
            payload={"code": "(map dec x)", "task_family": "list_mapping"},
            outcome="verified",
        )
        tree3 = DiscoveryTree(task_id="t3")
        tree3.add_node(
            action_type="verify",
            payload={"code": "(filter is_even x)", "task_family": "list_filtering"},
            outcome="verified",
        )

        all_samples = self.consolidator.extract_all_samples([tree1, tree2, tree3])
        self.assertEqual(len(all_samples), 3)

        # Sample 2 from 3
        replay_batch = self.consolidator.sample_replay_batch(all_samples, n=2, random_seed=42)
        self.assertEqual(len(replay_batch), 2)

        # Format into MLX pairs
        mlx_data = self.consolidator.format_mlx_dataset(replay_batch)
        self.assertEqual(len(mlx_data), 2)
        for item in mlx_data:
            self.assertIn("prompt", item)
            self.assertIn("completion", item)
            self.assertIn("<|im_start|>", item["prompt"])

        # Compute surrogate loss
        loss_dict = self.consolidator.compute_surrogate_loss(
            new_samples=all_samples[:2],
            replay_samples=all_samples[2:],
            kl_penalty=0.05,
        )
        self.assertIn("loss_total", loss_dict)
        self.assertIn("loss_sft_new", loss_dict)
        self.assertIn("loss_replay", loss_dict)
        self.assertGreater(loss_dict["loss_total"], 0.0)


if __name__ == "__main__":
    unittest.main()
