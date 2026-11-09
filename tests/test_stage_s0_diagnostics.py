"""Stage S0 regression tests: Diagnostics infrastructure and zero silent exception swallowing.

References:
- reports/audit.md: H5 (smt_distinguisher.py:122,160,199,265), H8 (cegis_loop.py:45-64,164,236),
  H11 (sandbox.py:29,40), H12 (value_compressor.py:31,71,114,126).
"""

import ast
from pathlib import Path
import unittest

from eve3.config import EveConfig
from eve3.models import CandidateProgram
from eve3.system1_proposer.sandbox import ProgramSandbox
from eve3.system2_falsifier.cegis_loop import CEGISLoop
from eve3.system2_falsifier.smt_distinguisher import SMTDistinguisher
from eve3.system3_crystallizer.value_compressor import ValueCompressor


class TestStageS0Diagnostics(unittest.TestCase):
    """Verifies S0 diagnostics counters and elimination of silent except Exception blocks."""

    def test_cegis_result_exposes_all_required_diagnostics_fields(self):
        """CEGISResult.diagnostics must expose oracle_queries, z3_calls, z3_fallbacks,
        z3_timeouts, llm_calls, sandbox_rejections, and swallowed_errors."""
        loop = CEGISLoop(EveConfig(max_falsification_rounds=3))
        examples = [([1, 2], [2, 3])]
        oracle_fn = lambda x: [v + 1 for v in x]
        held_out = [([0, -1], [1, 0])]

        res = loop.run_synthesis(
            initial_examples=examples,
            oracle_fn=oracle_fn,
            held_out_tests=held_out,
        )

        self.assertTrue(hasattr(res, "diagnostics"), "CEGISResult must have a 'diagnostics' attribute")
        diag = res.diagnostics
        for field_name in (
            "oracle_queries",
            "z3_calls",
            "z3_fallbacks",
            "z3_timeouts",
            "llm_calls",
            "sandbox_rejections",
            "swallowed_errors",
        ):
            self.assertTrue(hasattr(diag, field_name), f"diagnostics missing field '{field_name}'")
            self.assertIn(field_name, diag.to_dict(), f"diagnostics.to_dict() missing '{field_name}'")

        self.assertGreaterEqual(diag.oracle_queries, len(res.probes_used))
        self.assertIsInstance(diag.sandbox_rejections, dict)
        self.assertIsInstance(diag.swallowed_errors, dict)

    def test_oracle_queries_counts_failed_oracle_invocations(self):
        """S0 / H8: oracle_queries must count every call to oracle_fn, including failed ones."""
        call_counter = {"count": 0}

        def flaky_oracle(x):
            call_counter["count"] += 1
            if call_counter["count"] == 1:
                raise ValueError("Simulated oracle failure on first query")
            return [v * 2 for v in x]

        loop = CEGISLoop(EveConfig(max_falsification_rounds=3))
        res = loop.run_synthesis(
            initial_examples=[([0], [0])],
            oracle_fn=flaky_oracle,
            held_out_tests=[([2, 3], [4, 6])],
        )

        self.assertEqual(res.diagnostics.oracle_queries, call_counter["count"])
        self.assertGreaterEqual(res.diagnostics.oracle_queries, 1)
        self.assertGreaterEqual(
            res.diagnostics.swallowed_errors.get("cegis_loop.oracle_query", 0),
            1,
        )

    def test_sandbox_rejections_categorized_by_exception_type(self):
        """S0 / H11: ProgramSandbox must classify rejections by exception type in diagnostics."""
        sandbox = ProgramSandbox(timeout_per_exec=0.2)
        raw_codes = [
            "(+ x",                       # DSLParserError
            "(+ x 1)",                    # TypeError on list input []
            "(map (lambda (a) (+ a 1)) x)",  # Valid
        ]
        examples = [([], [])]
        valid = sandbox.filter_valid_candidates(raw_codes, examples)
        self.assertEqual(len(valid), 1)

        self.assertGreaterEqual(sandbox.diagnostics.sandbox_rejections.get("DSLParserError", 0), 1)
        self.assertGreaterEqual(sandbox.diagnostics.sandbox_rejections.get("TypeError", 0), 1)
        self.assertGreaterEqual(
            sandbox.diagnostics.swallowed_errors.get("sandbox.filter_valid_candidates.parse", 0),
            1,
        )
        self.assertGreaterEqual(
            sandbox.diagnostics.swallowed_errors.get("sandbox.filter_valid_candidates.exec", 0),
            1,
        )

    def test_smt_distinguisher_records_z3_calls_and_fallbacks(self):
        """S0 / H5: SMTDistinguisher must count z3_calls and z3_fallbacks in diagnostics."""
        dist = SMTDistinguisher()
        p1 = CandidateProgram("(+ x 1)")
        p2 = CandidateProgram("(+ x 2)")
        probe = dist.find_distinguishing_input(p1, p2)
        self.assertIsNotNone(probe)
        self.assertGreaterEqual(dist.diagnostics.z3_calls, 1)

        # Unsupported primitive triggers explicit fallback counter
        p_unsup1 = CandidateProgram("(sum x)")
        p_unsup2 = CandidateProgram("(length x)")
        _ = dist.find_distinguishing_input(p_unsup1, p_unsup2)
        self.assertGreaterEqual(dist.diagnostics.z3_fallbacks, 1)

    def test_value_compressor_records_swallowed_errors_in_diagnostics(self):
        """S0 / H12: ValueCompressor must count swallowed exceptions instead of silent pass/continue."""
        vc = ValueCompressor(gamma=1.0)
        programs = [
            {"code": "(unclosed_sexpr", "task_family": "list_mapping", "reuse_count": 1},
            {"code": "(map (lambda (a) (+ a 1)) x)", "task_family": "list_mapping", "reuse_count": 1},
        ]
        _ = vc.extract_candidate_abstractions(programs)
        self.assertGreaterEqual(
            vc.diagnostics.swallowed_errors.get("value_compressor.extract_candidate_abstractions", 0),
            1,
        )

    def test_no_bare_except_exception_in_eve3_codebase(self):
        """Iron Rule 3 & S1.1: No bare except, except (..., Exception), BaseException,
        or contextlib.suppress(Exception) in eve3/, experiments/, or scripts/."""
        root_dir = Path(__file__).parent.parent
        target_dirs = [root_dir / "eve3", root_dir / "experiments", root_dir / "scripts"]
        violations = []
        for d in target_dirs:
            if not d.exists():
                continue
            for py_file in sorted(d.rglob("*.py")):
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler):
                        if node.type is None:
                            violations.append(f"{py_file.relative_to(root_dir)}:{node.lineno} bare except:")
                        elif isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
                            violations.append(
                                f"{py_file.relative_to(root_dir)}:{node.lineno} except {node.type.id}:"
                            )
                        elif isinstance(node.type, ast.Tuple):
                            for elt in node.type.elts:
                                if isinstance(elt, ast.Name) and elt.id in ("Exception", "BaseException"):
                                    violations.append(
                                        f"{py_file.relative_to(root_dir)}:{node.lineno} except (..., {elt.id}):"
                                    )
                    elif isinstance(node, ast.Call):
                        func_name = ""
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            func_name = node.func.attr
                        if func_name == "suppress":
                            for arg in node.args:
                                if isinstance(arg, ast.Name) and arg.id in ("Exception", "BaseException"):
                                    violations.append(
                                        f"{py_file.relative_to(root_dir)}:{node.lineno} suppress({arg.id})"
                                    )
        self.assertEqual(
            violations,
            [],
            f"Found prohibited blanket except blocks / suppress calls in codebase:\n" + "\n".join(violations),
        )

    def test_threadpool_worker_exceptions_recorded_in_cegis_diagnostics(self):
        """S0.1 / S1.1: Exceptions raised inside ThreadPool worker threads must be recorded in diagnostics."""
        from concurrent.futures import ThreadPoolExecutor
        from eve3.models import Diagnostics, active_diagnostics_scope

        # Case 1: Sandbox evaluating failing candidate through interpreter's ThreadPoolExecutor
        sandbox = ProgramSandbox(timeout_per_exec=0.2)
        # Construct candidate that executes division by zero or invalid type in worker thread
        cands = [
            "(+ x 1)",             # TypeError on list input [1]
            "(/ 1 0)",             # ZeroDivisionError
            "(tail (head x))",     # TypeError: 'int' object is not subscriptable / head returns int
        ]
        examples = [([1, 2], [2, 3])]
        _ = sandbox.filter_valid_candidates(cands, examples)
        self.assertGreaterEqual(sandbox.diagnostics.sandbox_rejections.get("TypeError", 0), 1)
        self.assertGreaterEqual(
            sandbox.diagnostics.swallowed_errors.get("sandbox.filter_valid_candidates.exec", 0),
            1,
        )

        # Case 2: Concurrent evaluation in a multi-threaded ThreadPoolExecutor
        diag = Diagnostics()
        with active_diagnostics_scope(diag):
            def _worker_eval(code_str: str):
                sb = ProgramSandbox(timeout_per_exec=0.2)
                sb.diagnostics = diag
                sb.filter_valid_candidates([code_str], [([1, 2], [2, 3])])

            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(_worker_eval, ["(+ x 1)", "(/ 1 0)", "(tail 42)"]))

        self.assertGreaterEqual(diag.sandbox_rejections.get("TypeError", 0), 1)
        self.assertGreaterEqual(diag.swallowed_errors.get("sandbox.filter_valid_candidates.exec", 0), 2)

    def test_swallowed_errors_ratchet_only_decreases(self):
        """S0.1 / S1.1 Ratchet test: Swallowed error counts in diagnostics must never exceed baseline."""
        import json
        baseline_path = Path(__file__).parent / "diagnostics_ratchet_baseline.json"
        self.assertTrue(baseline_path.exists(), "Ratchet baseline JSON missing")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["max_allowed_swallowed_errors"]

        # Run representative CEGISLoop task and check that every recorded swallowed error <= baseline
        loop = CEGISLoop(EveConfig(max_falsification_rounds=3))
        res = loop.run_synthesis(
            initial_examples=[([1, 2], [2, 3])],
            oracle_fn=lambda x: [v + 1 for v in x],
            held_out_tests=[([0], [1])],
        )

        for loc, count in res.diagnostics.swallowed_errors.items():
            max_allowed = baseline.get(loc, float("inf"))
            self.assertLessEqual(
                count,
                max_allowed,
                f"Swallowed error at {loc} count={count} exceeded ratchet baseline max={max_allowed}",
            )


if __name__ == "__main__":
    unittest.main()
