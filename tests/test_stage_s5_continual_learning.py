"""Tests for Stage S5 Task S5.3: Continual Learning, Library Composition, and Forward Transfer (H15/H18)."""

import tempfile
import unittest
from pathlib import Path

from eve3.config import EveConfig
from eve3.models import LearnedAbstraction
from eve3.search.controller import SearchController
from eve3.system1_proposer.sandbox import ProgramSandbox
from eve3.system2_falsifier.cegis_loop import CEGISLoop
from eve3.system3_crystallizer.library import KnowledgeLibrary
from experiments.run_continual_learning import run_continual_learning_experiment


class TestStageS5ContinualLearning(unittest.TestCase):

    def test_search_controller_generates_compositional_library_candidates(self):
        """SearchController must compose crystallized operators with reduction/structural primitives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb_path = Path(tmpdir) / "test_comp_kb.db"
            kb = KnowledgeLibrary(kb_path)

            # Record an operator that filters even numbers
            abs_filter = LearnedAbstraction(
                name="op_evens_only",
                pattern_sexpr="(filter (lambda (a) (is_even a)) x)",
                applicable_task_families=["list_filtering"],
            )
            kb.record_learned_abstraction(abs_filter)

            cfg = EveConfig()
            controller = SearchController(config=cfg, knowledge_library=kb)

            # Test task: filter even numbers and sum
            examples = [
                ([1, 2, 3, 4], 6),
                ([2, 4, 6], 12),
            ]

            proposals = controller.propose_candidates(
                examples=examples,
                strategy="library_only",
            )

            proposal_codes = [p.code_str for p in proposals]
            self.assertIn(
                "(sum (op_evens_only x))",
                proposal_codes,
                f"Expected '(sum (op_evens_only x))' in library proposals, got: {proposal_codes}",
            )

    def test_run_continual_learning_under_generic_enumeration_mode(self):
        """Continual learning experiment under generic_enumeration (non-leaky) must achieve positive FWT."""
        results = run_continual_learning_experiment(proposer_mode="generic_enumeration")

        # Must meet all preregistered criteria
        self.assertLessEqual(results["bwt_forgetting_pct"], 2.0)
        self.assertLessEqual(results["general_drop_pct"], 3.0)
        self.assertGreaterEqual(results["fwt_delta"], 10.0)


if __name__ == "__main__":
    unittest.main()
