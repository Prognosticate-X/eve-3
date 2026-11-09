"""Few-Shot Prompt Integrity and Zero Benchmark Overlap Test (Prompt S1.1 Section D.1).

Guarantees that:
1. prompts/fewshot.json contains valid identifiers, clear syntax rules, and >= 3 few-shot tasks.
2. None of the few-shot tasks, task names, or reference programs overlap with any benchmark in benchmarks/.
3. Each few-shot reference program correctly executes and satisfies its own example pairs.
"""

import json
from pathlib import Path
import unittest

from eve3.dsl.interpreter import DSLInterpreter, SExprParser


class TestFewshotIntegrity(unittest.TestCase):
    """Verifies fewshot prompt integrity and non-overlap with benchmark tasks."""

    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.fewshot_path = self.root_dir / "prompts" / "fewshot.json"
        self.assertTrue(self.fewshot_path.exists(), "prompts/fewshot.json must exist")
        self.fewshot_data = json.loads(self.fewshot_path.read_text(encoding="utf-8"))

    def test_fewshot_structure_and_syntax_rules(self):
        """Must define valid identifiers, syntax rules, and at least 3 tasks."""
        self.assertIn("valid_identifiers", self.fewshot_data)
        self.assertIn("syntax_rules", self.fewshot_data)
        tasks = self.fewshot_data.get("fewshot_tasks", [])
        self.assertGreaterEqual(len(tasks), 3, "Must have between 3 and 5 fewshot tasks")

    def test_zero_overlap_with_all_benchmarks(self):
        """None of the few-shot reference programs or task names may appear in benchmarks/."""
        bench_dir = self.root_dir / "benchmarks"
        bench_task_names = set()
        bench_reference_progs = set()

        for json_file in bench_dir.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            tasks = data.get("tasks", data) if isinstance(data, dict) else data
            if isinstance(tasks, list):
                for t in tasks:
                    if isinstance(t, dict):
                        if "task_name" in t:
                            bench_task_names.add(t["task_name"])
                        if "task_id" in t:
                            bench_task_names.add(t["task_id"])
                        if "reference_program" in t:
                            bench_reference_progs.add(t["reference_program"])

        for fs_task in self.fewshot_data["fewshot_tasks"]:
            fs_name = fs_task["task_name"]
            fs_ref = fs_task["reference_program"]

            self.assertNotIn(
                fs_name,
                bench_task_names,
                f"Few-shot task name {fs_name!r} overlaps with benchmark tasks!",
            )
            self.assertNotIn(
                fs_ref,
                bench_reference_progs,
                f"Few-shot reference program {fs_ref!r} overlaps with benchmark tasks!",
            )

    def test_fewshot_references_are_semantically_correct(self):
        """Each fewshot reference program must pass its own input/output examples."""
        interp = DSLInterpreter()
        parser = SExprParser()

        for fs_task in self.fewshot_data["fewshot_tasks"]:
            ref_code = fs_task["reference_program"]
            ast_node = parser.parse(ref_code)
            for ex in fs_task["examples"]:
                inp = ex["input"]
                expected = ex["output"]
                actual = interp.run(ast_node, inp, timeout_seconds=0.2)
                self.assertEqual(
                    actual,
                    expected,
                    f"Reference {ref_code} failed on {inp}: expected {expected}, got {actual}",
                )


if __name__ == "__main__":
    unittest.main()
