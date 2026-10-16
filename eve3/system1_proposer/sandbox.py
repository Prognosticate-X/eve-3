"""System 1 Sandbox: candidate program validation against visible I/O pairs."""

import time
from typing import Any, List, Optional, Tuple

from eve3.dsl.interpreter import DSLInterpreter, DSLParserError, ExecutionTimeoutError
from eve3.models import CandidateProgram, CandidateStatus, VerificationEvidence


class ProgramSandbox:
    """Executes and filters candidate programs against I/O specifications."""

    def __init__(self, timeout_per_exec: float = 0.5):
        self.timeout = timeout_per_exec
        self.interpreter = DSLInterpreter()

    def filter_valid_candidates(
        self,
        raw_candidates: List[str],
        examples: List[Tuple[Any, Any]],
        created_by: str = "heuristic",
    ) -> List[CandidateProgram]:
        """Parse raw code strings and keep only those that satisfy all given examples."""
        valid_candidates: List[CandidateProgram] = []

        for code in raw_candidates:
            try:
                candidate = CandidateProgram(code, created_by=created_by)
            except (DSLParserError, Exception):
                continue

            matches_all = True
            t0 = time.perf_counter()
            for inp, expected_out in examples:
                try:
                    actual_out = self.interpreter.run(candidate.ast, inp, timeout_seconds=self.timeout)
                    if actual_out != expected_out:
                        matches_all = False
                        break
                except (ExecutionTimeoutError, Exception):
                    matches_all = False
                    break
            runtime_ms = (time.perf_counter() - t0) * 1000.0

            evidence = VerificationEvidence(
                method="unit_test",
                scope="observed_examples",
                passed=matches_all,
                runtime_ms=runtime_ms,
            )
            candidate.attach_evidence(evidence)

            if matches_all and candidate not in valid_candidates:
                valid_candidates.append(candidate)

        return valid_candidates
