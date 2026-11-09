"""System 2: Exact Bayesian Active Probe Selection and Posterior Update.

Implements the formal mutual information formulation for splitting version space:
IG(x) = H(b) - sum_v q_v(x) * H(b | G_v(x))
"""

import itertools
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from eve3.dsl.interpreter import DSLParserError, ExecutionTimeoutError
from eve3.models import CandidateStatus, Diagnostics
from eve3.system1_proposer.sandbox import CandidateProgram

logger = logging.getLogger(__name__)


def entropy(probs: List[float]) -> float:
    """Shannon entropy H(p) = -sum p_i * log2(p_i)."""
    h = 0.0
    for p in probs:
        if p > 1e-12:
            h -= p * math.log2(p)
    return h


def renormalize(probs: List[float], indices: List[int]) -> List[float]:
    """Extract sub-distribution on indices and re-normalize."""
    sub = [probs[i] for i in indices]
    total = sum(sub)
    if total <= 1e-12:
        return [1.0 / len(indices)] * len(indices) if indices else []
    return [p / total for p in sub]


class BayesianProber:
    """Manages version space beliefs, calculates Information Gain, and selects optimal probes."""

    def __init__(
        self,
        cost_penalty_lambda: float = 0.05,
        smoothing_epsilon: float = 1e-6,
        noise_model: str = "deterministic",
    ):
        self.cost_penalty_lambda = cost_penalty_lambda
        self.smoothing_epsilon = smoothing_epsilon
        self.noise_model = noise_model
        self.diagnostics = Diagnostics()

    def _get_noise_epsilon(self) -> float:
        if self.noise_model.startswith("noisy"):
            import re
            m = re.search(r"noisy\(([^)]+)\)", self.noise_model)
            if m:
                try:
                    return float(m.group(1).strip())
                except ValueError:
                    return self.smoothing_epsilon
            return self.smoothing_epsilon
        return 0.0

    def initialize_beliefs(self, hypotheses: List[CandidateProgram]) -> List[float]:
        r"""Compute initial Occam/MDL prior: b_i \propto 2^{-L(P_i)}."""
        if not hypotheses:
            return []
        
        # Calculate unnormalized priors
        raw_weights = [2.0 ** (-float(p.description_length)) for p in hypotheses]
        total = sum(raw_weights)
        if total <= 1e-12:
            return [1.0 / len(hypotheses)] * len(hypotheses)
        return [w / total for w in raw_weights]

    def group_by_output(
        self,
        hypotheses: List[CandidateProgram],
        probe_input: Any,
        timeout: float = 0.5,
    ) -> Dict[str, List[int]]:
        """Evaluate all hypotheses on probe_input and group indices by output value."""
        groups: Dict[str, List[int]] = {}
        for idx, p in enumerate(hypotheses):
            try:
                out = p.evaluate(probe_input, timeout=timeout)
                # Key by canonical string representation to group unhashable types like lists
                out_key = repr(out)
            except (
                ExecutionTimeoutError,
                DSLParserError,
                NameError,
                AttributeError,
                ValueError,
                TypeError,
                ZeroDivisionError,
                IndexError,
                KeyError,
                RuntimeError,
                ArithmeticError,
                LookupError,
            ) as exc:
                self.diagnostics.record_swallowed_error("bayesian_prober.group_by_output", exc)
                logger.debug("Swallowed error in group_by_output for %s on %r: %s", p.code_str, probe_input, exc)
                # S1.1: Each failing candidate gets its own unique error partition so errors are never lumped together
                out_key = f"__ERROR_{type(exc).__name__}_{idx}__"

            if out_key not in groups:
                groups[out_key] = []
            groups[out_key].append(idx)
        return groups

    def compute_information_gain(
        self,
        hypotheses: List[CandidateProgram],
        beliefs: List[float],
        probe_input: Any,
        timeout: float = 0.5,
    ) -> float:
        """Compute closed-form mutual information IG(x) between hypothesis space and probe outcome."""
        groups = self.group_by_output(hypotheses, probe_input, timeout=timeout)
        h_prior = entropy(beliefs)

        conditional_entropy = 0.0
        for idxs in groups.values():
            q_v = sum(beliefs[i] for i in idxs)
            sub_dist = renormalize(beliefs, idxs)
            conditional_entropy += q_v * entropy(sub_dist)

        ig = h_prior - conditional_entropy
        return max(0.0, ig)

    def select_best_probe(
        self,
        hypotheses: List[CandidateProgram],
        beliefs: List[float],
        candidate_probes: List[Any],
        cost_fn: Optional[Callable[[Any], float]] = None,
        timeout: float = 0.5,
    ) -> Tuple[Optional[Any], float]:
        """Find probe maximizing: score(x) = IG(x) - lambda * C(x)."""
        if not candidate_probes or len(hypotheses) <= 1:
            return None, 0.0

        best_probe = None
        best_score = -float("inf")

        for probe in candidate_probes:
            ig = self.compute_information_gain(hypotheses, beliefs, probe, timeout=timeout)
            cost = cost_fn(probe) if cost_fn is not None else 1.0
            score = ig - self.cost_penalty_lambda * cost

            if score > best_score:
                best_score = score
                best_probe = probe

        return best_probe, best_score

    def update_beliefs(
        self,
        hypotheses: List[CandidateProgram],
        beliefs: List[float],
        probe_input: Any,
        observed_output: Any,
        timeout: float = 0.5,
    ) -> List[float]:
        """Bayesian posterior update with explicit noise model and collapse handling."""
        likelihoods: List[float] = []
        is_deterministic = (self.noise_model == "deterministic")
        eps = self._get_noise_epsilon()

        for p in hypotheses:
            try:
                actual_out = p.evaluate(probe_input, timeout=timeout)
                if actual_out == observed_output:
                    likelihood = 1.0 if is_deterministic else (1.0 - eps)
                else:
                    if is_deterministic:
                        likelihood = 0.0
                        p.falsified = True
                        p.status = CandidateStatus.REJECTED
                    else:
                        likelihood = eps
            except (
                ExecutionTimeoutError,
                DSLParserError,
                ValueError,
                TypeError,
                ZeroDivisionError,
                IndexError,
                KeyError,
                RuntimeError,
                ArithmeticError,
                LookupError,
            ) as exc:
                self.diagnostics.record_swallowed_error("bayesian_prober.update_beliefs", exc)
                logger.debug("Swallowed error in update_beliefs for %s on %r: %s", p.code_str, probe_input, exc)
                if is_deterministic:
                    likelihood = 0.0
                    p.falsified = True
                    p.status = CandidateStatus.REJECTED
                else:
                    likelihood = eps

            likelihoods.append(likelihood)

        new_beliefs = [b * l for b, l in zip(beliefs, likelihoods)]
        total = sum(new_beliefs)

        # Hypothesis space collapse protection
        if total <= 1e-12:
            if is_deterministic:
                # All candidates strictly falsified in deterministic setting
                return [0.0] * len(hypotheses)
            # Fallback to uniform distribution across remaining hypotheses
            return [1.0 / len(hypotheses)] * len(hypotheses)

        return [b / total for b in new_beliefs]
