# EVE-3: Neurosymbolic AGI Architecture

> **A closed-loop cognitive architecture combining Hypothesis Proposal, Bayesian Active Falsification, and Value-Weighted Knowledge Crystallization.**

<p align="center">
  <b>English</b> • <a href="README_zh.md">简体中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Active%20Research-orange.svg" alt="Status: Active Research" />
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" />
  <img src="https://img.shields.io/badge/python-3.10+-brightgreen.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Apple%20Silicon-M--series%20Optimized-black.svg" alt="Apple Silicon Optimized" />
</p>

---

> [!NOTE]
> **Project Status: Active Research**  
> This repository represents an ongoing, active foundational research project exploring neurosymbolic AGI algorithms. Algorithms, domain-specific languages (DSLs), active probers, and system interfaces are undergoing rapid iterative experimentation.

---

## 🔬 1. Core Thesis & Research Motivation

Modern Large Language Models (LLMs) operate primarily via massive passive pattern matching and unguided stochastic next-token generation. However, achieving genuine autonomous general intelligence (AGI) requires an active scientific discovery loop:

$$\text{Hypothesis Generation} \xrightarrow{\quad} \text{Active Falsification} \xrightarrow{\quad} \text{Knowledge Crystallization}$$

EVE-3 explores a central, testable research question:

> **Does a closed-loop "Propose $\to$ Falsify $\to$ Crystallize" architecture achieve significantly higher sample efficiency and cross-task generalization than unguided generation or passive few-shot learning within a resource-bounded laptop environment?**

Rather than tackling unconstrained continuous multi-modal domains upfront, EVE-3 grounds this question in **Neurosymbolic Program Synthesis**—a domain where program behaviors are exact, verifiably falsifiable, and capable of symbolic reuse.

---

## 🏛️ 2. Tri-System Cognitive Architecture

EVE-3 decomposes the discovery and synthesis loop into three mathematically grounded systems:

```
                  +-----------------------------------+
                  |      Task / I-O Examples          |
                  +-----------------+-----------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|  System 1: Intuition & Hypothesis Proposer                             |
|  - Local LLM (MLX + Qwen2.5-Coder-3B-Instruct) / Heuristic Generator   |
|  - Fast Sandbox Filtering (Syntax & Visible Example Compliance)        |
+-----------------------------------+-----------------------------------+
                                    | Candidate Programs H = {P_1, ... P_k}
                                    v
+-----------------------------------------------------------------------+
|  System 2: Bayesian Active Falsification Engine                       |
|  - SMT Solver (Z3) Pairwise Distinguishing Probe Synthesis            |
|  - Closed-form Information Gain: IG(x) = H(b) - \sum q_v H(b|G_v)     |
|  - Active Environment Query -> Bayesian Posterior Update              |
+-----------------------------------+-----------------------------------+
                                    | Verified Robust Program P*
                                    v
+-----------------------------------------------------------------------+
|  System 3: Knowledge Crystallization & Library Learning               |
|  - SQLite Persistent Storage of Operators & Verified Programs         |
|  - Value-Weighted Abstraction Mining: Benefit_w(L) - \gamma |L|       |
|  - Operator Promotion back into System 1 Prompt / Primitives          |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|  Discovery Tree & Replay Simulator (RSI Layer)                        |
|  - Tree-structured exploration history recording                      |
|  - Counterfactual policy evaluation at near-zero marginal cost        |
+-----------------------------------------------------------------------+
```

### System 1: Intuition Proposer (`eve3/system1_proposer`)
- Employs local quantized small language models (e.g., `Qwen2.5-Coder-3B-Instruct` 4-bit running on Apple Silicon unified memory via `mlx-lm`) as an intuition generator.
- Generates candidate DSL programs consistent with visible examples without requiring expensive full-scale fine-tuning.
- Sandboxed execution isolates candidates, catching syntax errors and infinite loops before deep verification.

### System 2: Bayesian Active Falsifier (`eve3/system2_falsifier`)
- Formalizes verification as **Counterexample-Guided Inductive Synthesis (CEGIS)** and **Generalized Binary Search**.
- Generates precise distinguishing inputs $x$ where $P_i(x) \neq P_j(x)$ using an SMT solver (Z3), avoiding blind random sampling.
- Selects the probe maximizing **closed-form Mutual Information (Information Gain)**:
  $$IG(x) = H(b) - \sum_{v \in \mathcal{V}(x)} q_v(x) \cdot H\big(b \mid G_v(x)\big)$$
