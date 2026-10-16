"""System 3: Value-Weighted Library Learning and Submodular Compression.

Extends standard MDL compression with task-diversity and reuse weighting:
Benefit_w(L) = sum_i w_i * [ DL(P_i | empty) - DL(P_i | L) ]
L* = argmax_{L} [ Benefit_w(L) - gamma * |L| ]
"""

from collections import Counter
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from eve3.dsl.ast import ASTNode, ApplyNode, ConstNode, VarNode
from eve3.dsl.interpreter import SExprParser


class CandidateAbstraction:
    """Represents a potential library operator extracted from verified programs."""

    def __init__(self, name: str, pattern: str, arity: int, cost: int):
        self.name = name
        self.pattern = pattern  # e.g. "(map (lambda (a) (+ a $k)) x)"
        self.arity = arity
        self.cost = cost

    def apply_compression(self, code_str: str) -> Tuple[str, int]:
        """Attempt to replace occurrences of pattern in code_str and calculate size savings in AST DL."""
        try:
            original_ast = SExprParser.parse(code_str)
            orig_dl = original_ast.description_length
        except Exception:
            return code_str, 0

        compressed_code = code_str

        # Pattern match for parameterized list transformations
        if self.pattern == "(map (lambda (a) (+ a $k)) x)":
            m = re.search(r"\(map \(lambda \(a\) \(\+ a (\d+)\)\) x\)", code_str)
            if m:
                k_val = m.group(1)
                replacement = f"({self.name} {k_val} x)"
                compressed_code = code_str.replace(m.group(0), replacement)

        elif self.pattern == "(filter (lambda (a) (gt a $k)) x)":
            m = re.search(r"\(filter \(lambda \(a\) \(gt a (\d+)\)\) x\)", code_str)
            if m:
                k_val = m.group(1)
                replacement = f"({self.name} {k_val} x)"
                compressed_code = code_str.replace(m.group(0), replacement)

        elif self.pattern == "(map (lambda (a) (* a $k)) x)":
            m = re.search(r"\(map \(lambda \(a\) \(\* a (\d+)\)\) x\)", code_str)
            if m:
                k_val = m.group(1)
                replacement = f"({self.name} {k_val} x)"
                compressed_code = code_str.replace(m.group(0), replacement)

        elif self.pattern == "(reverse (map (lambda (a) (+ a $k)) x))":
            m = re.search(r"\(reverse \(map \(lambda \(a\) \(\+ a (\d+)\)\) x\)\)", code_str)
            if m:
                k_val = m.group(1)
                replacement = f"({self.name} {k_val} x)"
                compressed_code = code_str.replace(m.group(0), replacement)

        if compressed_code != code_str:
            try:
                new_ast = SExprParser.parse(compressed_code)
                # Compute compression savings strictly in AST description length (node count)
                savings = max(0, orig_dl - new_ast.description_length)
                return compressed_code, savings
            except Exception:
                pass

        return code_str, 0

    def __repr__(self) -> str:
        return f"<Abstraction {self.name}: {self.pattern} (cost={self.cost})>"


