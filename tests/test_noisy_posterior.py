"""Unit tests for Phase 9: Noisy Likelihood, Tempered Posterior, Null Hypothesis, and Calibration.

Verifies:
1. Noisy likelihood evaluation and diffuse null hypothesis h_empty.
2. Tempered posterior b_T(h) temperature scaling.
3. Sequential Probability Ratio Test (SPRT) statistical hypothesis falsification.
4. Expected Calibration Error (ECE) calculation and adaptive temperature controller.
"""

import math
import unittest

from eve3.system2_falsifier.calibration import CalibrationTracker
from eve3.system2_falsifier.noisy_likelihood import (
    NoisyHypothesis,
    NoisyLikelihoodEngine,
)


class TestNoisyPosterior(unittest.TestCase):
    """Test suite for statistical falsification under noise and calibration."""

    def setUp(self):
        self.engine = NoisyLikelihoodEngine(default_sigma=0.1, null_diffuse_likelihood=0.05)
        self.tracker = CalibrationTracker(num_bins=5, target_ece=0.05)

    def test_noisy_likelihood_and_null_hypothesis(self):
        """Verify continuous Gaussian likelihood and diffuse null hypothesis."""
        h1 = NoisyHypothesis("h1", predictor_fn=lambda x: x + 1.0, noise_sigma=0.1)
        h_null = self.engine.create_null_hypothesis()

        # Input x = 2.0 -> prediction = 3.0
        # Observation y = 3.01 (small noise) -> high likelihood
        p_close = self.engine.compute_likelihood(h1, 2.0, 3.01)
        self.assertGreater(p_close, 3.0)

        # Observation y = 5.0 (far out) -> negligible likelihood
        p_far = self.engine.compute_likelihood(h1, 2.0, 5.0)
        self.assertLess(p_far, 1e-4)

        # Null hypothesis assigns constant diffuse likelihood
        p_null_1 = self.engine.compute_likelihood(h_null, 2.0, 3.01)
        p_null_2 = self.engine.compute_likelihood(h_null, 2.0, 5.0)
        self.assertEqual(p_null_1, p_null_2)
        self.assertEqual(p_null_1, 0.05)

    def test_tempered_posterior_update(self):
        """Verify temperature scaling prevents overconfident posterior collapse under noise."""
        h1 = NoisyHypothesis("h1", predictor_fn=lambda x: x + 1.0, noise_sigma=0.1)
        h2 = NoisyHypothesis("h2", predictor_fn=lambda x: x + 2.0, noise_sigma=0.1)
        hypotheses = [h1, h2]

        prior = [0.5, 0.5]
        # x = 1.0, y = 2.05 (favors h1: pred=2.0, h2: pred=3.0)
        
        # 1. Standard temperature T = 1.0
        post_sharp = self.engine.update_tempered_posterior(hypotheses, prior, 1.0, 2.05, temperature=1.0)
        self.assertGreater(post_sharp[0], 0.99)

        # 2. Tempered temperature T = 4.0
        # Reset log-likelihood
        h1.log_likelihood_acc = 0.0
        h2.log_likelihood_acc = 0.0
        post_tempered = self.engine.update_tempered_posterior(hypotheses, prior, 1.0, 2.05, temperature=4.0)
        # Tempered posterior should be softer (less extreme belief collapse)
        self.assertLess(post_tempered[0], post_sharp[0])
        self.assertGreater(post_tempered[1], 0.01)

    def test_sprt_statistical_falsification(self):
        """Verify Sequential Probability Ratio Test falsifies erroneous hypothesis over repeated probes."""
        # True function is f(x) = 2x
        h_correct = NoisyHypothesis("h_correct", predictor_fn=lambda x: 2.0 * x, noise_sigma=0.1)
        h_wrong = NoisyHypothesis("h_wrong", predictor_fn=lambda x: 2.0 * x + 0.5, noise_sigma=0.1)
        hypotheses = [h_correct, h_wrong]

        prior = [0.5, 0.5]

        # Feed 10 sequential noisy observations from true function
        import random
        rng = random.Random(42)
        for i in range(1, 10):
            x = float(i)
            y_obs = 2.0 * x + rng.gauss(0.0, 0.05)
            prior = self.engine.update_tempered_posterior(hypotheses, prior, x, y_obs, temperature=1.0)

            # Check SPRT falsification against leading hypothesis (idx 0)
            falsified = self.engine.check_statistical_falsification(hypotheses, best_hypothesis_idx=0)
            if falsified:
                break

        # h_wrong must be statistically falsified
        self.assertTrue(h_wrong.falsified)
        self.assertFalse(h_correct.falsified)

    def test_expected_calibration_error_and_adaptation(self):
        """Verify ECE calculation and dynamic temperature adaptation."""
        tracker = CalibrationTracker(num_bins=5, target_ece=0.05)

        # Case 1: Perfectly calibrated predictions
        # 10 samples with 0.8 confidence and 80% accuracy
        confs_cal = [0.8] * 10
        accs_cal = [True] * 8 + [False] * 2
        report_cal = tracker.compute_ece(confs_cal, accs_cal)
        self.assertLessEqual(report_cal.ece, 0.05)
        self.assertTrue(report_cal.is_calibrated)

        # Case 2: Overconfident predictions (e.g. 0.95 confidence but only 50% accuracy)
        confs_over = [0.95] * 20
        accs_over = [True] * 10 + [False] * 10
        report_over = tracker.compute_ece(confs_over, accs_over)
        self.assertGreater(report_over.ece, 0.30)
        self.assertFalse(report_over.is_calibrated)
        # Verify adaptive temperature increased to combat overconfidence
        self.assertGreater(report_over.recommended_temperature, 1.0)


if __name__ == "__main__":
    unittest.main()
