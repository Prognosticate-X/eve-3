"""Phase 1 Empirical Audit Verification Script (Read-only against eve-3)."""
import itertools
import json
import math
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eve3.config import EveConfig
from eve3.dsl.interpreter import DSLInterpreter, ExecutionTimeoutError, SExprParser
from eve3.models import CandidateProgram, LearnedAbstraction
from eve3.system1_proposer.generator import HypothesisGenerator
from eve3.system1_proposer.sandbox import ProgramSandbox
from eve3.system2_falsifier.bayesian_prober import BayesianProber, entropy, renormalize
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus
from eve3.system2_falsifier.smt_distinguisher import SMTDistinguisher, SMTSupportLevel
from eve3.system3_crystallizer.library import KnowledgeLibrary
from eve3.system3_crystallizer.value_compressor import CandidateAbstraction, ValueCompressor
from eve3.discovery.tree import DiscoveryTree, ReplaySimulator
from eve3.discovery.policy import ExplorationPolicy
from eve3.plasticity.adapter_bank import AdapterBank
from eve3.plasticity.regression_gate import RegressionGate, RegressionGateConfig
from eve3.search.controller import SearchController

prober = BayesianProber()

print("=== H3: Exact check where p_long MATCHES and p_short is FALSIFIED ===")
p_short = CandidateProgram("x")  # DL=1
# Construct p_long with DL=22 that evaluates [1, 2] -> [2, 3]:
p_long = CandidateProgram("(reverse (reverse (reverse (reverse (reverse (reverse (map (lambda (a) (+ a 1)) (reverse (reverse (reverse (reverse (reverse (reverse (reverse (reverse (reverse (reverse x)))))))))))))))))")
print(f"  p_short DL={p_short.description_length}, p_long DL={p_long.description_length}")
print(f"  p_short([1, 2])={p_short.evaluate([1, 2])}, p_long([1, 2])={p_long.evaluate([1, 2])}")
b_asym = prober.initialize_beliefs([p_short, p_long])
print(f"  Initial MDL beliefs: b_short={b_asym[0]:.8f}, b_long={b_asym[1]:.8f}")
b_asym_post = prober.update_beliefs([p_short, p_long], b_asym, probe_input=[1, 2], observed_output=[2, 3])
print(f"  After probe [1,2]->[2,3] (p_short FALSIFIED, p_long MATCHES): b_short={b_asym_post[0]:.8f}, b_long={b_asym_post[1]:.8f}")
print(f"  Falsified p_short remains top-1: {b_asym_post[0] > b_asym_post[1]} (and b_short > 1e-4 so not pruned in CEGIS!)")

print("\n=== H5: SMT Distinguisher Coverage & Scaling (k=5, 10, 20, 40) ===")
dist = SMTDistinguisher()
import z3
for code in [
    "(+ x 1)",
    "(eq x 1)",
    "(gt x 0)",
    "(length x)",
    "(tail x)",
    "(head x)",
    "(reverse x)",
    "(map (lambda (a) (+ a 1)) x)",
    "(filter (lambda (a) (gt a 0)) x)",
    "(fold (lambda (acc a) (+ acc a)) 0 x)",
]:
    ast_node = SExprParser.parse(code)
    supp, reason = dist.check_ast_support(ast_node)
    z3_int = dist._ast_to_z3_int(ast_node, z3.Int("x"), z3)
    seq_sort = z3.SeqSort(z3.IntSort())
    z3_seq = dist._ast_to_z3_seq(ast_node, z3.Const("x_seq", seq_sort), z3, seq_sort)
    print(f"  {code:38s} | check_ast_support={supp.value:15s} | _ast_to_z3_int={z3_int is not None!s:5s} | _ast_to_z3_seq={z3_seq is not None!s:5s}")

p_test1 = CandidateProgram("(+ x 1)")
p_test2 = CandidateProgram("(+ x 2)")
probe_test = dist.find_distinguishing_input(p_test1, p_test2)
print(f"  (+ x 1) vs (+ x 2) find_distinguishing_input: {probe_test!r} (Z3 crashed with m[x]=None and fell back to heuristic!)")

