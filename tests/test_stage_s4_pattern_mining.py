"""Tests for Stage S4 Dynamic AST Pattern Mining & Submodular Extraction [H12]."""

import pytest
from eve3.system3_crystallizer.value_compressor import CandidateAbstraction, ValueCompressor


class TestStageS4PatternMining:
    """Validate dynamic AST subtree mining, lambda handling, and general compression."""

    def test_dynamic_lambda_pattern_mining_no_crash(self):
        """H12: Mining lambda expressions extracts abstractions without AttributeError or NameError."""
        vc = ValueCompressor(gamma=1.0)
        programs = [
            {"code": "(map (lambda (a) (+ a 1)) x)", "task_family": "list_mapping", "reuse_count": 3},
            {"code": "(map (lambda (a) (+ a 2)) x)", "task_family": "list_mapping", "reuse_count": 3},
        ]
        abstractions = vc.extract_candidate_abstractions(programs)
        assert len(abstractions) > 0

        # No swallowed exceptions during mining
        assert vc.diagnostics.swallowed_errors.get("value_compressor.extract_candidate_abstractions", 0) == 0

        # Mined candidate must include the generalized map pattern
        patterns = [a.pattern for a in abstractions]
        assert any("(map (lambda (a) (+ a $k)) x)" in p for p in patterns)

    def test_dynamic_pattern_compression_savings(self):
        """H12: CandidateAbstraction.apply_compression yields AST DL savings on matching code."""
        cand = CandidateAbstraction(
            name="op_map_inc",
            pattern="(map (lambda (a) (+ a $k)) x)",
            arity=2,
            cost=3,
        )
        code = "(map (lambda (a) (+ a 5)) x)"
        compressed, savings = cand.apply_compression(code)
        assert compressed == "(op_map_inc 5 x)"
        assert savings > 0

    def test_arbitrary_nested_subpattern_mining(self):
        """H12: Subtree mining extracts recurring multi-step composite operations."""
        vc = ValueCompressor(gamma=0.5)
        programs = [
            {"code": "(reverse (map (lambda (a) (+ a 1)) x))", "task_family": "composite", "reuse_count": 2},
            {"code": "(reverse (map (lambda (a) (+ a 2)) x))", "task_family": "composite", "reuse_count": 2},
        ]
        abstractions = vc.extract_candidate_abstractions(programs)
        assert len(abstractions) > 0
        patterns = [a.pattern for a in abstractions]
        assert any("(reverse (map (lambda (a) (+ a $k)) x))" in p for p in patterns)
