"""Unit tests for Phase 7: Autonomous Discovery & Curriculum (Explorer).

Verifies:
1. Operator combination and parameter mutation task generation.
2. Complex / failed task decomposition into sub-goals.
3. Zone of Proximal Development (ZPD) learnability filtering [0.2, 0.8].
4. Multi-objective curriculum scoring (IG, Compression, Learning Progress, Redundancy).
5. Clustering coverage entropy and anti-collapse guardrail triggers.
6. Property-based metamorphic blindspot testing.
"""

from pathlib import Path
import tempfile
import unittest

from eve3.dsl.interpreter import DSLInterpreter, SExprParser
from eve3.explorer.coverage import CoverageConfig, CoverageGuard, MetamorphicValidator
from eve3.explorer.curriculum import Curriculum, CurriculumConfig
from eve3.models import CandidateProgram, Task
from eve3.system3_crystallizer.library import KnowledgeLibrary


class TestCurriculumFilter(unittest.TestCase):
    """Test suite for curriculum generation, learnability filtering, and coverage guards."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_kb.db"
        self.kb = KnowledgeLibrary(self.db_path)
        self.curriculum = Curriculum(seed=123)
        self.guard = CoverageGuard()
        self.validator = MetamorphicValidator()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_task_generation_and_mutation(self):
        """Verify operator combination and mutation generates executable, valid tasks."""
        tasks = self.curriculum.propose_from_operators(self.kb, n=3)
        self.assertEqual(len(tasks), 3)

        interpreter = DSLInterpreter()
        for task in tasks:
            self.assertEqual(task.source, "mutation")
            self.assertTrue(len(task.visible_examples) >= 2)
            self.assertTrue(len(task.hidden_tests) >= 2)
            self.assertIsNotNone(task.reference_program)

            # Verify that reference program executes and matches the generated outputs
            ast = SExprParser.parse(task.reference_program)
            for ex in task.visible_examples:
                actual = interpreter.run(ast, ex["input"])
                self.assertEqual(actual, ex["output"])
            for ex in task.hidden_tests:
                actual = interpreter.run(ast, ex["input"])
                self.assertEqual(actual, ex["output"])

    def test_task_decomposition(self):
        """Verify decomposition breaks complex composite task into learnable sub-goals."""
        parent_task = Task(
            task_id="comp_parent_01",
            task_family="list_composition",
            description="Filter positive numbers and increment",
            visible_examples=[
                {"input": [1, -2, 3], "output": [2, 4]},
                {"input": [0, -5], "output": []},
            ],
            hidden_tests=[
                {"input": [10, -10, 5], "output": [11, 6]},
            ],
            reference_program="(map (lambda (a) (+ a 1)) (filter (lambda (a) (> a 0)) x))",
        )

        sub_tasks = self.curriculum.propose_from_decomposition([parent_task], max_tasks=1)
        self.assertEqual(len(sub_tasks), 1)
        sub = sub_tasks[0]
        self.assertEqual(sub.source, "decomposition")
        self.assertEqual(sub.metadata.get("parent_task_id"), "comp_parent_01")
        self.assertEqual(sub.reference_program, "(filter (lambda (a) (> a 0)) x)")

        # Verify sub-goal I/O is correct
        interpreter = DSLInterpreter()
        sub_ast = SExprParser.parse(sub.reference_program)
        for ex in sub.visible_examples:
            out = interpreter.run(sub_ast, ex["input"])
            self.assertEqual(out, ex["output"])

    def test_learnability_filter(self):
        """Verify learnability filter rejects trivial and impossible tasks, keeping moderate."""
        # 1. Trivial task (depth 1, simple base operation)
        trivial_task = Task(
            task_id="trivial_01",
            task_family="list_mapping",
            description="Simple increment",
            visible_examples=[{"input": [1], "output": [2]}],
            hidden_tests=[{"input": [2], "output": [3]}],
            reference_program="(inc x)",
            metadata={"ast_depth": 1, "ast_nodes": 2},
        )
        self.curriculum.family_outcomes["list_mapping"] = [True] * 10
        p_trivial = self.curriculum.estimate_difficulty(trivial_task)
        self.assertGreater(p_trivial, 0.80)
        self.assertFalse(self.curriculum.learnable(trivial_task))

        # 2. Impossible task (extreme depth and complex nested nodes)
        impossible_task = Task(
            task_id="impossible_01",
            task_family="list_composition",
            description="Deep nested fold",
            visible_examples=[{"input": [1], "output": [2]}],
            hidden_tests=[{"input": [2], "output": [3]}],
            reference_program="(map (lambda (a) (+ a 1)) (filter (lambda (b) (> b 0)) (reverse x)))",
            metadata={"ast_depth": 6, "ast_nodes": 16},
        )
        self.curriculum.family_outcomes["list_composition"] = [False] * 10
        p_impossible = self.curriculum.estimate_difficulty(impossible_task)
        self.assertLess(p_impossible, 0.20)
        self.assertFalse(self.curriculum.learnable(impossible_task))

        # 3. Moderate learnable task (in the Zone of Proximal Development)
        moderate_task = Task(
            task_id="moderate_01",
            task_family="list_mapping",
            description="Map add two",
            visible_examples=[{"input": [1, 2], "output": [3, 4]}],
            hidden_tests=[{"input": [5], "output": [7]}],
            reference_program="(map (lambda (a) (+ a 2)) x)",
            metadata={"ast_depth": 3, "ast_nodes": 6},
        )
        self.curriculum.family_outcomes["list_mapping"] = [True, False, True, False]
        p_moderate = self.curriculum.estimate_difficulty(moderate_task)
        self.assertTrue(0.20 <= p_moderate <= 0.80)
        self.assertTrue(self.curriculum.learnable(moderate_task))

    def test_multi_objective_scoring(self):
        """Verify multi-objective score computation and redundancy penalization."""
        task1 = Task(
            task_id="score_task_01",
            task_family="list_mapping",
            description="Transform list elements",
            visible_examples=[
                {"input": [-2, 0, 5], "output": [-1, 1, 6]},
                {"input": [10, -5], "output": [11, -4]},
            ],
            hidden_tests=[{"input": [], "output": []}],
            reference_program="(map (lambda (a) (+ a 1)) x)",
        )

        score_fresh = self.curriculum.score(task1)
        self.assertTrue(0.0 <= score_fresh <= 1.0)

        # Simulate repeatedly recording task1 to create high redundancy
        for _ in range(15):
            self.curriculum.record_task_outcome(task1, success=True)

        score_redundant = self.curriculum.score(task1)
        # Redundant task score should be penalized compared to when it was fresh
        self.assertLess(score_redundant, score_fresh)

    def test_coverage_clustering_entropy(self):
        """Verify cluster entropy calculation over diverse vs homogeneous task sets."""
        # 1. Homogeneous task set (all identical mapping tasks)
        homogeneous_tasks = [
            Task(
                task_id=f"homo_{i}",
                task_family="list_mapping",
                description="Increment by 1",
                visible_examples=[{"input": [1, 2], "output": [2, 3]}],
                hidden_tests=[],
                metadata={"ast_depth": 2},
            )
            for i in range(10)
        ]
        h_collapsed = self.guard.compute_clustering_entropy(homogeneous_tasks)
        self.assertLess(h_collapsed, 0.20)

        # 2. Diverse task set across different families and output types
        diverse_tasks = [
            Task(task_id="div_0", task_family="list_mapping", description="map", visible_examples=[{"input": [1], "output": [2]}], hidden_tests=[], metadata={"ast_depth": 2}),
            Task(task_id="div_1", task_family="list_filtering", description="filter", visible_examples=[{"input": [-2, 3], "output": [3]}], hidden_tests=[], metadata={"ast_depth": 2}),
            Task(task_id="div_2", task_family="list_reduction", description="sum", visible_examples=[{"input": [1, 2], "output": 3}], hidden_tests=[], metadata={"ast_depth": 2}),
            Task(task_id="div_3", task_family="list_structural", description="rev", visible_examples=[{"input": [1, 2], "output": [2, 1]}], hidden_tests=[], metadata={"ast_depth": 2}),
            Task(task_id="div_4", task_family="list_composition", description="comp", visible_examples=[{"input": [1, 2], "output": 10}], hidden_tests=[], metadata={"ast_depth": 4}),
        ]
        h_diverse = self.guard.compute_clustering_entropy(diverse_tasks)
        self.assertGreater(h_diverse, 0.50)

    def test_anti_collapse_guardrail(self):
        """Verify guardrails detect excessive synthetic ratio and entropy collapse."""
        # Case A: Synthetic ratio exceeds 60%
        tasks_high_synth = [
            Task(task_id=f"t_{i}", task_family="list_mapping", description="", visible_examples=[], hidden_tests=[], source="mutation")
            for i in range(8)
        ] + [
            Task(task_id=f"t_{i}", task_family="list_mapping", description="", visible_examples=[], hidden_tests=[], source="anchor")
            for i in range(2)
        ]
        status_synth = self.guard.check_guardrails(tasks_high_synth)
        self.assertFalse(status_synth.passed)
        self.assertEqual(status_synth.recommended_action, "boost_anchor_injection")
        self.assertEqual(status_synth.synthetic_ratio, 0.80)

        # Case B: Balanced tasks pass guardrails
        tasks_balanced = [
            Task(task_id="b_0", task_family="list_mapping", description="", visible_examples=[{"input": [1], "output": [2]}], hidden_tests=[], source="mutation", metadata={"ast_depth": 2}),
            Task(task_id="b_1", task_family="list_filtering", description="", visible_examples=[{"input": [-1, 2], "output": [2]}], hidden_tests=[], source="anchor", metadata={"ast_depth": 2}),
            Task(task_id="b_2", task_family="list_reduction", description="", visible_examples=[{"input": [1, 2], "output": 3}], hidden_tests=[], source="anchor", metadata={"ast_depth": 2}),
            Task(task_id="b_3", task_family="list_structural", description="", visible_examples=[{"input": [1, 2], "output": [2, 1]}], hidden_tests=[], source="anchor", metadata={"ast_depth": 2}),
            Task(task_id="b_4", task_family="list_composition", description="", visible_examples=[{"input": [1, 2], "output": 10}], hidden_tests=[], source="mutation", metadata={"ast_depth": 4}),
        ]
        status_balanced = self.guard.check_guardrails(tasks_balanced)
        self.assertTrue(status_balanced.passed)
        self.assertEqual(status_balanced.recommended_action, "ok")

    def test_metamorphic_validator(self):
        """Verify property-based metamorphic tests validate program generalizability."""
        # 1. Valid program: (map (lambda (a) (+ a 1)) x)
        valid_cand = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
        mapping_task = Task(
            task_id="map_task",
            task_family="list_mapping",
            description="Increment by 1",
            visible_examples=[],
            hidden_tests=[],
        )
        passed, reason = self.validator.validate_program_blindspots(valid_cand, mapping_task)
        self.assertTrue(passed)
        self.assertIsNone(reason)

        # 2. Defective program that violates empty list handling or output type
        buggy_cand = CandidateProgram("(sum x)")  # Returns int instead of list for mapping
        passed_buggy, reason_buggy = self.validator.validate_program_blindspots(buggy_cand, mapping_task)
        self.assertFalse(passed_buggy)
        self.assertIsNotNone(reason_buggy)


if __name__ == "__main__":
    unittest.main()
