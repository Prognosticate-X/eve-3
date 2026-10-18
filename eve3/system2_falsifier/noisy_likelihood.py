"""Noisy Likelihood: Statistical Falsification, Tempered Posterior, and Null Hypothesis.

Implements Phase 9 Active Falsification under Sensor/Simulation Noise:
- Continuous & discrete observation likelihood models p(y | x, h).
- Tempered Bayesian posterior b_T(h) to prevent overconfident belief collapse.
- None-of-the-above null hypothesis h_empty to prevent premature false convergence.
- Closed-form mutual information / Information Gain IG(x) in noisy domains.
- Sequential probability ratio testing (SPRT) for robust statistical hypothesis rejection.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


@dataclass
class NoisyHypothesis:
    """Hypothesis wrapper tracking predictive mean, variance, and cumulative log-likelihood."""
    hypothesis_id: str
    predictor_fn: Optional[Callable[[Any], Any]] = None
    is_null_hypothesis: bool = False  # True for h_empty
    noise_sigma: float = 0.1
    log_likelihood_acc: float = 0.0
    falsified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class NoisyLikelihoodEngine:
    """Evaluates noisy likelihoods, computes tempered posteriors, and selects distinguishing probes."""

    def __init__(
        self,
        default_sigma: float = 0.1,
        null_diffuse_likelihood: float = 0.05,
        alpha_significance: float = 0.01,
    ):
        self.default_sigma = default_sigma
        self.null_likelihood = null_diffuse_likelihood
        self.alpha = alpha_significance
        # SPRT rejection threshold: log(alpha / (1 - alpha))
        self.sprt_reject_threshold = math.log(self.alpha / (1.0 - self.alpha))

    def create_null_hypothesis(self) -> NoisyHypothesis:
        """Create the diffuse 'none-of-the-above' null hypothesis h_empty."""
        return NoisyHypothesis(
            hypothesis_id="h_null",
            predictor_fn=None,
            is_null_hypothesis=True,
            noise_sigma=1.0,
            metadata={"description": "none-of-the-above diffuse prior"},
        )

    def compute_likelihood(
        self,
        hyp: NoisyHypothesis,
        x: Any,
        y: Any,
    ) -> float:
        """Compute observation likelihood p(y | x, h)."""
        if hyp.is_null_hypothesis or hyp.predictor_fn is None:
            return self.null_likelihood

        try:
            pred = hyp.predictor_fn(x)
        except Exception:
            return 1e-6  # Execution failure penalized

        # 1. Scalar continuous observation: Gaussian likelihood
        if isinstance(y, (int, float)) and isinstance(pred, (int, float)):
            diff = float(y) - float(pred)
            sigma = max(1e-3, hyp.noise_sigma)
            gaussian_p = (1.0 / (math.sqrt(2.0 * math.pi) * sigma)) * math.exp(-0.5 * (diff / sigma) ** 2)
            return max(1e-6, gaussian_p)

        # 2. Vector continuous observation: Multi-variate isotropic Gaussian
        if isinstance(y, (list, tuple)) and isinstance(pred, (list, tuple)):
            if len(y) != len(pred):
                return 1e-6
            sse = sum((float(y[i]) - float(pred[i])) ** 2 for i in range(len(y)))
            sigma = max(1e-3, hyp.noise_sigma)
            p = math.exp(-0.5 * sse / (sigma ** 2))
            return max(1e-6, p)

        # 3. Categorical / Exact match with label noise epsilon
        match = (y == pred)
        epsilon = 0.05
        return (1.0 - epsilon) if match else epsilon

    def update_tempered_posterior(
        self,
        hypotheses: List[NoisyHypothesis],
        prior_beliefs: List[float],
        x: Any,
        y: Any,
        temperature: float = 1.0,
    ) -> List[float]:
        """Update Bayesian posterior with temperature exponentiation: b_T(h) ~ b0 * prod(p_t)^(1/T)."""
        T = max(1.0, temperature)
        unnorm_beliefs: List[float] = []

        for h, b0 in zip(hypotheses, prior_beliefs):
            if h.falsified:
                unnorm_beliefs.append(0.0)
                continue

            likelihood = self.compute_likelihood(h, x, y)
            # Accumulate log-likelihood for SPRT statistical testing
            h.log_likelihood_acc += math.log(max(1e-10, likelihood))

            # Tempered update: p^(1/T)
            tempered_lik = math.pow(max(1e-10, likelihood), 1.0 / T)
            unnorm_beliefs.append(b0 * tempered_lik)

        total = sum(unnorm_beliefs)
        if total <= 1e-12:
            # Avoid division by zero: revert to uniform over survivors
            survivors = [h for h in hypotheses if not h.falsified]
            u = 1.0 / len(survivors) if survivors else 0.0
            return [u if not h.falsified else 0.0 for h in hypotheses]

        posterior = [b / total for b in unnorm_beliefs]
        return posterior

    def check_statistical_falsification(
        self,
        hypotheses: List[NoisyHypothesis],
        best_hypothesis_idx: int,
    ) -> List[str]:
        """Run Sequential Probability Ratio Test (SPRT) to statistically falsify hypotheses."""
        falsified_ids: List[str] = []
        if best_hypothesis_idx < 0 or best_hypothesis_idx >= len(hypotheses):
            return falsified_ids

        best_h = hypotheses[best_hypothesis_idx]
        best_ll = best_h.log_likelihood_acc

        for h in hypotheses:
            if h.falsified or h.is_null_hypothesis:
                continue
            # Log-Likelihood Ratio against leading hypothesis
            llr = h.log_likelihood_acc - best_ll
            if llr < self.sprt_reject_threshold:
                h.falsified = True
                falsified_ids.append(h.hypothesis_id)

        return falsified_ids

    def compute_noisy_information_gain(
        self,
        hypotheses: List[NoisyHypothesis],
        beliefs: List[float],
        candidate_probes: List[Any],
        temperature: float = 1.0,
    ) -> Tuple[Any, float]:
        """Select input x maximizing Mutual Information IG(x) = H(Y|x) - sum b_T(h) H(Y|x, h)."""
        best_probe = None
        best_ig = -1.0

        for x in candidate_probes:
            # Predict outputs across hypotheses
            pred_outputs: Dict[Any, float] = {}
            for h, b in zip(hypotheses, beliefs):
                if b <= 1e-4 or h.falsified:
                    continue
                try:
                    if h.is_null_hypothesis or h.predictor_fn is None:
                        out = "null_output"
                    else:
                        out = repr(h.predictor_fn(x))
                except Exception:
                    out = "error"
                pred_outputs[out] = pred_outputs.get(out, 0.0) + b

            # Total output entropy H(Y|x)
            h_total = 0.0
            for p in pred_outputs.values():
                if p > 0.0:
                    h_total -= p * math.log(p)

            # Conditional entropy under Gaussian/noise assumption
            h_cond = sum(b * (0.5 * math.log(2.0 * math.pi * math.e * (h.noise_sigma ** 2)))
                         for h, b in zip(hypotheses, beliefs) if b > 1e-4)

            ig = max(0.0, h_total - 0.1 * abs(h_cond))
            if ig > best_ig:
                best_ig = ig
                best_probe = x

        return best_probe, max(0.0, best_ig)
