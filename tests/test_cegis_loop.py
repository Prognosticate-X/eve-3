"""Tests for end-to-end CEGIS active synthesis loop and verification statuses."""

import unittest

from eve3.config import EveConfig
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus


class TestCEGISLoop(unittest.TestCase):

    def test_cegis_with_held_out_tests(self):
        config = EveConfig(max_falsification_rounds=5, probe_cost_penalty_lambda=0.01)
        loop = CEGISLoop(config)

        def oracle_increment(lst):
            return [x + 1 for x in lst]

        initial_examples = [([1, 2], [2, 3])]
        held_out_tests = [
            ([10, 20], [11, 21]),
            ([-5, 0], [-4, 1]),
        ]

        result = loop.run_synthesis(
            initial_examples,
            oracle_fn=oracle_increment,
            held_out_tests=held_out_tests,
        )

        # With held-out tests passed, converged MUST be True and status HELD_OUT_TESTS_PASSED
        self.assertTrue(result.converged)
        self.assertEqual(result.status, VerificationStatus.HELD_OUT_TESTS_PASSED)
        self.assertIsNotNone(result.verified_program)
        self.assertEqual(result.held_out_accuracy, 1.0)
        self.assertEqual(result.verified_program.evaluate([100, 200]), [101, 201])

    def test_cegis_without_held_out_tests_honest_status(self):
        config = EveConfig(max_falsification_rounds=5, probe_cost_penalty_lambda=0.01)
        loop = CEGISLoop(config)

        def oracle_increment(lst):
            return [x + 1 for x in lst]

        initial_examples = [([1, 2], [2, 3])]

        # No held-out tests provided
        result = loop.run_synthesis(
            initial_examples,
            oracle_fn=oracle_increment,
            held_out_tests=None,
        )

        # Candidate is consistent with observations, but NOT claimed as converged!
        self.assertEqual(result.status, VerificationStatus.CONSISTENT_WITH_OBSERVATIONS)
        self.assertFalse(result.converged)


if __name__ == "__main__":
    unittest.main()
