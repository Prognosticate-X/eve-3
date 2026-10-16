"""System 2: Distinguishing Input Generator using SMT (Z3) and Fuzzing."""

import itertools
import random
from typing import Any, List, Optional, Set, Tuple

from eve3.system1_proposer.sandbox import CandidateProgram


class SMTDistinguisher:
    """Finds distinguishing inputs x such that P_i(x) != P_j(x)."""

    def __init__(self):
        self._z3_available = self._check_z3()

    def _check_z3(self) -> bool:
        try:
            import z3
            return True
        except ImportError:
            return False

    def find_distinguishing_input(
        self,
        p1: CandidateProgram,
        p2: CandidateProgram,
        timeout_ms: int = 500,
    ) -> Optional[Any]:
        """Attempt to find input x where p1(x) != p2(x)."""
        # If Z3 is available, try symbolic solver
        if self._z3_available:
            try:
                res = self._z3_solve_distinguishing(p1, p2, timeout_ms)
                if res is not None:
                    return res
            except Exception:
                pass

        # Fallback to smart boundary heuristic sampling
        return self._heuristic_distinguishing(p1, p2)

    def _z3_solve_distinguishing(
        self,
        p1: CandidateProgram,
        p2: CandidateProgram,
        timeout_ms: int,
    ) -> Optional[Any]:
        """Z3 SMT solver formulation for integer arithmetic distinguishing inputs."""
        import z3

        # Formulate for integer input 'x'
        s = z3.Solver()
        s.set("timeout", timeout_ms)
        x = z3.Int("x")

        # Basic SMT expression mapping for simple expressions
        expr1 = self._ast_to_z3(p1.ast, x, z3)
        expr2 = self._ast_to_z3(p2.ast, x, z3)

        if expr1 is not None and expr2 is not None:
            s.add(expr1 != expr2)
            if s.check() == z3.sat:
                m = s.model()
                val = m[x].as_long()
                # Verify in interpreter
                try:
                    if p1.evaluate(val) != p2.evaluate(val):
                        return val
                except Exception:
                    pass

        return None

    def _ast_to_z3(self, ast_node: Any, z3_var: Any, z3: Any) -> Optional[Any]:
        """Map AST to Z3 integer expression where possible."""
        from eve3.dsl.ast import ApplyNode, ConstNode, VarNode

        if isinstance(ast_node, VarNode) and ast_node.name in ("x", "input"):
            return z3_var
        if isinstance(ast_node, ConstNode) and isinstance(ast_node.value, int):
            return z3.IntVal(ast_node.value)
        if isinstance(ast_node, ApplyNode):
            sub_args = [self._ast_to_z3(arg, z3_var, z3) for arg in ast_node.args]
            if any(a is None for a in sub_args):
                return None
            if ast_node.op_name == "+" and len(sub_args) == 2:
                return sub_args[0] + sub_args[1]
            if ast_node.op_name == "-" and len(sub_args) == 2:
                return sub_args[0] - sub_args[1]
            if ast_node.op_name == "*" and len(sub_args) == 2:
                return sub_args[0] * sub_args[1]
            if ast_node.op_name == "inc" and len(sub_args) == 1:
                return sub_args[0] + 1
            if ast_node.op_name == "dec" and len(sub_args) == 1:
                return sub_args[0] - 1
            if ast_node.op_name == "neg" and len(sub_args) == 1:
                return -sub_args[0]
        return None

    def _heuristic_distinguishing(
        self,
        p1: CandidateProgram,
        p2: CandidateProgram,
    ) -> Optional[Any]:
        """Sample from boundary values and structural test cases."""
        probes = self.generate_default_probes()
        for x in probes:
            try:
                out1 = p1.evaluate(x)
                out2 = p2.evaluate(x)
                if out1 != out2:
                    return x
            except Exception:
                continue
        return None

    def generate_candidate_probe_pool(
        self,
        hypotheses: List[CandidateProgram],
        max_pool_size: int = 32,
    ) -> List[Any]:
        """Generate candidate probes by pairing hypotheses and finding distinguishing inputs."""
        probes: List[Any] = []
        seen = set()

        def add_probe(p: Any):
            p_repr = repr(p)
            if p_repr not in seen:
                seen.add(p_repr)
                probes.append(p)

        # 1. Pairwise distinguishing inputs
        for p1, p2 in itertools.combinations(hypotheses[:8], 2):
            diff = self.find_distinguishing_input(p1, p2)
            if diff is not None:
                add_probe(diff)
            if len(probes) >= max_pool_size:
                break

        # 2. Add boundary probes
        for default_p in self.generate_default_probes():
            if len(probes) >= max_pool_size:
                break
            add_probe(default_p)

        return probes

    @staticmethod
    def generate_default_probes() -> List[Any]:
        """Domain boundary probes for list and integer transformations."""
        return [
            [],
            [0],
            [1],
            [-1],
            [1, 2],
            [2, 1],
            [0, 0, 0],
            [1, 2, 3, 4, 5],
            [-5, -2, 0, 3, 8],
            [10, 20, 30],
            [2, 4, 6, 8],
            [1, 3, 5, 7],
            [100, -100],
            0,
            1,
            -1,
            2,
            5,
            10,
            -10,
            100,
        ]
