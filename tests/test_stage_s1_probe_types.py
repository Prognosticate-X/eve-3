"""Stage S1.1 Tests: Probe type distinction and elimination of TypeError in probe evaluation.

References:
- Prompt S1.1 Section B: 探针类型修复
1. 探针池按程序输入类型区分（标量/列表），类型不匹配的探针不参与该候选评估。
2. group_by_output 中执行异常不得并入公共 "<ERROR>" 类：异常候选各自单独成类，或该探针对含异常候选的集合直接作废并计数。
3. 提交修复前后 TypeError 计数对比（swallowed_errors 两处应降为接近 0）。
"""

import unittest
from eve3.config import EveConfig
from eve3.models import CandidateProgram, Diagnostics
from eve3.system2_falsifier.bayesian_prober import BayesianProber
from eve3.system2_falsifier.cegis_loop import CEGISLoop
from eve3.system2_falsifier.smt_distinguisher import SMTDistinguisher


class TestStageS1ProbeTypes(unittest.TestCase):
    """Verifies that probe candidates match input types and do not swallow TypeErrors."""

    def test_group_by_output_does_not_lump_errors_into_common_class(self):
        """B.2: group_by_output must not lump multiple erroring candidates into a single __EXEC_ERROR__ class."""
        prober = BayesianProber()
        # Two candidates that fail with errors on [1, 2] (e.g. division by zero, invalid operation)
        c1 = CandidateProgram("(/ 1 0)")
        c2 = CandidateProgram("(tail 42)")  # type error inside
        hypotheses = [c1, c2]

        groups = prober.group_by_output(hypotheses, [1, 2])
        # They must NOT be in the same equivalence class!
        self.assertNotIn(
            "__EXEC_ERROR__",
            groups,
            "Common __EXEC_ERROR__ class must not be used",
        )
        # c1 and c2 must be in different groups (or isolated)
        group_lists = list(groups.values())
        for g in group_lists:
            self.assertLessEqual(len(g), 1, "Erroring candidates must not be grouped together into a shared partition")

    def test_distinguisher_generates_typed_probes(self):
        """B.1: SMTDistinguisher must generate domain-appropriate probes (list vs int)."""
        dist = SMTDistinguisher()
        p1 = CandidateProgram("(reverse x)")
        p2 = CandidateProgram("(tail x)")

        # List domain probe generation
        probes_list = dist.generate_candidate_probe_pool([p1, p2], domain_hint="list")
        for p in probes_list:
            self.assertIsInstance(
                p.value,
                list,
                f"Expected list probe for list domain, got {type(p.value)}: {p.value}",
            )

        # Int domain probe generation
        p_int1 = CandidateProgram("(+ x 1)")
        p_int2 = CandidateProgram("(+ x 2)")
        probes_int = dist.generate_candidate_probe_pool([p_int1, p_int2], domain_hint="int")
        for p in probes_int:
            self.assertIsInstance(
                p.value,
                int,
                f"Expected int probe for int domain, got {type(p.value)}: {p.value}",
            )

    def test_heuristic_distinguishing_has_zero_type_errors_on_list_programs(self):
        """B.3: Evaluating heuristic probes on list programs must not produce TypeErrors."""
        dist = SMTDistinguisher()
        p1 = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
        p2 = CandidateProgram("(map (lambda (a) (* a 2)) x)")

        # Run heuristic distinguishing with domain_hint="list"
        _ = dist._heuristic_distinguishing(p1, p2, domain_hint="list")

        type_errors = dist.diagnostics.swallowed_error_details.get(
            "smt_distinguisher._heuristic_distinguishing", {}
        ).get("TypeError", 0)
        self.assertEqual(
            type_errors,
            0,
            f"Expected 0 TypeErrors in smt_distinguisher._heuristic_distinguishing, got {type_errors}",
        )

    def test_cegis_loop_runs_with_near_zero_swallowed_type_errors(self):
        """B.3: CEGISLoop on list task must have zero TypeErrors from probe type mismatches."""
        cfg = EveConfig(max_falsification_rounds=3, proposer_mode="generic_enumeration", enumerator_max_depth=3)
        loop = CEGISLoop(cfg)
        examples = [([1, 2, 3], [3, 2, 1]), ([4, 5], [5, 4])]
        oracle = lambda x: list(reversed(x))
        held_out = [([0, -1], [-1, 0])]

        res = loop.run_synthesis(
            initial_examples=examples,
            oracle_fn=oracle,
            held_out_tests=held_out,
            task_family="list_structural",
        )

        type_err_dist = res.diagnostics.swallowed_error_details.get(
            "smt_distinguisher._heuristic_distinguishing", {}
        ).get("TypeError", 0)
        type_err_prober = res.diagnostics.swallowed_error_details.get(
            "bayesian_prober.group_by_output", {}
        ).get("TypeError", 0)

        self.assertEqual(
            type_err_dist,
            0,
            f"Expected 0 TypeErrors in smt_distinguisher._heuristic_distinguishing, got {type_err_dist}",
        )
        self.assertEqual(
            type_err_prober,
            0,
            f"Expected 0 TypeErrors in bayesian_prober.group_by_output, got {type_err_prober}",
        )


if __name__ == "__main__":
    unittest.main()
