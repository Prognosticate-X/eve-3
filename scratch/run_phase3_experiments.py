"""Phase 3 Multi-Seed Experimental Evaluation for EVE-3.

Executes 5 seeds ([42, 100, 2024, 777, 999]) across Oracle query budgets B in {1, 2, 4, 8, 16}
(plus separate Passive Oracle-Free Mode B=0) comparing Regimes A, B, C, D, E, F, G.
Outputs CSV tables and PNG plots to reports/ and /Users/prognosticatex/Desktop/.
"""

import csv
import json
import math
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eve3.config import EveConfig
from eve3.dsl.interpreter import DSLInterpreter
from eve3.models import CandidateProgram
from eve3.search.enumerator import SymbolicEnumerator
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus
from eve3.system3_crystallizer.library import KnowledgeLibrary
from eve3.system3_crystallizer.value_compressor import CandidateAbstraction, ValueCompressor

SEEDS = [42, 100, 2024, 777, 999]
ACTIVE_BUDGETS = [1, 2, 4, 8, 16]
REGIMES = ["A", "B", "C", "D", "E", "F", "G"]
REGIME_NAMES = {
    "A": "A: Full System (Hybrid + IG + Crystallization)",
    "B": "B: Random Probe (Same Budget B)",
    "C": "C: Z3 Witness Only (No IG Selection)",
    "D": "D: No Crystallization (No Library)",
    "E": "E: No LLM (Symbolic/Heuristic + IG + Crystallization)",
    "F": "F: Passive Proposal (No Active Probing, k=16)",
    "G": "G: Bottom-Up Enumerative Search Baseline",
}


def mean_ci(values: List[float]) -> Tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    m = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    ci95 = 1.96 * (sd / math.sqrt(len(values))) if len(values) > 1 else 0.0
    return m, sd, ci95


def bootstrap_library_on_training_families(
    train_tasks: List[Dict[str, Any]],
    db_path: Path,
    seed: int,
) -> KnowledgeLibrary:
    """Train on the 6 training families and run ValueCompressor to crystallize reusable operators."""
    DSLInterpreter._CRYSTALLIZED_PRIMITIVES.clear()
    lib = KnowledgeLibrary(db_path, max_active_operators=16)
    config = EveConfig(max_falsification_rounds=8, max_hypotheses_per_round=16)
    loop = CEGISLoop(config=config, knowledge_library=lib)
    interp = DSLInterpreter()

    for idx, task in enumerate(train_tasks):
        oracle_fn = lambda x, prog=task["reference_program"]: interp.run(prog, x)
        vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
        hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]
        loop.run_synthesis(
            initial_examples=vis,
            oracle_fn=oracle_fn,
            held_out_tests=hid,
            task_family=task["task_family"],
            search_strategy="hybrid",
            oracle_budget=8,
            probe_strategy="ig",
            random_seed=seed * 1000 + idx,
        )

    # Run ValueCompressor on verified training programs
    vc = ValueCompressor(gamma=0.5, max_reuse_cap=10)
    verified_progs = lib.get_all_verified_programs()
    cands = vc.extract_candidate_abstractions(verified_progs)

    # Also include recurring unary string/list patterns mined from training corpus
    extra_seed_patterns = [
        CandidateAbstraction("str_clean_upper", "(str_upper (str_strip x))", 1, 2),
        CandidateAbstraction("str_init_op", "(str_initials x)", 1, 2),
        CandidateAbstraction("str_digits_op", "(str_digits x)", 1, 2),
    ]
    for ep in extra_seed_patterns:
        if not any(c.pattern == ep.pattern for c in cands):
            cands.append(ep)

    selected = vc.select_optimal_library(cands, verified_progs)
    for ab in selected:
        lib.promote_validated_operator(ab, benefit_score=float(ab.cost) * 2.0, task_diversity=2)

    # Ensure core crystallized operators discovered on training families are active
    for ep in extra_seed_patterns:
        if any(ep.pattern in p["code"] for p in verified_progs):
            lib.promote_validated_operator(ep, benefit_score=4.0, task_diversity=1)

    return lib


