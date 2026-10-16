"""System 1 Sandbox: candidate program validation against visible I/O pairs."""

import time
from typing import Any, List, Optional, Tuple

from eve3.dsl.ast import ASTNode
from eve3.dsl.interpreter import DSLInterpreter, DSLParserError, ExecutionTimeoutError, SExprParser


class CandidateProgram:
    """Represents a hypothesized program candidate with metadata."""

    def __init__(self, code_str: str, ast: Optional[ASTNode] = None):
        self.code_str = code_str.strip()
        self.ast = ast if ast is not None else SExprParser.parse(self.code_str)

    @property
    def description_length(self) -> int:
        return self.ast.description_length

    def evaluate(self, input_val: Any, timeout: float = 1.0) -> Any:
        interp = DSLInterpreter()
        return interp.run(self.ast, input_val, timeout_seconds=timeout)

    def __str__(self) -> str:
        return self.code_str

    def __repr__(self) -> str:
        return f"CandidateProgram({self.code_str!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CandidateProgram):
            return False
        return self.code_str == other.code_str

    def __hash__(self) -> int:
        return hash(self.code_str)


class ProgramSandbox:
    """Executes and filters candidate programs against I/O specifications."""

    def __init__(self, timeout_per_exec: float = 0.5):
        self.timeout = timeout_per_exec
        self.interpreter = DSLInterpreter()

    def filter_valid_candidates(
        self,
        raw_candidates: List[str],
        examples: List[Tuple[Any, Any]],
    ) -> List[CandidateProgram]:
        """Parse raw code strings and keep only those that satisfy all given examples."""
        valid_candidates: List[CandidateProgram] = []

        for code in raw_candidates:
            try:
                candidate = CandidateProgram(code)
            except (DSLParserError, Exception):
                continue

            matches_all = True
            for inp, expected_out in examples:
                try:
                    actual_out = self.interpreter.run(candidate.ast, inp, timeout_seconds=self.timeout)
                    if actual_out != expected_out:
                        matches_all = False
                        break
                except (ExecutionTimeoutError, Exception):
                    matches_all = False
                    break

            if matches_all and candidate not in valid_candidates:
                valid_candidates.append(candidate)

        return valid_candidates
