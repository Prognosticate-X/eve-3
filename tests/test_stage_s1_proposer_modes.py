"""Stage S1 Regression Tests: Proposer Modes, Generic Bottom-Up Enumeration, and MLX Sampler Compatibility.

Covers H9 & H10 from reports/audit.md and Stage S1 requirements:
1. EveConfig.proposer_mode in {"leaky_templates", "generic_enumeration", "llm_only", "llm_plus_enumeration"},
   defaulting to non-leaky ("generic_enumeration").
2. True bottom-up AST enumeration in SymbolicEnumerator ordered by AST depth without hardcoded benchmark answers,
   plus candidate provenance tracking (source_detail: template index, enumeration depth, or llm call).
3. Elimination of template #27 answer leakage on held-out list_composition.
4. No silent fallback to heuristic templates in llm_only mode.
5. Real MLX-LM smoke test verifying sampler API compatibility (llm_calls > 0, zero TypeError on temp).
"""

import unittest
from unittest.mock import patch
import pytest

from eve3.config import EveConfig
from eve3.dsl.interpreter import DSLInterpreter
from eve3.models import reset_global_diagnostics
from eve3.search.controller import SearchController
from eve3.search.enumerator import SymbolicEnumerator
from eve3.system1_proposer.generator import HypothesisGenerator
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus


def _mlx_and_model_available() -> Tuple[bool, str]:
    try:
        import mlx.core  # noqa: F401
        import mlx_lm  # noqa: F401
    except ImportError as exc:
        return False, f"mlx-lm not installed: {exc}"
    from pathlib import Path
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--mlx-community--Qwen2.5-Coder-3B-Instruct-4bit"
    if not cache_dir.exists():
        return False, f"Model cache not found at {cache_dir}"
    return True, ""


from typing import Tuple
_MLX_OK, _MLX_REASON = _mlx_and_model_available()


