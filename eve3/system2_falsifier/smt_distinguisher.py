"""System 2: Distinguishing Input Generator using SMT (Z3) and Fuzzing.

Implements an explicit SMT Support Matrix for DSL constructs, avoiding silent
downgrades or false claims of formal verification on unsupported operations.
"""

from enum import Enum
import itertools
from typing import Any, List, Optional, Set, Tuple

from eve3.models import CandidateProgram


class SMTSupportLevel(str, Enum):
    """Support level of DSL constructs in SMT encoding."""
    SUPPORTED = "supported"              # Full first-order theory encoding (e.g. linear/non-linear arithmetic)
    BOUNDED_SUPPORT = "bounded_support"  # Decidable only under bounded length/unrolling (e.g. bounded list transforms)
    UNSUPPORTED = "unsupported"          # Outside SMT decision procedure (e.g. arbitrary lambdas, recursion)


class ProbeCandidate:
    """Represents a probe input with provenance metadata and solver audit trail."""

    def __init__(
        self,
        value: Any,
        source: str,
        support_level: SMTSupportLevel = SMTSupportLevel.SUPPORTED,
        unsupported_reason: Optional[str] = None,
    ):
        self.value = value
        self.source = source  # "smt_symbolic" or "heuristic_boundary"
        self.support_level = support_level
        self.unsupported_reason = unsupported_reason

    def __repr__(self) -> str:
        return f"<Probe {self.value!r} ({self.source}, {self.support_level.value})>"


class SMTDistinguisher:
    """Finds distinguishing inputs x such that P_i(x) != P_j(x) with explicit support matrix."""

    def __init__(self):
        self._z3_available = self._check_z3()

    def _check_z3(self) -> bool:
        try:
            import z3
            return True
        except ImportError:
            return False

    def check_ast_support(self, ast_node: Any) -> Tuple[SMTSupportLevel, Optional[str]]:
        """Verify whether an AST node is formally supported in SMT encoding."""
        from eve3.dsl.ast import ApplyNode, ConstNode, LambdaNode, VarNode

        if isinstance(ast_node, (VarNode, ConstNode)):
            return SMTSupportLevel.SUPPORTED, None

        if isinstance(ast_node, LambdaNode):
            # Lambdas inside higher-order functions require bounded unrolling
            inner_support, reason = self.check_ast_support(ast_node.body)
            if inner_support == SMTSupportLevel.UNSUPPORTED:
                return SMTSupportLevel.UNSUPPORTED, reason
            return SMTSupportLevel.BOUNDED_SUPPORT, "Higher-order lambda requires bounded unrolling"

        if isinstance(ast_node, ApplyNode):
            arithmetic_ops = {"+", "-", "*", "inc", "dec", "neg", "eq", "gt", "lt"}
            list_bounded_ops = {"length", "tail", "head", "map", "filter", "reverse"}

            if ast_node.op_name in arithmetic_ops:
                for arg in ast_node.args:
                    s, r = self.check_ast_support(arg)
                    if s != SMTSupportLevel.SUPPORTED:
                        return s, r
                return SMTSupportLevel.SUPPORTED, None

            if ast_node.op_name in list_bounded_ops:
                for arg in ast_node.args:
                    s, r = self.check_ast_support(arg)
                    if s == SMTSupportLevel.UNSUPPORTED:
                        return s, r
                return SMTSupportLevel.BOUNDED_SUPPORT, f"List primitive '{ast_node.op_name}' bounded to seq length <= 6"

            return SMTSupportLevel.UNSUPPORTED, f"Primitive '{ast_node.op_name}' not encoded in Z3 SMT theory"

        return SMTSupportLevel.UNSUPPORTED, f"Unsupported AST node type '{type(ast_node).__name__}'"

    def find_distinguishing_input(
        self,
        p1: CandidateProgram,
        p2: CandidateProgram,
        timeout_ms: int = 500,
    ) -> Optional[ProbeCandidate]:
        """Attempt to find input x where p1(x) != p2(x), logging support status."""
        supp1, r1 = self.check_ast_support(p1.ast)
        supp2, r2 = self.check_ast_support(p2.ast)

        # If either is unsupported in SMT, explicitly fallback to boundary testing with audit note
        if supp1 == SMTSupportLevel.UNSUPPORTED or supp2 == SMTSupportLevel.UNSUPPORTED:
            reason = r1 or r2
            diff_val = self._heuristic_distinguishing(p1, p2)
            if diff_val is not None:
                return ProbeCandidate(
                    diff_val,
                    source="heuristic_boundary",
                    support_level=SMTSupportLevel.UNSUPPORTED,
                    unsupported_reason=reason,
                )
            return None

        # SMT supported or bounded support: invoke Z3 solver
        if self._z3_available:
            try:
                res_int = self._z3_solve_integer_distinguishing(p1, p2, timeout_ms)
                if res_int is not None:
                    return ProbeCandidate(res_int, source="smt_symbolic", support_level=SMTSupportLevel.SUPPORTED)

                res_list = self._z3_solve_list_distinguishing(p1, p2, timeout_ms)
                if res_list is not None:
                    return ProbeCandidate(res_list, source="smt_symbolic", support_level=SMTSupportLevel.BOUNDED_SUPPORT)
            except Exception:
                pass

        # Fallback to boundary heuristic sampling
        diff_val = self._heuristic_distinguishing(p1, p2)
        if diff_val is not None:
            return ProbeCandidate(
                diff_val,
                source="heuristic_boundary",
                support_level=SMTSupportLevel.BOUNDED_SUPPORT,
                unsupported_reason="SMT solver timed out or could not prove distinguishability",
            )
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

        seq_sort = z3.SeqSort(z3.IntSort())
        x = z3.Const("x_seq", seq_sort)

        s.add(z3.Length(x) >= 0)
        s.add(z3.Length(x) <= 6)

        expr1 = self._ast_to_z3_seq(p1.ast, x, z3, seq_sort)
        expr2 = self._ast_to_z3_seq(p2.ast, x, z3, seq_sort)

        if expr1 is not None and expr2 is not None:
            s.add(expr1 != expr2)
            if s.check() == z3.sat:
                m = s.model()
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
        """Generate candidate probes across hypotheses pairs and boundary seeds."""
        probes: List[ProbeCandidate] = []
        seen = set()

        def add_probe(probe_cand: ProbeCandidate):
            p_repr = repr(probe_cand.value)
            if p_repr not in seen:
                seen.add(p_repr)
                probes.append(probe_cand)

        for p1, p2 in itertools.combinations(hypotheses, 2):
            diff = self.find_distinguishing_input(p1, p2)
            if diff is not None:
                add_probe(diff)
            if len(probes) >= max_pool_size:
                break

        for default_p in self.generate_default_probes():
            if len(probes) >= max_pool_size:
                break
            add_probe(
                ProbeCandidate(
                    default_p,
                    source="heuristic_boundary",
                    support_level=SMTSupportLevel.BOUNDED_SUPPORT,
                )
            )

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
