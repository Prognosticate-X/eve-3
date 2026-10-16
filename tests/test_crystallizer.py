"""Tests for System 3 SQLite Knowledge Base and Value-Weighted Compression."""

from pathlib import Path
import tempfile
import unittest

from eve3.system1_proposer.sandbox import CandidateProgram
from eve3.system3_crystallizer.library import KnowledgeLibrary
from eve3.system3_crystallizer.value_compressor import CandidateAbstraction, ValueCompressor


class TestCrystallizer(unittest.TestCase):

    def test_sqlite_library_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_knowledge.sqlite"
            lib = KnowledgeLibrary(db_path)

            prog = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
            pid = lib.record_verified_program(prog, task_family="list_mapping")
            self.assertIsNotNone(pid)

            # Record again to trigger reuse update
            pid2 = lib.record_verified_program(prog, task_family="list_mapping")
            self.assertEqual(pid, pid2)

            progs = lib.get_all_verified_programs()
            self.assertEqual(len(progs), 1)
            self.assertEqual(progs[0]["verification_count"], 2)
            self.assertEqual(progs[0]["reuse_count"], 1)

    def test_dynamic_pattern_mining_and_value_weighted_selection(self):
        compressor = ValueCompressor(gamma=0.5)

        programs = [
            {"code": "(map (lambda (a) (+ a 1)) x)", "description_length": 10, "reuse_count": 5, "task_family": "family_a"},
            {"code": "(map (lambda (a) (+ a 2)) x)", "description_length": 10, "reuse_count": 3, "task_family": "family_b"},
            {"code": "(reverse x)", "description_length": 2, "reuse_count": 0, "task_family": "family_c"},
        ]

        # Dynamically mine abstractions from program ASTs
        mined_candidates = compressor.extract_candidate_abstractions(programs)
        self.assertGreater(len(mined_candidates), 0)

        # Select optimal library via submodular greedy search
        selected = compressor.select_optimal_library(mined_candidates, programs)
        self.assertGreater(len(selected), 0)
        # Verify selected operator provides real AST DL savings
        selected_patterns = [a.pattern for a in selected]
        self.assertTrue(any("map" in p for p in selected_patterns))


if __name__ == "__main__":
    unittest.main()