class TestStageS1ProposerModes(unittest.TestCase):
    def setUp(self) -> None:
        reset_global_diagnostics()

    def test_proposer_mode_config_defaults_to_non_leaky(self) -> None:
        """S1.2/S1.3: EveConfig.proposer_mode defaults to 'generic_enumeration' and validates mode names."""
        cfg = EveConfig()
        self.assertEqual(cfg.proposer_mode, "generic_enumeration")

        for valid_mode in ("leaky_templates", "generic_enumeration", "llm_only", "llm_plus_enumeration"):
            c = EveConfig(proposer_mode=valid_mode)
            self.assertEqual(c.proposer_mode, valid_mode)

        with self.assertRaises(ValueError):
            EveConfig(proposer_mode="invalid_mode_xyz")

    def test_generic_enumeration_orders_by_ast_depth_and_tracks_provenance(self) -> None:
        """S1.2/S1.3: generic_enumeration enumerates bottom-up by true AST depth and records source_detail."""
        enum = SymbolicEnumerator(max_depth=3)
        cands = enum.enumerate_candidates(
            domain_hint="list",
            max_candidates=40,
            mode="generic_enumeration",
        )
        self.assertGreater(len(cands), 10)

        # Depths must be non-decreasing and <= max_depth (3)
        depths = [c.depth for c in cands]
        self.assertEqual(depths, sorted(depths), "Bottom-up enumeration must be ordered by non-decreasing AST depth")
        self.assertLessEqual(max(depths), 3)

        # Every candidate must carry source_detail provenance indicating enumeration depth
        for c in cands:
            self.assertTrue(
                hasattr(c, "source_detail") and c.source_detail.startswith(f"enum:depth={c.depth}"),
                f"Expected source_detail starting with 'enum:depth={c.depth}', got {getattr(c, 'source_detail', None)!r}",
            )

        # True depth-3 composition (tail (reverse x)) must be enumerated at depth 3
        codes = [c.code_str for c in cands]
        self.assertIn("(tail (reverse x))", codes)
        # Depth-5 hardcoded template from old enumerator must NOT appear in max_depth=3 generic enumeration
        self.assertNotIn("(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 1)) x))", codes)

    def test_leaky_vs_generic_enumeration_on_held_out_composition(self) -> None:
        """S1.1/S1.5: filter_evens_and_sum only passes under leaky_templates (#27), while reverse_and_tail passes under generic_enumeration at depth=3."""
        interp = DSLInterpreter()

        # Held-out task 1: filter_evens_and_sum -> (sum (filter (lambda (a) (is_even a)) x)) (AST depth 5)
        vis_evens_sum = [([1, 2, 3, 4], 6), ([1, 3, 5], 0)]
        hid_evens_sum = [([], 0), ([10, 15, 20], 30), ([2, 4, 6], 12)]
        oracle_evens_sum = lambda x: interp.run("(sum (filter (lambda (a) (is_even a)) x))", x)

        loop_leaky = CEGISLoop(EveConfig(proposer_mode="leaky_templates", max_falsification_rounds=5))
        res_leaky_1 = loop_leaky.run_synthesis(vis_evens_sum, oracle_evens_sum, hid_evens_sum)
        self.assertTrue(res_leaky_1.converged)
        self.assertEqual(res_leaky_1.verified_program.source_detail, "template:#27")

        loop_generic = CEGISLoop(EveConfig(proposer_mode="generic_enumeration", max_falsification_rounds=5))
        res_generic_1 = loop_generic.run_synthesis(vis_evens_sum, oracle_evens_sum, hid_evens_sum)
        self.assertFalse(res_generic_1.converged)
        self.assertEqual(res_generic_1.status, VerificationStatus.COLLAPSED)

        # Held-out task 3: reverse_and_tail -> (tail (reverse x)) (AST depth 3)
        vis_rev_tail = [([1, 2, 3], [2, 1]), ([5], [])]
        hid_rev_tail = [([], []), ([10, 20, 30, 40], [30, 20, 10])]
        oracle_rev_tail = lambda x: interp.run("(tail (reverse x))", x)

        res_leaky_3 = loop_leaky.run_synthesis(vis_rev_tail, oracle_rev_tail, hid_rev_tail)
        self.assertFalse(res_leaky_3.converged)

        res_generic_3 = loop_generic.run_synthesis(vis_rev_tail, oracle_rev_tail, hid_rev_tail)
        self.assertTrue(res_generic_3.converged)
        self.assertEqual(res_generic_3.verified_program.code_str, "(tail (reverse x))")
        self.assertTrue(res_generic_3.verified_program.source_detail.startswith("enum:depth=3"))

    def test_llm_only_mode_never_falls_back_to_heuristic_or_enumerator(self) -> None:
        """S1.4: llm_only mode must never silently fall back to heuristic templates when LLM fails or returns empty."""
        cfg = EveConfig(proposer_mode="llm_only")
        ctrl = SearchController(cfg)
        with patch.object(ctrl.generator, "_can_use_mlx", return_value=False):
            with self.assertRaises(RuntimeError):
                ctrl.propose_candidates([([1, 2], [2, 3])])

    @pytest.mark.skipif(not _MLX_OK, reason=_MLX_REASON or "MLX-LM not available")
    def test_mlx_llm_smoke_test_sampler_compatibility_and_telemetry(self) -> None:
        """S1.4: Real MLX-LM smoke test verifying sampler API (llm_calls > 0, no temp TypeError) and LLM telemetry."""
        cfg = EveConfig(proposer_mode="llm_only", max_hypotheses_per_round=5)
        gen = HypothesisGenerator(cfg)
        examples = [([1, 2, 3], [2, 3, 4]), ([0, -1, 5], [1, 0, 6])]
        cands = gen.generate_hypotheses(examples, max_candidates=5)
        self.assertGreater(gen.diagnostics.llm_calls, 0)
        self.assertEqual(gen.diagnostics.swallowed_errors.get("generator._generate_raw_proposals", 0), 0)
        self.assertGreater(len(gen.diagnostics.llm_latencies_ms), 0)
        self.assertGreater(gen.diagnostics.llm_raw_candidates, 0)
        for c in cands:
            self.assertTrue(c.source_detail.startswith("llm:call="))


if __name__ == "__main__":
    unittest.main()