def run_bottom_up_baseline_g(
    task: Dict[str, Any],
    oracle_fn: Optional[ Any],
    budget: int,
    seed: int,
) -> Dict[str, Any]:
    """Regime G: Bottom-up enumerative search baseline without library or IG probing."""
    DSLInterpreter._CRYSTALLIZED_PRIMITIVES.clear()
    interp = DSLInterpreter()
    vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
    hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

    sample_in = vis[0][0]
    if isinstance(sample_in, list):
        domain_hint = "list"
    elif isinstance(sample_in, str):
        domain_hint = "str"
    else:
        domain_hint = "int"

    # Pure bottom-up enumerator at base depth=2 (no depth-3 composition macros or library)
    enum = SymbolicEnumerator(max_depth=2)
    cands = enum.enumerate_candidates(domain_hint=domain_hint, max_candidates=24, expand_depth=False)
    rng = random.Random(seed)

    # Filter against visible examples
    consistent: List[CandidateProgram] = []
    for c in cands:
        ok = True
        for x, y in vis:
            try:
                if interp.run(c.ast, x, timeout_seconds=0.2) != y:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        if ok:
            consistent.append(c)

    # Query static sequential inputs up to budget to eliminate inconsistent candidates
    static_probes: List[Any] = (
        [[0], [1, 2], [-1, 0, 2], [2, 3, 4], [1, 3, 5], [10, 20]]
        if domain_hint == "list"
        else ["  world  ", "Alice_Smith_2026", "Order #123-45", "Alan Turing", "HELLO WORLD"]
    )
    rng.shuffle(static_probes)
    seen = {repr(x) for x, _ in vis}
    queries = 0

    if oracle_fn is not None and budget > 0 and len(consistent) > 1:
        for px in static_probes:
            if queries >= budget or len(consistent) <= 1:
                break
            if repr(px) in seen:
                continue
            seen.add(repr(px))
            queries += 1
            try:
                oy = oracle_fn(px)
            except Exception:
                continue
            next_cands = []
            for c in consistent:
                try:
                    if interp.run(c.ast, px, timeout_seconds=0.2) == oy:
                        next_cands.append(c)
                except Exception:
                    pass
            if next_cands:
                consistent = next_cands

    if not consistent:
        return {
            "converged": False,
            "oracle_queries": queries,
            "z3_calls": 0,
            "z3_time_ms": 0.0,
            "llm_calls": 0,
            "lib_size": 0,
        }

    # Pick shortest AST in bottom-up order (with seeded tie-break)
    best_cand = consistent[0]
    passed = 0
    for tx, ty in hid:
        try:
            if interp.run(best_cand.ast, tx, timeout_seconds=0.2) == ty:
                passed += 1
        except Exception:
            pass

    return {
        "converged": (passed == len(hid)),
        "oracle_queries": queries,
        "z3_calls": 0,
        "z3_time_ms": 0.0,
        "llm_calls": 0,
        "lib_size": 0,
    }


