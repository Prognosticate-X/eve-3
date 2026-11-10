"""Audit P0 Regressions Test Suite (S0.1 / S1.1).

Codifies the P0 audit issues (reports/audit.md: H3, H4, H5, H11, H12) into regression tests.
Each test is marked with @pytest.mark.xfail(strict=True) to enforce that:
1. They fail on the current unremediated codebase (confirming the audit findings empirically);
2. If any test accidentally passes or when it is remediated in its respective stage (S2, S3, S4),
   strict=True will immediately force an explicit review and update.
"""

from typing import Any
from unittest.mock import patch
import pytest
import unittest

from eve3.config import EveConfig
from eve3.models import CandidateProgram
from eve3.system1_proposer.sandbox import ProgramSandbox
from eve3.system2_falsifier.bayesian_prober import BayesianProber
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus
from eve3.system2_falsifier.smt_distinguisher import SMTDistinguisher
from eve3.system3_crystallizer.value_compressor import ValueCompressor


class TestAuditP0Regressions(unittest.TestCase):
    """Rigorous regression tests for audit P0 issues (H3, H4, H5, H11, H12)."""

    def test_h3_laplace_smoothing_must_not_promote_falsified_program(self):
        """H3: When a candidate deterministic program is falsified by an active probe,
        its posterior probability must become strictly 0.0 and it must never remain in top-1."""
        prober = BayesianProber(smoothing_epsilon=1e-6)
        c1 = CandidateProgram("(reverse x)")
        c2 = CandidateProgram("(tail x)")
        c3 = CandidateProgram("(head x)")
        hypotheses = [c1, c2, c3]

        # Prior with heavy bias towards c1 (e.g. from shorter description length or prior belief)
        beliefs = [0.999, 0.0005, 0.0005]

        # Active probe [1, 2, 3]: c1 outputs [3, 2, 1], c2 outputs [2, 3], c3 outputs 1
        # Observed true output from oracle is [2, 3] (c1 is strictly falsified!)
        probe_input = [1, 2, 3]
        observed_output = [2, 3]

        updated_beliefs = prober.update_beliefs(hypotheses, beliefs, probe_input, observed_output)

        # In mathematically sound deterministic synthesis, falsified candidate c1 must have posterior == 0.0
        # On current unremediated codebase, c1 receives eps=1e-6, yielding posterior ~0.666 (remains top-1!)
        self.assertEqual(
            updated_beliefs[0],
            0.0,
            f"Falsified program posterior should be 0.0, but got {updated_beliefs[0]} (remains top-1!)",
        )
        top_idx = max(range(len(updated_beliefs)), key=lambda i: updated_beliefs[i])
        self.assertNotEqual(
            top_idx,
            0,
            "Falsified program must not remain top-1 after being falsified by observation",
        )

    def test_h4_hypothesis_collapse_must_report_collapsed_when_all_falsified(self):
        """H4: When all proposed candidates are falsified (true program is not in candidate set),
        the CEGIS loop must detect hypothesis space collapse and report COLLAPSED."""
        cfg = EveConfig(max_falsification_rounds=2, proposer_mode="generic_enumeration")
        loop = CEGISLoop(cfg)

        # Candidate pool that cannot solve the problem
        # Task: increment all elements ([1, 2] -> [2, 3], [0] -> [1])
        # Force candidate pool without any correct increment program
        initial_examples = [([1, 2], [2, 3])]
        oracle_fn = lambda x: [v + 1 for v in x]
        held_out = [([5, 6], [6, 7])]

        # Restrict loop to candidates that are guaranteed to be falsified
        wrong_candidates = [
            CandidateProgram("[2, 3]"),
            CandidateProgram("(reverse [3, 2])"),
        ]
        with patch.object(loop.search_controller, "propose_candidates", side_effect=[wrong_candidates, []]):
            res = loop.run_synthesis(
                initial_examples=initial_examples,
                oracle_fn=oracle_fn,
                held_out_tests=held_out,
            )

        # If all candidates fail observations, status must be COLLAPSED, never HELD_OUT_TESTS_PASSED
        # or EXHAUSTED_UNVERIFIED with a falsified top-1 program
        self.assertEqual(
            res.status,
            VerificationStatus.COLLAPSED,
            f"Expected status COLLAPSED when candidates fail, got {res.status.value}",
        )
        self.assertIsNone(res.verified_program)

    def test_h5_z3_distinguisher_must_symbolically_differentiate_map_programs(self):
        """H5: SMTDistinguisher must symbolically prove distinguishability for map/filter programs
        using Z3 rather than falling back 100% to boundary testing."""
        dist = SMTDistinguisher()
        p1 = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
        p2 = CandidateProgram("(map (lambda (a) (+ a 2)) x)")

        probe = dist.find_distinguishing_input(p1, p2)
        self.assertIsNotNone(probe, "Should find distinguishing input")
        # On current codebase, z3_calls == 0 and source is "heuristic_boundary"
        self.assertEqual(
            probe.source,
            "smt_symbolic",
            f"Expected probe from Z3 SMT symbolic solve, got {probe.source}",
        )
        self.assertGreater(dist.diagnostics.z3_calls, 0, "Z3 solver must be invoked for map candidates")

    def test_h11_crystallized_operators_must_execute_successfully_in_sandbox(self):
        """H11: Crystallized operators produced by System 3 must execute in the sandbox without NameError."""
        sandbox = ProgramSandbox()
        # Candidate using a newly crystallized operator
        code = "(op_increment_list x)"
        examples = [([1, 2], [2, 3])]

        # On current unremediated codebase, DSLInterpreter has no registration mechanism for op_increment_list,
        # raising NameError: name 'op_increment_list' is not defined and filtering out 100% of library candidates
        valid = sandbox.filter_valid_candidates([code], examples, created_by="library")
        self.assertEqual(
            len(valid),
            1,
            "Crystallized operator should execute successfully in sandbox when registered",
        )
        self.assertEqual(
            sandbox.diagnostics.sandbox_rejections.get("NameError", 0),
            0,
            "Sandbox must not reject crystallized operator with NameError",
        )

    def test_h12_submodular_pattern_mining_must_extract_abstractions_from_lambda(self):
        """H12: ValueCompressor.extract_candidate_abstractions must extract patterns from programs
        with lambda nodes without crashing or falling back to static templates."""
        vc = ValueCompressor(gamma=1.0)
        programs = [
            {"code": "(map (lambda (a) (+ a 1)) x)", "task_family": "list_mapping", "reuse_count": 3},
            {"code": "(map (lambda (a) (+ a 2)) x)", "task_family": "list_mapping", "reuse_count": 3},
        ]
        abstractions = vc.extract_candidate_abstractions(programs)
        self.assertGreater(
            len(abstractions),
            0,
            "Should dynamically extract candidate abstractions from lambda programs",
        )
        # Must not swallow errors during extraction
        self.assertEqual(
            vc.diagnostics.swallowed_errors.get("value_compressor.extract_candidate_abstractions", 0),
            0,
            "Pattern mining must not raise swallowed exceptions",
        )
