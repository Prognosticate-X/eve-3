"""System 2: CEGIS Loop (Counterexample-Guided Inductive Synthesis).

Iteratively generates hypotheses, selects maximal information gain probes,
and updates Bayesian posterior distributions with explicit verification statuses.
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from eve3.config import EveConfig
from eve3.system1_proposer.generator import HypothesisGenerator
from eve3.system1_proposer.sandbox import CandidateProgram
from eve3.system2_falsifier.bayesian_prober import BayesianProber
from eve3.system2_falsifier.smt_distinguisher import SMTDistinguisher


class VerificationStatus(str, Enum):
    """Rigorous verification status levels for synthesis outcomes."""
    CANDIDATE_FOUND = "candidate_found"                         # Matches visible examples only
    CONSISTENT_WITH_OBSERVATIONS = "consistent_with_observations" # Survived all active probes, but not tested on held-out suite
    HELD_OUT_TESTS_PASSED = "held_out_tests_passed"             # Empirically verified on unseen hidden test suite
    FORMALLY_VERIFIED = "formally_verified"                     # Proved equivalent across domain via SMT solver
    EXHAUSTED_UNVERIFIED = "exhausted_unverified"               # Search stopped without sufficient confidence or remaining ambiguity
    COLLAPSED = "collapsed"                                     # Version space collapsed (no candidate matches observations)


class CEGISResult:
    """Outcome of CEGIS falsification loop with explicit verification guarantees."""

    def __init__(
        self,
        status: VerificationStatus,
        verified_program: Optional[CandidateProgram],
        rounds_executed: int,
        probes_used: List[Tuple[Any, Any]],  # [(probe_x, oracle_y)]
        final_beliefs: List[float],
        surviving_candidates: List[CandidateProgram],
        held_out_accuracy: Optional[float] = None,
    ):
        self.status = status
        self.verified_program = verified_program
        self.rounds_executed = rounds_executed
        self.probes_used = probes_used
        self.final_beliefs = final_beliefs
        self.surviving_candidates = surviving_candidates
        self.held_out_accuracy = held_out_accuracy

    @property
    def converged(self) -> bool:
        """True ONLY if the program passed held-out test suite or formal SMT verification."""
        return self.status in (
            VerificationStatus.HELD_OUT_TESTS_PASSED,
            VerificationStatus.FORMALLY_VERIFIED,
        )

    def __repr__(self) -> str:
        prog_str = self.verified_program.code_str if self.verified_program else "None"
        return f"<CEGISResult: status={self.status.value}, converged={self.converged}, program={prog_str!r}>"


class CEGISLoop:
    """Orchestrates active falsification between System 1 and System 2."""

    def __init__(
        self,
        config: Optional[EveConfig] = None,
        knowledge_library: Optional[Any] = None,
    ):
        self.config = config or EveConfig()
        self.knowledge_library = knowledge_library
        self.generator = HypothesisGenerator(self.config)
        self.prober = BayesianProber(
            cost_penalty_lambda=self.config.probe_cost_penalty_lambda,
            smoothing_epsilon=self.config.laplace_smoothing_epsilon,
        )
        self.distinguisher = SMTDistinguisher()

    def run_synthesis(
        self,
        initial_examples: List[Tuple[Any, Any]],
        oracle_fn: Callable[[Any], Any],
        held_out_tests: Optional[List[Tuple[Any, Any]]] = None,
        task_family: str = "generic",
        library_primitives: Optional[List[str]] = None,
    ) -> CEGISResult:
        """Run active falsification loop and validate against held-out tests."""
        current_examples = list(initial_examples)
        probes_used: List[Tuple[Any, Any]] = []

        # Pull crystallized operators from knowledge base if available
        active_prims = list(library_primitives or [])
        crystallized_ops = []
        if self.knowledge_library is not None:
            crystallized_ops = self.knowledge_library.get_crystallized_operators()
            for op in crystallized_ops:
                if op["operator_name"] not in active_prims:
                    active_prims.append(op["operator_name"])

        # 1. Generate initial hypotheses
        hypotheses = self.generator.generate_hypotheses(
            current_examples,
            library_primitives=active_prims,
            crystallized_operators=crystallized_ops,
            max_candidates=self.config.max_hypotheses_per_round,
        )

        if not hypotheses:
            return CEGISResult(
                status=VerificationStatus.COLLAPSED,
                verified_program=None,
                rounds_executed=0,
                probes_used=[],
                final_beliefs=[],
                surviving_candidates=[],
            )

        beliefs = self.prober.initialize_beliefs(hypotheses)

        for round_idx in range(1, self.config.max_falsification_rounds + 1):
            # Check high-confidence single hypothesis
            if len(hypotheses) == 1 and beliefs[0] > 0.95:
                return self._finalize_result(
                    candidate=hypotheses[0],
                    rounds=round_idx,
                    probes=probes_used,
                    beliefs=beliefs,
                    survivors=hypotheses,
                    held_out_tests=held_out_tests,
                    task_family=task_family,
                )

            # Generate candidate probes across all hypothesis pairs
            probe_candidates = self.distinguisher.generate_candidate_probe_pool(
                hypotheses, max_pool_size=self.config.falsification_probe_pool_size
            )

            # Filter out inputs already evaluated in current_examples
            seen_inputs = {repr(x) for x, _ in current_examples}
            novel_probes = [p.value for p in probe_candidates if repr(p.value) not in seen_inputs]

            if not novel_probes:
                # No more distinguishing probes found
                best_idx = max(range(len(beliefs)), key=lambda i: beliefs[i])
                return self._finalize_result(
                    candidate=hypotheses[best_idx],
                    rounds=round_idx,
                    probes=probes_used,
                    beliefs=beliefs,
                    survivors=hypotheses,
                    held_out_tests=held_out_tests,
                    task_family=task_family,
                )

            # Select probe maximizing Information Gain
            best_x, score = self.prober.select_best_probe(hypotheses, beliefs, novel_probes)
            if best_x is None:
                best_idx = max(range(len(beliefs)), key=lambda i: beliefs[i])
                return self._finalize_result(
                    candidate=hypotheses[best_idx],
                    rounds=round_idx,
                    probes=probes_used,
                    beliefs=beliefs,
                    survivors=hypotheses,
                    held_out_tests=held_out_tests,
                    task_family=task_family,
                )

            # Query Oracle
            try:
                oracle_y = oracle_fn(best_x)
            except Exception:
                continue

            current_examples.append((best_x, oracle_y))
            probes_used.append((best_x, oracle_y))

            # Update Bayesian posterior
            beliefs = self.prober.update_beliefs(hypotheses, beliefs, best_x, oracle_y)

            # Prune hypotheses with negligible belief (falsified)
            survivors = []
            survivor_beliefs = []
            for h, b in zip(hypotheses, beliefs):
                if b > 1e-4:
                    survivors.append(h)
                    survivor_beliefs.append(b)

            if not survivors:
                # Version space collapse: re-generate hypotheses with updated examples
                hypotheses = self.generator.generate_hypotheses(
                    current_examples,
                    library_primitives=active_prims,
                    crystallized_operators=crystallized_ops,
                    max_candidates=self.config.max_hypotheses_per_round,
                )
                if not hypotheses:
                    return CEGISResult(
                        status=VerificationStatus.COLLAPSED,
                        verified_program=None,
                        rounds_executed=round_idx,
                        probes_used=probes_used,
                        final_beliefs=[],
                        surviving_candidates=[],
                    )
                beliefs = self.prober.initialize_beliefs(hypotheses)
            else:
                hypotheses = survivors
                b_total = sum(survivor_beliefs)
                beliefs = [b / b_total for b in survivor_beliefs]

        # Max rounds reached
        best_idx = max(range(len(beliefs)), key=lambda i: beliefs[i])
        return self._finalize_result(
            candidate=hypotheses[best_idx],
            rounds=self.config.max_falsification_rounds,
            probes=probes_used,
            beliefs=beliefs,
            survivors=hypotheses,
            held_out_tests=held_out_tests,
            task_family=task_family,
        )

    def _finalize_result(
        self,
        candidate: CandidateProgram,
        rounds: int,
        probes: List[Tuple[Any, Any]],
        beliefs: List[float],
        survivors: List[CandidateProgram],
        held_out_tests: Optional[List[Tuple[Any, Any]]],
        task_family: str,
    ) -> CEGISResult:
        """Evaluate candidate on held-out tests and assign honest verification status."""
        import time
        from eve3.models import VerificationEvidence

        if held_out_tests:
            passed = 0
            t0 = time.perf_counter()
            for test_x, expected_y in held_out_tests:
                try:
                    if candidate.evaluate(test_x) == expected_y:
                        passed += 1
                except Exception:
                    pass
            runtime_ms = (time.perf_counter() - t0) * 1000.0

            accuracy = passed / len(held_out_tests)
            is_verified = (accuracy >= 1.0)

            evidence = VerificationEvidence(
                method="held_out_test",
                scope="held_out_suite",
                passed=is_verified,
                runtime_ms=runtime_ms,
            )
            candidate.attach_evidence(evidence)

            if is_verified:
                if self.knowledge_library is not None:
                    self.knowledge_library.record_verified_program(
                        candidate, task_family=task_family
                    )
                return CEGISResult(
                    status=VerificationStatus.HELD_OUT_TESTS_PASSED,
                    verified_program=candidate,
                    rounds_executed=rounds,
                    probes_used=probes,
                    final_beliefs=beliefs,
                    surviving_candidates=survivors,
                    held_out_accuracy=1.0,
                )
            else:
                return CEGISResult(
                    status=VerificationStatus.EXHAUSTED_UNVERIFIED,
                    verified_program=candidate,
                    rounds_executed=rounds,
                    probes_used=probes,
                    final_beliefs=beliefs,
                    surviving_candidates=survivors,
                    held_out_accuracy=accuracy,
                )

        # No held-out tests provided
        evidence = VerificationEvidence(
            method="unit_test",
            scope="observed_examples",
            passed=True,
        )
        candidate.attach_evidence(evidence)
        return CEGISResult(
            status=VerificationStatus.CONSISTENT_WITH_OBSERVATIONS,
            verified_program=candidate,
            rounds_executed=rounds,
            probes_used=probes,
            final_beliefs=beliefs,
            surviving_candidates=survivors,
            held_out_accuracy=None,
        )

