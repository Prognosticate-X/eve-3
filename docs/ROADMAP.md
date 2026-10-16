# EVE-3 Implementation Roadmap & Milestones

This roadmap outlines the phased execution strategy for EVE-3, designed for rapid empirical validation on a single MacBook M1 Max (32GB Unified Memory).

---

## Phase Overview

```
Phase 0: Foundations (DSL, Interpreter, Benchmark Schemas)
   │
   ▼
Phase 1: System 1 (Hypothesis Generator & Sandbox Runner)
   │
   ▼
Phase 2: System 2 (Bayesian Active Falsifier & SMT Prober)
   │
   ▼
Phase 3: System 3 (SQLite Knowledge Base & Value-Weighted Library)
   │
   ▼
Phase 4: Closed-Loop Benchmarking & Comparative Ablation
   │
   ▼
Phase 5: Cross-Domain Downstream Transfer (Agent Rules & Heuristics)
```

---

## Detailed Phases

### Phase 0: Foundations & Substrate
- [x] Functional S-expression DSL AST (`ast.py`).
- [x] Sandboxed interpreter with timeout and recursion control (`interpreter.py`).
- [x] Core functional primitives (arithmetic, comparisons, lists, higher-order functions).
- [x] Structured benchmark task definition schema (`benchmarks/list_functions.json`).
- **Milestone Criteria**: Executing arbitrary DSL AST strings safely within specified resource bounds.

### Phase 1: System 1 Intuition Proposer
- [x] Prompt construction with primitive signatures and input-output demonstrations.
- [x] MLX Qwen2.5-Coder integration harness for Apple Silicon.
- [x] Multi-candidate sandbox verification filtering syntax and execution errors.
- **Milestone Criteria**: Generating at least one valid candidate program matching visible examples for seed tasks.

### Phase 2: System 2 Active Falsification Engine
- [x] Exact Shannon entropy and closed-form Mutual Information calculation (`bayesian_prober.py`).
- [x] Distinguishing input generation via Z3 SMT solver and boundary fuzzing (`smt_distinguisher.py`).
- [x] Bayesian posterior update with Laplace smoothing and hypothesis collapse protection.
- [x] Counterexample-Guided Inductive Synthesis (CEGIS) loop coordinator (`cegis_loop.py`).
- **Milestone Criteria**: Demonstrating that active Bayesian probe selection requires significantly fewer samples to converge than unguided random testing.

### Phase 3: System 3 Crystallization & Operator Library
- [x] SQLite persistent schema for verified programs, operators, and discovery runs (`library.py`).
- [x] Value-weighted abstraction mining formula integrating task-family diversity (`value_compressor.py`).
- [x] Submodular greedy library selection algorithm.
- [ ] Direct Python bindings to Stitch / e-graphs for large-scale AST anti-unification.
- **Milestone Criteria**: Library automatically abstracts recurring patterns into parameterizable operators without exponential library bloat.

### Phase 4: Closed-Loop Evaluation & Ablation Study
- [ ] Run benchmark evaluation across 3 experimental regimes:
  1. **Full EVE-3**: Hypothesis Proposal + Bayesian Active Falsification + Crystallized Library Reuse.
  2. **No-Crystallization Baseline**: Proposal + Active Falsification, but starting from scratch on each task.
  3. **No-Falsification Baseline**: Accepts the first candidate passing visible examples (overfitting prone).
- [ ] Measure core metrics:
  - Sample Efficiency (probes required to reach 100% hidden test accuracy).
  - Generalization Rate on held-out tasks.
  - Library Reuse Ratio.
  - Convergence curve of library size vs. task count.

### Phase 5: Cross-Domain Transfer (Downstream Applications)
- [ ] Apply the verified "Hypothesis-Falsify-Crystallize" loop to agent prompt/parameter tuning and rule discovery in production workflows.
- [ ] Evaluate off-policy trajectory replaying for autonomous coding agents.
