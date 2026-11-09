"""System 1 Sandbox: candidate program validation against visible I/O pairs."""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from eve3.dsl.interpreter import DSLInterpreter, DSLParserError, ExecutionTimeoutError
from eve3.models import CandidateProgram, CandidateStatus, Diagnostics, VerificationEvidence

logger = logging.getLogger(__name__)


class ProgramSandbox:
    """Executes and filters candidate programs against I/O specifications."""

    def __init__(self, timeout_per_exec: float = 0.5):
        self.timeout = timeout_per_exec
        self.interpreter = DSLInterpreter()
        self.diagnostics = Diagnostics()

    def filter_valid_candidates(
        self,
        raw_candidates: List[Union[str, Tuple[str, str], CandidateProgram]],
        examples: List[Tuple[Any, Any]],
        created_by: str = "heuristic",
        source_details: Optional[Dict[str, str]] = None,
    ) -> List[CandidateProgram]:
        """Parse raw code strings and keep only those that satisfy all given examples."""
        valid_candidates: List[CandidateProgram] = []

        for item in raw_candidates:
            if isinstance(item, CandidateProgram):
                code = item.code_str
                detail = item.source_detail
                cand_created_by = item.created_by
            elif isinstance(item, tuple) and len(item) == 2:
                code, detail = item[0], item[1]
                cand_created_by = created_by
            else:
                code = str(item)
                detail = (source_details or {}).get(code, created_by)
                cand_created_by = created_by

            try:
                candidate = CandidateProgram(
                    code,
                    created_by=cand_created_by,
                    source_detail=detail,
                )
                if cand_created_by == "llm":
                    self.diagnostics.record_llm_candidate_stats(raw=1, syntax_valid=1, sandbox_passed=0)
            except (DSLParserError, ValueError, TypeError, SyntaxError, KeyError, IndexError) as exc:
                if cand_created_by == "llm":
                    self.diagnostics.record_llm_candidate_stats(raw=1, syntax_valid=0, sandbox_passed=0)
                self.diagnostics.record_sandbox_rejection(exc)
                self.diagnostics.record_swallowed_error("sandbox.filter_valid_candidates.parse", exc)
                logger.debug("Sandbox rejected invalid syntax %r: %s", code, exc)
                continue

            matches_all = True
            t0 = time.perf_counter()
            for inp, expected_out in examples:
                try:
                    actual_out = self.interpreter.run(candidate.ast, inp, timeout_seconds=self.timeout)
                    if actual_out != expected_out or type(actual_out) is not type(expected_out):
                        matches_all = False
                        break
                except (
                    ExecutionTimeoutError,
                    DSLParserError,
                    NameError,
                    AttributeError,
                    ValueError,
                    TypeError,
                    ZeroDivisionError,
                    IndexError,
                    KeyError,
                    RuntimeError,
                    RecursionError,
                    ArithmeticError,
                    LookupError,
                    MemoryError,
                ) as exc:
                    self.diagnostics.record_sandbox_rejection(exc)
                    self.diagnostics.record_swallowed_error("sandbox.filter_valid_candidates.exec", exc)
                    logger.debug("Sandbox rejected candidate %r on %r: %s", code, inp, exc)
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

            if matches_all:
                if cand_created_by == "llm":
                    self.diagnostics.record_llm_candidate_stats(raw=0, syntax_valid=0, sandbox_passed=1)
                if candidate not in valid_candidates:
                    valid_candidates.append(candidate)

        return valid_candidates
