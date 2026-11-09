"""Stage S1 Comprehensive Evaluation Script.

Evaluates EVE-3 across all proposer_modes:
  - leaky_templates (labeled '含答案泄漏，仅作参考')
  - generic_enumeration (enumerator_max_depth=3 and enumerator_max_depth=4)
  - llm_only (using mlx-community/Qwen2.5-Coder-3B-Instruct-4bit via mlx-lm==0.32.2)
  - llm_plus_enumeration (enumerator_max_depth=3 and enumerator_max_depth=4)

Also re-runs all 9 scripts under experiments/ comparing leaky_templates vs non-leaky
generic_enumeration (d=3 and d=4), capturing stdout and full Diagnostics counters.

Complies with all S1 and S1.1-S1.5 additional constraints:
  1. All crystallized-library-dependent arms ('With-Lib', 'Full_System' library part, etc.)
     are marked 'INVALID_PENDING_S4'.
  2. Outputs full diagnostics summaries (oracle_queries, z3_calls, z3_fallbacks, z3_timeouts,
     llm_calls, llm_latencies_ms, llm_raw_candidates, llm_syntax_valid_candidates,
     llm_sandbox_passed_candidates, sandbox_rejections, swallowed_errors).
  3. Under non-leaky modes, records for every task the first-hit provenance
     (template:#N / enum:depth=d:#idx / llm:call=c:line=l) and builds the explicit
     '泄漏依赖清单' (tasks that pass ONLY under leaky_templates).
  4. Runs a full round of llm_only across all unique benchmark tasks and reports
     llm_calls, per-call latency (ms), syntax-validity rate, and sandbox pass rate.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import re
import runpy
import time
from typing import Any, Dict, List, Tuple

import eve3.config as eve_config_mod
from eve3.config import EveConfig
from eve3.dsl.interpreter import DSLInterpreter, SExprParser
from eve3.models import GLOBAL_DIAGNOSTICS
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "benchmarks"
EXP_DIR = REPO_ROOT / "experiments"


def make_oracle(ref_prog: str):
    interp = DSLInterpreter()
    ast = SExprParser().parse(ref_prog)

    def oracle(x: Any) -> Any:
        return interp.run(ast, x, timeout_seconds=0.5)

    return oracle


def load_unique_tasks() -> List[Dict[str, Any]]:
    """Load the 13 unique benchmark tasks across all benchmark JSON files in canonical order."""
    files = [
        "dev_train.json",
        "dev_eval.json",
        "held_out_test.json",
        "list_functions.json",
        "families/list_mapping.json",
        "families/list_filtering.json",
        "families/list_reduction.json",
        "families/list_structural.json",
        "families/list_composition.json",
    ]
    by_name: Dict[str, Dict[str, Any]] = {}
    for rel in files:
        p = BENCH_DIR / rel
        raw = json.loads(p.read_text(encoding="utf-8"))
        tasks = raw.get("tasks", raw) if isinstance(raw, dict) else raw
        for t in tasks:
            name = t.get("task_name") or t.get("task_id")
            train_raw = t.get("train_examples") or t.get("visible_examples") or t.get("examples", [])
            held_raw = t.get("held_out_examples") or t.get("hidden_tests") or t.get("test_examples", [])
            if name not in by_name:
                by_name[name] = {
                    "task_name": name,
                    "family": t.get("family", raw.get("family", "general") if isinstance(raw, dict) else "general"),
                    "description": t.get("description", ""),
                    "reference_program": t["reference_program"],
                    "train_examples": [(ex["input"], ex["output"]) for ex in train_raw],
                    "held_out_examples": [(ex["input"], ex["output"]) for ex in held_raw],
                    "appears_in": [rel],
                }
            else:
                if rel not in by_name[name]["appears_in"]:
                    by_name[name]["appears_in"].append(rel)
    return list(by_name.values())


def evaluate_task_under_config(task: Dict[str, Any], cfg: EveConfig) -> Dict[str, Any]:
    loop = CEGISLoop(cfg)
    oracle = make_oracle(task["reference_program"])
    t0 = time.perf_counter()
    res = loop.run_synthesis(
        initial_examples=list(task["train_examples"]),
        oracle_fn=oracle,
        held_out_tests=list(task["held_out_examples"]),
        task_family=task["family"],
        search_strategy="hybrid",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    passed = res.status in (
        VerificationStatus.HELD_OUT_TESTS_PASSED,
        VerificationStatus.FORMALLY_VERIFIED,
    )
    first_hit_cand = res.verified_program
    return {
        "task_name": task["task_name"],
        "family": task["family"],
        "reference_program": task["reference_program"],
        "status": res.status.value,
        "passed": passed,
        "held_out_accuracy": res.held_out_accuracy,
        "verified_program": first_hit_cand.code_str if first_hit_cand else None,
        "first_hit_created_by": first_hit_cand.created_by if first_hit_cand else None,
        "first_hit_source_detail": first_hit_cand.source_detail if first_hit_cand else None,
        "surviving_candidates": [
            {"code": c.code_str, "created_by": c.created_by, "source_detail": c.source_detail}
            for c in res.surviving_candidates
        ],
        "rounds_used": res.rounds_executed,
        "elapsed_ms": round(elapsed_ms, 2),
        "diagnostics": res.diagnostics.to_dict(),
    }


def aggregate_diagnostics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    agg = {
        "oracle_queries": 0,
        "z3_calls": 0,
        "z3_fallbacks": 0,
        "z3_timeouts": 0,
        "llm_calls": 0,
        "llm_latencies_ms": [],
        "llm_raw_candidates": 0,
        "llm_syntax_valid_candidates": 0,
        "llm_sandbox_passed_candidates": 0,
        "sandbox_rejections": {},
        "swallowed_errors": {},
        "swallowed_error_details": {},
    }
    for r in records:
        d = r["diagnostics"]
        agg["oracle_queries"] += d.get("oracle_queries", 0)
        agg["z3_calls"] += d.get("z3_calls", 0)
        agg["z3_fallbacks"] += d.get("z3_fallbacks", 0)
        agg["z3_timeouts"] += d.get("z3_timeouts", 0)
        agg["llm_calls"] += d.get("llm_calls", 0)
        agg["llm_latencies_ms"].extend(d.get("llm_latencies_ms", []))
        agg["llm_raw_candidates"] += d.get("llm_raw_candidates", 0)
        agg["llm_syntax_valid_candidates"] += d.get("llm_syntax_valid_candidates", 0)
        agg["llm_sandbox_passed_candidates"] += d.get("llm_sandbox_passed_candidates", 0)
        for k, v in d.get("sandbox_rejections", {}).items():
            agg["sandbox_rejections"][k] = agg["sandbox_rejections"].get(k, 0) + v
        for k, v in d.get("swallowed_errors", {}).items():
            agg["swallowed_errors"][k] = agg["swallowed_errors"].get(k, 0) + v
        for loc, emap in d.get("swallowed_error_details", {}).items():
            dest = agg["swallowed_error_details"].setdefault(loc, {})
            for et, cnt in emap.items():
                dest[et] = dest.get(et, 0) + cnt
    return agg


def run_experiments_comparison() -> Dict[str, Any]:
    """Run all 9 scripts under experiments/ across leaky_templates, generic_enumeration(d=3), generic_enumeration(d=4)."""
    exp_scripts = sorted(EXP_DIR.glob("run_*.py"))
    exp_modes = [
        ("leaky_templates", "leaky_templates", 4),
        ("generic_enumeration_d3", "generic_enumeration", 3),
        ("generic_enumeration_d4", "generic_enumeration", 4),
    ]
    orig_init = EveConfig.__init__
    exp_results: Dict[str, Dict[str, Any]] = {}

    for script_path in exp_scripts:
        rel_name = f"experiments/{script_path.name}"
        exp_results[rel_name] = {}
        for mode_label, p_mode, max_d in exp_modes:
            def _patched_init(self, *args, _pm=p_mode, _md=max_d, **kwargs):
                kwargs["proposer_mode"] = _pm
                kwargs["enumerator_max_depth"] = _md
                orig_init(self, *args, **kwargs)

            EveConfig.__init__ = _patched_init
            GLOBAL_DIAGNOSTICS.reset()
            buf = io.StringIO()
            t0 = time.perf_counter()
            try:
                with contextlib.redirect_stdout(buf):
                    runpy.run_path(str(script_path), run_name="__main__")
            finally:
                EveConfig.__init__ = orig_init
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            stdout_text = buf.getvalue()
            diag_dict = GLOBAL_DIAGNOSTICS.to_dict()
            # Extract key metric lines from stdout
            metric_lines = [
                line.strip()
                for line in stdout_text.splitlines()
                if any(
                    kw in line
                    for kw in (
                        "Pass Rate",
                        "Accuracy",
                        "Solved",
                        "Without-Lib",
                        "With-Lib",
                        "No_System",
                        "Full_System",
                        "Forward Transfer",
                        "Backward Forgetting",
                        "General Coding",
                        "Stage ",
                        "Cycle ",
                        "Generation ",
                    )
                )
            ]
            exp_results[rel_name][mode_label] = {
                "proposer_mode": p_mode,
                "enumerator_max_depth": max_d,
                "elapsed_ms": round(elapsed_ms, 2),
                "diagnostics": diag_dict,
                "key_lines": metric_lines,
                "stdout": stdout_text,
            }
            print(f"  [EXP {mode_label}] {rel_name} ({elapsed_ms:.1f} ms) oracle={diag_dict['oracle_queries']} z3_fb={diag_dict['z3_fallbacks']}")
    return exp_results


def main() -> None:
    unique_tasks = load_unique_tasks()
    print(f"Loaded {len(unique_tasks)} unique benchmark tasks.")

    mode_configs: List[Tuple[str, str, EveConfig]] = [
        (
            "leaky_templates",
            "含答案泄漏，仅作参考 (27 hardcoded heuristic templates + 67 leaky enumerator templates)",
            EveConfig(proposer_mode="leaky_templates", max_falsification_rounds=5),
        ),
        (
            "generic_enumeration_d3",
            "通用自底向上枚举 (max_depth=3, 仅一阶 DSL 组合, 无高阶 lambda)",
            EveConfig(proposer_mode="generic_enumeration", enumerator_max_depth=3, max_falsification_rounds=5),
        ),
        (
            "generic_enumeration_d4",
            "通用自底向上枚举 (max_depth=4, 含单层高阶 map/filter/fold 原语枚举)",
            EveConfig(proposer_mode="generic_enumeration", enumerator_max_depth=4, max_falsification_rounds=5),
        ),
        (
            "llm_only",
            "仅本地 MLX LLM (Qwen2.5-Coder-3B-Instruct-4bit, max_falsification_rounds=5)",
            EveConfig(proposer_mode="llm_only", max_falsification_rounds=5),
        ),
        (
            "llm_plus_enumeration_d3",
            "LLM + 通用自底向上枚举 (max_depth=3)",
            EveConfig(proposer_mode="llm_plus_enumeration", enumerator_max_depth=3, max_falsification_rounds=5),
        ),
        (
            "llm_plus_enumeration_d4",
            "LLM + 通用自底向上枚举 (max_depth=4)",
            EveConfig(proposer_mode="llm_plus_enumeration", enumerator_max_depth=4, max_falsification_rounds=5),
        ),
    ]

    results_by_mode: Dict[str, Any] = {}
    for mode_key, note, cfg in mode_configs:
        print(f"\n=== Running mode: {mode_key} ({note}) ===")
        t_mode = time.perf_counter()
        task_records = []
        for task in unique_tasks:
            rec = evaluate_task_under_config(task, cfg)
            task_records.append(rec)
            print(
                f"  [{mode_key}] {task['task_name']:22s} -> {rec['status']:22s} "
                f"prog={rec['verified_program']} source={rec['first_hit_source_detail']}"
            )
        mode_ms = (time.perf_counter() - t_mode) * 1000.0
        pass_count = sum(1 for r in task_records if r["passed"])
        diag_agg = aggregate_diagnostics(task_records)
        results_by_mode[mode_key] = {
            "mode_key": mode_key,
            "note": note,
            "proposer_mode": cfg.proposer_mode,
            "enumerator_max_depth": cfg.enumerator_max_depth,
            "pass_count": pass_count,
            "total_tasks": len(task_records),
            "pass_rate": round(pass_count / len(task_records), 4),
            "total_elapsed_ms": round(mode_ms, 2),
            "diagnostics_summary": diag_agg,
            "tasks": task_records,
        }

    # Compute split-level pass rates across all 9 benchmark JSON files for each mode
    split_files = [
        "dev_train.json",
        "dev_eval.json",
        "held_out_test.json",
        "list_functions.json",
        "families/list_mapping.json",
        "families/list_filtering.json",
        "families/list_reduction.json",
        "families/list_structural.json",
        "families/list_composition.json",
    ]
    split_summaries: Dict[str, Dict[str, Any]] = {}
    for split_rel in split_files:
        raw = json.loads((BENCH_DIR / split_rel).read_text(encoding="utf-8"))
        tasks = raw.get("tasks", raw) if isinstance(raw, dict) else raw
        task_names = [t.get("task_name") or t.get("task_id") for t in tasks]
        split_summaries[split_rel] = {"num_tasks": len(task_names), "task_names": task_names, "by_mode": {}}
        for mode_key, mode_data in results_by_mode.items():
            by_task = {r["task_name"]: r for r in mode_data["tasks"]}
            passed = sum(1 for tn in task_names if by_task[tn]["passed"])
            split_summaries[split_rel]["by_mode"][mode_key] = {
                "passed": passed,
                "total": len(task_names),
                "pass_rate": round(passed / len(task_names), 4),
            }

    # Build explicit Leakage-Dependent Task List ("泄漏依赖清单")
    leaky_map = {r["task_name"]: r for r in results_by_mode["leaky_templates"]["tasks"]}
    gen_d3_map = {r["task_name"]: r for r in results_by_mode["generic_enumeration_d3"]["tasks"]}
    gen_d4_map = {r["task_name"]: r for r in results_by_mode["generic_enumeration_d4"]["tasks"]}
    llm_only_map = {r["task_name"]: r for r in results_by_mode["llm_only"]["tasks"]}

    leakage_dependent_vs_d3 = []
    leakage_dependent_vs_d4 = []
    solved_only_by_non_leaky = []

    for task in unique_tasks:
        tn = task["task_name"]
        l_pass = leaky_map[tn]["passed"]
        d3_pass = gen_d3_map[tn]["passed"]
        d4_pass = gen_d4_map[tn]["passed"]
        if l_pass and not d3_pass:
            leakage_dependent_vs_d3.append({
                "task_name": tn,
                "family": task["family"],
                "reference_program": task["reference_program"],
                "leaky_source": leaky_map[tn]["first_hit_source_detail"],
                "d3_status": gen_d3_map[tn]["status"],
                "d4_passed": d4_pass,
                "d4_source": gen_d4_map[tn]["first_hit_source_detail"],
            })
        if l_pass and not d4_pass:
            leakage_dependent_vs_d4.append({
                "task_name": tn,
                "family": task["family"],
                "reference_program": task["reference_program"],
                "leaky_source": leaky_map[tn]["first_hit_source_detail"],
                "d4_status": gen_d4_map[tn]["status"],
                "llm_only_passed": llm_only_map[tn]["passed"],
            })
        if (d3_pass or d4_pass) and not l_pass:
            solved_only_by_non_leaky.append({
                "task_name": tn,
                "family": task["family"],
                "reference_program": task["reference_program"],
                "leaky_status": leaky_map[tn]["status"],
                "d3_passed": d3_pass,
                "d3_source": gen_d3_map[tn]["first_hit_source_detail"],
                "d4_passed": d4_pass,
                "d4_source": gen_d4_map[tn]["first_hit_source_detail"],
            })

    # Compute LLM-only detailed telemetry
    llm_diag = results_by_mode["llm_only"]["diagnostics_summary"]
    latencies = llm_diag["llm_latencies_ms"]
    raw_cands = llm_diag["llm_raw_candidates"]
    syntax_valid = llm_diag["llm_syntax_valid_candidates"]
    sandbox_passed = llm_diag["llm_sandbox_passed_candidates"]
    llm_telemetry = {
        "model_name": EveConfig().model_name,
        "mlx_lm_version": "0.32.2",
        "mlx_version": "0.32.4",
        "total_llm_calls": llm_diag["llm_calls"],
        "latencies_ms": [round(x, 2) for x in latencies],
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "min_latency_ms": round(min(latencies), 2) if latencies else 0.0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
        "raw_candidates": raw_cands,
        "syntax_valid_candidates": syntax_valid,
        "syntax_valid_rate": round(syntax_valid / raw_cands, 4) if raw_cands > 0 else 0.0,
        "sandbox_passed_candidates": sandbox_passed,
        "sandbox_pass_rate_of_raw": round(sandbox_passed / raw_cands, 4) if raw_cands > 0 else 0.0,
        "sandbox_pass_rate_of_syntax_valid": round(sandbox_passed / syntax_valid, 4) if syntax_valid > 0 else 0.0,
    }

    print("\n=== Re-running all 9 experiments/*.py scripts across leaky vs non-leaky modes ===")
    experiments_comparison = run_experiments_comparison()

    # Crystallized-library arms marked INVALID_PENDING_S4 per S1 Constraint 1
    crystallized_arms_status = {
        "run_library_ablation.py::With-Lib": "INVALID_PENDING_S4 (crystallized operators trigger NameErrors in DSLInterpreter; not interpreted in S1)",
        "run_full_ablation.py::Full_System (library part)": "INVALID_PENDING_S4 (crystallized operators trigger NameErrors in DSLInterpreter)",
        "run_full_ablation.py::No_System2_ActiveProbing (library part)": "INVALID_PENDING_S4 (crystallized operators trigger NameErrors in DSLInterpreter)",
        "run_autonomous_curriculum.py::Library crystallization": "INVALID_PENDING_S4 (crystallized operators trigger NameErrors in DSLInterpreter)",
        "run_memory_consolidation.py::Library crystallization": "INVALID_PENDING_S4 (crystallized operators trigger NameErrors in DSLInterpreter)",
    }

    output = {
        "ig_probe_type_mismatch_notice": (
            "UNFIXED_IN_S1 (Scheduled for S2/S3): BayesianProber.group_by_output and "
            "SMTDistinguisher._heuristic_distinguishing still evaluate integer probes [-2..5] "
            "on list-processing candidates, raising TypeError -> '<ERROR>' equivalence classes "
            "and distorting IG calculation when >1 candidate survives."
        ),
        "crystallized_library_arms": crystallized_arms_status,
        "results_by_mode": results_by_mode,
        "split_summaries": split_summaries,
        "leakage_dependent_vs_d3": leakage_dependent_vs_d3,
        "leakage_dependent_vs_d4": leakage_dependent_vs_d4,
        "solved_only_by_non_leaky": solved_only_by_non_leaky,
        "llm_telemetry": llm_telemetry,
        "experiments_comparison": experiments_comparison,
    }

    scratch_out = Path(__file__).resolve().parent / "s1_evaluation_output.json"
    reports_out = Path(__file__).resolve().parent.parent / "reports" / "s1_evaluation_output.json"
    scratch_out.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    reports_out.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved S1 evaluation output to {reports_out}")


if __name__ == "__main__":
    main()
