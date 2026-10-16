# EVE-3 System Architecture

## 1. Architectural Overview

EVE-3 is structured into three cooperating subsystems designed to establish a closed-loop scientific discovery and program synthesis engine:

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

---

## 2. Component Breakdown

### 2.1 System 1: Intuition Proposer (`eve3/system1_proposer`)
- **Role**: Explores the infinite program space and generates candidate hypotheses.
- **Engine**:
  - Primary: Few-shot prompting with `mlx-lm` running quantized small open-source models (e.g. `Qwen2.5-Coder-3B-Instruct-4bit`) on Apple Silicon unified memory.
  - Secondary / CI: Structural heuristic synthesizer generating canonical list and arithmetic combinations.
- **Sandbox**: Isolates candidate execution with wall-clock timeout bounds, recursion depth caps, and syntax validation.

### 2.2 System 2: Active Falsifier (`eve3/system2_falsifier`)
- **Role**: Efficiently eliminates false hypotheses using minimal probes.
- **Distinguishing Input Engine**: Encodes program pairs into Z3 formulas to find inputs $x$ where $P_i(x) \neq P_j(x)$, backed by property-based boundary testing (`hypothesis`).
- **Active Selection**: Calculates exact Shannon mutual information (closed-form Information Gain) to select the single most disambiguating input.
- **Bayesian Posterior Tracker**: Updates beliefs with Laplace smoothing to prevent division-by-zero crashes upon noisy observations or version space depletion.

### 2.3 System 3: Knowledge Crystallizer (`eve3/system3_crystallizer`)
- **Role**: Compresses and solidifies proven knowledge into reusable building blocks.
- **Persistent Store**: SQLite database maintaining `verified_programs`, `crystallized_operators`, and `discovery_runs`.
- **Value-Weighted Compression**: Discovers common sub-expression patterns and weights compression utility by empirical reuse frequency and cross-task family diversity.

### 2.4 Discovery Tree & Replay Simulator (`eve3/discovery`)
- **Role**: Provides the foundation for Recursive Self-Improvement (RSI).
- **Core Principle**: Exploration trajectories are recorded as structured directed trees rather than linear text logs.
- **Simulation**: Enables off-policy counterfactual experiments (e.g., assessing alternative ranking heuristics) over recorded histories without expensive model inference or environment evaluation.

---

## 3. Hardware Alignment & Operational Philosophy
- **Hardware Profile**: Engineered specifically for single-machine deployment on Apple Silicon (MacBook M1 Max, 32GB RAM).
- **Zero Cloud Dependency**: Entire synthesis, SMT solving, and LLM inference operate fully offline without external API latency or costs.
- **Bounded Footprint**: Model weights (~2GB), Python environment (~2GB), and SQLite storage (<1GB) fit comfortably within local disk budgets.
