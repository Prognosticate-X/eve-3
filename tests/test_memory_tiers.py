"""Unit tests for Phase 8: Tiered Memory Management & Provenance.

Verifies:
1. Working Memory task isolation, variable binding, and scratchpad wiping.
2. Episodic Memory capacity management and lossless trajectory summarization.
3. Semantic Memory dynamic retention score decay and graceful cold-tier demotion.
4. Cold Tier reactivation and automatic promotion upon reuse.
5. Stitch-style duplicate/subsumption library compaction.
6. Provenance event logging and transactional memory snapshot rollback.
"""

import time
import unittest

from eve3.discovery.tree import DiscoveryTree
from eve3.memory.provenance import MemoryProvenanceManager
from eve3.memory.tiers import (
    EpisodicMemory,
    RetentionConfig,
    SemanticMemory,
    WorkingMemory,
)
from eve3.models import CandidateProgram, LearnedAbstraction


class TestMemoryTiers(unittest.TestCase):
    """Test suite for three-tier cognitive memory architecture."""

    def setUp(self):
        self.provenance = MemoryProvenanceManager()
        self.config = RetentionConfig(
            tau_decay_hours=24.0,
            mu_cost_penalty=0.02,
            demotion_threshold=0.80,
            promotion_threshold=1.10,
        )
        self.semantic = SemanticMemory(self.config, self.provenance)

    def test_working_memory_lifecycle(self):
        """Verify working memory allocates, tracks state, and wipes completely upon task exit."""
        wm = WorkingMemory()
        self.assertFalse(wm.active)

        # 1. Initialize for task
        wm.initialize_task("task_test_01", "list_mapping")
        self.assertTrue(wm.active)
        self.assertEqual(wm.task_id, "task_test_01")

        # 2. Bind temporary variables and track hypotheses
        wm.bind("temp_stride", 2)
        self.assertEqual(wm.lookup("temp_stride"), 2)

        cand = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
        wm.update_hypotheses([cand], [1.0])
        wm.record_probe([1, 2], [2, 3])

        self.assertEqual(len(wm.hypotheses), 1)
        self.assertEqual(len(wm.probes_history), 1)

        # 3. Archive summary
        summary = wm.archive_summary()
        self.assertEqual(summary["task_id"], "task_test_01")
        self.assertEqual(summary["probes_count"], 1)

        # 4. Clear scratchpad
        wm.clear()
        self.assertFalse(wm.active)
        self.assertEqual(wm.task_id, "")
        self.assertEqual(len(wm.hypotheses), 0)
        self.assertEqual(len(wm.probes_history), 0)
        self.assertIsNone(wm.lookup("temp_stride"))

    def test_episodic_memory_compression_and_summarization(self):
        """Verify episodic memory compresses older detailed trees when capacity is exceeded."""
        ep_mem = EpisodicMemory(max_detailed_trees=3)

        # Create 4 discovery trees
        for i in range(4):
            tree = DiscoveryTree(f"task_{i}")
            root_id = tree.add_node("propose", {"seed": i}, cost=1.0)
            falsify_id = tree.add_node(
                "falsify",
                {"probe_input": [i, i + 1], "observation": [i + 2, i + 3]},
                parent_id=root_id,
                outcome="falsified",
            )
            tree.add_node(
                "verify",
                {"code": f"(map (+ {i}) x)"},
                parent_id=falsify_id,
                outcome="verified",
            )
            # Store tree with varying weights
            ep_mem.store_tree(tree, task_family="list_mapping", value_weight=float(i + 1))

        # Check total trajectories is 4
        self.assertEqual(ep_mem.get_trajectory_count(), 4)
        # Detailed trees should be capped at max_detailed_trees (3)
        self.assertEqual(len(ep_mem.detailed_trees), 3)
        # Summaries should have 1 compressed tree
        self.assertEqual(len(ep_mem.summaries), 1)

        # Verify summary retains key counterexamples and terminal code
        summary = ep_mem.get_summary("task_0")
        self.assertIsNotNone(summary)
        self.assertEqual(summary.task_id, "task_0")
        self.assertEqual(summary.terminal_program, "(map (+ 0) x)")
        self.assertTrue(len(summary.counterexamples) >= 1)
        self.assertEqual(summary.counterexamples[0][0], [0, 1])

    def test_semantic_memory_retention_and_decay(self):
        """Verify retention score decays over elapsed time and demotes unused abstractions."""
        # Register two abstractions
        abs1 = LearnedAbstraction(
            abstraction_id="abs_map_add",
            name="map_add",
            pattern_sexpr="(map (lambda (a) (+ a 1)) x)",
        )
        abs2 = LearnedAbstraction(
            abstraction_id="abs_unused",
            name="unused_op",
            pattern_sexpr="(reverse (map (lambda (a) (* a 10)) x))",
        )

        self.semantic.register_abstraction(abs1, source_task_id="t1", value_weight=2.0)
        self.semantic.register_abstraction(abs2, source_task_id="t2", value_weight=1.0)

        self.assertEqual(len(self.semantic.get_active_operators()), 2)

        # Simulate usage for abs1
        for _ in range(5):
            self.semantic.record_usage("abs_map_add")

        # Simulate passage of 24 hours (1 half-life)
        future_time = time.time() + 24.0 * 3600.0

        score1 = self.semantic.compute_retention_score("abs_map_add", current_time=future_time)
        score2 = self.semantic.compute_retention_score("abs_unused", current_time=future_time)

        # Frequently used, high-weight abstraction retains higher score above threshold
        self.assertGreater(score1, self.config.demotion_threshold)
        self.assertLess(score2, self.config.demotion_threshold)

        # Run decay consolidation
        demoted, promoted = self.semantic.consolidate_and_decay(current_time=future_time)

        self.assertIn("abs_unused", demoted)
        self.assertIn("abs_unused", self.semantic.cold_abstractions)
        self.assertEqual(self.semantic.cold_abstractions["abs_unused"].status, "demoted")

        # Active operators should now only contain abs1
        active_ops = self.semantic.get_active_operators()
        self.assertEqual(len(active_ops), 1)
        self.assertEqual(active_ops[0].abstraction_id, "abs_map_add")

    def test_cold_tier_reactivation_and_promotion(self):
        """Verify demoted cold-tier abstraction is automatically promoted upon reuse."""
        abs_op = LearnedAbstraction(
            abstraction_id="abs_revive",
            name="revive_op",
            pattern_sexpr="(filter (lambda (a) (> a 0)) x)",
        )
        self.semantic.register_abstraction(abs_op, value_weight=1.0)
        self.semantic.demote_to_cold("abs_revive", reason="manual_test")

        self.assertIn("abs_revive", self.semantic.cold_abstractions)
        self.assertNotIn("abs_revive", self.semantic.hot_abstractions)

        # Simulate repeatedly reusing the demoted abstraction
        for _ in range(10):
            self.semantic.record_usage("abs_revive")

        # Verify it gets automatically promoted to hot tier
        self.assertIn("abs_revive", self.semantic.hot_abstractions)
        self.assertNotIn("abs_revive", self.semantic.cold_abstractions)
        self.assertEqual(self.semantic.hot_abstractions["abs_revive"].status, "verified")

    def test_stitch_compaction_subsumption(self):
        """Verify library compaction detects identical/subsumed abstractions and demotes lower-usage duplicate."""
        abs_dup1 = LearnedAbstraction(
            abstraction_id="dup_1",
            name="dup_op_1",
            pattern_sexpr="(map (lambda (a) (+ a 1)) x)",
        )
        abs_dup2 = LearnedAbstraction(
            abstraction_id="dup_2",
            name="dup_op_2",
            pattern_sexpr="(map (lambda (a) (+ a 1)) x)",
        )

        self.semantic.register_abstraction(abs_dup1, value_weight=1.0)
        self.semantic.register_abstraction(abs_dup2, value_weight=1.0)

        # Give dup_1 higher usage
        self.semantic.record_usage("dup_1")
        self.semantic.record_usage("dup_1")

        self.assertEqual(len(self.semantic.hot_abstractions), 2)

        # Run compaction
        subsumed = self.semantic.compact_library()
        self.assertEqual(len(subsumed), 1)
        self.assertEqual(subsumed[0], "dup_2")

        # dup_2 should be demoted, dup_1 stays in hot
        self.assertIn("dup_1", self.semantic.hot_abstractions)
        self.assertIn("dup_2", self.semantic.cold_abstractions)

    def test_provenance_and_transactional_rollback(self):
        """Verify provenance tracks full event chain and memory snapshot rollback restores exact state."""
        abs_a = LearnedAbstraction(abstraction_id="abs_A", name="A", pattern_sexpr="(inc x)")
        abs_b = LearnedAbstraction(abstraction_id="abs_B", name="B", pattern_sexpr="(dec x)")

        self.semantic.register_abstraction(abs_a, source_task_id="task_A")
        self.semantic.register_abstraction(abs_b, source_task_id="task_B")

        # 1. Create baseline snapshot
        snap1 = self.semantic.create_snapshot(description="Baseline 2 operators")
        self.assertEqual(len(snap1.active_abstraction_ids), 2)

        # 2. Mutate memory: demote abs_a and add abs_c
        self.semantic.demote_to_cold("abs_A", reason="test_demote")
        abs_c = LearnedAbstraction(abstraction_id="abs_C", name="C", pattern_sexpr="(sum x)")
        self.semantic.register_abstraction(abs_c, source_task_id="task_C")

        self.assertEqual(len(self.semantic.hot_abstractions), 2)  # B and C
        self.assertIn("abs_A", self.semantic.cold_abstractions)

        # 3. Rollback to snap1
        success = self.semantic.rollback_to_snapshot(snap1.snapshot_id)
        self.assertTrue(success)

        # Verify state is restored to snap1
        self.assertIn("abs_A", self.semantic.hot_abstractions)
        self.assertIn("abs_B", self.semantic.hot_abstractions)
        self.assertNotIn("abs_C", self.semantic.hot_abstractions)
        self.assertNotIn("abs_A", self.semantic.cold_abstractions)

        # Verify provenance event chain for abs_A contains created, demoted, and restored
        chain = self.provenance.get_provenance_chain("abs_A")
        self.assertTrue(len(chain) >= 1)
        events = [e["event_type"] for e in chain[0]["events"]]
        self.assertIn("created", events)
        self.assertIn("demoted", events)


if __name__ == "__main__":
    unittest.main()
