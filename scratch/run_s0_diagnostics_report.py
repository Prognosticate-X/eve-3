"""Stage S0 Acceptance Runner: Executes full test suite and all 9 experiment scripts,
collecting and printing GLOBAL_DIAGNOSTICS counters to expose previously silent failures.
"""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eve3.models import get_global_diagnostics, reset_global_diagnostics


def run_all_tests_with_diagnostics():
    reset_global_diagnostics()
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(REPO_ROOT / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    diag = get_global_diagnostics().to_dict()
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "diagnostics": diag,
    }


def run_script_path(script_path: Path):
    import runpy
    reset_global_diagnostics()
    runpy.run_path(str(script_path), run_name="__main__")
    return get_global_diagnostics().to_dict()


def main():
    report = {}
    print("=== 1. Running Full Unit Test Suite (86 tests) with Diagnostics ===")
    test_res = run_all_tests_with_diagnostics()
    report["unit_test_suite"] = test_res
    print(json.dumps(test_res, indent=2))

    scripts = sorted((REPO_ROOT / "experiments").glob("run_*.py"))

    exp_reports = {}
    for fpath in scripts:
        rel_name = str(fpath.relative_to(REPO_ROOT))
        print(f"\n=== Running {rel_name} ===")
        diag = run_script_path(fpath)
        exp_reports[rel_name] = diag
        print(f"Diagnostics for {rel_name}:")
        print(json.dumps(diag, indent=2))

    report["experiments"] = exp_reports
    out_path = Path(__file__).resolve().parent / "s0_diagnostics_output.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved full S0 diagnostics report to {out_path}")


if __name__ == "__main__":
    main()
