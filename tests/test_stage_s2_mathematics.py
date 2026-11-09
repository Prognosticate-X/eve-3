"""Stage S2: Numerical Unit Tests for Mutual Information (IG) Formulation (H2).

Verifies the mathematical correctness of:
IG(x) = H(b) - sum_v q_v * H(b | G_v(x))
against analytical hand-calculated values under both uniform and non-uniform priors.
Audit reference: reports/audit.md:88-102, 126-154 (H2); docs/MATHEMATICS.md.
"""

import math
import unittest

from eve3.models import CandidateProgram
from eve3.system2_falsifier.bayesian_prober import BayesianProber, entropy


class TestStageS2InformationGainMathematics(unittest.TestCase):
    """Rigorous analytical numerical tests for Bayesian information gain."""

    def setUp(self):
        self.prober = BayesianProber()
        self.p1 = CandidateProgram("(+ x 1)")
        self.p2 = CandidateProgram("(+ x 2)")
        self.p3 = CandidateProgram("(* x 2)")
        self.hypotheses = [self.p1, self.p2, self.p3]

    def test_h2_uniform_prior_two_partitions_hand_calculation(self):
        """Case A: 3 candidates with uniform prior [1/3, 1/3, 1/3], probe x=1 produces 2 partitions:
        G_2 = {p1, p3} (outputs 2, q_2=2/3, H(b|G_2)=1.0 bit)
        G_3 = {p2} (output 3, q_3=1/3, H(b|G_3)=0.0 bit)
        IG(1) = log2(3) - 2/3 * 1.0 = 0.9182958340544896 bits."""
        beliefs = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
        hand_prior_entropy = math.log2(3.0)  # ~1.584962500721156
        hand_conditional_entropy = (2.0 / 3.0) * 1.0 + (1.0 / 3.0) * 0.0
        expected_ig = hand_prior_entropy - hand_conditional_entropy

        actual_ig = self.prober.compute_information_gain(
            self.hypotheses, beliefs, probe_input=1
        )

        self.assertAlmostEqual(
            actual_ig,
            expected_ig,
            places=6,
            msg=f"IG(1) must match hand-calculated {expected_ig:.8f}, got {actual_ig:.8f}",
        )
        self.assertAlmostEqual(actual_ig, 0.91829583, places=6)

    def test_h2_uniform_prior_three_partitions_hand_calculation(self):
        """Case B: 3 candidates with uniform prior [1/3, 1/3, 1/3], probe x=0 produces 3 partitions:
        G_1 = {p1} (output 1), G_2 = {p2} (output 2), G_0 = {p3} (output 0)
        All conditional entropies H(b|G_v) = 0.0
        IG(0) = log2(3) - 0.0 = 1.584962500721156 bits."""
        beliefs = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
        expected_ig = math.log2(3.0)

        actual_ig = self.prober.compute_information_gain(
            self.hypotheses, beliefs, probe_input=0
        )

        self.assertAlmostEqual(
            actual_ig,
            expected_ig,
            places=6,
            msg=f"IG(0) must match hand-calculated {expected_ig:.8f}, got {actual_ig:.8f}",
        )
        self.assertAlmostEqual(actual_ig, 1.58496250, places=6)

    def test_h2_nonuniform_prior_hand_calculation(self):
        """Case C: Non-uniform prior b = [0.6, 0.3, 0.1].
        Probe x=1:
        G_2 = {p1, p3} -> q_2 = 0.6 + 0.1 = 0.7
        b|G_2 = [6/7, 1/7] -> H(b|G_2) = -(6/7 log2(6/7) + 1/7 log2(1/7))
        G_3 = {p2} -> q_3 = 0.3 -> H(b|G_3) = 0.0
        IG(1) = H([0.6, 0.3, 0.1]) - 0.7 * H([6/7, 1/7])."""
        beliefs = [0.6, 0.3, 0.1]
        h_prior = -(0.6 * math.log2(0.6) + 0.3 * math.log2(0.3) + 0.1 * math.log2(0.1))
        h_cond_g2 = -((6.0 / 7.0) * math.log2(6.0 / 7.0) + (1.0 / 7.0) * math.log2(1.0 / 7.0))
        expected_ig = h_prior - 0.7 * h_cond_g2

        actual_ig = self.prober.compute_information_gain(
            self.hypotheses, beliefs, probe_input=1
        )

        self.assertAlmostEqual(
            actual_ig,
            expected_ig,
            places=6,
            msg=f"Non-uniform IG must match hand-calculated {expected_ig:.8f}, got {actual_ig:.8f}",
        )
        self.assertAlmostEqual(actual_ig, 0.88129090, places=6)

    def test_h2_qv_is_posterior_mass_sum_not_arithmetic_mean(self):
        """Ensure q_v is the sum of hypothesis probabilities in partition, not simple count ratio."""
        # Biased prior: p1 has 0.9 prior mass, p3 has 0.01 prior mass
        beliefs = [0.90, 0.09, 0.01]
        groups = self.prober.group_by_output(self.hypotheses, probe_input=1)
        # Partition G_2 contains indices 0 (p1) and 2 (p3)
        g2_indices = groups["2"]
        q_v = sum(beliefs[i] for i in g2_indices)
        arithmetic_mean = len(g2_indices) / len(self.hypotheses)  # 2/3 = 0.6667

        self.assertAlmostEqual(q_v, 0.91, places=6)
        self.assertNotAlmostEqual(q_v, arithmetic_mean, places=2)


if __name__ == "__main__":
    unittest.main()
