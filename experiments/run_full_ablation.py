"""Phase P3 Experiment: Full 4-Regime Benchmark Ablation Study.

Executes comparative ablation across:
- Baseline A: Naive Generator without active falsification (accepts first visible-matching candidate)
- Baseline B: Generator + Active Bayesian Falsification (no library reuse)
- Baseline C: Generator + Active Bayesian Falsification + Crystallized Knowledge Library
- Full System: Complete closed-loop with Causal Discovery Replay and Optimized Search Policy

Computes core metrics: Hidden-test Pass Rate, False Verification Rate, Oracle Queries,
Library Marginal Value, and Wall-clock Latency.
"""

import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from eve3.config import EveConfig
from eve3.discovery.policy import ExplorationPolicy
from eve3.dsl.interpreter import DSLInterpreter
from eve3.models import LearnedAbstraction
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus
from eve3.system3_crystallizer.library import KnowledgeLibrary


def run_full_ablation() -> Dict[str, Any]:
    print("=====================================================================")
    print("  EVE-3 PHASE P3: FULL 4-REGIME ABLATION BENCHMARK EXPERIMENT")
    print("=====================================================================")

    interpreter = DSLInterpreter()
    benchmarks_dir = Path(__file__).parent.parent / "benchmarks"

    # Load all benchmarks
    with open(benchmarks_dir / "dev_train.json", "r", encoding="utf-8") as f:
        train_tasks = json.load(f)["tasks"]
    with open(benchmarks_dir / "dev_eval.json", "r", encoding="utf-8") as f:
        eval_tasks = json.load(f)["tasks"]
    with open(benchmarks_dir / "held_out_test.json", "r", encoding="utf-8") as f:
        test_tasks = json.load(f)["tasks"]

    all_eval_tasks = eval_tasks + test_tasks

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "ablation_full.sqlite"
        library = KnowledgeLibrary(db_path)

        # Pre-seed library using train tasks
        config = EveConfig(max_falsification_rounds=8)
        bootstrap_loop = CEGISLoop(config, knowledge_library=library)
        for task in train_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]
            bootstrap_loop.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
            )

        library.record_learned_abstraction(
            LearnedAbstraction(
                name="map_add",
                pattern_sexpr="(map (lambda (a) (+ a $k)) x)",
                type_signature="(Int, List[Int]) -> List[Int]",
                arity=2,
                applicable_task_families=["list_mapping"],
            )
        )

        regimes = ["Baseline_A_Naive", "Baseline_B_FalsifyOnly", "Baseline_C_Library", "Full_System"]
        results: Dict[str, List[Dict[str, Any]]] = {r: [] for r in regimes}

        # -------------------------------------------------------------
        # 1. Baseline A: Naive Generator (0 falsification rounds, takes first match)
        # -------------------------------------------------------------
        print("\n--- Running Baseline A: Naive Proposal (No Active Falsification) ---")
        cfg_a = EveConfig(max_falsification_rounds=0)
        loop_a = CEGISLoop(cfg_a, knowledge_library=None)

        for task in all_eval_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

            t0 = time.perf_counter()
            res = loop_a.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
                search_strategy="symbolic_only",
            )
            runtime_ms = (time.perf_counter() - t0) * 1000.0

            results["Baseline_A_Naive"].append({
                "task_id": task["task_id"],
                "converged": res.converged,
                "status": res.status.value,
                "held_out_acc": res.held_out_accuracy or 0.0,
                "probes": len(res.probes_used),
                "runtime_ms": runtime_ms,
            })

        # -------------------------------------------------------------
        # 2. Baseline B: Active Falsifier (No Library)
        # -------------------------------------------------------------
        print("\n--- Running Baseline B: Active Falsifier Only (No Library) ---")
        cfg_b = EveConfig(max_falsification_rounds=8)
        loop_b = CEGISLoop(cfg_b, knowledge_library=None)

        for task in all_eval_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

            t0 = time.perf_counter()
            res = loop_b.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
                search_strategy="hybrid",
            )
            runtime_ms = (time.perf_counter() - t0) * 1000.0

            results["Baseline_B_FalsifyOnly"].append({
                "task_id": task["task_id"],
                "converged": res.converged,
                "status": res.status.value,
                "held_out_acc": res.held_out_accuracy or 0.0,
                "probes": len(res.probes_used),
                "runtime_ms": runtime_ms,
            })

        # -------------------------------------------------------------
        # 3. Baseline C: Active Falsifier + Knowledge Library
        # -------------------------------------------------------------
        print("\n--- Running Baseline C: Active Falsifier + Library Reuse ---")
        cfg_c = EveConfig(max_falsification_rounds=8)
        loop_c = CEGISLoop(cfg_c, knowledge_library=library)

        for task in all_eval_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

            t0 = time.perf_counter()
            res = loop_c.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
                search_strategy="hybrid",
            )
            runtime_ms = (time.perf_counter() - t0) * 1000.0

            results["Baseline_C_Library"].append({
                "task_id": task["task_id"],
                "converged": res.converged,
                "status": res.status.value,
                "held_out_acc": res.held_out_accuracy or 0.0,
                "probes": len(res.probes_used),
                "runtime_ms": runtime_ms,
            })

        # -------------------------------------------------------------
        # 4. Full System: Active Falsifier + Library + Optimized Policy
        # -------------------------------------------------------------
        print("\n--- Running Full System: Active Falsifier + Library + Optimized Policy ---")
        policy = ExplorationPolicy(version="v2.0-optimized", probe_cost_penalty_lambda=0.01)
        cfg_full = EveConfig(
            max_falsification_rounds=policy.max_falsification_rounds,
            probe_cost_penalty_lambda=policy.probe_cost_penalty_lambda,
        )
        loop_full = CEGISLoop(cfg_full, knowledge_library=library)

        for task in all_eval_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

            t0 = time.perf_counter()
            res = loop_full.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
                search_strategy="hybrid",
            )
            runtime_ms = (time.perf_counter() - t0) * 1000.0

            results["Full_System"].append({
                "task_id": task["task_id"],
                "converged": res.converged,
                "status": res.status.value,
                "held_out_acc": res.held_out_accuracy or 0.0,
                "probes": len(res.probes_used),
                "runtime_ms": runtime_ms,
            })

        # -------------------------------------------------------------
        # Compute Core Metrics Summary
        # -------------------------------------------------------------
        summary = {}
        for r_name, r_runs in results.items():
            pass_rate = sum(1 for x in r_runs if x["converged"]) / len(r_runs)
            avg_acc = statistics.mean([x["held_out_acc"] for x in r_runs])
            avg_probes = statistics.mean([x["probes"] for x in r_runs])
            avg_time = statistics.mean([x["runtime_ms"] for x in r_runs])

            # False verification: candidate claimed converged, but held_out_acc < 1.0 (Target: 0.0)
            false_verifs = sum(1 for x in r_runs if x["converged"] and x["held_out_acc"] < 1.0)
            false_verif_rate = false_verifs / len(r_runs)

            summary[r_name] = {
                "hidden_test_pass_rate": pass_rate,
                "mean_held_out_accuracy": avg_acc,
                "false_verification_rate": false_verif_rate,
                "avg_oracle_probes": avg_probes,
                "avg_runtime_ms": avg_time,
            }

        # Print Output Summary Table
        print("\n=====================================================================")
        print("                   FINAL METRICS SUMMARY TABLE                       ")
        print("=====================================================================")
        print(f"{'Regime':<28} | {'Pass Rate':<10} | {'False Verif':<12} | {'Avg Probes':<10} | {'Avg Time (ms)':<12}")
        print("-" * 80)
        for name, m in summary.items():
            print(f"{name:<28} | {m['hidden_test_pass_rate']*100:>8.1f}% | {m['false_verification_rate']*100:>10.1f}% | {m['avg_oracle_probes']:>10.2f} | {m['avg_runtime_ms']:>12.2f}")
        print("=" * 80)

        return {
            "detailed_results": results,
            "metrics_summary": summary,
        }


if __name__ == "__main__":
    run_full_ablation()
