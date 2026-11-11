"""System 2: Distinguishing Input Generator using SMT (Z3) and Fuzzing.

Implements an explicit SMT Support Matrix for DSL constructs, avoiding silent
downgrades or false claims of formal verification on unsupported operations.
"""

from enum import Enum
import itertools
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from eve3.dsl.interpreter import DSLParserError, ExecutionTimeoutError
from eve3.models import CandidateProgram, Diagnostics

logger = logging.getLogger(__name__)


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
        self.diagnostics = Diagnostics()
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
        domain_hint: str = "generic",
    ) -> Optional[ProbeCandidate]:
        """Attempt to find input x where p1(x) != p2(x), logging support status."""
        supp1, r1 = self.check_ast_support(p1.ast)
        supp2, r2 = self.check_ast_support(p2.ast)

        # Detect domain if generic
        effective_domain = domain_hint
        if effective_domain == "generic":
            list_ops = {"reverse", "tail", "head", "sum", "length", "map", "filter", "fold", "cons", "concat"}
            code_tokens = set(p1.code_str.replace("(", " ").replace(")", " ").split())
            if list_ops.intersection(code_tokens):
                effective_domain = "list"
            else:
                effective_domain = "int"

        # If either is unsupported in SMT, explicitly fallback to boundary testing with audit note
        if supp1 == SMTSupportLevel.UNSUPPORTED or supp2 == SMTSupportLevel.UNSUPPORTED:
            self.diagnostics.record_z3_fallback()
            reason = r1 or r2
            diff_val = self._heuristic_distinguishing(p1, p2, domain_hint=effective_domain)
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
                if effective_domain != "list":
                    res_int = self._z3_solve_integer_distinguishing(p1, p2, timeout_ms)
                    if res_int is not None:
                        return ProbeCandidate(res_int, source="smt_symbolic", support_level=SMTSupportLevel.SUPPORTED)

                if effective_domain != "int":
                    res_list = self._z3_solve_list_distinguishing(p1, p2, timeout_ms)
                    if res_list is not None:
                        return ProbeCandidate(res_list, source="smt_symbolic", support_level=SMTSupportLevel.BOUNDED_SUPPORT)
            except (
                AttributeError,
                TypeError,
                ValueError,
                RuntimeError,
                KeyError,
                IndexError,
                ArithmeticError,
            ) as exc:
                self.diagnostics.record_swallowed_error("smt_distinguisher.find_distinguishing_input", exc)
                logger.warning("Z3 distinguishing solve raised %s: %s", type(exc).__name__, exc)

        # Fallback to boundary heuristic sampling
        self.diagnostics.record_z3_fallback()
        diff_val = self._heuristic_distinguishing(p1, p2, domain_hint=effective_domain)
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
            self.diagnostics.record_z3_call()
            check_res = s.check()
            if check_res == z3.unknown:
                self.diagnostics.record_z3_timeout()
            elif check_res == z3.sat:
                m = s.model()
                val = m[x].as_long()
                try:
                    if p1.evaluate(val) != p2.evaluate(val):
                        return val
                except (
                    ExecutionTimeoutError,
                    DSLParserError,
                    ValueError,
                    TypeError,
                    ZeroDivisionError,
                    IndexError,
                    KeyError,
                    RuntimeError,
                    ArithmeticError,
                ) as exc:
                    self.diagnostics.record_swallowed_error(
                        "smt_distinguisher._z3_solve_integer_distinguishing", exc
                    )
                    logger.debug("Integer witness evaluation error: %s", exc)

        return None

    def _eval_ast_bounded(self, ast_node: Any, env: Dict[str, Any], z3: Any) -> Optional[Any]:
        """Symbolically evaluate AST node over bounded lists and scalar Z3 expressions."""
        from eve3.dsl.ast import ApplyNode, ConstNode, IfElseNode, LambdaNode, VarNode

        if isinstance(ast_node, VarNode):
            return env.get(ast_node.name)

        if isinstance(ast_node, ConstNode):
            if isinstance(ast_node.value, int):
                return z3.IntVal(ast_node.value)
            if isinstance(ast_node.value, bool):
                return z3.BoolVal(ast_node.value)
            if isinstance(ast_node.value, list):
                return [z3.IntVal(v) for v in ast_node.value]
            return None

        if isinstance(ast_node, IfElseNode):
            cond = self._eval_ast_bounded(ast_node.condition, env, z3)
            then_b = self._eval_ast_bounded(ast_node.then_expr, env, z3)
            else_b = self._eval_ast_bounded(ast_node.else_expr, env, z3)
            if cond is not None and then_b is not None and else_b is not None:
                return z3.If(cond, then_b, else_b)
            return None

        if isinstance(ast_node, ApplyNode):
            op = ast_node.op_name
            args = ast_node.args

            if op == "map" and len(args) == 2:
                fn_node, list_arg = args[0], args[1]
                if not isinstance(fn_node, LambdaNode) or not fn_node.arg_names:
                    return None
                lst = self._eval_ast_bounded(list_arg, env, z3)
                if not isinstance(lst, list):
                    return None
                var_name = fn_node.arg_names[0]
                res = []
                for elem in lst:
                    sub_env = dict(env)
                    sub_env[var_name] = elem
                    out_elem = self._eval_ast_bounded(fn_node.body, sub_env, z3)
                    if out_elem is None:
                        return None
                    res.append(out_elem)
                return res

            if op == "reverse" and len(args) == 1:
                lst = self._eval_ast_bounded(args[0], env, z3)
                if isinstance(lst, list):
                    return list(reversed(lst))
                return None

            if op == "tail" and len(args) == 1:
                lst = self._eval_ast_bounded(args[0], env, z3)
                if isinstance(lst, list):
                    return lst[1:] if len(lst) > 0 else []
                return None

            if op == "head" and len(args) == 1:
                lst = self._eval_ast_bounded(args[0], env, z3)
                if isinstance(lst, list):
                    return lst[0] if len(lst) > 0 else z3.IntVal(0)
                return None

            if op == "length" and len(args) == 1:
                lst = self._eval_ast_bounded(args[0], env, z3)
                if isinstance(lst, list):
                    return z3.IntVal(len(lst))
                return None

            if op == "sum" and len(args) == 1:
                lst = self._eval_ast_bounded(args[0], env, z3)
                if isinstance(lst, list):
                    if not lst:
                        return z3.IntVal(0)
                    acc = lst[0]
                    for it in lst[1:]:
                        acc = acc + it
                    return acc
                return None

            if op == "+" and len(args) == 2:
                a1 = self._eval_ast_bounded(args[0], env, z3)
                a2 = self._eval_ast_bounded(args[1], env, z3)
                return (a1 + a2) if (a1 is not None and a2 is not None) else None

            if op == "-" and len(args) == 2:
                a1 = self._eval_ast_bounded(args[0], env, z3)
                a2 = self._eval_ast_bounded(args[1], env, z3)
                return (a1 - a2) if (a1 is not None and a2 is not None) else None

            if op == "*" and len(args) == 2:
                a1 = self._eval_ast_bounded(args[0], env, z3)
                a2 = self._eval_ast_bounded(args[1], env, z3)
                return (a1 * a2) if (a1 is not None and a2 is not None) else None

            if op == "inc" and len(args) == 1:
                a = self._eval_ast_bounded(args[0], env, z3)
                return (a + 1) if a is not None else None

            if op == "dec" and len(args) == 1:
                a = self._eval_ast_bounded(args[0], env, z3)
                return (a - 1) if a is not None else None

            if op == "neg" and len(args) == 1:
                a = self._eval_ast_bounded(args[0], env, z3)
                return (-a) if a is not None else None

            if op == "eq" and len(args) == 2:
                a1 = self._eval_ast_bounded(args[0], env, z3)
                a2 = self._eval_ast_bounded(args[1], env, z3)
                return (a1 == a2) if (a1 is not None and a2 is not None) else None

            if op == "gt" and len(args) == 2:
                a1 = self._eval_ast_bounded(args[0], env, z3)
                a2 = self._eval_ast_bounded(args[1], env, z3)
                return (a1 > a2) if (a1 is not None and a2 is not None) else None

            if op == "lt" and len(args) == 2:
                a1 = self._eval_ast_bounded(args[0], env, z3)
                a2 = self._eval_ast_bounded(args[1], env, z3)
                return (a1 < a2) if (a1 is not None and a2 is not None) else None

        return None

    def _z3_solve_list_distinguishing(
        self,
        p1: CandidateProgram,
        p2: CandidateProgram,
        timeout_ms: int,
    ) -> Optional[List[int]]:
        """Z3 SMT solver formulation for bounded list transformations."""
        import z3

        s = z3.Solver()
        s.set("timeout", timeout_ms)

        for k in (1, 2, 3, 0):
            elems = [z3.Int(f"x_{k}_{i}") for i in range(k)]
            env = {"x": elems, "input": elems}

            expr1 = self._eval_ast_bounded(p1.ast, env, z3)
            expr2 = self._eval_ast_bounded(p2.ast, env, z3)

            if expr1 is None or expr2 is None:
                continue

            # Case A: both outputs are lists
            if isinstance(expr1, list) and isinstance(expr2, list):
                if len(expr1) != len(expr2):
                    self.diagnostics.record_z3_call()
                    witness = [0] * k
                    try:
                        if p1.evaluate(witness) != p2.evaluate(witness):
                            return witness
                    except (
                        ExecutionTimeoutError,
                        DSLParserError,
                        ValueError,
                        TypeError,
                        ZeroDivisionError,
                        IndexError,
                        KeyError,
                        RuntimeError,
                        ArithmeticError,
                    ) as exc:
                        self.diagnostics.record_swallowed_error(
                            "smt_distinguisher._z3_solve_list_distinguishing", exc
                        )
                    continue

                if not expr1:
                    continue

                diff_cond = z3.Or([e1 != e2 for e1, e2 in zip(expr1, expr2)])
                s.push()
                s.add(diff_cond)
                self.diagnostics.record_z3_call()
                check_res = s.check()
                if check_res == z3.unknown:
                    self.diagnostics.record_z3_timeout()
                elif check_res == z3.sat:
                    m = s.model()
                    witness = [m.eval(elems[i], model_completion=True).as_long() for i in range(k)]
                    try:
                        if p1.evaluate(witness) != p2.evaluate(witness):
                            return witness
                    except (
                        ExecutionTimeoutError,
                        DSLParserError,
                        ValueError,
                        TypeError,
                        ZeroDivisionError,
                        IndexError,
                        KeyError,
                        RuntimeError,
                        ArithmeticError,
                    ) as exc:
                        self.diagnostics.record_swallowed_error(
                            "smt_distinguisher._z3_solve_list_distinguishing", exc
                        )
                s.pop()

            # Case B: both outputs are scalar (e.g. sum, length)
            elif not isinstance(expr1, list) and not isinstance(expr2, list):
                s.push()
                s.add(expr1 != expr2)
                self.diagnostics.record_z3_call()
                check_res = s.check()
                if check_res == z3.unknown:
                    self.diagnostics.record_z3_timeout()
                elif check_res == z3.sat:
                    m = s.model()
                    witness = [m.eval(elems[i], model_completion=True).as_long() for i in range(k)]
                    try:
                        if p1.evaluate(witness) != p2.evaluate(witness):
                            return witness
                    except (
                        ExecutionTimeoutError,
                        DSLParserError,
                        ValueError,
                        TypeError,
                        ZeroDivisionError,
                        IndexError,
                        KeyError,
                        RuntimeError,
                        ArithmeticError,
                    ) as exc:
                        self.diagnostics.record_swallowed_error(
                            "smt_distinguisher._z3_solve_list_distinguishing", exc
                        )
                s.pop()

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
        domain_hint: str = "generic",
    ) -> Optional[Any]:
        """Sample from boundary values and structural test cases."""
        probes = self.generate_default_probes(domain_hint=domain_hint)
        for x in probes:
            try:
                out1 = p1.evaluate(x)
                out2 = p2.evaluate(x)
                if out1 != out2:
                    return x
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
                ArithmeticError,
                LookupError,
            ) as exc:
                self.diagnostics.record_swallowed_error("smt_distinguisher._heuristic_distinguishing", exc)
                continue
        return None

    def generate_candidate_probe_pool(
        self,
        hypotheses: List[CandidateProgram],
        domain_hint: str = "generic",
        max_pool_size: int = 32,
    ) -> List[ProbeCandidate]:
        """Generate candidate probes across hypotheses pairs and boundary seeds."""
        effective_domain = domain_hint
        if effective_domain == "generic" and hypotheses:
            list_ops = {"reverse", "tail", "head", "sum", "length", "map", "filter", "fold", "cons", "concat"}
            code_tokens = set(hypotheses[0].code_str.replace("(", " ").replace(")", " ").split())
            if list_ops.intersection(code_tokens):
                effective_domain = "list"
            else:
                effective_domain = "int"

        probes: List[ProbeCandidate] = []
        seen = set()

        def add_probe(probe_cand: ProbeCandidate):
            p_repr = repr(probe_cand.value)
            if p_repr not in seen:
                seen.add(p_repr)
                probes.append(probe_cand)

        for p1, p2 in itertools.combinations(hypotheses, 2):
            diff = self.find_distinguishing_input(p1, p2, domain_hint=effective_domain)
            if diff is not None:
                add_probe(diff)
            if len(probes) >= max_pool_size:
                break

        for default_p in self.generate_default_probes(domain_hint=effective_domain):
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
    def generate_default_probes(domain_hint: str = "generic") -> List[Any]:
        """Domain boundary probes for list and integer transformations."""
        list_probes = [
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
        ]
        int_probes = [
            0,
            1,
            -1,
            2,
            5,
            10,
            -10,
            100,
        ]
        if domain_hint == "list":
            return list_probes
        if domain_hint == "int":
            return int_probes
        return list_probes + int_probes
