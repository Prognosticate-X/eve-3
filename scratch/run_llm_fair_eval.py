"""Fair Local LLM Evaluation Runner (Prompt S1.1 Section D).

Evaluates mlx-community/Qwen2.5-Coder-3B-Instruct-4bit on all 13 unique tasks across:
  - k=8, temp=0.7
  - k=8, temp=1.0
  - k=16, temp=0.7
  - k=16, temp=1.0
with 3-5 clean non-benchmark few-shot examples and up to 2 rounds of parsing/execution error feedback.

Strict Closed Accounting (D.3):
  raw_candidates = syntax_invalid + exec_error + wrong_output + passed
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import mlx_lm
from mlx_lm.sample_utils import make_sampler

from eve3.config import EveConfig
from eve3.dsl.interpreter import DSLInterpreter, DSLParserError, ExecutionTimeoutError, SExprParser
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scratch.run_s1_evaluation import load_unique_tasks
FEWSHOT_PATH = REPO_ROOT / "prompts" / "fewshot.json"


def load_fewshot_data() -> Dict[str, Any]:
    return json.loads(FEWSHOT_PATH.read_text(encoding="utf-8"))


def build_fair_prompt(examples: List[Tuple[Any, Any]], k: int) -> str:
    data = load_fewshot_data()
    prims = ", ".join(data["valid_identifiers"])
    rules = "\n".join(f"- {r}" for r in data["syntax_rules"])
    fs_parts = []
    for t in data["fewshot_tasks"]:
        ex_str = "\n".join(f"  Input: {e['input']} -> Output: {e['output']}" for e in t["examples"])
        fs_parts.append(f"Task: {t['description']}\n{ex_str}\nSolution: {t['reference_program']}")
    fewshots_str = "\n\n".join(fs_parts)
    target_str = "\n".join(f"  Input: {inp} -> Output: {out}" for inp, out in examples)

    prompt = (
        "You are an expert neurosymbolic program synthesizer for EVE-3.\n\n"
        f"Available DSL Primitives: {prims}\n\n"
        f"DSL Syntax Rules:\n{rules}\n\n"
        f"Reference Examples:\n\n{fewshots_str}\n\n"
        f"Target Task:\n{target_str}\n\n"
        f"Generate {k} candidate DSL expressions (one per line) that transform 'x' to the output:\nCandidates:\n"
    )
    return prompt


def extract_candidate_lines(response: str, k: int) -> List[str]:
    lines = []
    for raw in response.splitlines():
        s = raw.strip()
        if not s or s.startswith("```"):
            continue
        s = re.sub(r"^(?:\d+[\.\)]\s*|[-*]\s*)", "", s).strip()
        if s.startswith("`") and s.endswith("`") and len(s) > 2:
            s = s[1:-1].strip()
        if s.startswith("(") or s == "x":
            lines.append(s)
    return lines[:k]


def test_candidate(code: str, examples: List[Tuple[Any, Any]], interp: DSLInterpreter, parser: SExprParser) -> Tuple[str, str]:
    """Classifies candidate into strictly one of: 'syntax_invalid', 'exec_error', 'wrong_output', 'passed'."""
    try:
        ast_node = parser.parse(code)
    except (DSLParserError, ValueError, TypeError, SyntaxError, KeyError, IndexError) as exc:
        return "syntax_invalid", f"Parser error: {exc}"

    for inp, expected in examples:
        try:
            actual = interp.run(ast_node, inp, timeout_seconds=0.2)
            if actual != expected or type(actual) is not type(expected):
                return "wrong_output", f"On input {inp}, produced {actual} but expected {expected}"
        except (
            ExecutionTimeoutError,
            NameError,
            AttributeError,
            ValueError,
            TypeError,
            ZeroDivisionError,
            IndexError,
            KeyError,
            RuntimeError,
            RecursionError,
            ArithmeticError,
            LookupError,
        ) as exc:
            return "exec_error", f"On input {inp}, crashed with {type(exc).__name__}: {exc}"

    return "passed", "Success"


def repair_candidate_with_feedback(
    model: Any,
    tokenizer: Any,
    failed_code: str,
    category: str,
    reason: str,
    examples: List[Tuple[Any, Any]],
    temperature: float,
    interp: DSLInterpreter,
    parser: SExprParser,
    max_rounds: int = 2,
) -> Tuple[str, str, int, float]:
    """Iteratively repairs candidate using up to max_rounds of feedback."""
    current_code = failed_code
    current_category = category
    current_reason = reason
    total_calls = 0
    total_latency_ms = 0.0

    target_str = "\n".join(f"  Input: {inp} -> Output: {out}" for inp, out in examples)

    for round_idx in range(1, max_rounds + 1):
        if current_category == "passed":
            break

        repair_prompt = (
            f"The candidate program `{current_code}` failed.\n"
            f"Error details: {current_reason}\n\n"
            f"Target Task Examples:\n{target_str}\n\n"
            "Please fix the program. Return ONLY the single corrected DSL expression:"
        )

        formatted = repair_prompt
        if hasattr(tokenizer, "apply_chat_template"):
            formatted = tokenizer.apply_chat_template(
                [{"role": "user", "content": repair_prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )

        sampler = make_sampler(temp=float(temperature))
        total_calls += 1
        t0 = time.perf_counter()
        resp = mlx_lm.generate(model, tokenizer, prompt=formatted, sampler=sampler, max_tokens=128)
        total_latency_ms += (time.perf_counter() - t0) * 1000.0

        repaired_lines = extract_candidate_lines(resp, 1)
        if not repaired_lines:
            break

        current_code = repaired_lines[0]
        current_category, current_reason = test_candidate(current_code, examples, interp, parser)

    return current_code, current_category, total_calls, total_latency_ms


def run_configuration(
    model: Any,
    tokenizer: Any,
    tasks: List[Dict[str, Any]],
    k: int,
    temperature: float,
) -> Dict[str, Any]:
    interp = DSLInterpreter()
    parser = SExprParser()

    total_raw = 0
    total_syntax_invalid = 0
    total_exec_error = 0
    total_wrong_output = 0
    total_initial_passed = 0
    total_repaired_passed = 0

    task_results = []
    total_llm_calls = 0
    total_latency_ms = 0.0

    print(f"\n>>> Running Config: k={k}, temp={temperature} across {len(tasks)} tasks")

    for t in tasks:
        train_ex = t["train_examples"]
        prompt = build_fair_prompt(train_ex, k)

        formatted = prompt
        if hasattr(tokenizer, "apply_chat_template"):
            formatted = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )

        sampler = make_sampler(temp=float(temperature))
        total_llm_calls += 1
        t0 = time.perf_counter()
        resp = mlx_lm.generate(model, tokenizer, prompt=formatted, sampler=sampler, max_tokens=384)
        lat_ms = (time.perf_counter() - t0) * 1000.0
        total_latency_ms += lat_ms

        raw_cands = extract_candidate_lines(resp, k)
        task_raw = len(raw_cands)
        total_raw += task_raw

        task_syntax_invalid = 0
        task_exec_error = 0
        task_wrong_output = 0
        task_initial_passed = 0
        task_repaired_passed = 0

        initial_passed_flag = False
        repaired_passed_flag = False

        cand_records = []
        for code in raw_cands:
            cat, reason = test_candidate(code, train_ex, interp, parser)
            if cat == "syntax_invalid":
                task_syntax_invalid += 1
            elif cat == "exec_error":
                task_exec_error += 1
            elif cat == "wrong_output":
                task_wrong_output += 1
            elif cat == "passed":
                task_initial_passed += 1
                initial_passed_flag = True

            # If not passed, attempt up to 2 rounds of feedback repair
            final_code = code
            final_cat = cat
            repair_calls = 0
            repair_lat_ms = 0.0
            if cat != "passed":
                final_code, final_cat, repair_calls, repair_lat_ms = repair_candidate_with_feedback(
                    model, tokenizer, code, cat, reason, train_ex, temperature, interp, parser, max_rounds=2
                )
                total_llm_calls += repair_calls
                total_latency_ms += repair_lat_ms

            if final_cat == "passed":
                repaired_passed_flag = True
                task_repaired_passed += 1

            cand_records.append({
                "initial_code": code,
                "initial_cat": cat,
                "initial_reason": reason,
                "final_code": final_code,
                "final_cat": final_cat,
                "repair_calls": repair_calls,
            })

        total_syntax_invalid += task_syntax_invalid
        total_exec_error += task_exec_error
        total_wrong_output += task_wrong_output
        total_initial_passed += task_initial_passed

        # Closed accounting check for this task
        assert task_raw == task_syntax_invalid + task_exec_error + task_wrong_output + task_initial_passed, "Accounting mismatch!"

        # Also verify against held-out tests if any candidate passed
        solved_held_out = False
        winning_prog = None
        for r in cand_records:
            if r["final_cat"] == "passed":
                try:
                    ast_node = parser.parse(r["final_code"])
                    all_hid_match = True
                    for h_in, h_out in t["held_out_examples"]:
                        if interp.run(ast_node, h_in, timeout_seconds=0.2) != h_out:
                            all_hid_match = False
                            break
                    if all_hid_match:
                        solved_held_out = True
                        winning_prog = r["final_code"]
                        break
                except Exception:
                    continue

        task_results.append({
            "task_name": t["task_name"],
            "raw_count": task_raw,
            "syntax_invalid": task_syntax_invalid,
            "exec_error": task_exec_error,
            "wrong_output": task_wrong_output,
            "initial_passed": task_initial_passed,
            "repaired_passed": task_repaired_passed,
            "pass_at_k_initial": initial_passed_flag,
            "pass_at_k_repaired": (initial_passed_flag or repaired_passed_flag),
            "solved_held_out": solved_held_out,
            "winning_prog": winning_prog,
            "candidates": cand_records,
        })

        print(
            f"  {t['task_name']:24s} | raw={task_raw} [syn_inv={task_syntax_invalid}, "
            f"exec_err={task_exec_error}, wrong={task_wrong_output}, pass={task_initial_passed}] | "
            f"repaired_pass={task_repaired_passed} | held_out_win={winning_prog}"
        )

    # Global closed accounting assertion
    assert total_raw == total_syntax_invalid + total_exec_error + total_wrong_output + total_initial_passed

    tasks_solved_initial = sum(1 for tr in task_results if tr["pass_at_k_initial"])
    tasks_solved_repaired = sum(1 for tr in task_results if tr["pass_at_k_repaired"])
    tasks_solved_held_out = sum(1 for tr in task_results if tr["solved_held_out"])

    return {
        "k": k,
        "temperature": temperature,
        "total_tasks": len(tasks),
        "total_llm_calls": total_llm_calls,
        "total_latency_ms": round(total_latency_ms, 2),
        "mean_latency_per_call_ms": round(total_latency_ms / total_llm_calls, 2) if total_llm_calls > 0 else 0.0,
        "raw_candidates": total_raw,
        "syntax_invalid": total_syntax_invalid,
        "syntax_invalid_pct": round(total_syntax_invalid / total_raw * 100, 2) if total_raw > 0 else 0.0,
        "exec_error": total_exec_error,
        "exec_error_pct": round(total_exec_error / total_raw * 100, 2) if total_raw > 0 else 0.0,
        "wrong_output": total_wrong_output,
        "wrong_output_pct": round(total_wrong_output / total_raw * 100, 2) if total_raw > 0 else 0.0,
        "passed": total_initial_passed,
        "passed_pct": round(total_initial_passed / total_raw * 100, 2) if total_raw > 0 else 0.0,
        "pass_at_k_initial_tasks": tasks_solved_initial,
        "pass_at_k_initial_rate": round(tasks_solved_initial / len(tasks), 4),
        "pass_at_k_repaired_tasks": tasks_solved_repaired,
        "pass_at_k_repaired_rate": round(tasks_solved_repaired / len(tasks), 4),
        "tasks_solved_held_out": tasks_solved_held_out,
        "tasks_solved_held_out_rate": round(tasks_solved_held_out / len(tasks), 4),
        "tasks_breakdown": task_results,
    }


def main():
    tasks = load_unique_tasks()
    print(f"Loaded {len(tasks)} unique benchmark tasks for fair LLM evaluation.")

    model_name = EveConfig().model_name
    print(f"Loading local MLX model: {model_name} ...")
    model, tokenizer = mlx_lm.load(model_name)

    configurations = [
        (8, 0.7),
        (8, 1.0),
        (16, 0.7),
        (16, 1.0),
    ]

    all_configs_results = []
    for k, temp in configurations:
        res = run_configuration(model, tokenizer, tasks, k, temp)
        all_configs_results.append(res)

    output = {
        "model_name": model_name,
        "accounting_rule": "raw = syntax_invalid + exec_error + wrong_output + passed",
        "configurations": all_configs_results,
    }

    out_file = REPO_ROOT / "reports" / "llm_fair_eval_output.json"
    out_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved fair LLM evaluation results to {out_file}")


if __name__ == "__main__":
    main()
