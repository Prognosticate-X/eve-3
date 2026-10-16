# EVE-3: Neurosymbolic AGI Architecture

> **A closed-loop cognitive architecture combining Hypothesis Proposal, Bayesian Active Falsification, and Value-Weighted Knowledge Crystallization.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![Hardware: Apple Silicon](https://img.shields.io/badge/optimized%20for-Apple%20Silicon%20(M--series)-black.svg)](https://github.com/ml-explore/mlx)

---

## 🔬 Core Thesis & Motivation

Modern Large Language Models (LLMs) rely predominantly on massive pre-training corpora and unguided generation. However, achieving general intelligence in open-ended and symbolic domains requires an active scientific loop:

$$\text{Hypothesis Generation} \xrightarrow{\quad} \text{Active Falsification} \xrightarrow{\quad} \text{Knowledge Crystallization}$$

EVE-3 investigates a central empirical question:

> **Does a closed-loop "Propose $\to$ Falsify $\to$ Crystallize" architecture achieve significantly higher sample efficiency and cross-task generalization than unguided generation or passive few-shot learning within a resource-bounded laptop environment?**

---

## 🏛️ Tri-System Architecture

EVE-3 decomposes problem-solving and program synthesis into three cooperating, mathematically principled systems:

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

### 1. System 1: Intuition Proposer (`eve3/system1_proposer`)
- Uses quantized open models (e.g. `Qwen2.5-Coder-3B-Instruct` via Apple Silicon MLX) as a fast, heuristic hypothesis generator.
- Synthesizes candidate programs in a Domain-Specific Language (DSL) satisfying initial visible examples.
- Sandboxed execution isolates candidates to prevent infinite loops and memory exhaustion.

### 2. System 2: Active Bayesian Falsifier (`eve3/system2_falsifier`)
- Operates under Counterexample-Guided Inductive Synthesis (CEGIS).
- Employs an SMT solver (Z3) to systematically synthesize **distinguishing inputs** $x$ where $P_i(x) \neq P_j(x)$ rather than relying on random fuzzing.
- Selects optimal probes by maximizing **exact closed-form Information Gain (Mutual Information)**:
  $$IG(x) = H(b) - \sum_{v} q_v(x) \cdot H\big(b \mid G_v(x)\big)$$
- Updates Bayesian beliefs with Laplace smoothing and hypothesis collapse protection.

### 3. System 3: Knowledge Crystallizer (`eve3/system3_crystallizer`)
- Automatically mines recurring structures from robustly verified programs and abstracts them into parameterizable library operators.
- Implements a **Value-Weighted Submodular Optimization Objective**:
  $$\mathcal{L}^* = \arg\max_{\mathcal{L} \subseteq \text{Candidates}} \Big[ \sum_i w_i \cdot \big(\text{DL}(P_i \mid \varnothing) - \text{DL}(P_i \mid \mathcal{L})\big) - \gamma \cdot \text{Cost}(\mathcal{L}) \Big]$$
  where program weights $w_i = |\text{TaskFamilies}(P_i)| \times (1 + \ln(1 + \text{ReuseCount}_i))$ prioritize cross-domain generalization.
- Persists knowledge into a zero-maintenance, local SQLite database.

---

## 🔄 Recursive Self-Improvement (RSI) via Discovery Trees

Drawing upon insights from *Dream-RSI* (arXiv:2609.14858) and *The Last AI Built by Humans* (arXiv:2609.11873):

- **Exploration trajectories are stored as structured Discovery Trees** rather than unstructured conversational text logs.
- Because evaluating programs against physical or symbolic environments is computationally expensive, **historical discovery trees serve as a Replay Simulator**.
- Alternative exploration policies and prober ranking heuristics can be evaluated offline with **zero marginal evaluation cost**, avoiding repetitive agent calls and mitigating prompt confirmation bias.

---

## 📂 Repository Structure

```
eve-3/
├── README.md                          # Project overview and specifications
├── pyproject.toml                     # Modern package and dependency configuration
├── requirements.txt                   # Direct pip dependencies
├── LICENSE                            # MIT License
├── docs/
│   ├── ARCHITECTURE.md                # System component deep-dive
│   ├── MATHEMATICS.md                 # Full mathematical derivations & proofs
│   ├── ROADMAP.md                     # Phased experimental roadmap (Phases 0-5)
│   └── RSI_INTEGRATION.md             # Discovery tree & replay simulator theory
├── eve3/
│   ├── __init__.py
│   ├── config.py                      # Global configuration settings
│   ├── dsl/                           # Functional Domain-Specific Language
│   │   ├── ast.py                     # AST nodes, MDL metrics, S-expression serializer
│   │   ├── interpreter.py             # S-expression parser and safe runtime
│   │   └── primitives.py              # List, arithmetic, and higher-order operators
│   ├── system1_proposer/              # Intuition engine & LLM harness
│   │   ├── generator.py               # MLX-LM / heuristic proposal generator
│   │   └── sandbox.py                 # Multi-candidate sandbox validator
│   ├── system2_falsifier/             # Active Bayesian falsification engine
│   │   ├── bayesian_prober.py         # Shannon entropy, closed-form IG, Laplace update
│   │   ├── smt_distinguisher.py       # Z3 distinguishing probe synthesis
│   │   └── cegis_loop.py              # CEGIS orchestration loop
│   ├── system3_crystallizer/          # Knowledge base & library learning
│   │   ├── library.py                 # SQLite persistent storage
│   │   └── value_compressor.py        # Submodular value-weighted compression
│   └── discovery/                     # RSI replay engine
│       └── tree.py                    # Structured Discovery Tree & counterfactual simulator
├── benchmarks/
│   └── list_functions.json            # Seed benchmark tasks (mapping, filtering, reductions)
└── tests/
    ├── test_dsl.py                    # AST and parser verification
    ├── test_prober.py                 # Information Gain & Bayesian update tests
    ├── test_crystallizer.py           # SQLite persistence & value weighting tests
    ├── test_discovery_tree.py         # Discovery tree recording and replay tests
    └── test_cegis_loop.py             # End-to-end CEGIS active synthesis tests
```

---

## ⚡ Quickstart

### 1. Installation
Clone repository and install dependencies:

```bash
git clone https://github.com/Prognosticate-X/eve-3.git
cd eve-3
pip install -e .
```

For Apple Silicon MLX and SMT solving support:
```bash
pip install -r requirements.txt
```

### 2. Run Test Suite
Verify that all core subsystems, interpreters, Bayesian probers, and crystallizers pass:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### 3. Basic Usage: Active CEGIS Synthesis

```python
from eve3.config import EveConfig
from eve3.system2_falsifier.cegis_loop import CEGISLoop

# Define ground-truth oracle (e.g. increment all elements)
def oracle(lst):
    return [x + 1 for x in lst]

# Initialize CEGIS Active Synthesis Loop
config = EveConfig(max_falsification_rounds=5)
loop = CEGISLoop(config)

# Run synthesis with minimal initial examples
initial_examples = [([1, 2], [2, 3])]
result = loop.run_synthesis(initial_examples, oracle_fn=oracle)

if result.converged:
    print(f"Synthesized Program: {result.verified_program.code_str}")
    print(f"Rounds: {result.rounds_executed}, Probes: {result.probes_used}")
    print("Generalization Check on [10, 20]:", result.verified_program.evaluate([10, 20]))
```

---

## 📚 Key References & Literature

1. **Active Learning for Neurosymbolic Program Synthesis** (arXiv:2508.15750) — *Version space splitting and distinguishing query synthesis.*
2. **Dream-RSI: Recursive Self-Improvement through Evolving Worlds** (arXiv:2609.14858, Google × DeepMind × UMD) — *Exploration policy refinement via discovery tree replay simulators.*
3. **The Last AI Built by Humans: Toward Genuine Recursive Self-Improvement** (arXiv:2609.11873) — *RSI formalization and five-stage autonomy roadmap.*
4. **Generalized Binary Search** (Nowak, 2011) — *Information-theoretic sample complexity bounds for version space disambiguation.*
5. **DreamCoder: Bootstrapping inductive program synthesis with wake-sleep library learning** (Ellis et al.) — *Foundational neurosymbolic program synthesis and library learning.*
6. **Stitch: Top-Down Synthesis for Library Learning** (Bowers et al., arXiv:2211.16605) — *Scalable AST compression and abstraction extraction.*

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
