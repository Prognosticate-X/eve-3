"""System 1 Sandbox: candidate program validation against visible I/O pairs."""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from eve3.dsl.interpreter import (
    DSLDepthExceededError,
    DSLInterpreter,
    DSLParserError,
    ExecutionTimeoutError,
)
from eve3.models import CandidateProgram, CandidateStatus, Diagnostics, VerificationEvidence

logger = logging.getLogger(__name__)


class ProgramSandbox:
    """Executes and filters candidate programs against I/O specifications."""

    def __init__(
        self,
        timeout_per_exec: float = 0.5,
        max_ast_depth: Optional[int] = 8,
        step_budget: int = 20000,
        max_output_size: int = 1000,
        max_integer_bits: int = 2048,
        max_recursion_depth: int = 50,
        extra_primitives: Optional[Dict[str, Any]] = None,
    ):
        self.timeout = timeout_per_exec
        self.max_ast_depth = max_ast_depth
        self.step_budget = step_budget
        self.max_output_size = max_output_size
        self.max_integer_bits = max_integer_bits
        self.max_recursion_depth = max_recursion_depth
        self.interpreter = DSLInterpreter(extra_primitives=extra_primitives)
        self.diagnostics = Diagnostics()

    def register_operator(
        self,
        name: str,
        body_or_fn: Union[str, Callable[..., Any], Any],
        arity: int = 1,
    ) -> None:
        """Register operator directly into the sandbox's DSLInterpreter."""
        self.interpreter.register_operator(name, body_or_fn, arity=arity)

    def register_crystallized_operators(self, operators: List[Dict[str, Any]]) -> None:
        """Batch register crystallized library operators into interpreter environment."""
        for op in operators:
            name = op.get("operator_name") or op.get("name")
            body = op.get("body_sexpr") or op.get("pattern_sexpr")
            arity = op.get("arity", 1)
            if name and body:
                self.register_operator(name, body, arity=arity)

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

            if self.max_ast_depth is not None and candidate.ast.depth > self.max_ast_depth:
                exc = DSLDepthExceededError(
                    f"Candidate AST depth ({candidate.ast.depth}) exceeds maximum allowed depth ({self.max_ast_depth})"
                )
                self.diagnostics.record_sandbox_rejection(exc)
                self.diagnostics.record_swallowed_error("sandbox.filter_valid_candidates.parse", exc)
                logger.debug("Sandbox rejected candidate %r depth: %s", code, exc)
                continue

            matches_all = True
            t0 = time.perf_counter()
            for inp, expected_out in examples:
                try:
                    actual_out = self.interpreter.run(
                        candidate.ast,
                        inp,
                        timeout_seconds=self.timeout,
                        step_budget=self.step_budget,
                        max_depth=self.max_ast_depth,
                        max_output_size=self.max_output_size,
                        max_integer_bits=self.max_integer_bits,
                        max_recursion_depth=self.max_recursion_depth,
                    )
                    if actual_out != expected_out or type(actual_out) is not type(expected_out):
                        matches_all = False
                        break
                except (
                    ExecutionTimeoutError,
                    DSLDepthExceededError,
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
