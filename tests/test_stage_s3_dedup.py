"""Tests for Stage S3 Candidate Deduplication (AST alpha-equivalence) and Prompt Alignment [H9]."""

import pytest
from eve3.config import EveConfig
from eve3.dsl.interpreter import SExprParser
from eve3.models import CandidateProgram
from eve3.search.controller import SearchController
from eve3.system1_proposer.generator import HypothesisGenerator
from eve3.system1_proposer.sandbox import ProgramSandbox


class TestStageS3DedupAndPromptAlignment:
    """Validate alpha-equivalence normalization, deduplication, and dynamic prompt alignment."""

    def test_ast_canonical_sexpr_alpha_equivalence(self):
        """H9: Lambda bound variables normalize to canonical de Bruijn-like IDs."""
        ast1 = SExprParser.parse("(map (lambda (a) (+ a 1)) x)")
        ast2 = SExprParser.parse("(map (lambda (b) (+ b 1)) x)")

        assert hasattr(ast1, "to_canonical_sexpr"), "ASTNode must implement to_canonical_sexpr"
        canonical1 = ast1.to_canonical_sexpr()
        canonical2 = ast2.to_canonical_sexpr()

        assert canonical1 == canonical2
        assert "$0" in canonical1

    def test_nested_lambdas_alpha_equivalence(self):
        """H9: Nested lambdas and closures maintain consistent canonical numbering."""
        ast1 = SExprParser.parse("(lambda (a) (lambda (b) (+ a b)))")
        ast2 = SExprParser.parse("(lambda (x) (lambda (y) (+ x y)))")

        assert ast1.to_canonical_sexpr() == ast2.to_canonical_sexpr()

    def test_candidate_program_equality_and_alpha_equivalence(self):
        """H9: CandidateProgram equality and hashing are based on canonical alpha-equivalence."""
        c1 = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
        c2 = CandidateProgram("(map (lambda (b) (+ b 1)) x)")
        c3 = CandidateProgram("(map (lambda (a) (+ a 2)) x)")

        assert c1.is_alpha_equivalent(c2)
        assert not c1.is_alpha_equivalent(c3)
        assert c1 == c2
        assert c1 != c3
        assert hash(c1) == hash(c2)
        assert len({c1, c2}) == 1

    def test_sandbox_deduplicates_alpha_equivalent_candidates(self):
        """H9: ProgramSandbox filters out redundant alpha-equivalent candidates."""
        sandbox = ProgramSandbox()
        raw_cands = [
            "(map (lambda (a) (+ a 1)) x)",
            "(map (lambda (b) (+ b 1)) x)",
            "(map (lambda (c) (+ c 1)) x)",
        ]
        examples = [([1, 2], [2, 3])]

        valid = sandbox.filter_valid_candidates(raw_cands, examples)
        assert len(valid) == 1
        assert valid[0].canonical_code == "(map (lambda ($0) (+ $0 1)) x)"

    def test_search_controller_deduplicates_alpha_equivalent_proposals(self):
        """H9: SearchController.propose_candidates avoids proposing alpha-equivalent duplicates."""
        controller = SearchController()
        examples = [([1, 2], [2, 3])]
        # In mock/unit setup, passing duplicate candidates through add_candidates
        c1 = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
        c2 = CandidateProgram("(map (lambda (b) (+ b 1)) x)")

        proposals = controller.propose_candidates(examples, strategy="symbolic_only", max_candidates=10)
        canonical_set = {getattr(p, "canonical_code", p.code_str) for p in proposals}
        assert len(canonical_set) == len(proposals), "Proposals contains duplicate alpha-equivalent programs!"

    def test_build_prompt_dynamically_aligns_candidate_count(self):
        """H9: HypothesisGenerator.build_prompt reflects requested candidate count, not hardcoded 5."""
        gen = HypothesisGenerator(EveConfig(max_hypotheses_per_round=16))
        examples = [([1, 2], [2, 3])]

        prompt16 = gen.build_prompt(examples, num_candidates=16)
        assert "generate 16 candidate DSL programs" in prompt16
        assert "generate 5 candidate DSL programs" not in prompt16

        prompt8 = gen.build_prompt(examples, num_candidates=8)
        assert "generate 8 candidate DSL programs" in prompt8
