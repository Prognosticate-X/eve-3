"""Tests for Stage S4 Crystallized Operator Registration & Execution [H11, H14]."""

from pathlib import Path
import tempfile
import pytest

from eve3.config import EveConfig
from eve3.models import LearnedAbstraction
from eve3.search.controller import SearchController
from eve3.system1_proposer.sandbox import ProgramSandbox
from eve3.system3_crystallizer.library import KnowledgeLibrary


class TestStageS4Operators:
    """Validate operator registration, sandbox execution, and active operator capping."""

    def test_default_crystallized_operators_execute_in_sandbox(self):
        """H11: Standard/crystallized primitives like op_increment_list execute without NameError."""
        sandbox = ProgramSandbox()
        valid = sandbox.filter_valid_candidates(
            ["(op_increment_list x)"], [([1, 2], [2, 3])], created_by="library"
        )
        assert len(valid) == 1
        assert sandbox.diagnostics.sandbox_rejections.get("NameError", 0) == 0

    def test_dynamic_operator_registration_from_sexpr(self):
        """H11: Dynamically register an arity-1 operator from S-expression."""
        sandbox = ProgramSandbox()
        assert hasattr(sandbox, "register_operator"), "ProgramSandbox must implement register_operator"
        sandbox.register_operator("op_double_list", "(map (lambda (a) (* a 2)) x)", arity=1)

        valid = sandbox.filter_valid_candidates(
            ["(op_double_list x)"], [([1, 2, 3], [2, 4, 6])], created_by="library"
        )
        assert len(valid) == 1
        assert sandbox.diagnostics.sandbox_rejections.get("NameError", 0) == 0

    def test_parameterized_dynamic_operator_registration(self):
        """H11: Dynamically register an arity-2 parameterized operator."""
        sandbox = ProgramSandbox()
        sandbox.register_operator("op_add_k", "(map (lambda (a) (+ a $k)) x)", arity=2)

        valid = sandbox.filter_valid_candidates(
            ["(op_add_k 5 x)"], [([10, 20], [15, 25])], created_by="library"
        )
        assert len(valid) == 1
        assert sandbox.diagnostics.sandbox_rejections.get("NameError", 0) == 0

    def test_search_controller_syncs_library_operators_to_sandbox(self):
        """H11: SearchController automatically registers KnowledgeLibrary operators into its sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_kb.sqlite"
            kb = KnowledgeLibrary(db_path)
            kb.record_learned_abstraction(
                LearnedAbstraction(
                    name="op_rev_tail",
                    pattern_sexpr="(reverse (tail x))",
                    arity=1,
                )
            )

            controller = SearchController(EveConfig(), knowledge_library=kb)
            valid = controller.sandbox.filter_valid_candidates(
                ["(op_rev_tail x)"], [([1, 2, 3], [3, 2])], created_by="library"
            )
            assert len(valid) == 1
            assert controller.sandbox.diagnostics.sandbox_rejections.get("NameError", 0) == 0

    def test_h14_max_active_library_operators_cap(self):
        """H14: EveConfig.max_active_library_operators caps active operators to avoid template starvation."""
        cfg = EveConfig(max_active_library_operators=4)
        assert cfg.max_active_library_operators == 4

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cap.sqlite"
            kb = KnowledgeLibrary(db_path)
            # Register 10 operators
            for i in range(10):
                kb.record_crystallized_operator(
                    operator_name=f"op_test_{i}",
                    body_sexpr="(inc x)",
                    arity=1,
                    benefit_score=float(i),
                )

            controller = SearchController(cfg, knowledge_library=kb)
            proposals = controller.propose_candidates(
                examples=[(1, 2)],
                strategy="library_only",
                max_candidates=16,
            )
            # Proposals should not exceed cap * variants
            assert len(proposals) <= cfg.max_active_library_operators