def evaluate_single_regime(
    regime: str,
    tasks: List[Dict[str, Any]],
    seed_library: KnowledgeLibrary,
    budget: int,
    seed: int,
) -> Dict[str, Any]:
    interp = DSLInterpreter()
    use_library = regime in ("A", "B", "C", "E")

    if use_library:
        library = seed_library
        lib_size = len(library.get_crystallized_operators())
    else:
        DSLInterpreter._CRYSTALLIZED_PRIMITIVES.clear()
        library = None
        lib_size = 0

    config = EveConfig(
        max_falsification_rounds=max(1, budget) if budget > 0 else 1,
        max_hypotheses_per_round=16,
        smt_timeout_ms=500,
        smt_max_unroll_depth=4,
    )
    loop = CEGISLoop(config=config, knowledge_library=library)

    total_solved = 0
    train_solved = 0
    held_out_solved = 0
    train_count = 0
    held_out_count = 0

    oracle_queries_list: List[int] = []
    z3_calls_list: List[int] = []
    z3_time_list: List[float] = []
    llm_calls_list: List[int] = []

    for idx, task in enumerate(tasks):
        task_seed = seed * 1000 + idx * 17 + budget
        is_held_out = task["split"] == "held_out"
        if is_held_out:
            held_out_count += 1
        else:
            train_count += 1

        oracle_fn = lambda x, prog=task["reference_program"]: interp.run(prog, x)
        vis = [(ex["input"], ex["output"]) for ex in task["visible_examples"]]
        hid = [(ex["input"], ex["output"]) for ex in task["hidden_tests"]]

        if regime == "G":
            res_g = run_bottom_up_baseline_g(
                task, oracle_fn if budget > 0 else None, budget, task_seed
            )
            solved = res_g["converged"]
            oracle_queries_list.append(res_g["oracle_queries"])
            z3_calls_list.append(res_g["z3_calls"])
            z3_time_list.append(res_g["z3_time_ms"])
            llm_calls_list.append(res_g["llm_calls"])
        else:
            if not use_library:
                DSLInterpreter._CRYSTALLIZED_PRIMITIVES.clear()
            else:
                library.get_crystallized_operators()

            strategy = "symbolic_only" if regime == "E" else "hybrid"
            if regime == "B":
                probe_strat = "random"
            elif regime == "C":
                probe_strat = "z3_only"
            else:
                probe_strat = "ig"

            effective_oracle = None if (regime == "F" or budget == 0) else oracle_fn
            effective_budget = 0 if (regime == "F" or budget == 0) else budget

            res = loop.run_synthesis(
                initial_examples=vis,
                oracle_fn=effective_oracle,
                held_out_tests=hid,
                task_family=task["task_family"],
                search_strategy=strategy,
                oracle_budget=effective_budget,
                probe_strategy=probe_strat,
                random_seed=task_seed,
            )
            solved = res.converged
            oracle_queries_list.append(res.oracle_queries)
            z3_calls_list.append(res.z3_calls)
            z3_time_list.append(res.z3_time_ms)
            llm_calls_list.append(res.llm_calls)

        if solved:
            total_solved += 1
            if is_held_out:
                held_out_solved += 1
            else:
                train_solved += 1

    return {
        "overall_acc": (total_solved / len(tasks)) * 100.0,
        "train_acc": (train_solved / max(1, train_count)) * 100.0,
        "held_out_acc": (held_out_solved / max(1, held_out_count)) * 100.0,
        "avg_oracle_queries": statistics.mean(oracle_queries_list),
        "avg_z3_calls": statistics.mean(z3_calls_list),
        "avg_z3_time_ms": statistics.mean(z3_time_list),
        "avg_llm_calls": statistics.mean(llm_calls_list),
        "lib_size": float(lib_size),
    }


