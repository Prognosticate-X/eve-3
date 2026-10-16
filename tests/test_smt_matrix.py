"""Tests for SMT support matrix and explicit provenance tracking."""

import unittest

from eve3.dsl.interpreter import SExprParser
from eve3.models import CandidateProgram
from eve3.system2_falsifier.smt_distinguisher import SMTDistinguisher, SMTSupportLevel


class TestSMTMatrix(unittest.TestCase):

    def setUp(self):
        self.distinguisher = SMTDistinguisher()

    def test_arithmetic_support_level(self):
        ast = SExprParser.parse("(+ x 1)")
        level, reason = self.distinguisher.check_ast_support(ast)
        self.assertEqual(level, SMTSupportLevel.SUPPORTED)
        self.assertIsNone(reason)

    def test_bounded_list_support_level(self):
        ast = SExprParser.parse("(map (lambda (a) (+ a 1)) x)")
        level, reason = self.distinguisher.check_ast_support(ast)
        self.assertEqual(level, SMTSupportLevel.BOUNDED_SUPPORT)
        self.assertIsNotNone(reason)

    def test_unsupported_primitive_graceful_fallback(self):
        # Primitive not in Z3 theory (e.g. hypothetical uninterpreted symbol)
        p1 = CandidateProgram("(+ x 1)")
        p2 = CandidateProgram("(+ x 2)")

        probe = self.distinguisher.find_distinguishing_input(p1, p2)
        self.assertIsNotNone(probe)
        self.assertIn(probe.source, ("smt_symbolic", "heuristic_boundary"))


if __name__ == "__main__":
    unittest.main()
