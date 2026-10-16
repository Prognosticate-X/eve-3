"""Tests for core data models and verification evidence tracking."""

import unittest

from eve3.dsl.interpreter import SExprParser
from eve3.models import CandidateProgram, CandidateStatus, VerificationEvidence


class TestModels(unittest.TestCase):

    def test_candidate_program_initialization(self):
        cand = CandidateProgram("(map (lambda (a) (+ a 1)) x)", created_by="llm")
        self.assertEqual(cand.status, CandidateStatus.CANDIDATE)
        self.assertEqual(cand.created_by, "llm")
        self.assertEqual(len(cand.evidence_ids), 0)
        self.assertGreater(cand.description_length, 0)

    def test_evidence_attachment_and_status_transitions(self):
        cand = CandidateProgram("(reverse x)", created_by="heuristic")

        # Observed examples unit test
        ev1 = VerificationEvidence(
            candidate_id=cand.candidate_id,
            method="unit_test",
            scope="observed_examples",
            passed=True,
        )
        cand.attach_evidence(ev1)
        self.assertEqual(cand.status, CandidateStatus.CONSISTENT)
        self.assertEqual(len(cand.evidence_ids), 1)

        # Held-out suite verification
        ev2 = VerificationEvidence(
            candidate_id=cand.candidate_id,
            method="held_out_test",
            scope="held_out_suite",
            passed=True,
        )
        cand.attach_evidence(ev2)
        self.assertEqual(cand.status, CandidateStatus.HELD_OUT_PASSED)

        # Rejection by counterexample
        ev_fail = VerificationEvidence(
            candidate_id=cand.candidate_id,
            method="counterexample_probe",
            scope="active_probe",
            passed=False,
        )
        cand.attach_evidence(ev_fail)
        self.assertEqual(cand.status, CandidateStatus.REJECTED)


if __name__ == "__main__":
    unittest.main()
