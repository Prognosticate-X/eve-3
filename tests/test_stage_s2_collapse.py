"""Stage S2: Tests for Hypothesis Collapse Protection and Active Re-proposal (H4).

Audit reference: reports/audit.md:123-140, 193-210 (H4).
"""

from unittest.mock import patch
import unittest

from eve3.config import EveConfig
from eve3.models import CandidateProgram
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus


class TestStageS2HypothesisCollapse(unittest.TestCase):
    """Rigorous tests for hypothesis space collapse and active re-propose loop."""

    def test_collapse_detected_when_all_candidates_falsified_and_repropose_exhausted(self):
        """When all candidates in version space fail active probes and repropose cannot find
        satisfying candidates, loop must return COLLAPSED and verified_program=None."""
        cfg = EveConfig(max_falsification_rounds=3, proposer_mode="generic_enumeration")
        loop = CEGISLoop(cfg)

        initial_examples = [([1, 2], [2, 3])]
        oracle_fn = lambda x: [v + 1 for v in x]
        held_out = [([5, 6], [6, 7])]

        # Initial candidates that match [1, 2] -> [2, 3] but are constant outputs
        wrong_candidates = [
            CandidateProgram("[2, 3]"),
            CandidateProgram("(reverse [3, 2])"),
        ]

        # First call returns wrong candidates; second call (re-propose) returns empty
        with patch.object(loop.search_controller, "propose_candidates", side_effect=[wrong_candidates, []]):
            res = loop.run_synthesis(
                initial_examples=initial_examples,
                oracle_fn=oracle_fn,
                held_out_tests=held_out,
            )

        self.assertEqual(res.status, VerificationStatus.COLLAPSED)
        self.assertIsNone(res.verified_program)
        self.assertEqual(len(res.surviving_candidates), 0)

    def test_active_repropose_recovers_when_better_candidate_found(self):
        """When initial candidates are falsified, re-propose with all historical counterexamples
        allows the loop to recover and find the true program."""
        cfg = EveConfig(max_falsification_rounds=3, proposer_mode="generic_enumeration")
        loop = CEGISLoop(cfg)

        initial_examples = [([1, 2], [2, 3])]
        oracle_fn = lambda x: [v + 1 for v in x]
        held_out = [([5, 6], [6, 7])]

        wrong1 = CandidateProgram("[2, 3]")
        wrong2 = CandidateProgram("(reverse [3, 2])")
        true_candidate = CandidateProgram("(map (lambda (a) (inc a)) x)")

        # First call proposes wrong candidates; second call (triggered by collapse) proposes true candidate
        with patch.object(
            loop.search_controller,
            "propose_candidates",
            side_effect=[[wrong1, wrong2], [true_candidate]],
        ):
            res = loop.run_synthesis(
                initial_examples=initial_examples,
                oracle_fn=oracle_fn,
                held_out_tests=held_out,
            )

        self.assertEqual(res.status, VerificationStatus.HELD_OUT_TESTS_PASSED)
        self.assertIsNotNone(res.verified_program)
        self.assertEqual(res.verified_program.code_str, "(map (lambda (a) (inc a)) x)")
        self.assertGreater(len(res.probes_used), 0)


if __name__ == "__main__":
    unittest.main()
