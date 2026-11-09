"""Symbolic Enumerative Synthesizer for EVE-3.

Provides deterministic bottom-up / top-down enumerative search for small depth
ASTs, ensuring guaranteed convergence on micro-tasks without LLM dependencies.
"""

import logging
from typing import Any, List, Optional, Set, Tuple

from eve3.dsl.ast import ApplyNode, ConstNode, LambdaNode, VarNode
from eve3.dsl.interpreter import DSLParserError
from eve3.models import CandidateProgram, CandidateStatus, Diagnostics

logger = logging.getLogger(__name__)


class SymbolicEnumerator:
    """Enumerates valid functional ASTs up to a bounded depth."""

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth
        self.diagnostics = Diagnostics()

    def enumerate_candidates(
        self,
        domain_hint: str = "list",  # "list" or "int"
        constant_pool: Optional[List[int]] = None,
        max_candidates: int = 30,
        mode: str = "generic_enumeration",
    ) -> List[CandidateProgram]:
        """Generate candidate programs up to max_depth."""
        if mode == "leaky_templates":
            return self._enumerate_leaky_templates(
                domain_hint=domain_hint,
                constant_pool=constant_pool,
                max_candidates=max_candidates,
            )
        return self._enumerate_generic_bottom_up(
            domain_hint=domain_hint,
            constant_pool=constant_pool,
            max_candidates=max_candidates,
        )

    def _enumerate_generic_bottom_up(
        self,
        domain_hint: str = "list",
        constant_pool: Optional[List[int]] = None,
        max_candidates: int = 30,
    ) -> List[CandidateProgram]:
        # C.2: Constant pool de-benchmarking: strictly {0, 1} unless explicitly passed from examples
        consts = sorted(set(constant_pool if constant_pool is not None else [0, 1]))
        candidates: List[CandidateProgram] = []
        seen: Set[str] = set()

        def add_code_at_depth(code: str, expected_depth: int) -> None:
            if expected_depth > self.max_depth or len(candidates) >= max_candidates:
                return
            if code in seen:
                return
            try:
                cand = CandidateProgram(
                    code_str=code,
                    status=CandidateStatus.CANDIDATE,
                    created_by="enumerator",
                    source_detail=f"enum:depth={expected_depth}:#{len(candidates) + 1}",
                )
                if cand.depth != expected_depth:
                    return
                seen.add(code)
                candidates.append(cand)
            except (DSLParserError, ValueError, TypeError, SyntaxError, KeyError, IndexError) as exc:
                self.diagnostics.record_swallowed_error("enumerator.enumerate_candidates", exc)
                logger.debug("Enumerator failed to parse %r: %s", code, exc)

        # Depth 1 (AST depth == 1): input variable
        if self.max_depth >= 1:
            add_code_at_depth("x", 1)

        # Depth 2 (AST depth == 2): single primitive applications on depth-1 atoms
        if self.max_depth >= 2:
            if domain_hint in ("list", "generic"):
                for op1 in ("reverse", "tail", "head", "sum", "length"):
                    add_code_at_depth(f"({op1} x)", 2)
                for k in (0, 1):
                    add_code_at_depth(f"(cons {k} x)", 2)
                add_code_at_depth("(concat x x)", 2)

            if domain_hint in ("int", "generic"):
                for op1 in ("inc", "dec", "neg", "is_even", "is_odd"):
                    add_code_at_depth(f"({op1} x)", 2)
                for k in consts:
                    for op2 in ("+", "-", "*", "gt", "lt", "eq"):
                        add_code_at_depth(f"({op2} x {k})", 2)

        # Depth 3 (AST depth == 3): two-step first-order compositions & depth-1 lambda bodies
        if self.max_depth >= 3:
            if domain_hint in ("list", "generic"):
                d2_unary_lists = ["(reverse x)", "(tail x)"]
                for e2 in d2_unary_lists:
                    for op1 in ("reverse", "tail", "head", "sum", "length"):
                        add_code_at_depth(f"({op1} {e2})", 3)
                # Higher-order map with depth-1 lambda body (AST depth == 3)
                for body_d1 in ("a", "0", "1"):
                    add_code_at_depth(f"(map (lambda (a) {body_d1}) x)", 3)
                # Binary cons/concat with depth-2 subtrees
                for int_d2 in ("(head x)", "(sum x)", "(length x)"):
                    add_code_at_depth(f"(cons {int_d2} x)", 3)
                for e2 in d2_unary_lists:
                    add_code_at_depth(f"(concat {e2} x)", 3)
                    add_code_at_depth(f"(concat x {e2})", 3)
                for e2_bin in ("(cons 0 x)", "(cons 1 x)", "(concat x x)"):
                    for op1 in ("reverse", "tail", "head", "sum", "length"):
                        add_code_at_depth(f"({op1} {e2_bin})", 3)

            if domain_hint in ("int", "generic"):
                for k in consts[:3]:
                    for op1 in ("inc", "dec", "neg"):
                        add_code_at_depth(f"({op1} (+ x {k}))", 3)

        # Depth 4 (AST depth == 4): single higher-order primitive (map/filter/fold) with depth-2 body
        if self.max_depth >= 4 and domain_hint in ("list", "generic"):
            for op1 in ("inc", "dec", "neg"):
                add_code_at_depth(f"(map (lambda (a) ({op1} a)) x)", 4)
            for pred1 in ("is_even", "is_odd"):
                add_code_at_depth(f"(filter (lambda (a) ({pred1} a)) x)", 4)
            for k in consts:
                for op2 in ("+", "-", "*"):
                    add_code_at_depth(f"(map (lambda (a) ({op2} a {k})) x)", 4)
                for pred2 in ("gt", "lt", "eq"):
                    add_code_at_depth(f"(filter (lambda (a) ({pred2} a {k})) x)", 4)
            add_code_at_depth("(map (lambda (a) (* a a)) x)", 4)
            add_code_at_depth("(fold (lambda (acc item) (+ acc item)) 0 x)", 4)
            add_code_at_depth("(fold (lambda (acc item) (* acc item)) 1 x)", 4)

        return candidates

    def _enumerate_leaky_templates(
        self,
        domain_hint: str = "list",
        constant_pool: Optional[List[int]] = None,
        max_candidates: int = 30,
    ) -> List[CandidateProgram]:
        """Legacy hardcoded template list retained only for leaky_templates comparison."""
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
                        source_detail=f"leaky_enum:#{len(candidates) + 1}",
                    )
                    candidates.append(cand)
                except (DSLParserError, ValueError, TypeError, SyntaxError, KeyError, IndexError) as exc:
                    self.diagnostics.record_swallowed_error("enumerator.enumerate_candidates", exc)
                    logger.debug("Enumerator failed to parse %r: %s", code, exc)

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