for k in [5, 10, 20, 40]:
    # Use (* x i) + i so x appears non-trivially in Z3 model, plus (+ x i) via find_distinguishing_input
    int_cands = [CandidateProgram(f"(+ (* x {i+1}) {i})") for i in range(k)]
    t0 = time.perf_counter()
    pairs = list(itertools.combinations(int_cands, 2))
    sat_count = 0
    for c1, c2 in pairs:
        res = dist._z3_solve_integer_distinguishing(c1, c2, timeout_ms=500)
        if res is not None:
            sat_count += 1
    dt_ms = (time.perf_counter() - t0) * 1000.0
    list_cands = [CandidateProgram(f"(map (lambda (a) (+ a {i})) x)") for i in range(k)]
    t1 = time.perf_counter()
    for c1, c2 in itertools.combinations(list_cands, 2):
        dist.find_distinguishing_input(c1, c2, timeout_ms=500)
    dt_list_ms = (time.perf_counter() - t1) * 1000.0
    print(f"  k={k:2d} ({len(pairs):3d} pairs): int_Z3={dt_ms:7.2f}ms (sat={sat_count}/{len(pairs)}), list_find_dist={dt_list_ms:7.2f}ms")

print("\n=== H11: Sandbox Timeout & Resource Bypass Checks ===")
interp = DSLInterpreter()
# Test ThreadPoolExecutor timeout blocking behavior:
# Create a slow fold that takes ~80ms (under 20000 steps), with timeout_seconds=0.001 (1ms)
big_list = list(range(3000))
t0 = time.perf_counter()
try:
    interp.run("(map (lambda (a) (+ a 1)) x)", big_list, timeout_seconds=0.0001, step_budget=100000)
except ExecutionTimeoutError:
    elapsed = (time.perf_counter() - t0) * 1000.0
    print(f"  Timeout set to 0.1ms (0.0001s), actual wall-clock wait: {elapsed:.2f}ms (ThreadPoolExecutor.__exit__ waits for worker thread!)")

# Fold repeated squaring: (fold (lambda (acc item) (* acc acc)) 10 x) with len(x)=14 -> 10^(2^14) in only 72 steps!
fold_power = "(fold (lambda (acc item) (* acc acc)) 10 x)"
res_tower = interp.run(fold_power, list(range(14)), timeout_seconds=1.0, step_budget=100)
print(f"  Fold repeated squaring: input len=14, step_budget=100 -> result bit_length={res_tower.bit_length()} bits in <100 steps!")

# Fold list doubling: (fold (lambda (acc item) (concat acc acc)) [1] x) with len(x)=20 -> 2^20 = 1,048,576 elements in ~100 steps!
fold_bomb = "(fold (lambda (acc item) (concat acc acc)) [1] x)"
t0 = time.perf_counter()
res_bomb = interp.run(fold_bomb, list(range(20)), timeout_seconds=2.0, step_budget=500)
dt_bomb = (time.perf_counter() - t0) * 1000.0
print(f"  Fold memory bomb: input len=20, step_budget=500 -> output list length={len(res_bomb)} in {dt_bomb:.1f}ms!")

print("\n=== H12: ValueCompressor Exhaustive vs Greedy & Submodularity Test ===")
vc = ValueCompressor(gamma=1.2)
# Check how many patterns apply_compression actually supports:
# Lines 37-64 of value_compressor.py ONLY support 4 hardcoded patterns!
dyn_progs = [
    {"code": "(filter (lambda (a) (lt a 5)) x)", "reuse_count": 2, "task_family": "f1"},
    {"code": "(filter (lambda (a) (lt a 10)) x)", "reuse_count": 2, "task_family": "f2"},
]
mined = vc.extract_candidate_abstractions(dyn_progs)
for m in mined:
    _, sav = m.apply_compression("(filter (lambda (a) (lt a 5)) x)")
    print(f"  Mined candidate: {m.name:10s} pattern={m.pattern:38s} cost={m.cost} -> actual savings on matching prog={sav}")

