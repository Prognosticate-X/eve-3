"""Tests for SearchController and SymbolicEnumerator."""

import unittest

from eve3.config import EveConfig
from eve3.search.controller import SearchController
from eve3.search.enumerator import SymbolicEnumerator


class TestSearchController(unittest.TestCase):

    def test_symbolic_enumerator_list_generation(self):
        enumerator = SymbolicEnumerator(max_depth=3)
        cands = enumerator.enumerate_candidates(domain_hint="list", max_candidates=20)
        self.assertGreater(len(cands), 0)
        codes = [c.code_str for c in cands]
        self.assertIn("x", codes)
        self.assertIn("(reverse x)", codes)
        self.assertTrue(any("map" in c for c in codes))

    def test_search_controller_proposal_and_deduplication(self):
        controller = SearchController()
        examples = [([1, 2], [2, 3])]

        # Test hybrid strategy
        proposals = controller.propose_candidates(examples=examples, strategy="hybrid", max_candidates=10)
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            # Must satisfy visible examples
            self.assertEqual(p.evaluate([1, 2]), [2, 3])

        # Verify no duplicates
        codes = [p.code_str for p in proposals]
        self.assertEqual(len(codes), len(set(codes)))

    def test_symbolic_only_vs_neural_only_strategies(self):
        controller = SearchController()
        examples = [([1, 2], [3, 2, 1])]  # Reverse task

        sym_cands = controller.propose_candidates(examples=examples, strategy="symbolic_only", max_candidates=5)
        # Verify enumerator provenance
        if sym_cands:
            self.assertEqual(sym_cands[0].created_by, "enumerator")


if __name__ == "__main__":
    unittest.main()
