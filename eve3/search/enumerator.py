"""Symbolic Enumerative Synthesizer for EVE-3.

Provides deterministic bottom-up / top-down enumerative search for small depth
ASTs, ensuring guaranteed convergence on micro-tasks without LLM dependencies.
"""

from typing import Any, List, Optional, Set, Tuple

from eve3.dsl.ast import ApplyNode, ConstNode, LambdaNode, VarNode
from eve3.models import CandidateProgram, CandidateStatus


class SymbolicEnumerator:
    """Enumerates valid functional ASTs up to a bounded depth."""

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth

    def enumerate_candidates(
        self,
        domain_hint: str = "list",  # "list" or "int"
        constant_pool: Optional[List[int]] = None,
        max_candidates: int = 30,
    ) -> List[CandidateProgram]:
        """Generate candidate programs up to max_depth."""
        consts = constant_pool or [0, 1, 2, -1, 3]
        candidates: List[CandidateProgram] = []
        seen: Set[str] = set()

        def add_code(code: str):
            if code not in seen and len(candidates) < max_candidates:
                seen.add(code)
                try:
                    cand = CandidateProgram(
                        code_str=code,
                        status=CandidateStatus.CANDIDATE,
                        created_by="enumerator",
                    )
                    candidates.append(cand)
                except Exception:
                    pass

        # Depth 1: identity
        add_code("x")

        # Depth 2: list primitives & single-step transforms
        if domain_hint in ("list", "generic"):
            add_code("(reverse x)")
            add_code("(tail x)")
            add_code("(head x)")
            add_code("(sum x)")
            add_code("(length x)")

            # Simple unary map / filter
            add_code("(map (lambda (a) (inc a)) x)")
            add_code("(map (lambda (a) (dec a)) x)")
            add_code("(map (lambda (a) (neg a)) x)")
            add_code("(filter (lambda (a) (is_even a)) x)")
            add_code("(filter (lambda (a) (is_odd a)) x)")

            # Parameterized map / filter with constant pool
            for k in consts:
                add_code(f"(map (lambda (a) (+ a {k})) x)")
                add_code(f"(map (lambda (a) (- a {k})) x)")
                add_code(f"(map (lambda (a) (* a {k})) x)")
                add_code(f"(filter (lambda (a) (gt a {k})) x)")
                add_code(f"(filter (lambda (a) (lt a {k})) x)")
                add_code(f"(filter (lambda (a) (eq a {k})) x)")

            # Reductions
            add_code("(fold (lambda (acc item) (+ acc item)) 0 x)")
            add_code("(fold (lambda (acc item) (* acc item)) 1 x)")

            # Depth 3: compositions
            if self.max_depth >= 3:
                for k in (1, 2):
                    add_code(f"(reverse (map (lambda (a) (+ a {k})) x))")
                    add_code(f"(sum (map (lambda (a) (+ a {k})) x))")
                    add_code(f"(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a {k})) x))")

        if domain_hint in ("int", "generic"):
            for k in consts:
                add_code(f"(+ x {k})")
                add_code(f"(- x {k})")
                add_code(f"(* x {k})")
            add_code("(inc x)")
            add_code("(dec x)")
            add_code("(neg x)")

        return candidates
