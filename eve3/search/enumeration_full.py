"""True Bottom-Up AST Enumeration with Observational Equivalence (OE) Pruning.

Implements enumeration_full baseline (Prompt S1.1 Section C.3).
Allows arbitrary nesting of first-order and higher-order DSL primitives,
bounded strictly by AST node budget (max_size) and wall-clock timeout budget.
"""

from __future__ import annotations

import itertools
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from eve3.dsl.interpreter import DSLInterpreter, DSLParserError, ExecutionTimeoutError, SExprParser
from eve3.models import CandidateProgram, CandidateStatus, Diagnostics

logger = logging.getLogger(__name__)


def extract_constants_from_examples(examples: List[Tuple[Any, Any]]) -> List[int]:
    """C.2: Constant pool de-benchmarking: constants strictly from {0, 1} U values appearing in examples."""
    pool: Set[int] = {0, 1}
    for inp, out in examples:
        for val in (inp, out):
            if isinstance(val, int):
                pool.add(val)
            elif isinstance(val, (list, tuple)):
                for item in val:
                    if isinstance(item, int):
                        pool.add(item)
    return sorted(pool)


class BottomUpOEEnumerator:
    """True bottom-up AST synthesizer with observational-equivalence signature pruning."""

    def __init__(
        self,
        max_size: int = 9,
        timeout_seconds: float = 60.0,
    ):
        self.max_size = max_size
        self.timeout_seconds = timeout_seconds
        self.interpreter = DSLInterpreter()
        self.parser = SExprParser()
        self.diagnostics = Diagnostics()

    @staticmethod
    def to_hashable(val: Any) -> Any:
        if isinstance(val, (list, tuple)):
            return tuple(BottomUpOEEnumerator.to_hashable(v) for v in val)
        return val

    def synthesize(
        self,
        train_examples: List[Tuple[Any, Any]],
        held_out_tests: Optional[List[Tuple[Any, Any]]] = None,
        constant_pool: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Run bottom-up enumeration with OE pruning to find satisfying programs."""
        t0 = time.perf_counter()
        if not train_examples:
            return {"solved": False, "program": None, "elapsed_ms": 0.0, "total_enumerated": 0, "size": None}

        consts = sorted(set(constant_pool if constant_pool is not None else extract_constants_from_examples(train_examples)))
        target_sig = tuple(self.to_hashable(out) for _, out in train_examples)

        # Expressions organized by AST size: size -> list of (code_str, type_tag, sig)
        # Type tags: "list", "int", "bool"
        by_size: Dict[int, List[Tuple[str, str, Tuple[Any, ...]]]] = {s: [] for s in range(1, self.max_size + 1)}
        sig_seen: Dict[Tuple[str, Tuple[Any, ...]], int] = {}  # (type_tag, sig) -> min_size

        total_enumerated = 0

        def _eval_on_train(code: str) -> Optional[Tuple[Any, ...]]:
            try:
                ast_node = self.parser.parse(code)
                sig = []
                for inp, _ in train_examples:
                    out = self.interpreter.run(ast_node, inp, timeout_seconds=0.2)
                    sig.append(self.to_hashable(out))
                return tuple(sig)
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
            ):
                return None

        def _register(code: str, type_tag: str, size: int) -> Optional[str]:
            nonlocal total_enumerated
            if size > self.max_size:
                return None
            total_enumerated += 1
            sig = _eval_on_train(code)
            if sig is None:
                return None

            # Check if this solves training examples
            if sig == target_sig:
                return code

            key = (type_tag, sig)
            if key not in sig_seen or size < sig_seen[key]:
                sig_seen[key] = size
                by_size[size].append((code, type_tag, sig))
            return None

        # Build reusable lambda predicates/mappings for higher-order combinators
        # Unary list transforms on elements: (inc a), (dec a), (neg a), (+ a k), (- a k), (* a k)
        int_to_int_lambdas: List[Tuple[str, int]] = [
            ("(lambda (a) (inc a))", 3),
            ("(lambda (a) (dec a))", 3),
            ("(lambda (a) (neg a))", 3),
        ]
        for k in consts:
            for op in ("+", "-", "*"):
                int_to_int_lambdas.append((f"(lambda (a) ({op} a {k}))", 4))

        # Int to bool predicates on elements: (is_even a), (is_odd a), (gt a k), (lt a k), (eq a k)
        int_to_bool_lambdas: List[Tuple[str, int]] = [
            ("(lambda (a) (is_even a))", 3),
            ("(lambda (a) (is_odd a))", 3),
        ]
        for k in consts:
            for pred in ("gt", "lt", "eq"):
                int_to_bool_lambdas.append((f"(lambda (a) ({pred} a {k}))", 4))

        # Size 1: Variable and Constants
        sol = _register("x", "list", 1)
        if sol:
            return self._finalize(sol, t0, total_enumerated, 1, held_out_tests)

        for c in consts:
            sol = _register(str(c), "int", 1)
            if sol:
                return self._finalize(sol, t0, total_enumerated, 1, held_out_tests)

        # Enumerate by increasing AST size
        for current_size in range(2, self.max_size + 1):
            if (time.perf_counter() - t0) > self.timeout_seconds:
                break

            # 1. Unary list operators: (reverse e), (tail e) [cost = 1 + size(e)]
            inner_size = current_size - 1
            for code_in, tag, _ in by_size.get(inner_size, []):
                if tag == "list":
                    for op in ("reverse", "tail"):
                        sol = _register(f"({op} {code_in})", "list", current_size)
                        if sol:
                            return self._finalize(sol, t0, total_enumerated, current_size, held_out_tests)

                    for op in ("sum", "length", "head"):
                        sol = _register(f"({op} {code_in})", "int", current_size)
                        if sol:
                            return self._finalize(sol, t0, total_enumerated, current_size, held_out_tests)

                elif tag == "int":
                    for op in ("inc", "dec", "neg"):
                        sol = _register(f"({op} {code_in})", "int", current_size)
                        if sol:
                            return self._finalize(sol, t0, total_enumerated, current_size, held_out_tests)

            # 2. Binary list operators: (cons e1 e2), (concat e1 e2) [cost = 1 + s1 + s2]
            for s1 in range(1, current_size - 1):
                s2 = current_size - 1 - s1
                for c1, tag1, _ in by_size.get(s1, []):
                    for c2, tag2, _ in by_size.get(s2, []):
                        if tag1 == "int" and tag2 == "list":
                            sol = _register(f"(cons {c1} {c2})", "list", current_size)
                            if sol:
                                return self._finalize(sol, t0, total_enumerated, current_size, held_out_tests)
                        if tag1 == "list" and tag2 == "list":
                            sol = _register(f"(concat {c1} {c2})", "list", current_size)
                            if sol:
                                return self._finalize(sol, t0, total_enumerated, current_size, held_out_tests)

            # 3. Higher-order operators:
            # (filter (lambda (a) pred) list_expr) [cost = 1 + size(pred_lambda) + size(list_expr)]
            for lam_code, lam_size in int_to_bool_lambdas:
                list_size = current_size - 1 - lam_size
                if list_size >= 1:
                    for list_code, tag, _ in by_size.get(list_size, []):
                        if tag == "list":
                            sol = _register(f"(filter {lam_code} {list_code})", "list", current_size)
                            if sol:
                                return self._finalize(sol, t0, total_enumerated, current_size, held_out_tests)

            # (map (lambda (a) body) list_expr) [cost = 1 + size(map_lambda) + size(list_expr)]
            for lam_code, lam_size in int_to_int_lambdas:
                list_size = current_size - 1 - lam_size
                if list_size >= 1:
                    for list_code, tag, _ in by_size.get(list_size, []):
                        if tag == "list":
                            sol = _register(f"(map {lam_code} {list_code})", "list", current_size)
                            if sol:
                                return self._finalize(sol, t0, total_enumerated, current_size, held_out_tests)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "solved": False,
            "program": None,
            "elapsed_ms": round(elapsed_ms, 2),
            "total_enumerated": total_enumerated,
            "size": None,
        }

    def _finalize(
        self,
        program: str,
        t0: float,
        total_enumerated: int,
        size: int,
        held_out_tests: Optional[List[Tuple[Any, Any]]],
    ) -> Dict[str, Any]:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        passed_held_out = True
        if held_out_tests:
            try:
                ast_node = self.parser.parse(program)
                for inp, expected in held_out_tests:
                    actual = self.interpreter.run(ast_node, inp, timeout_seconds=0.2)
                    if actual != expected or type(actual) is not type(expected):
                        passed_held_out = False
                        break
            except (
                DSLParserError,
                DSLExecutionError,
                ExecutionTimeoutError,
                TypeError,
                ZeroDivisionError,
                IndexError,
                ValueError,
                KeyError,
                AttributeError,
                RecursionError,
            ):
                passed_held_out = False

        return {
            "solved": passed_held_out,
            "program": program,
            "elapsed_ms": round(elapsed_ms, 2),
            "total_enumerated": total_enumerated,
            "size": size,
            "held_out_passed": passed_held_out,
        }
