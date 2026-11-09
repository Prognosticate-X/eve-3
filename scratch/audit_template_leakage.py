"""Exhaustive audit of all 27 generator.py templates and all enumerator.py templates against all benchmark tasks."""

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eve3.dsl.interpreter import DSLInterpreter

interp = DSLInterpreter()

GENERATOR_TEMPLATES = [
    # Identity and simple lists
    (1, 134, "x"),
    (2, 135, "(reverse x)"),
    (3, 136, "(tail x)"),
    # Mapping transformations
    (4, 138, "(map (lambda (a) (+ a 1)) x)"),
    (5, 139, "(map (lambda (a) (+ a 2)) x)"),
    (6, 140, "(map (lambda (a) (- a 1)) x)"),
    (7, 141, "(map (lambda (a) (* a 2)) x)"),
    (8, 142, "(map (lambda (a) (* a a)) x)"),
    (9, 143, "(map (lambda (a) (inc a)) x)"),
    (10, 144, "(map (lambda (a) (dec a)) x)"),
    (11, 145, "(map (lambda (a) (neg a)) x)"),
    # Filtering
    (12, 147, "(filter (lambda (a) (is_even a)) x)"),
    (13, 148, "(filter (lambda (a) (is_odd a)) x)"),
    (14, 149, "(filter (lambda (a) (gt a 0)) x)"),
    (15, 150, "(filter (lambda (a) (gt a 2)) x)"),
    (16, 151, "(filter (lambda (a) (gt a 3)) x)"),
    (17, 152, "(filter (lambda (a) (lt a 5)) x)"),
    # Aggregation & Reductions
    (18, 154, "(sum x)"),
    (19, 155, "(length x)"),
    (20, 156, "(head x)"),
    (21, 157, "(fold (lambda (acc item) (+ acc item)) 0 x)"),
    (22, 158, "(fold (lambda (acc item) (+ acc 1)) 0 x)"),
    (23, 159, "(fold (lambda (acc item) (* acc item)) 1 x)"),
    # Chained transformations
    (24, 161, "(reverse (map (lambda (a) (* a 2)) x))"),
    (25, 162, "(map (lambda (a) (* a 2)) (reverse x))"),
    (26, 163, "(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 1)) x))"),
    (27, 164, "(sum (filter (lambda (a) (is_even a)) x))"),
]