- Updates Bayesian posterior beliefs with Laplace smoothing and hypothesis collapse protection.

### System 3: Knowledge Crystallizer (`eve3/system3_crystallizer`)
- Automatically discovers shared structural sub-expressions across verified programs.
- Implements a **Value-Weighted Submodular Optimization Objective**:
  $$\mathcal{L}^* = \arg\max_{\mathcal{L} \subseteq \text{Candidates}} \Big[ \sum_{i=1}^N w_i \cdot \big(\text{DL}(P_i \mid \varnothing) - \text{DL}(P_i \mid \mathcal{L})\big) - \gamma \cdot \text{Cost}(\mathcal{L}) \Big]$$
  where program weights $w_i = |\text{TaskFamilies}(P_i)| \times (1 + \ln(1 + \text{ReuseCount}_i))$ prioritize abstractions that generalize across disparate task families.
- Stores verified programs, operators, and metadata in a zero-maintenance local SQLite database.

---

## 🔄 3. Recursive Self-Improvement (RSI) via Discovery Trees

In line with recent breakthroughs in recursive self-improvement (*Dream-RSI*, arXiv:2609.14858; *The Last AI Built by Humans*, arXiv:2609.11873):

- **Trajectories are assets, not ephemeral logs**: Exploration histories are structured as directed trees (`DiscoveryTree`).
- **Zero-Marginal-Cost Policy Simulation**: In program synthesis and scientific discovery, program execution and environment evaluation represent the principal bottleneck. Historical discovery trees serve as an offline **Replay Simulator**, enabling the system to evaluate alternative exploration heuristics counterfactually without invoking expensive models or evaluators.

---

## 🛡️ 4. Multi-Timescale Plasticity & Regression Gatekeeper

Following our pre-registered protocol ([`docs/PREREGISTRATION.md`](docs/PREREGISTRATION.md)), parameter adaptability and continual learning follow a multi-timescale hierarchy rather than fragile online SGD:

- **T0 (Immediate)**: In-context retrieval from persistent SQLite symbolic library (`KnowledgeLibrary`).
- **T1 (Consolidation)**: Offline "sleep" phase LoRA fine-tuning (`Consolidator`) with value-weighted replay:
  $$p(i) \propto w_i \cdot e^{-\Delta t_i / \tau} \cdot (1 + \text{hardness}_i)$$
- **T2 (Base Merge)**: Long-term periodic weight assimilation following audit approval.
- **Task Family Isolation**: LoRA adapters are compartmentalized by task family (`AdapterBank`) to prevent negative interference.
- **Automated Regression Gate (`RegressionGate`)**: Strictly rejects adapter updates if any historical family regresses $> 2\%$, general non-DSL coding probe score drops $> 3\%$, or false verification rate exceeds $0.0\%$.

---

## 📂 5. Repository Structure

