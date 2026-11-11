"""Tests for Stage S4 Submodular Value Function & Reuse Saturation [H13]."""

import pytest
from eve3.system3_crystallizer.value_compressor import CandidateAbstraction, ValueCompressor


class TestStageS4Submodular:
    """Validate reuse saturation (anti-lock-in) and order-independent set evaluation."""

    def test_reuse_saturation_prevents_positive_feedback_lockin(self):
        """H13: Program weight saturates at max_reuse_saturation to avoid suppressing better new abstractions."""
        vc = ValueCompressor(max_reuse_saturation=10.0)

        meta_10 = {"reuse_count": 10, "task_family": "list_mapping"}
        meta_100 = {"reuse_count": 100, "task_family": "list_mapping"}
        meta_1000 = {"reuse_count": 1000, "task_family": "list_mapping"}

        w_10 = vc.calculate_program_weight(meta_10)
        w_100 = vc.calculate_program_weight(meta_100)
        w_1000 = vc.calculate_program_weight(meta_1000)

        assert w_10 == w_100 == w_1000, f"Weight should saturate at reuse=10, but got {w_10}, {w_100}, {w_1000}"
        assert w_1000 < 5.0, "Saturated weight must have a reasonable bound"

    def test_order_independent_library_benefit(self):
        """H12/H13: Library evaluation must be order-independent (a true set function)."""
        vc = ValueCompressor(gamma=1.0)

        c1 = CandidateAbstraction(
            name="c1_map_add",
            pattern="(map (lambda (a) (+ a $k)) x)",
            arity=2,
            cost=2,
        )
        c2 = CandidateAbstraction(
            name="c2_rev_map_add",
            pattern="(reverse (map (lambda (a) (+ a $k)) x))",
            arity=2,
            cost=4,
        )

        programs = [
            {"code": "(reverse (map (lambda (a) (+ a 1)) x))", "task_family": "f1", "reuse_count": 1},
            {"code": "(reverse (map (lambda (a) (+ a 2)) x))", "task_family": "f1", "reuse_count": 1},
            {"code": "(map (lambda (a) (+ a 3)) x)", "task_family": "f2", "reuse_count": 1},
        ]
        weights = [1.0, 1.0, 1.0]

        b_12 = vc.compute_weighted_benefit([c1, c2], programs, weights)
        b_21 = vc.compute_weighted_benefit([c2, c1], programs, weights)

        assert b_12 == b_21, f"Evaluation order caused asymmetry: f([c1, c2])={b_12} != f([c2, c1])={b_21}"

    def test_better_new_abstraction_wins_over_stale_lower_saving_abstraction(self):
        """H13: A new abstraction with 6 AST savings beats a stale one with 2 AST savings despite history."""
        vc = ValueCompressor(gamma=0.2, max_reuse_saturation=5.0)

        programs = [
            {"code": "(reverse (map (lambda (a) (+ a 1)) x))", "task_family": "f1", "reuse_count": 100},
            {"code": "(reverse (map (lambda (a) (+ a 2)) x))", "task_family": "f1", "reuse_count": 100},
        ]

        # Stale abstraction saves only the inner map (+2 savings)
        a_stale = CandidateAbstraction(name="stale_inner", pattern="(map (lambda (a) (+ a $k)) x)", arity=2, cost=2)
        # Better new abstraction saves the entire outer composite (+5 savings)
        a_better = CandidateAbstraction(name="better_outer", pattern="(reverse (map (lambda (a) (+ a $k)) x))", arity=2, cost=3)

        selected = vc.select_optimal_library([a_stale, a_better], programs)
        selected_names = [a.name for a in selected]

        assert "better_outer" in selected_names, "Better abstraction should be selected despite reuse history"