consts = [0, 1, 2, -1, 3]
ENUMERATOR_TEMPLATES = []
ENUMERATOR_TEMPLATES.append(("depth=1", 50, "x", "all"))
ENUMERATOR_TEMPLATES.append(("depth=2", 54, "(reverse x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 55, "(tail x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 56, "(head x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 57, "(sum x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 58, "(length x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 60, "(map (lambda (a) (inc a)) x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 61, "(map (lambda (a) (dec a)) x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 62, "(map (lambda (a) (neg a)) x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 63, "(filter (lambda (a) (is_even a)) x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 64, "(filter (lambda (a) (is_odd a)) x)", "list"))
for k in consts:
    ENUMERATOR_TEMPLATES.append(("depth=2 (k-loop)", 68, f"(map (lambda (a) (+ a {k})) x)", "list"))
    ENUMERATOR_TEMPLATES.append(("depth=2 (k-loop)", 69, f"(map (lambda (a) (- a {k})) x)", "list"))
    ENUMERATOR_TEMPLATES.append(("depth=2 (k-loop)", 70, f"(map (lambda (a) (* a {k})) x)", "list"))
    ENUMERATOR_TEMPLATES.append(("depth=2 (k-loop)", 71, f"(filter (lambda (a) (gt a {k})) x)", "list"))
    ENUMERATOR_TEMPLATES.append(("depth=2 (k-loop)", 72, f"(filter (lambda (a) (lt a {k})) x)", "list"))
    ENUMERATOR_TEMPLATES.append(("depth=2 (k-loop)", 73, f"(filter (lambda (a) (eq a {k})) x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 76, "(fold (lambda (acc item) (+ acc item)) 0 x)", "list"))
ENUMERATOR_TEMPLATES.append(("depth=2", 77, "(fold (lambda (acc item) (* acc item)) 1 x)", "list"))
for k in (1, 2):
    ENUMERATOR_TEMPLATES.append(("depth=3 (k-loop)", 82, f"(reverse (map (lambda (a) (+ a {k})) x))", "list"))
    ENUMERATOR_TEMPLATES.append(("depth=3 (k-loop)", 83, f"(sum (map (lambda (a) (+ a {k})) x))", "list"))
    ENUMERATOR_TEMPLATES.append(("depth=3 (k-loop)", 84, f"(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a {k})) x))", "list"))
for k in consts:
    ENUMERATOR_TEMPLATES.append(("int (k-loop)", 88, f"(+ x {k})", "int"))
    ENUMERATOR_TEMPLATES.append(("int (k-loop)", 89, f"(- x {k})", "int"))
    ENUMERATOR_TEMPLATES.append(("int (k-loop)", 90, f"(* x {k})", "int"))
ENUMERATOR_TEMPLATES.append(("int", 91, "(inc x)", "int"))
ENUMERATOR_TEMPLATES.append(("int", 92, "(dec x)", "int"))
ENUMERATOR_TEMPLATES.append(("int", 93, "(neg x)", "int"))

# Load all benchmark tasks
bench_files = [
    "benchmarks/dev_train.json",
    "benchmarks/dev_eval.json",
    "benchmarks/held_out_test.json",
    "benchmarks/list_functions.json",
    "benchmarks/families/list_mapping.json",
    "benchmarks/families/list_filtering.json",
    "benchmarks/families/list_reduction.json",
    "benchmarks/families/list_structural.json",
    "benchmarks/families/list_composition.json",
]

all_tasks = []
for bf in bench_files:
    data = json.loads((REPO_ROOT / bf).read_text(encoding="utf-8"))
    for t in data["tasks"]:
        all_tasks.append({
            "file": bf,
            "task_id": t["task_id"],
            "task_family": t.get("task_family", data.get("family_id", "unknown")),
            "reference_program": t["reference_program"],
            "visible_examples": t["visible_examples"],
            "hidden_tests": t.get("hidden_tests", []),
        })


def check_matches(code_str: str):
    exact_matches = []
    semantic_matches = []
    for t in all_tasks:
        if t["reference_program"] == code_str:
            exact_matches.append(f"{t['file']}::{t['task_id']}")
        else:
            # Check semantic equivalence on all visible + hidden examples
            all_ex = t["visible_examples"] + t["hidden_tests"]
            if all_ex:
                ok = True
                for ex in all_ex:
                    try:
                        out = interp.run(code_str, ex["input"], timeout_seconds=0.2)
                        if out != ex["output"] or type(out) is not type(ex["output"]):
                            ok = False
                            break
                    except Exception:
                        ok = False
                        break
                if ok:
                    semantic_matches.append(f"{t['file']}::{t['task_id']} (ref: {t['reference_program']})")
    return exact_matches, semantic_matches


output = {
    "generator_templates": [],
    "enumerator_templates": [],
    "benchmark_task_coverage": [],
}

for idx, line_no, code in GENERATOR_TEMPLATES:
    exact, sem = check_matches(code)
    output["generator_templates"].append({
        "index": idx,
        "line": line_no,
        "code": code,
        "exact_matches": exact,
        "semantic_matches": sem,
    })

for idx, (cat, line_no, code, dom) in enumerate(ENUMERATOR_TEMPLATES, 1):
    exact, sem = check_matches(code)
    output["enumerator_templates"].append({
        "index": idx,
        "category": cat,
        "line": line_no,
        "domain": dom,
        "code": code,
        "exact_matches": exact,
        "semantic_matches": sem,
    })

gen_codes = {c for _, _, c in GENERATOR_TEMPLATES}
enum_all_codes = {c for _, _, c, _ in ENUMERATOR_TEMPLATES}
enum_top30_list = [c for _, _, c, dom in ENUMERATOR_TEMPLATES if dom in ("all", "list")][:30]
enum_top32_list = [c for _, _, c, dom in ENUMERATOR_TEMPLATES if dom in ("all", "list")][:32]

for t in all_tasks:
    ref = t["reference_program"]
    in_gen_exact = ref in gen_codes
    in_enum_exact = ref in enum_all_codes
    in_enum_top32 = ref in enum_top32_list
    # Also check semantic match in generator or enumerator
    gen_sem = []
    for _, _, gc in GENERATOR_TEMPLATES:
        all_ex = t["visible_examples"] + t["hidden_tests"]
        try:
            if all(interp.run(gc, ex["input"], timeout_seconds=0.2) == ex["output"] for ex in all_ex):
                gen_sem.append(gc)
        except Exception:
            pass
    enum_sem = []
    for _, _, ec, dom in ENUMERATOR_TEMPLATES:
        if dom not in ("all", "list"):
            continue
        all_ex = t["visible_examples"] + t["hidden_tests"]
        try:
            if all(interp.run(ec, ex["input"], timeout_seconds=0.2) == ex["output"] for ex in all_ex):
                enum_sem.append(ec)
        except Exception:
            pass
    output["benchmark_task_coverage"].append({
        "file": t["file"],
        "task_id": t["task_id"],
        "reference_program": ref,
        "in_generator_exact": in_gen_exact,
        "in_enumerator_exact": in_enum_exact,
        "in_enumerator_top32": in_enum_top32,
        "generator_semantic_matches": gen_sem,
        "enumerator_semantic_matches": enum_sem,
    })

out_path = Path(__file__).resolve().parent / "template_leakage_audit.json"
out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
print("Wrote", out_path)