```
eve-3/
├── README.md                          # English project overview & architecture
├── README_zh.md                       # 中文文档与系统架构说明
├── pyproject.toml                     # Python packaging & dependencies
├── requirements.txt                   # Pip dependency requirements
├── LICENSE                            # MIT License
├── docs/
│   ├── ARCHITECTURE.md                # In-depth architectural blueprint
│   ├── AUTONOMOUS_CURRICULUM_RESULTS.md # Phase 7 autonomous curriculum & exploration results
│   ├── CONSOLIDATION.md               # Sleep consolidation & replay gate design
│   ├── CONTINUAL_LEARNING_RESULTS.md  # Continual learning (BWT/FWT) empirical benchmark results
│   ├── EXPERIMENT_RESULTS.md          # 4-Regime empirical benchmark results
│   ├── MATHEMATICS.md                 # Full mathematical formulations & derivations
│   ├── MEMORY_MANAGEMENT_RESULTS.md   # Phase 8 tiered memory & retention decay results
│   ├── PREREGISTRATION.md             # Formal preregistered metrics and acceptance criteria
│   ├── ROADMAP.md                     # Phased experimental roadmap (Phases 0-11)
│   └── RSI_INTEGRATION.md             # Discovery tree & replay simulator theory
├── eve3/
│   ├── config.py                      # Global configuration & hyperparameters
│   ├── models.py                      # CandidateProgram, VerificationEvidence, LearnedAbstraction, Task
│   ├── dsl/                           # Functional Domain-Specific Language
│   │   ├── ast.py                     # AST nodes, MDL metrics, step limits
│   │   ├── interpreter.py             # Parser & sandboxed execution engine
│   │   └── primitives.py              # Functional primitives (+, -, map, filter, fold, comparisons)
│   ├── system1_proposer/              # Intuition generator & sandbox
│   │   ├── generator.py               # MLX-LM harness & heuristic synthesizer
│   │   └── sandbox.py                 # Candidate program validator
│   ├── system2_falsifier/             # Active Bayesian falsification engine
│   │   ├── bayesian_prober.py         # Shannon entropy, closed-form IG, Laplace update
│   │   ├── smt_distinguisher.py       # Z3 distinguishing probe synthesis & SMT matrix
│   │   └── cegis_loop.py              # CEGIS orchestration loop with honest status
│   ├── system3_crystallizer/          # Knowledge base & library learning
│   │   ├── library.py                 # SQLite persistent storage of learned abstractions
│   │   └── value_compressor.py        # Submodular AST-node MDL value-weighted compression
│   ├── explorer/                      # Autonomous Curriculum & Coverage Guards (Phase 7)
│   │   ├── curriculum.py              # Task generation, ZPD filter [0.2, 0.8], multi-objective scoring
│   │   └── coverage.py                # Clustering entropy H(C), anti-collapse guards, metamorphic validation
│   ├── memory/                        # Tiered Cognitive Memory & Provenance (Phase 8)
│   │   ├── tiers.py                   # Working, Episodic (summarized), and Semantic (Hot/Cold decay) memory
│   │   └── provenance.py              # Provenance event tracking, immutable snapshots, and rollback
│   ├── envs/                          # Discrete & Physical Simulated Environments (Phase 9)
│   │   ├── grid_tasks.py              # L1 ARC-style 2D discrete visual grid transformations & oracles
│   │   └── sim_adapter.py             # L2 continuous 2D planar physics simulation with process/sensor noise
│   ├── safety/                        # Hard Execution Safety & Boundary Enforcement (Phase 9)
│   │   └── action_limiter.py          # ActionLimiter workspace bounds, magnitude clamping, E-stop & human enable
│   ├── discovery/                     # RSI replay engine
│   │   ├── tree.py                    # Causal Discovery Tree & counterfactual simulator
│   │   └── policy.py                  # Versioned exploration policies
│   ├── plasticity/                    # Multi-timescale plasticity & safety gate
│   │   ├── adapter_bank.py            # Isolated LoRA adapter management & rollback
│   │   ├── consolidator.py            # Sleep phase value-weighted replay & training loop
│   │   └── regression_gate.py         # Preregistered regression safety gatekeeper
│   └── search/                        # Multi-strategy search controller
│       ├── controller.py              # Unified neural/symbolic search scheduler
│       └── enumerator.py              # Type-directed symbolic AST enumerator
├── benchmarks/
│   ├── families/                      # Structured benchmark task families
│   │   ├── manifest.json              # Task family index & hold-out declarations
│   │   ├── list_mapping.json          # Mapping family
│   │   ├── list_filtering.json        # Filtering family
│   │   ├── list_reduction.json        # Reduction family
│   │   ├── list_structural.json       # Structural family
│   │   └── list_composition.json      # Strictly held-out composition family (FWT test)
│   ├── general_coding_probe.json      # General non-DSL coding probe (retention test)
│   ├── dev_train.json                 # Training split
│   ├── dev_eval.json                  # In-distribution evaluation split
│   └── held_out_test.json             # Held-out generalization split
├── experiments/
│   ├── run_autonomous_curriculum.py   # Autonomous curriculum benchmark runner (Arm A5 vs A4)
│   ├── run_continual_learning.py      # Continual learning (BWT/FWT) benchmark runner
│   ├── run_env_simulation.py          # Phase 9 L1/L2 simulation & statistical falsification runner
│   ├── run_full_ablation.py           # 4-regime ablation benchmark runner
│   ├── run_library_ablation.py        # Library reuse ablation runner
│   ├── run_memory_consolidation.py    # Tiered memory & retention decay benchmark runner
│   └── run_policy_evolution.py        # Policy replay & held-out correlation runner
├── tests/                             # 68 rigorous test suites (100% passing)
```

---

## ⚡ 6. Quickstart

### Installation
```bash
git clone https://github.com/Prognosticate-X/eve-3.git
cd eve-3
pip install -e .
```