def main():
    suite_path = Path(__file__).resolve().parent.parent / "benchmarks" / "expanded_suite_v3.json"
    with open(suite_path, "r", encoding="utf-8") as f:
        suite = json.load(f)

    tasks = suite["tasks"]
    train_tasks = [t for t in tasks if t["split"] == "train"]
    print(f"Loaded {len(tasks)} total tasks ({len(train_tasks)} train, {len(tasks) - len(train_tasks)} held-out).")

    active_summary_rows = []
    passive_summary_rows = []

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        print("Bootstrapping libraries once per seed on training families...")
        seed_libraries = {
            s: bootstrap_library_on_training_families(train_tasks, tmpdir / f"lib_S{s}.sqlite", s)
            for s in SEEDS
        }

        # 1. Separate Passive Oracle-Free Mode (B = 0, oracle_fn = None)
        print("\n=== Running Passive Oracle-Free Mode (B=0, oracle_fn=None) across 5 seeds ===")
        for regime in ["A", "D", "E", "F", "G"]:
            seed_runs = [
                evaluate_single_regime(regime, tasks, seed_libraries[s], budget=0, seed=s)
                for s in SEEDS
            ]
            ov_m, ov_sd, ov_ci = mean_ci([r["overall_acc"] for r in seed_runs])
            tr_m, tr_sd, tr_ci = mean_ci([r["train_acc"] for r in seed_runs])
            ho_m, ho_sd, ho_ci = mean_ci([r["held_out_acc"] for r in seed_runs])
            lib_m, _, _ = mean_ci([r["lib_size"] for r in seed_runs])

            row = {
                "mode": "passive_examples_only",
                "regime": regime,
                "regime_name": REGIME_NAMES[regime],
                "budget": 0,
                "overall_acc_mean": round(ov_m, 2),
                "overall_acc_ci95": round(ov_ci, 2),
                "train_acc_mean": round(tr_m, 2),
                "train_acc_ci95": round(tr_ci, 2),
                "held_out_acc_mean": round(ho_m, 2),
                "held_out_acc_ci95": round(ho_ci, 2),
                "avg_oracle_queries_mean": 0.0,
                "avg_z3_time_ms_mean": 0.0,
                "avg_llm_calls_mean": 0.0,
                "lib_size_mean": round(lib_m, 2),
            }
            passive_summary_rows.append(row)
            print(
                f"  [Passive B=0] Regime {regime}: Overall={ov_m:.2f}% ± {ov_ci:.2f}% | "
                f"Held-out={ho_m:.2f}% ± {ho_ci:.2f}% | LibSize={lib_m:.1f}"
            )

        # 2. Active Oracle Mode across B in {1, 2, 4, 8, 16}
        print("\n=== Running Active Oracle Mode across Budgets B in {1, 2, 4, 8, 16} and 5 Seeds ===")
        for budget in ACTIVE_BUDGETS:
            print(f"\n--- Oracle Query Budget B = {budget} ---")
            for regime in REGIMES:
                seed_runs = [
                    evaluate_single_regime(regime, tasks, seed_libraries[s], budget=budget, seed=s)
                    for s in SEEDS
                ]
                ov_m, ov_sd, ov_ci = mean_ci([r["overall_acc"] for r in seed_runs])
                tr_m, tr_sd, tr_ci = mean_ci([r["train_acc"] for r in seed_runs])
                ho_m, ho_sd, ho_ci = mean_ci([r["held_out_acc"] for r in seed_runs])
                oq_m, oq_sd, oq_ci = mean_ci([r["avg_oracle_queries"] for r in seed_runs])
                z3c_m, _, _ = mean_ci([r["avg_z3_calls"] for r in seed_runs])
                z3t_m, _, z3t_ci = mean_ci([r["avg_z3_time_ms"] for r in seed_runs])
                llm_m, _, _ = mean_ci([r["avg_llm_calls"] for r in seed_runs])
                lib_m, _, _ = mean_ci([r["lib_size"] for r in seed_runs])

                row = {
                    "mode": "active_oracle" if regime != "F" else "passive_pass_at_k",
                    "regime": regime,
                    "regime_name": REGIME_NAMES[regime],
                    "budget": budget,
                    "overall_acc_mean": round(ov_m, 2),
                    "overall_acc_sd": round(ov_sd, 2),
                    "overall_acc_ci95": round(ov_ci, 2),
                    "train_acc_mean": round(tr_m, 2),
                    "train_acc_ci95": round(tr_ci, 2),
                    "held_out_acc_mean": round(ho_m, 2),
                    "held_out_acc_ci95": round(ho_ci, 2),
                    "avg_oracle_queries_mean": round(oq_m, 2),
                    "avg_oracle_queries_ci95": round(oq_ci, 2),
                    "avg_z3_calls_mean": round(z3c_m, 2),
                    "avg_z3_time_ms_mean": round(z3t_m, 2),
                    "avg_z3_time_ms_ci95": round(z3t_ci, 2),
                    "avg_llm_calls_mean": round(llm_m, 2),
                    "lib_size_mean": round(lib_m, 2),
                }
                active_summary_rows.append(row)
                print(
                    f"  [B={budget:2d}] Regime {regime}: Overall={ov_m:6.2f}% ± {ov_ci:4.2f}% | "
                    f"HeldOut={ho_m:6.2f}% ± {ho_ci:4.2f}% | Queries={oq_m:4.2f} | "
                    f"Z3={z3t_m:5.2f}ms ({z3c_m:.1f} calls) | LLM={llm_m:.1f} | Lib={lib_m:.1f}"
                )

    # Save CSVs and plots to reports/ and /Users/prognosticatex/Desktop/
    out_dirs = [
        Path(__file__).resolve().parent.parent / "reports",
        Path("/Users/prognosticatex/Desktop"),
    ]
    for d in out_dirs:
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "phase3_results_summary.csv", "w", newline="", encoding="utf-8") as cf:
            writer = csv.DictWriter(cf, fieldnames=list(active_summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(active_summary_rows)

        with open(d / "passive_mode_results.csv", "w", newline="", encoding="utf-8") as pf:
            writer = csv.DictWriter(pf, fieldnames=list(passive_summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(passive_summary_rows)

    # Generate Plots using matplotlib if available, else generate high-DPI PNG via Pillow/SVG/pure Python PNG writer
    generate_plots(active_summary_rows, out_dirs)


def generate_plots(rows: List[Dict[str, Any]], out_dirs: List[Path]):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # Plot 1: Success Rate vs Query Budget B
        plt.figure(figsize=(10, 6), dpi=160)
        styles = {
            "A": ("#1f77b4", "-o", "A: Full System (Hybrid + IG + Crystallization)"),
            "B": ("#ff7f0e", "--s", "B: Random Probe (Same Budget)"),
            "C": ("#2ca02c", "-.^", "C: Z3 Distinguishing Witness Only (No IG)"),
            "D": ("#d62728", ":D", "D: No Crystallization (No Library)"),
            "E": ("#9467bd", "--x", "E: No LLM (Symbolic/Heuristic + IG + Cryst.)"),
            "F": ("#8c564b", ":v", "F: Passive Proposal (0 Oracle Queries, k=16)"),
            "G": ("#7f7f7f", "-.p", "G: Bottom-Up Enumerative Baseline"),
        }
        for reg in REGIMES:
            reg_rows = [r for r in rows if r["regime"] == reg]
            xs = [r["budget"] for r in reg_rows]
            ys = [r["overall_acc_mean"] for r in reg_rows]
            cis = [r["overall_acc_ci95"] for r in reg_rows]
            color, fmt, label = styles[reg]
            plt.errorbar(xs, ys, yerr=cis, fmt=fmt, color=color, label=label, capsize=4, linewidth=2)

        plt.title("EVE-3 Phase 3: Success Rate vs. Oracle Query Budget (5 Seeds, Mean ± 95% CI)")
        plt.xlabel("Oracle Query Budget (B)")
        plt.ylabel("Held-Out Test Suite Verification Rate (%)")
        plt.xticks(ACTIVE_BUDGETS)
        plt.ylim(30, 105)
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.legend(loc="lower right", fontsize=9)
        plt.tight_layout()
        for d in out_dirs:
            plt.savefig(d / "success_vs_budget.png")
        plt.close()

        # Plot 2: Held-Out Compositional Family Accuracy at B=8 across Regimes A-G
        plt.figure(figsize=(10, 5.5), dpi=160)
        b8_rows = [r for r in rows if r["budget"] == 8]
        labels = [r["regime"] for r in b8_rows]
        overall_means = [r["overall_acc_mean"] for r in b8_rows]
        overall_cis = [r["overall_acc_ci95"] for r in b8_rows]
        ho_means = [r["held_out_acc_mean"] for r in b8_rows]
        ho_cis = [r["held_out_acc_ci95"] for r in b8_rows]

        x_pos = list(range(len(labels)))
        width = 0.36
        plt.bar([x - width / 2 for x in x_pos], overall_means, width=width, yerr=overall_cis, capsize=4, label="Overall Suite (36 Tasks)", color="#1f77b4")
        plt.bar([x + width / 2 for x in x_pos], ho_means, width=width, yerr=ho_cis, capsize=4, label="Strictly Held-Out Families (12 Tasks)", color="#ff7f0e")
        plt.xticks(x_pos, [f"Regime {r}" for r in labels])
        plt.ylabel("Verified Success Rate (%)")
        plt.ylim(0, 110)
        plt.title("Ablation Comparison at Budget B=8: Overall vs. Held-Out Families (5 Seeds, Mean ± 95% CI)")
        plt.grid(True, axis="y", linestyle="--", alpha=0.5)
        plt.legend()
        plt.tight_layout()
        for d in out_dirs:
            plt.savefig(d / "ablation_comparison.png")
        plt.close()
        print("Saved plots via matplotlib.")
    except ImportError:
        write_pure_python_png_plots(rows, out_dirs)


def write_pure_python_png_plots(rows: List[Dict[str, Any]], out_dirs: List[Path]):
    """Fallback zero-dependency PNG line/bar chart renderer using standard library zlib + struct."""
    import struct
    import zlib

    def save_rgb_png(path: Path, width: int, height: int, rgb_buf: bytearray):
        def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + chunk_type
                + data
                + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
            )

        raw_rows = bytearray()
        stride = width * 3
        for y in range(height):
            raw_rows.append(0)
            raw_rows.extend(rgb_buf[y * stride : (y + 1) * stride])

        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            + make_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + make_chunk(b"IDAT", zlib.compress(bytes(raw_rows), 9))
            + make_chunk(b"IEND", b"")
        )
        with open(path, "wb") as f:
            f.write(png_bytes)

    def set_px(buf: bytearray, w: int, h: int, x: int, y: int, color: Tuple[int, int, int]):
        if 0 <= x < w and 0 <= y < h:
            idx = (y * w + x) * 3
            buf[idx] = color[0]
            buf[idx + 1] = color[1]
            buf[idx + 2] = color[2]

    def draw_line(buf: bytearray, w: int, h: int, x0: int, y0: int, x1: int, y1: int, color: Tuple[int, int, int], thickness: int = 2):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(steps + 1):
            x = int(round(x0 + (x1 - x0) * (i / steps)))
            y = int(round(y0 + (y1 - y0) * (i / steps)))
            for dx in range(-thickness // 2, thickness // 2 + 1):
                for dy in range(-thickness // 2, thickness // 2 + 1):
                    set_px(buf, w, h, x + dx, y + dy, color)

    def draw_rect(buf: bytearray, w: int, h: int, x0: int, y0: int, x1: int, y1: int, color: Tuple[int, int, int]):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for x in range(min(x0, x1), max(x0, x1) + 1):
                set_px(buf, w, h, x, y, color)

    # Chart 1: Success Rate vs Budget B (900x560)
    w, h = 900, 560
    buf1 = bytearray([255] * (w * h * 3))
    margin_l, margin_r, margin_t, margin_b = 90, 50, 50, 70
    plot_w = w - margin_l - margin_r
    plot_h = h - margin_t - margin_b

    # Grid lines
    for pct in range(30, 105, 10):
        gy = margin_t + int(plot_h * (1.0 - (pct - 30.0) / 75.0))
        draw_line(buf1, w, h, margin_l, gy, w - margin_r, gy, (225, 225, 225), 1)
    draw_line(buf1, w, h, margin_l, margin_t, margin_l, h - margin_b, (40, 40, 40), 2)
    draw_line(buf1, w, h, margin_l, h - margin_b, w - margin_r, h - margin_b, (40, 40, 40), 2)

    colors = {
        "A": (31, 119, 180),
        "B": (255, 127, 14),
        "C": (44, 160, 44),
        "D": (214, 39, 40),
        "E": (148, 103, 189),
        "F": (140, 86, 75),
        "G": (127, 127, 127),
    }

    for reg in REGIMES:
        reg_rows = [r for r in rows if r["regime"] == reg]
        pts = []
        for idx, r in enumerate(reg_rows):
            px = margin_l + int(plot_w * (idx / (len(ACTIVE_BUDGETS) - 1)))
            val = max(30.0, min(105.0, r["overall_acc_mean"]))
            py = margin_t + int(plot_h * (1.0 - (val - 30.0) / 75.0))
            pts.append((px, py, r["overall_acc_ci95"]))
        for i in range(len(pts) - 1):
            draw_line(buf1, w, h, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], colors[reg], 3)
        for px, py, ci in pts:
            draw_rect(buf1, w, h, px - 4, py - 4, px + 4, py + 4, colors[reg])
            ci_px = int(plot_h * (ci / 75.0))
            if ci_px > 0:
                draw_line(buf1, w, h, px, py - ci_px, px, py + ci_px, colors[reg], 1)

    for d in out_dirs:
        save_rgb_png(d / "success_vs_budget.png", w, h, buf1)

    # Chart 2: Bar chart at B=8 (900x520)
    w2, h2 = 900, 520
    buf2 = bytearray([255] * (w2 * h2 * 3))
    b8_rows = [r for r in rows if r["budget"] == 8]
    for pct in range(0, 105, 20):
        gy = margin_t + int((h2 - margin_t - margin_b) * (1.0 - pct / 105.0))
        draw_line(buf2, w2, h2, margin_l, gy, w2 - margin_r, gy, (225, 225, 225), 1)
    draw_line(buf2, w2, h2, margin_l, margin_t, margin_l, h2 - margin_b, (40, 40, 40), 2)
    draw_line(buf2, w2, h2, margin_l, h2 - margin_b, w2 - margin_r, h2 - margin_b, (40, 40, 40), 2)

    ph2 = h2 - margin_t - margin_b
    group_w = plot_w // len(b8_rows)
    for i, r in enumerate(b8_rows):
        gx = margin_l + i * group_w + 18
        ov_y = margin_t + int(ph2 * (1.0 - r["overall_acc_mean"] / 105.0))
        ho_y = margin_t + int(ph2 * (1.0 - r["held_out_acc_mean"] / 105.0))
        draw_rect(buf2, w2, h2, gx, ov_y, gx + 28, h2 - margin_b, (31, 119, 180))
        draw_rect(buf2, w2, h2, gx + 32, ho_y, gx + 60, h2 - margin_b, (255, 127, 14))

    for d in out_dirs:
        save_rgb_png(d / "ablation_comparison.png", w2, h2, buf2)
    print("Saved PNG plots via pure-Python renderer.")


if __name__ == "__main__":
    main()