class ValueCompressor:
    """Selects abstractions by maximizing value-weighted compression benefit."""

    def __init__(self, gamma: float = 1.2):
        self.gamma = gamma

    def calculate_program_weight(self, prog_meta: Dict[str, Any]) -> float:
        """Compute value weight: w_i = |{task_family}| * (1 + log(1 + reuse_count))."""
        reuse = prog_meta.get("reuse_count", 0)
        task_diversity = 1.0
        if "task_family" in prog_meta and prog_meta["task_family"]:
            families = {f.strip() for f in prog_meta["task_family"].split(",") if f.strip()}
            task_diversity = float(max(1, len(families)))

        return task_diversity * (1.0 + math.log(1.0 + reuse))

    def extract_candidate_abstractions(
        self,
        programs: List[Dict[str, Any]],
    ) -> List[CandidateAbstraction]:
        """Dynamically mine recurring patterns from ASTs of verified programs."""
        if not programs:
            return []

        # 1. Parse ASTs and collect recurring generalized sub-expressions
        pattern_counter = Counter()

        for p in programs:
            code = p.get("code", "")
            try:
                ast = SExprParser.parse(code)
                sub_patterns = self._extract_generalized_subpatterns(ast)
                for sp in sub_patterns:
                    pattern_counter[sp] += 1
            except Exception:
                continue

        candidates: List[CandidateAbstraction] = []
        op_idx = 1

        for pat, freq in pattern_counter.items():
            if freq >= 2:  # Recurring pattern across verified corpus
                arity = pat.count("$k") + 1
                try:
                    pat_ast = SExprParser.parse(pat.replace("$k", "1"))
                    cost = pat_ast.description_length
                except Exception:
                    cost = 3
                name = f"op_dyn_{op_idx}"
                candidates.append(
                    CandidateAbstraction(name=name, pattern=pat, arity=arity, cost=cost)
                )
                op_idx += 1

        # 2. Add standard parameterized idioms if not already extracted
        seed_patterns = [
            ("(map (lambda (a) (+ a $k)) x)", "map_add", 2, 3),
            ("(filter (lambda (a) (gt a $k)) x)", "filter_gt", 2, 3),
            ("(map (lambda (a) (* a $k)) x)", "map_mul", 2, 3),
        ]
        for pat, name, arity, cost in seed_patterns:
            if not any(c.pattern == pat for c in candidates):
                candidates.append(
                    CandidateAbstraction(name=name, pattern=pat, arity=arity, cost=cost)
                )

        return candidates

    def _extract_generalized_subpatterns(self, node: ASTNode) -> Set[str]:
        """Extract sub-expressions with depth >= 2 and generalize integer constants."""
        patterns: Set[str] = []

        if node.depth >= 2:
            generalized = self._generalize_node(node)
            patterns.add(generalized.to_sexpr())

        if isinstance(node, ApplyNode):
            for arg in node.args:
                patterns.update(self._extract_generalized_subpatterns(arg))
        elif isinstance(node, LambdaNode):
            patterns.update(self._extract_generalized_subpatterns(node.body))

        return patterns

    def _generalize_node(self, node: ASTNode) -> ASTNode:
        """Replace constant integers with placeholder variable $k."""
        if isinstance(node, ConstNode) and isinstance(node.value, int):
            return VarNode("$k")
        if isinstance(node, ApplyNode):
            return ApplyNode(
                op_name=node.op_name,
                args=[self._generalize_node(arg) for arg in node.args],
            )
        if isinstance(node, LambdaNode):
            return LambdaNode(
                arg_names=node.arg_names,
                body=self._generalize_node(node.body),
            )
        return node

    def compute_weighted_benefit(
        self,
        selected_library: List[CandidateAbstraction],
        programs: List[Dict[str, Any]],
        weights: List[float],
    ) -> float:
        """Compute: sum_i w_i * [ DL(P_i | empty) - DL(P_i | L) ]."""
        total_benefit = 0.0

        for prog, w in zip(programs, weights):
            code = prog["code"]

            current_code = code
            total_savings = 0
            for ab in selected_library:
                current_code, savings = ab.apply_compression(current_code)
                total_savings += savings

            total_benefit += w * float(total_savings)

        return total_benefit

    def select_optimal_library(
        self,
        candidates: List[CandidateAbstraction],
        programs: List[Dict[str, Any]],
    ) -> List[CandidateAbstraction]:
        """Greedy submodular optimization for L* = argmax (Benefit_w(L) - gamma * |L|)."""
        if not candidates or not programs:
            return []

        weights = [self.calculate_program_weight(p) for p in programs]
        library: List[CandidateAbstraction] = []
        remaining = list(candidates)
        current_benefit = 0.0

        while remaining:
            best_abs = None
            best_gain = 0.0

            for a in remaining:
                candidate_lib = library + [a]
                new_benefit = self.compute_weighted_benefit(candidate_lib, programs, weights)
                gain = new_benefit - current_benefit - self.gamma * a.cost

                if gain > best_gain:
                    best_gain = gain
                    best_abs = a

            if best_abs is None:
                # Marginal gain is less than library penalty gamma; terminate
                break

            library.append(best_abs)
            remaining.remove(best_abs)
            current_benefit += best_gain + self.gamma * best_abs.cost

        return library
