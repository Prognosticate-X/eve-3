"""Tests for DSL S-expression parser and interpreter runtime."""

import unittest

from eve3.dsl.ast import ApplyNode, ConstNode, ExecutionStepLimitExceeded, VarNode
from eve3.dsl.interpreter import (
    DSLDepthExceededError,
    DSLInterpreter,
    DSLParserError,
    ExecutionTimeoutError,
    SExprParser,
)


class TestDSL(unittest.TestCase):

    def test_parser_basic_atoms(self):
        node = SExprParser.parse("42")
        self.assertIsInstance(node, ConstNode)
        self.assertEqual(node.value, 42)

        node = SExprParser.parse("true")
        self.assertIsInstance(node, ConstNode)
        self.assertIs(node.value, True)

        node = SExprParser.parse("x")
        self.assertIsInstance(node, VarNode)
        self.assertEqual(node.name, "x")

    def test_parser_list_literal(self):
        node = SExprParser.parse("[1, 2, 3]")
        self.assertIsInstance(node, ConstNode)
        self.assertEqual(node.value, [1, 2, 3])

    def test_parser_application_and_evaluation(self):
        interp = DSLInterpreter()

        # Simple addition
        res = interp.run("(+ 10 5)", input_val=None)
        self.assertEqual(res, 15)

        # Reverse list
        res = interp.run("(reverse x)", input_val=[1, 2, 3])
        self.assertEqual(res, [3, 2, 1])

        # Map increment
        res = interp.run("(map (lambda (a) (+ a 1)) x)", input_val=[1, 2, 3])
        self.assertEqual(res, [2, 3, 4])

        # Filter even
        res = interp.run("(filter (lambda (a) (is_even a)) x)", input_val=[1, 2, 3, 4, 5, 6])
        self.assertEqual(res, [2, 4, 6])

        # Fold sum
        res = interp.run("(fold (lambda (acc item) (+ acc item)) 0 x)", input_val=[1, 2, 3, 4])
        self.assertEqual(res, 10)

        # Conditional
        res = interp.run("(if (gt (length x) 2) true false)", input_val=[1, 2, 3])
        self.assertTrue(res)
        res = interp.run("(if (gt (length x) 2) true false)", input_val=[1])
        self.assertFalse(res)

    def test_parser_syntax_errors(self):
        with self.assertRaises(DSLParserError):
            SExprParser.parse("(+ 1 2")  # Missing closing paren

        with self.assertRaises(DSLParserError):
            SExprParser.parse("")

    def test_ast_depth_limits(self):
        # Program with depth 4
        prog = "(map (lambda (a) (+ a 1)) x)"
        ast = SExprParser.parse(prog)
        self.assertGreaterEqual(ast.depth, 3)

        with self.assertRaises(DSLDepthExceededError):
            SExprParser.parse(prog, max_depth=2)

    def test_execution_step_budget(self):
        interp = DSLInterpreter()
        # Normal execution fits in budget
        res = interp.run("(map (lambda (a) (+ a 1)) x)", input_val=[1, 2, 3], step_budget=100)
        self.assertEqual(res, [2, 3, 4])

        # Exhausted step budget raises error
        with self.assertRaises(ExecutionStepLimitExceeded):
            interp.run("(map (lambda (a) (+ a 1)) x)", input_val=list(range(50)), step_budget=10)


if __name__ == "__main__":
    unittest.main()
