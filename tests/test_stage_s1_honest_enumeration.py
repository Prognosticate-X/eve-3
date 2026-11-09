"""Tests for Stage S1.1 Section C: Enumerator Honestification and Generalization.

Verifies:
1. generic_enumeration candidate counts, primitives, and de-benchmarked constants.
2. enumeration_full bottom-up synthesis solves composite tasks without library learning.
3. Out-of-distribution constant generalization (benchmarks/ood_constants.json).
4. High-ambiguity benchmark (benchmarks/high_ambiguity.json) version space distribution.
"""

import json
from pathlib import Path
import unittest

from eve3.config import EveConfig
from eve3.dsl.interpreter import DSLInterpreter, SExprParser
from eve3.search.controller import SearchController
from eve3.search.enumeration_full import BottomUpOEEnumerator, extract_constants_from_examples
from eve3.search.enumerator import SymbolicEnumerator
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus


class TestStageS1HonestEnumeration(unittest.TestCase):
    """Regression suite for honest enumeration, OOD constants, and high ambiguity."""

    def test_constants_extracted_strictly_from_examples_and_base(self):
        """C.2: Constants must be strictly {0, 1} U values appearing in examples."""
        ex = [([10, 20], [14, 24]), ([-5], [-1])]
        consts = extract_constants_from_examples(ex)
        self.assertEqual(consts, [-5, -1, 0, 1, 10, 14, 20, 24])

        # Empty examples fallback strictly to {0, 1}
        self.assertEqual(extract_constants_from_examples([]), [0, 1])

    def test_enumeration_full_solves_composite_tasks_without_library(self):
        """C.3: True bottom-up enumeration with OE pruning solves composition tasks without library."""
        bench_path = Path(__file__).parent.parent / "benchmarks" / "families" / "list_composition.json"
        bench = json.loads(bench_path.read_text(encoding="utf-8"))
        enumerator = BottomUpOEEnumerator(max_size=9, timeout_seconds=60.0)

        for task in bench["tasks"]:
            train_ex = [(e["input"], e["output"]) for e in task["visible_examples"]]
            held_out = [(e["input"], e["output"]) for e in task["hidden_tests"]]
            res = enumerator.synthesize(train_ex, held_out)
            self.assertTrue(
                res["solved"],
                f"enumeration_full failed to solve {task['task_id']}: {res}",
            )
            self.assertIsNotNone(res["program"])
            self.assertLessEqual(res["size"], 9)
            self.assertLess(res["elapsed_ms"], 10000.0)

    def test_ood_constants_generalization(self):
        """C.4: Generic enumeration solves OOD constants (4, 6, 7, 3), while leaky templates fails."""
        ood_path = Path(__file__).parent.parent / "benchmarks" / "ood_constants.json"
        ood = json.loads(ood_path.read_text(encoding="utf-8"))["tasks"]

        cfg_generic = EveConfig(proposer_mode="generic_enumeration", enumerator_max_depth=4)
        loop_generic = CEGISLoop(cfg_generic)
        interp = DSLInterpreter()
        parser = SExprParser()

        generic_solved = 0
        for t in ood:
            oracle = lambda x, p=t["reference_program"]: interp.run(parser.parse(p), x)
            train_ex = [(e["input"], e["output"]) for e in t["visible_examples"]]
            held_out = [(e["input"], e["output"]) for e in t["hidden_tests"]]
            res = loop_generic.run_synthesis(train_ex, oracle, held_out)
            if res.status in (VerificationStatus.HELD_OUT_TESTS_PASSED, VerificationStatus.FORMALLY_VERIFIED):
                generic_solved += 1

        self.assertEqual(
            generic_solved,
            len(ood),
            f"generic_enumeration should solve all {len(ood)} OOD constant tasks, got {generic_solved}",
        )

        # Confirm leaky_templates fails on OOD constants due to template rigidity
        cfg_leaky = EveConfig(proposer_mode="leaky_templates", enumerator_max_depth=4)
        loop_leaky = CEGISLoop(cfg_leaky)
        leaky_solved = 0
        for t in ood:
            oracle = lambda x, p=t["reference_program"]: interp.run(parser.parse(p), x)
            train_ex = [(e["input"], e["output"]) for e in t["visible_examples"]]
            held_out = [(e["input"], e["output"]) for e in t["hidden_tests"]]
            res = loop_leaky.run_synthesis(train_ex, oracle, held_out)
            if res.status in (VerificationStatus.HELD_OUT_TESTS_PASSED, VerificationStatus.FORMALLY_VERIFIED):
                leaky_solved += 1

        self.assertEqual(
            leaky_solved,
            0,
            f"leaky_templates expected to solve 0 OOD tasks, got {leaky_solved}",
        )

    def test_high_ambiguity_suite_has_at_least_half_tasks_with_five_candidates(self):
        """C.5: High ambiguity suite must have >= 50% tasks with >= 5 consistent candidates."""
        ha_path = Path(__file__).parent.parent / "benchmarks" / "high_ambiguity.json"
        ha = json.loads(ha_path.read_text(encoding="utf-8"))["tasks"]

        cfg = EveConfig(proposer_mode="generic_enumeration", enumerator_max_depth=4)
        sc = SearchController(cfg)

        ge_5_count = 0
        for t in ha:
            train_ex = [(e["input"], e["output"]) for e in t["visible_examples"]]
            cands = sc.propose_candidates(train_ex, max_candidates=50)
            if len(cands) >= 5:
                ge_5_count += 1

        pct = ge_5_count / len(ha)
        self.assertGreaterEqual(
            pct,
            0.50,
            f"Expected >= 50% high-ambiguity tasks with >= 5 candidates, got {pct*100:.1f}% ({ge_5_count}/{len(ha)})",
        )


if __name__ == "__main__":
    unittest.main()
