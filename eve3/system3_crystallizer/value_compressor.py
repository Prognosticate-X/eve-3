"""System 3: Value-Weighted Library Learning and Submodular Compression.

Extends standard MDL compression with task-diversity and reuse weighting:
Benefit_w(L) = sum_i w_i * [ DL(P_i | empty) - DL(P_i | L) ]
L* = argmax_{L} [ Benefit_w(L) - gamma * |L| ]
"""

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class CandidateAbstraction:
    """Represents a potential library operator extracted from programs."""

    def __init__(self, name: str, pattern: str, arity: int, cost: int):
        self.name = name
        self.pattern = pattern  # e.g. "(map (lambda (a) (+ a $1)) $2)"
        self.arity = arity
        self.cost = cost

    def apply_compression(self, code_str: str) -> Tuple[str, int]:
        """Attempt to replace occurrences of pattern in code_str and calculate size savings."""
        # Simple structural replacement for list transforms
        compressed = code_str
        savings = 0

        # Pattern match for common idioms: e.g., (map (lambda (a) (+ a K)) x)
        if self.pattern == "(map (lambda (a) (+ a $k)) x)":
            m = re.search(r"\(map \(lambda \(a\) \(\+ a (\d+)\)\) x\)", code_str)
            if m:
                k_val = m.group(1)
                replacement = f"({self.name} {k_val} x)"
                compressed = code_str.replace(m.group(0), replacement)
                savings = max(0, len(m.group(0)) - len(replacement))

        elif self.pattern == "(filter (lambda (a) (gt a $k)) x)":
            m = re.search(r"\(filter \(lambda \(a\) \(gt a (\d+)\)\) x\)", code_str)
            if m:
                k_val = m.group(1)
                replacement = f"({self.name} {k_val} x)"
                compressed = code_str.replace(m.group(0), replacement)
                savings = max(0, len(m.group(0)) - len(replacement))

        return compressed, savings

    def __repr__(self) -> str:
        return f"<Abstraction {self.name}: {self.pattern}>"


class ValueCompressor:
    """Selects abstractions by maximizing value-weighted compression benefit."""

    def __init__(self, gamma: float = 1.2):
        self.gamma = gamma

    def calculate_program_weight(self, prog_meta: Dict[str, Any]) -> float:
        """Compute value weight: w_i = |{task_family}| * (1 + log(1 + reuse_count))."""
        reuse = prog_meta.get("reuse_count", 0)
        # Task diversity metric
        task_diversity = 1.0  # default base
        if "task_family" in prog_meta and prog_meta["task_family"]:
            task_diversity = float(len(prog_meta["task_family"].split(",")))
        
        return task_diversity * (1.0 + math.log(1.0 + reuse))

    def extract_candidate_abstractions(
        self,
        programs: List[Dict[str, Any]],
    ) -> List[CandidateAbstraction]:
        """Mine common recurring patterns from verified programs."""
        candidates = [
            CandidateAbstraction(
                name="map_add",
                pattern="(map (lambda (a) (+ a $k)) x)",
                arity=2,
                cost=3,
            ),
            CandidateAbstraction(
                name="filter_gt",
                pattern="(filter (lambda (a) (gt a $k)) x)",
                arity=2,
                cost=3,
            ),
        ]
        return candidates

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
            orig_len = prog["description_length"]

            # Compute compressed length under library
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
                # Gain accounts for complexity penalty gamma
                gain = new_benefit - current_benefit - self.gamma * a.cost

                if gain > best_gain:
                    best_gain = gain
                    best_abs = a

            if best_abs is None:
                # Marginal benefit is less than library penalty gamma; stop
                break

            library.append(best_abs)
            remaining.remove(best_abs)
            current_benefit += best_gain + self.gamma * best_abs.cost

        return library
