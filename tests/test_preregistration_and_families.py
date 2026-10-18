"""Tests for Preregistration Protocol, Manifest Integrity, and Task Family Isolation."""

import json
from pathlib import Path
import re
import unittest

from eve3.dsl.interpreter import DSLInterpreter


class TestPreregistrationAndFamilies(unittest.TestCase):

    def setUp(self):
        self.root_dir = Path(__file__).parent.parent
        self.benchmarks_dir = self.root_dir / "benchmarks"
        self.families_dir = self.benchmarks_dir / "families"
        self.interpreter = DSLInterpreter()

    def test_preregistration_doc_exists_and_contains_core_thresholds(self):
        prereg_path = self.root_dir / "docs" / "PREREGISTRATION.md"
        self.assertTrue(prereg_path.exists(), "PREREGISTRATION.md must exist in docs/")
        content = prereg_path.read_text(encoding="utf-8")

        # Verify mandatory threshold declarations (accounting for KaTeX math escapes like 30\%)
        self.assertTrue(re.search(r"30\\?%", content), "Sample efficiency threshold (30%) not found")
        self.assertTrue(re.search(r"\+10", content), "FWT threshold (+10) not found")
        self.assertTrue(re.search(r"\b2\b.*百分点", content), "BWT forgetting threshold (2%) not found")
        self.assertTrue(re.search(r"3\\?%", content), "General probe drop threshold (3%) not found")
        self.assertTrue(re.search(r"0\.05", content), "ECE threshold (0.05) not found")
        self.assertTrue(re.search(r"0\.0\\?%", content), "False verification threshold (0.0%) not found")

    def test_families_manifest_integrity_and_isolation(self):
        manifest_path = self.families_dir / "manifest.json"
        self.assertTrue(manifest_path.exists(), "manifest.json must exist in families/")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        training_families = manifest.get("training_families", [])
        held_out_families = manifest.get("held_out_families", [])

        # Held out suite must contain list_composition
        self.assertIn("list_composition", held_out_families)
        self.assertNotIn("list_composition", training_families)

        # Every declared family file must exist and have correct schema
        for fam_name, fam_info in manifest.get("families", {}).items():
            fam_path = self.families_dir / fam_info["path"]
            self.assertTrue(fam_path.exists(), f"Family file {fam_path} missing")
            with open(fam_path, "r", encoding="utf-8") as ff:
                data = json.load(ff)
                self.assertEqual(data["family_id"], fam_name)
                self.assertIn("tasks", data)
                self.assertGreaterEqual(len(data["tasks"]), fam_info["task_count"])

                # Check each task's reference program against visible examples
                for t in data["tasks"]:
                    ref_code = t["reference_program"]
                    for ex in t["visible_examples"]:
                        out = self.interpreter.run(ref_code, ex["input"])
                        self.assertEqual(out, ex["output"])

    def test_general_coding_probe_suite_schema(self):
        probe_path = self.benchmarks_dir / "general_coding_probe.json"
        self.assertTrue(probe_path.exists())
        with open(probe_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            probes = data.get("probes", [])
            self.assertGreaterEqual(len(probes), 5)
            for p in probes:
                self.assertIn("probe_id", p)
                self.assertIn("test_cases", p)
                self.assertGreaterEqual(len(p["test_cases"]), 2)


if __name__ == "__main__":
    unittest.main()
