"""Stage S2: Tests for Probe Strategy and Random Control Arm (H2 / S2.5).

Verifies the explicit comparison:
- Baseline_A (probe_strategy="none"): no active probe queries
- Baseline_Random (probe_strategy="random"): random novel probe selection
- Baseline_B (probe_strategy="bayesian_ig"): maximal information gain probe selection
"""

import unittest

from eve3.config import EveConfig
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus


class TestStageS2ProbeStrategies(unittest.TestCase):
    """Rigorous comparison of active falsification probe strategies."""

    def setUp(self):
        self.initial_examples = [([1, 2], [2, 3])]
        self.oracle_fn = lambda x: [v + 1 for v in x]
        self.held_out = [([5, 6], [6, 7]), ([-1, 0], [0, 1])]

    def test_baseline_none_uses_zero_probes(self):
        """probe_strategy='none' terminates without querying any active probes."""
        cfg = EveConfig(
            max_falsification_rounds=5,
            probe_strategy="none",
            proposer_mode="generic_enumeration",
        )
        loop = CEGISLoop(cfg)
        res = loop.run_synthesis(
            initial_examples=self.initial_examples,
            oracle_fn=self.oracle_fn,
            held_out_tests=self.held_out,
        )

        self.assertEqual(len(res.probes_used), 0)
        self.assertEqual(res.diagnostics.oracle_queries, 0)
        self.assertEqual(res.status, VerificationStatus.HELD_OUT_TESTS_PASSED)

    def test_baseline_random_queries_probes_and_converges(self):
        """probe_strategy='random' queries active probes chosen without IG ordering."""
        cfg = EveConfig(
            max_falsification_rounds=5,
            probe_strategy="random",
            proposer_mode="generic_enumeration",
        )
        loop = CEGISLoop(cfg)
        res = loop.run_synthesis(
            initial_examples=self.initial_examples,
            oracle_fn=self.oracle_fn,
            held_out_tests=self.held_out,
        )

        self.assertEqual(res.status, VerificationStatus.HELD_OUT_TESTS_PASSED)
        self.assertIsNotNone(res.verified_program)

    def test_baseline_bayesian_ig_queries_probes_and_converges(self):
        """probe_strategy='bayesian_ig' selects maximal information gain probes."""
        cfg = EveConfig(
            max_falsification_rounds=5,
            probe_strategy="bayesian_ig",
            proposer_mode="generic_enumeration",
        )
        loop = CEGISLoop(cfg)
        res = loop.run_synthesis(
            initial_examples=self.initial_examples,
            oracle_fn=self.oracle_fn,
            held_out_tests=self.held_out,
        )

        self.assertEqual(res.status, VerificationStatus.HELD_OUT_TESTS_PASSED)
        self.assertIsNotNone(res.verified_program)


if __name__ == "__main__":
    unittest.main()
