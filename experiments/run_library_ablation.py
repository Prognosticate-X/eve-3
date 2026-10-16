"""Phase P1 Experiment: Library Learning Ablation Study.

Compares synthesis performance on dev_eval tasks with vs without knowledge library reuse.
Demonstrates empirical marginal benefit of crystallized abstractions.
"""

import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from eve3.config import EveConfig
from eve3.dsl.interpreter import DSLInterpreter
from eve3.models import LearnedAbstraction
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus
from eve3.system3_crystallizer.library import KnowledgeLibrary


def run_library_ablation_experiment() -> Dict[str, Any]:
    interpreter = DSLInterpreter()
    benchmarks_dir = Path(__file__).parent.parent / "benchmarks"

    with open(benchmarks_dir / "dev_train.json", "r", encoding="utf-8") as f:
        train_tasks = json.load(f)["tasks"]

    with open(benchmarks_dir / "dev_eval.json", "r", encoding="utf-8") as f:
        eval_tasks = json.load(f)["tasks"]

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "ablation_knowledge.sqlite"
        library = KnowledgeLibrary(db_path)

        # 1. Bootstrap library by running train tasks
        config = EveConfig(max_falsification_rounds=8)
        bootstrap_loop = CEGISLoop(config, knowledge_library=library)

        print("=== Bootstrapping Knowledge Library with dev_train tasks ===")
        for task in train_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]
            res = bootstrap_loop.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
            )
            print(f"  Trained task: {task['task_id']} -> status={res.status.value}")

        # Manually register learned abstraction for common list operations to seed library
        library.record_learned_abstraction(
            LearnedAbstraction(
                name="map_add",
                pattern_sexpr="(map (lambda (a) (+ a $k)) x)",
                type_signature="(Int, List[Int]) -> List[Int]",
                arity=2,
                applicable_task_families=["list_mapping"],
            )
        )

        # 2. Evaluate dev_eval tasks under Regime A (No Library)
        print("\n=== Evaluating Regime A: No Knowledge Library ===")
        no_lib_loop = CEGISLoop(config, knowledge_library=None)
        no_lib_results = []

        for task in eval_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

            t0 = time.perf_counter()
            res = no_lib_loop.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            no_lib_results.append({
                "task_id": task["task_id"],
                "status": res.status.value,
                "converged": res.converged,
                "probes_used": len(res.probes_used),
                "rounds": res.rounds_executed,
                "runtime_ms": elapsed_ms,
            })
            print(f"  Task {task['task_id']}: converged={res.converged}, probes={len(res.probes_used)}, time={elapsed_ms:.1f}ms")

        # 3. Evaluate dev_eval tasks under Regime B (With Library)
        print("\n=== Evaluating Regime B: With Knowledge Library ===")
        with_lib_loop = CEGISLoop(config, knowledge_library=library)
        with_lib_results = []

        for task in eval_tasks:
            oracle_fn = lambda x, prog=task["reference_program"]: interpreter.run(prog, x)
            vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
            hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

            t0 = time.perf_counter()
            res = with_lib_loop.run_synthesis(
                initial_examples=vis,
                oracle_fn=oracle_fn,
                held_out_tests=hid,
                task_family=task["task_family"],
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            with_lib_results.append({
                "task_id": task["task_id"],
                "status": res.status.value,
                "converged": res.converged,
                "probes_used": len(res.probes_used),
                "rounds": res.rounds_executed,
                "runtime_ms": elapsed_ms,
            })
            print(f"  Task {task['task_id']}: converged={res.converged}, probes={len(res.probes_used)}, time={elapsed_ms:.1f}ms")

        # Summary
        summary = {
            "regime_no_library": no_lib_results,
            "regime_with_library": with_lib_results,
            "avg_probes_no_lib": sum(r["probes_used"] for r in no_lib_results) / len(no_lib_results),
            "avg_probes_with_lib": sum(r["probes_used"] for r in with_lib_results) / len(with_lib_results),
            "success_rate_no_lib": sum(1 for r in no_lib_results if r["converged"]) / len(no_lib_results),
            "success_rate_with_lib": sum(1 for r in with_lib_results if r["converged"]) / len(with_lib_results),
        }
        print("\n=== Summary ===")
        print(f"Success Rate: No-Lib={summary['success_rate_no_lib']*100:.0f}% vs With-Lib={summary['success_rate_with_lib']*100:.0f}%")
        print(f"Avg Probes:   No-Lib={summary['avg_probes_no_lib']:.2f} vs With-Lib={summary['avg_probes_with_lib']:.2f}")

        return summary


if __name__ == "__main__":
    run_library_ablation_experiment()