### Running Test Suite
Compatible with both standard library `unittest` and `pytest`:

```bash
# Run via standard library unittest discover
python3 -m unittest discover -s tests -p "test_*.py"

# Or run via pytest
pytest tests/
```

### Running an Active Synthesis Experiment
```python
from eve3.config import EveConfig
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus

# Ground-truth oracle function
def oracle(lst):
    return [x + 1 for x in lst]

# Execute active CEGIS loop with held-out validation
config = EveConfig(max_falsification_rounds=5)
loop = CEGISLoop(config)
result = loop.run_synthesis(
    initial_examples=[([1, 2], [2, 3])],
    oracle_fn=oracle,
    held_out_tests=[([10, 20], [11, 21]), ([-5, 0], [-4, 1])],
)

print(f"Status: {result.status.value}, Converged: {result.converged}")
if result.converged:
    print(f"Synthesized Program: {result.verified_program.code_str}")
    print(f"Held-out Accuracy: {result.held_out_accuracy * 100:.1f}%")
```

---

## 📈 6. Experimental Roadmap

- **Phase 0: Foundations & Substrate** (Completed) — Functional DSL AST, safe interpreter, and benchmark schemas.
- **Phase 1: System 1 Intuition Proposer** (Completed) — Prompt orchestration, MLX Qwen2.5-Coder harness, and sandbox validator.
- **Phase 2: System 2 Active Falsifier** (Completed) — Exact closed-form Information Gain, Z3 SMT distinguishing inputs, and Laplace-smoothed CEGIS loop.
- **Phase 3: System 3 Value-Weighted Crystallizer** (Completed) — SQLite persistent store, task-diversity weighting, and submodular greedy library learning.
- **Phase 4: Closed-Loop Benchmarking** (Completed) — 4-regime baseline ablation with zero false verification rate (0.0%).
- **Phase 5: Preregistration & Safety Gatekeeping** (Completed) — Preregistered metrics frozen (`docs/PREREGISTRATION.md`), task family benchmarks, and `RegressionGate`.
- **Phase 6: Sleep Consolidation & Continual Learning** (Completed) — Multi-timescale LoRA bank, value-weighted replay, zero forgetting (BWT = 0.0%), and forward transfer (FWT = +33.3%).
- **Phase 7: Autonomous Curriculum & Exploration** (Completed) — Self-generating tasks, ZPD learnability filtering [0.2, 0.8], cluster entropy tracking, anti-collapse guards, and metamorphic validation.
- **Phase 8: Tiered Memory Management & Provenance** (Completed) — Working, episodic (lossless summarization), and semantic (Hot/Cold decay) memory with Stitch-style compaction and rollback.
- **Phase 9: Discrete Visualized & Simulated Environments with Statistical Active Falsification under Noise** (Completed) — L1 ARC-style grid perception, L2 continuous 2D planar physics, ActionLimiter safety layer (0.00% penetrations), tempered posterior $b_T(h)$, diffuse null hypothesis $h_\varnothing$, SPRT hypothesis testing, and calibrated posterior (ECE = 0.0200 <= 0.05).
- **Phase 10: End-to-End Autonomous AGI Loop & Continual Self-Evolution** (Next) — Closed-loop integration across all multi-modal perception, simulation, tiered memory, and autonomous curriculum layers.

---

## 📚 7. Key References & Literature

1. **Active Learning for Neurosymbolic Program Synthesis** (arXiv:2508.15750) — *Version space splitting and distinguishing query synthesis.*
2. **Dream-RSI: Recursive Self-Improvement through Evolving Worlds** (arXiv:2609.14858, Google × DeepMind × UMD) — *Exploration policy refinement via discovery tree replay simulators.*
3. **The Last AI Built by Humans: Toward Genuine Recursive Self-Improvement** (arXiv:2609.11873) — *RSI formalization and five-stage autonomy roadmap.*
4. **Generalized Binary Search** (Nowak, 2011) — *Information-theoretic sample complexity bounds for version space disambiguation.*
5. **DreamCoder: Bootstrapping inductive program synthesis with wake-sleep library learning** (Ellis et al.) — *Foundational neurosymbolic program synthesis and library learning.*
6. **Stitch: Top-Down Synthesis for Library Learning** (Bowers et al., arXiv:2211.16605) — *Scalable AST compression and abstraction extraction.*

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
