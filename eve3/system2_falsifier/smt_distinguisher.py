"""System 2: Distinguishing Input Generator using SMT (Z3) and Fuzzing."""

import itertools
from typing import Any, List, Optional, Set, Tuple

from eve3.system1_proposer.sandbox import CandidateProgram


class ProbeCandidate:
    """Represents a probe input with provenance metadata."""

    def __init__(self, value: Any, source: str):
        self.value = value
        self.source = source  # "smt_symbolic" or "heuristic_boundary"

    def __repr__(self) -> str:
        return f"<Probe {self.value!r} ({self.source})>"


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
    ) -> Optional[ProbeCandidate]:
        """Attempt to find input x where p1(x) != p2(x)."""
        # If Z3 is available, try symbolic solver
        if self._z3_available:
            try:
                # 1. Try SMT for Integer domains
                res_int = self._z3_solve_integer_distinguishing(p1, p2, timeout_ms)
                if res_int is not None:
                    return ProbeCandidate(res_int, source="smt_symbolic")

                # 2. Try SMT for Sequence / List domains
                res_list = self._z3_solve_list_distinguishing(p1, p2, timeout_ms)
                if res_list is not None:
                    return ProbeCandidate(res_list, source="smt_symbolic")
            except Exception:
                pass

        # Fallback to smart boundary heuristic sampling
        diff_val = self._heuristic_distinguishing(p1, p2)
        if diff_val is not None:
            return ProbeCandidate(diff_val, source="heuristic_boundary")
        return None

    def _z3_solve_integer_distinguishing(
        self,
        p1: CandidateProgram,
        p2: CandidateProgram,
        timeout_ms: int,
    ) -> Optional[Any]:
        """Z3 SMT solver formulation for integer arithmetic distinguishing inputs."""
        import z3

        s = z3.Solver()
        s.set("timeout", timeout_ms)
        x = z3.Int("x")

        expr1 = self._ast_to_z3_int(p1.ast, x, z3)
        expr2 = self._ast_to_z3_int(p2.ast, x, z3)

        if expr1 is not None and expr2 is not None:
            s.add(expr1 != expr2)
            if s.check() == z3.sat:
                m = s.model()
                val = m[x].as_long()
                try:
                    if p1.evaluate(val) != p2.evaluate(val):
                        return val
                except Exception:
                    pass

        return None

    def _z3_solve_list_distinguishing(
        self,
        p1: CandidateProgram,
        p2: CandidateProgram,
        timeout_ms: int,
    ) -> Optional[List[int]]:
        """Z3 SMT solver formulation for sequence/list transformations."""
        import z3

        s = z3.Solver()
        s.set("timeout", timeout_ms)

        # Represent list x as bounded integer array or sequence
        seq_sort = z3.SeqSort(z3.IntSort())
        x = z3.Const("x_seq", seq_sort)

        # Bound sequence length to realistic probe lengths (0 to 6)
        s.add(z3.Length(x) >= 0)
        s.add(z3.Length(x) <= 6)

        expr1 = self._ast_to_z3_seq(p1.ast, x, z3, seq_sort)
        expr2 = self._ast_to_z3_seq(p2.ast, x, z3, seq_sort)

        if expr1 is not None and expr2 is not None:
            s.add(expr1 != expr2)
            if s.check() == z3.sat:
                m = s.model()
                # Extract sequence values from model
                extracted_seq = []
                seq_val = m.eval(x)
                try:
                    length = m.eval(z3.Length(x)).as_long()
                    for i in range(min(length, 10)):
                        elem = m.eval(seq_val[i]).as_long()
                        extracted_seq.append(elem)
                    if p1.evaluate(extracted_seq) != p2.evaluate(extracted_seq):
                        return extracted_seq
                except Exception:
                    pass

        return None

    def _ast_to_z3_int(self, ast_node: Any, z3_var: Any, z3: Any) -> Optional[Any]:
        """Map AST to Z3 integer expression where possible."""
        from eve3.dsl.ast import ApplyNode, ConstNode, VarNode

        if isinstance(ast_node, VarNode) and ast_node.name in ("x", "input"):
            return z3_var
        if isinstance(ast_node, ConstNode) and isinstance(ast_node.value, int):
            return z3.IntVal(ast_node.value)
        if isinstance(ast_node, ApplyNode):
            sub_args = [self._ast_to_z3_int(arg, z3_var, z3) for arg in ast_node.args]
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

    def _ast_to_z3_seq(self, ast_node: Any, z3_seq_var: Any, z3: Any, seq_sort: Any) -> Optional[Any]:
        """Map AST to Z3 sequence/list expression."""
        from eve3.dsl.ast import ApplyNode, ConstNode, VarNode

        if isinstance(ast_node, VarNode) and ast_node.name in ("x", "input"):
            return z3_seq_var
        if isinstance(ast_node, ConstNode) and isinstance(ast_node.value, list):
            seq = z3.Empty(seq_sort)
            for v in reversed(ast_node.value):
                seq = z3.Concat(z3.Unit(z3.IntVal(v)), seq)
            return seq
        if isinstance(ast_node, ApplyNode):
            if ast_node.op_name == "length" and len(ast_node.args) == 1:
                inner = self._ast_to_z3_seq(ast_node.args[0], z3_seq_var, z3, seq_sort)
                if inner is not None:
                    return z3.Length(inner)
            if ast_node.op_name == "tail" and len(ast_node.args) == 1:
                inner = self._ast_to_z3_seq(ast_node.args[0], z3_seq_var, z3, seq_sort)
                if inner is not None:
                    return z3.Extract(inner, 1, z3.Length(inner) - 1)
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
    ) -> List[ProbeCandidate]:
        """Generate candidate probes across ALL hypotheses pairs and boundary seeds."""
        probes: List[ProbeCandidate] = []
        seen = set()

        def add_probe(probe_cand: ProbeCandidate):
            p_repr = repr(probe_cand.value)
            if p_repr not in seen:
                seen.add(p_repr)
                probes.append(probe_cand)

        # 1. Pairwise distinguishing inputs across all hypotheses
        for p1, p2 in itertools.combinations(hypotheses, 2):
            diff = self.find_distinguishing_input(p1, p2)
            if diff is not None:
                add_probe(diff)
            if len(probes) >= max_pool_size:
                break

        # 2. Add boundary probes as fallback
        for default_p in self.generate_default_probes():
            if len(probes) >= max_pool_size:
                break
            add_probe(ProbeCandidate(default_p, source="heuristic_boundary"))

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