# Small-scale exhaustive search (8 candidate abstractions) vs greedy:
# Let's construct 8 candidate abstractions (including overlapping patterns supported by apply_compression):
cands_8 = [
    CandidateAbstraction("c1_map_add", "(map (lambda (a) (+ a $k)) x)", 2, 2),
    CandidateAbstraction("c2_rev_map_add", "(reverse (map (lambda (a) (+ a $k)) x))", 2, 2),
    CandidateAbstraction("c3_filter_gt", "(filter (lambda (a) (gt a $k)) x)", 2, 2),
    CandidateAbstraction("c4_map_mul", "(map (lambda (a) (* a $k)) x)", 2, 2),
    CandidateAbstraction("c5_map_add_dup", "(map (lambda (a) (+ a $k)) x)", 2, 3),
    CandidateAbstraction("c6_filter_lt_unsupported", "(filter (lambda (a) (lt a $k)) x)", 2, 2),
    CandidateAbstraction("c7_rev_map_add_expensive", "(reverse (map (lambda (a) (+ a $k)) x))", 2, 4),
    CandidateAbstraction("c8_map_mul_expensive", "(map (lambda (a) (* a $k)) x)", 2, 5),
]
progs_test = [
    {"code": "(reverse (map (lambda (a) (+ a 1)) x))", "reuse_count": 1, "task_family": "f1"},
    {"code": "(reverse (map (lambda (a) (+ a 2)) x))", "reuse_count": 1, "task_family": "f1"},
    {"code": "(filter (lambda (a) (gt a 3)) x)", "reuse_count": 0, "task_family": "f2"},
]
weights_test = [vc.calculate_program_weight(p) for p in progs_test]

# Check diminishing returns (submodularity):
# Let A = [], B = [c1_map_add], x = c2_rev_map_add (where A subset B, x not in B):
# Submodularity requires: f(A + [x]) - f(A) >= f(B + [x]) - f(B)
# Wait: what if A = [], B = [c1_map_add]?
# f([]) = 0
# f([c2_rev_map_add]) = w0*6 + w1*6 = 20.318
# f([c1_map_add]) = w0*4 + w1*4 = 13.545
# f([c1_map_add, c2_rev_map_add]) = 13.545 (because c1 already rewrote "(map (lambda (a) (+ a 1)) x)" into "(c1_map_add 1 x)", destroying the match for c2!)
# Even worse: what if Greedy picks c1 first (Suppose c1 has slightly lower cost or higher gain on another program)?
progs_sub = [
    {"code": "(reverse (map (lambda (a) (+ a 1)) x))", "reuse_count": 0, "task_family": "f1"},
    {"code": "(reverse (map (lambda (a) (+ a 2)) x))", "reuse_count": 0, "task_family": "f1"},
    {"code": "(map (lambda (a) (+ a 3)) x)", "reuse_count": 0, "task_family": "f1"},
]
w_sub = [vc.calculate_program_weight(p) for p in progs_sub]
# On progs_sub:
# c1_map_add (cost=2): saves 4 on prog1, 4 on prog2, 4 on prog3 -> Benefit = 12, Net = 12 - 1.2*2 = 9.6
# c2_rev_map_add (cost=2): saves 6 on prog1, 6 on prog2, 0 on prog3 -> Benefit = 12, Net = 12 - 1.2*2 = 9.6
# If c1 has cost=1 and c2 has cost=2:
c1 = CandidateAbstraction("c1_map_add", "(map (lambda (a) (+ a $k)) x)", 2, 2)
c2 = CandidateAbstraction("c2_rev_map_add", "(reverse (map (lambda (a) (+ a $k)) x))", 2, 1)
# Look at monotonicity violation if we evaluate [c1, c2] vs [c2, c1]:
print(f"  f([c1])={vc.compute_weighted_benefit([c1], progs_sub, w_sub):.2f}, f([c2])={vc.compute_weighted_benefit([c2], progs_sub, w_sub):.2f}")
print(f"  f([c1, c2])={vc.compute_weighted_benefit([c1, c2], progs_sub, w_sub):.2f} vs f([c2, c1])={vc.compute_weighted_benefit([c2, c1], progs_sub, w_sub):.2f}")

