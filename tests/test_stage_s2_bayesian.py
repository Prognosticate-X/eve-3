"""Stage S2: Tests for Bayesian Noise Models, Posterior Updates, and Falsification (H3).

Audit reference: reports/audit.md:104-121 (H3).
"""

import math
import unittest

from eve3.models import CandidateProgram, CandidateStatus
from eve3.system2_falsifier.bayesian_prober import BayesianProber


class TestStageS2BayesianNoiseModel(unittest.TestCase):
    """Rigorous tests for deterministic vs noisy Bayesian posterior updates."""

    def test_deterministic_posterior_strictly_zero_on_falsification(self):
        """In deterministic mode (default), mismatched candidates receive likelihood 0.0,
        posterior 0.0, and are marked falsified=True."""
        prober = BayesianProber(noise_model="deterministic")
        c1 = CandidateProgram("(reverse x)")
        c2 = CandidateProgram("(tail x)")
        hypotheses = [c1, c2]
        beliefs = [0.8, 0.2]

        probe_input = [1, 2, 3]
        observed_output = [2, 3]  # c1 outputs [3, 2, 1] (falsified), c2 outputs [2, 3] (consistent)

        updated_beliefs = prober.update_beliefs(hypotheses, beliefs, probe_input, observed_output)

        self.assertEqual(updated_beliefs[0], 0.0)
        self.assertEqual(updated_beliefs[1], 1.0)
        self.assertTrue(getattr(c1, "falsified", False))
        self.assertEqual(c1.status, CandidateStatus.REJECTED)
        self.assertFalse(getattr(c2, "falsified", False))

    def test_deterministic_posterior_when_all_falsified_returns_all_zeros(self):
        """When all candidates fail an observation in deterministic mode, all posteriors are 0.0."""
        prober = BayesianProber(noise_model="deterministic")
        c1 = CandidateProgram("(reverse x)")
        c2 = CandidateProgram("(tail x)")
        hypotheses = [c1, c2]
        beliefs = [0.5, 0.5]

        # Oracle output matches neither candidate
        updated_beliefs = prober.update_beliefs(hypotheses, beliefs, [1, 2, 3], [999])

        self.assertEqual(updated_beliefs, [0.0, 0.0])
        self.assertTrue(getattr(c1, "falsified", False))
        self.assertTrue(getattr(c2, "falsified", False))
        self.assertEqual(c1.status, CandidateStatus.REJECTED)
        self.assertEqual(c2.status, CandidateStatus.REJECTED)

    def test_noisy_mode_preserves_laplace_smoothing(self):
        """In noisy mode, mismatched candidates receive epsilon likelihood rather than 0.0."""
        eps = 0.05
        prober = BayesianProber(noise_model=f"noisy({eps})", smoothing_epsilon=eps)
        c1 = CandidateProgram("(reverse x)")
        c2 = CandidateProgram("(tail x)")
        hypotheses = [c1, c2]
        beliefs = [0.5, 0.5]

        updated_beliefs = prober.update_beliefs(hypotheses, beliefs, [1, 2, 3], [2, 3])

        # c1 failed, c2 matched
        self.assertGreater(updated_beliefs[0], 0.0)
        self.assertTrue(math.isclose(sum(updated_beliefs), 1.0))
        self.assertGreater(updated_beliefs[1], updated_beliefs[0])


if __name__ == "__main__":
    unittest.main()
