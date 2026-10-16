"""System 2: CEGIS Loop (Counterexample-Guided Inductive Synthesis).

Iteratively generates hypotheses, selects maximal information gain probes,
and updates Bayesian posterior distributions.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from eve3.config import EveConfig
from eve3.system1_proposer.generator import HypothesisGenerator
from eve3.system1_proposer.sandbox import CandidateProgram
from eve3.system2_falsifier.bayesian_prober import BayesianProber
from eve3.system2_falsifier.smt_distinguisher import SMTDistinguisher


class CEGISResult:
    """Outcome of CEGIS falsification loop."""

    def __init__(
        self,
        verified_program: Optional[CandidateProgram],
        rounds_executed: int,
        probes_used: List[Tuple[Any, Any]],  # [(probe_x, oracle_y)]
        final_beliefs: List[float],
        surviving_candidates: List[CandidateProgram],
    ):
        self.verified_program = verified_program
        self.rounds_executed = rounds_executed
        self.probes_used = probes_used
        self.final_beliefs = final_beliefs
        self.surviving_candidates = surviving_candidates

    @property
    def converged(self) -> bool:
        return self.verified_program is not None


class CEGISLoop:
    """Orchestrates active falsification between System 1 and System 2."""

    def __init__(self, config: Optional[EveConfig] = None):
        self.config = config or EveConfig()
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
        library_primitives: Optional[List[str]] = None,
    ) -> CEGISResult:
        """Run active falsification loop until convergence or max rounds."""
        current_examples = list(initial_examples)
        probes_used: List[Tuple[Any, Any]] = []

        # 1. Generate initial hypotheses
        hypotheses = self.generator.generate_hypotheses(
            current_examples,
            library_primitives=library_primitives,
            max_candidates=self.config.max_hypotheses_per_round,
        )

        if not hypotheses:
            return CEGISResult(None, 0, [], [], [])

        beliefs = self.prober.initialize_beliefs(hypotheses)

        for round_idx in range(1, self.config.max_falsification_rounds + 1):
            # Check convergence: single high-confidence hypothesis
            if len(hypotheses) == 1 and beliefs[0] > 0.95:
                return CEGISResult(hypotheses[0], round_idx, probes_used, beliefs, hypotheses)

            # Generate candidate probes
            probe_pool = self.distinguisher.generate_candidate_probe_pool(
                hypotheses, max_pool_size=self.config.falsification_probe_pool_size
            )

            # Filter out inputs already evaluated in current_examples
            seen_inputs = {repr(x) for x, _ in current_examples}
            novel_probes = [x for x in probe_pool if repr(x) not in seen_inputs]

            if not novel_probes:
                # No more distinguishing probes found; pick the maximum posterior hypothesis
                best_idx = max(range(len(beliefs)), key=lambda i: beliefs[i])
                return CEGISResult(hypotheses[best_idx], round_idx, probes_used, beliefs, hypotheses)

            # Select probe maximizing Information Gain
            best_x, score = self.prober.select_best_probe(hypotheses, beliefs, novel_probes)
            if best_x is None:
                best_idx = max(range(len(beliefs)), key=lambda i: beliefs[i])
                return CEGISResult(hypotheses[best_idx], round_idx, probes_used, beliefs, hypotheses)

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
                    library_primitives=library_primitives,
                    max_candidates=self.config.max_hypotheses_per_round,
                )
                if not hypotheses:
                    return CEGISResult(None, round_idx, probes_used, [], [])
                beliefs = self.prober.initialize_beliefs(hypotheses)
            else:
                hypotheses = survivors
                b_total = sum(survivor_beliefs)
                beliefs = [b / b_total for b in survivor_beliefs]

        # Max rounds reached
        best_idx = max(range(len(beliefs)), key=lambda i: beliefs[i])
        return CEGISResult(hypotheses[best_idx], self.config.max_falsification_rounds, probes_used, beliefs, hypotheses)