# Suppose c1 has gain 12 - 1.2*2 = 9.6, and c2 on 2 programs has gain 6*1.9 - 1.2*2 = 9.0:
progs_greedy_subopt = [
    {"code": "(reverse (map (lambda (a) (+ a 1)) x))", "reuse_count": 0, "task_family": "f1"},
    {"code": "(reverse (map (lambda (a) (+ a 2)) x))", "reuse_count": 0, "task_family": "f1"},
    {"code": "(map (lambda (a) (+ a 3)) x)", "reuse_count": 0, "task_family": "f1"},
]
# With w = [0.95, 0.95, 1.0]:
# c1 alone: 4*(0.95 + 0.95 + 1.0) = 11.6. With cost=2, gamma=1.2 -> net = 11.6 - 2.4 = 9.2
# c2 alone: 6*(0.95 + 0.95) = 11.4. With cost=2, gamma=1.2 -> net = 11.4 - 2.4 = 9.0
# Greedy picks c1 FIRST (9.2 > 9.0)!
# Then in step 2 of Greedy, remaining = [c2]. Greedy evaluates candidate_lib = [c1, c2]!
# Because c1 is applied FIRST in compute_weighted_benefit([c1, c2]), c1 rewrites prog1 and prog2 to "(reverse (c1 1 x))",
# so c2 gets ZERO savings on prog1 and prog2!
# Thus Greedy stops with [c1] (net objective = 9.2),
# whereas [c2, c1] (if c2 is applied first on prog1, prog2 giving 11.4, and c1 is applied on prog3 giving 4.0) has total benefit 15.4, net objective = 15.4 - 4.8 = 10.6!
vc_custom = ValueCompressor(gamma=1.2)
w_custom = [0.95, 0.95, 1.0]
for perm in [[c1], [c2], [c1, c2], [c2, c1]]:
    ben = vc_custom.compute_weighted_benefit(perm, progs_greedy_subopt, w_custom)
    cost = sum(a.cost for a in perm) * vc_custom.gamma
    print(f"  Library {[a.name for a in perm]}: Benefit={ben:.2f}, CostPenalty={cost:.2f}, NetObj={ben - cost:.2f}")

print("\n=== H13: Positive Feedback Lock-in Simulation ===")
# Early accidental abstraction A_early (saves 4 AST nodes, e.g., map_add) gets reused N times -> reuse_count grows.
# Later better abstraction A_better (saves 6 AST nodes across 2 programs, reuse_count=0).
for reuse_early in [0, 5, 20, 100]:
    p_early = {"code": "(map (lambda (a) (+ a 1)) x)", "reuse_count": reuse_early, "task_family": "f1"}
    p_better = {"code": "(reverse (map (lambda (a) (+ a 1)) x))", "reuse_count": 0, "task_family": "f1"}
    w_e = vc.calculate_program_weight(p_early)
    w_b = vc.calculate_program_weight(p_better)
    print(f"  reuse_early={reuse_early:3d} -> w_early={w_e:.3f} (4*w_e={4*w_e:.2f}) vs w_better={w_b:.3f} (6*w_b={6*w_b:.2f})")

print("\n=== H14: Prompt Length Growth Curve with Library Size ===")
gen = HypothesisGenerator()
examples_h14 = [([1, 2], [2, 3])]
for n_ops in [0, 5, 10, 25, 50, 100]:
    ops = [{"operator_name": f"op_crystallized_{i}", "arity": 2} for i in range(n_ops)]
    prompt = gen.build_prompt(examples_h14, crystallized_operators=ops)
    raw_cands = gen._heuristic_synthesizer(examples_h14, crystallized_operators=ops, max_candidates=10)
    print(f"  n_ops={n_ops:3d} -> prompt_chars={len(prompt):5d}, raw_cands_count={len(raw_cands)}, base_templates_displaced={sum(1 for c in raw_cands if 'op_crystallized_' in c)}/{len(raw_cands)}")

print("\n=== H16: DiscoveryTree Replay Out-of-Support Policy ===")
tree = DiscoveryTree("task_replay")
r_id = tree.add_node("propose", {"code": "x"}, cost=1.0)
p_id = tree.add_node("probe", {"probe": [1]}, parent_id=r_id, cost=0.5)
# Note: NO verify node in tree, or policy wants an action not in tree
sim = ReplaySimulator(tree)
res_unverified_tree = sim.evaluate_policy(ExplorationPolicy())
print(f"  Tree without verify node -> simulator output: {res_unverified_tree}")

print("\n=== H17 & H18: Policy/Gate mutability & AdapterBank/Controller execution ===")
gate = RegressionGate()
print(f"  Gate config before mutation: max_family_regression_pct={gate.config.max_family_regression_pct}")
gate.config.max_family_regression_pct = 99.0
print(f"  Gate config after runtime mutation: max_family_regression_pct={gate.config.max_family_regression_pct} (mutable dataclass!)")
