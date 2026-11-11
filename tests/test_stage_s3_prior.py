"""Stage S3: Tests for Configurable Bayesian Prior Distribution (H1).

Audit reference: reports/audit.md:98-124 (H1).
"""

import math
import unittest

from eve3.config import EveConfig
from eve3.models import CandidateProgram
from eve3.system2_falsifier.bayesian_prober import BayesianProber


class TestStageS3PriorModes(unittest.TestCase):
    """Rigorous tests for configurable prior distribution modes."""

    def setUp(self):
        self.p_short = CandidateProgram("x")  # description_length = 1
        self.p_med = CandidateProgram("(reverse x)")  # description_length = 2
        self.p_long = CandidateProgram("(map (lambda (a) (+ a 1)) x)")  # description_length = 7
        self.hypotheses = [self.p_short, self.p_med, self.p_long]

    def test_uniform_prior_mode(self):
        """Under prior_mode='uniform', all hypotheses receive equal 1/N prior mass."""
        prober = BayesianProber(prior_mode="uniform")
        beliefs = prober.initialize_beliefs(self.hypotheses)

        self.assertEqual(len(beliefs), 3)
        self.assertAlmostEqual(beliefs[0], 1.0 / 3.0, places=6)
        self.assertAlmostEqual(beliefs[1], 1.0 / 3.0, places=6)
        self.assertAlmostEqual(beliefs[2], 1.0 / 3.0, places=6)
        self.assertAlmostEqual(sum(beliefs), 1.0, places=6)

    def test_mdl_prior_mode_with_custom_decay(self):
        """Under prior_mode='mdl', prior is proportional to 2^(-decay * DL)."""
        # With decay=0.5:
        # p_short (DL=1): 2^(-0.5) = 0.7071
        # p_med (DL=2): 2^(-1.0) = 0.5000
        # p_long (DL=7): 2^(-3.5) = 0.0884
        prober = BayesianProber(prior_mode="mdl", mdl_prior_decay=0.5)
        beliefs = prober.initialize_beliefs(self.hypotheses)

        expected_raw = [2.0 ** (-0.5 * p.description_length) for p in self.hypotheses]
        total = sum(expected_raw)
        expected = [w / total for w in expected_raw]

        self.assertEqual(len(beliefs), 3)
        for act, exp in zip(beliefs, expected):
            self.assertAlmostEqual(act, exp, places=6)
        self.assertAlmostEqual(sum(beliefs), 1.0, places=6)
        # Verify ordering: short > med > long
        self.assertGreater(beliefs[0], beliefs[1])
        self.assertGreater(beliefs[1], beliefs[2])

    def test_llm_prior_mode_uses_candidate_logprob(self):
        """Under prior_mode='llm', candidate logprob is exponentiated to form prior weights."""
        c1 = CandidateProgram("x")
        c2 = CandidateProgram("(reverse x)")
        c1.logprob = -0.5
        c2.logprob = -2.0

        prober = BayesianProber(prior_mode="llm")
        beliefs = prober.initialize_beliefs([c1, c2])

        w1 = math.exp(-0.5)
        w2 = math.exp(-2.0)
        expected = [w1 / (w1 + w2), w2 / (w1 + w2)]

        self.assertAlmostEqual(beliefs[0], expected[0], places=6)
        self.assertAlmostEqual(beliefs[1], expected[1], places=6)

    def test_config_prior_mode_validation(self):
        """EveConfig validates prior_mode in {'mdl', 'uniform', 'llm'}."""
        cfg = EveConfig(prior_mode="uniform", mdl_prior_decay=0.8)
        self.assertEqual(cfg.prior_mode, "uniform")
        self.assertEqual(cfg.mdl_prior_decay, 0.8)

        with self.assertRaises(ValueError):
            EveConfig(prior_mode="invalid_prior_mode")


if __name__ == "__main__":
    unittest.main()
