# EVE-3 Mathematical & Algorithmic Foundations

This document provides rigorous mathematical formulations and theoretical derivations for the core components of the **EVE-3** AGI architecture, specifically **System 2 (Bayesian Active Falsification)** and **System 3 (Value-Weighted Knowledge Crystallization)**.

---

## 1. System 2: Exact Bayesian Active Probe Selection

### 1.1 Problem Formalization & Version Space

At round $t$ of program synthesis, System 1 proposes a candidate hypothesis set (the Version Space):

$$\mathcal{H} = \{P_1, P_2, \dots, P_k\}$$

where every program $P_i \in \mathcal{H}$ is consistent with all currently observed input-output examples $\mathcal{E}_t = \{(x_\tau, y_\tau)\}_{\tau=1}^t$.

Each candidate is assigned a belief weight (posterior probability) $b_i = \mathbb{P}(P^* = P_i \mid \mathcal{E}_t)$, with $\sum_{i=1}^k b_i = 1$.

#### Occam / Minimum Description Length (MDL) Prior
Before any external probes are executed, the initial prior $b^{(0)}$ is governed by algorithmic probability (Solomonoff-inspired MDL prior):

$$b_i^{(0)} = \frac{2^{-L(P_i)}}{\sum_{j=1}^k 2^{-L(P_j)}}$$

where $L(P_i)$ denotes the syntactic description length of program $P_i$ (e.g., number of AST nodes or serialized bits in the DSL grammar).

---

### 1.2 Closed-Form Information Gain (Mutual Information)

Given a candidate probe input $x$, each hypothesis yields an execution outcome $P_i(x)$. We partition the candidate set into equivalence classes grouped by output value $v$:

$$G_v(x) = \{ i \in \{1, \dots, k\} : P_i(x) = v \}$$

The marginal predictive probability of observing output $v$ under current beliefs is:

$$q_v(x) = \sum_{i \in G_v(x)} b_i$$

Because the hypothesis space $\mathcal{H}$ is discrete and finite, the **Mutual Information** $I(\mathcal{H}; Y \mid x)$ between the true identity of the program and the probe outcome $Y = P^*(x)$ has an **exact closed-form solution** without requiring Monte Carlo approximation:

$$IG(x) = H(b) - \sum_{v \in \mathcal{V}(x)} q_v(x) \cdot H\big(b \mid G_v(x)\big)$$

where:
- $H(b) = -\sum_{i=1}^k b_i \log_2(b_i)$ is the Shannon entropy of current beliefs.
- $b \mid G_v(x)$ is the normalized conditional belief distribution restricted to indices within $G_v(x)$:
  $$\big(b \mid G_v(x)\big)_i = \begin{cases} \dfrac{b_i}{q_v(x)}, & i \in G_v(x) \\ 0, & \text{otherwise} \end{cases}$$
- $H\big(b \mid G_v(x)\big) = -\sum_{i \in G_v(x)} \frac{b_i}{q_v(x)} \log_2\left(\frac{b_i}{q_v(x)}\right)$

---

### 1.3 Probe Optimization Objective

The optimal probe $x^*$ maximizes Information Gain while penalizing probe execution cost $C(x)$:

$$x^* = \arg\max_{x \in X_{\text{cand}}} \Big[ IG(x) - \lambda \cdot C(x) \Big]$$

where:
- $\lambda \ge 0$ is the cost-regularization hyperparameter.
- $C(x)$ represents evaluation complexity (e.g. execution time, sandbox memory, or external oracle query cost).

---

### 1.4 SMT Generation of Distinguishing Inputs

Instead of blind random fuzzing, candidate probes $X_{\text{cand}}$ are systematically synthesized using an SMT solver (Z3). For each pair of programs $(P_i, P_j) \in \mathcal{H} \times \mathcal{H}$ ($i \neq j$), we encode their operational semantics into SMT formulas $\Phi_{P_i}(x, y)$ and $\Phi_{P_j}(x, y)$ and pose the satisfiability query:

$$\exists x : \Phi_{P_i}(x, y_1) \land \Phi_{P_j}(x, y_2) \land (y_1 \neq y_2)$$

If satisfiable, the solver model provides a witness input $x$ guaranteed to split the version space by falsifying at least one of the two hypotheses.

---

### 1.5 Bayesian Posterior Update & Collapse Prevention

Upon submitting probe $x^*$ to the environment/oracle and receiving ground-truth observation $y_{\text{obs}}$:

$$b_i \leftarrow \begin{cases} 0, & \text{if } P_i(x^*) \neq y_{\text{obs}} \\[6pt] \dfrac{b_i}{q_{y_{\text{obs}}}(x^*)}, & \text{if } P_i(x^*) = y_{\text{obs}} \end{cases}$$

#### Collapse Protection (Hypothesis Space Collapse)
If $y_{\text{obs}}$ matches no candidate program in $\mathcal{H}$ ($\forall i, P_i(x^*) \neq y_{\text{obs}}$), $q_{y_{\text{obs}}}(x^*) = 0$, leading to zero division and total version space collapse. 

To ensure mathematical stability:
1. **Laplace Smoothing ($\epsilon$-regularization)**:
   $$\mathcal{L}(y_{\text{obs}} \mid P_i, x^*) = (1 - \epsilon) \cdot \mathbb{I}[P_i(x^*) = y_{\text{obs}}] + \epsilon \cdot \mathbb{I}[P_i(x^*) \neq y_{\text{obs}}]$$
2. **Version Space Replenishment**: If $\sum_i b_i \cdot \mathcal{L}_i < 10^{-12}$, the system issues an alert, falls back to a uniform floor, and invokes System 1 to expand search depth and synthesize new hypotheses.

---

## 2. System 3: Value-Weighted Knowledge Crystallization

### 2.1 Limitations of Standard MDL Compression

In standard library learning (e.g. DreamCoder / Stitch), candidate abstractions $\mathcal{L}$ are selected solely to minimize description length:

$$\mathcal{L}^* = \arg\min_{\mathcal{L}} \left[ |\mathcal{L}| + \sum_{i=1}^N \text{DL}(P_i \mid \mathcal{L}) \right]$$

**Defect**: This criterion rewards abstractions that compress the training corpus even if the shared structure is accidental and confined to a single task family, failing to reflect future reuse value across diverse domains.

---

### 2.2 Value-Weighted Compression Objective

EVE-3 introduces an explicit value weighting $w_i \ge 1$ for each verified program $P_i$:

$$\text{Benefit}_w(\mathcal{L}) = \sum_{i=1}^N w_i \cdot \Big[ \text{DL}(P_i \mid \varnothing) - \text{DL}(P_i \mid \mathcal{L}) \Big]$$

The optimal library $\mathcal{L}^*$ is formulated as a cardinality-regularized submodular optimization problem:

$$\mathcal{L}^* = \arg\max_{\mathcal{L} \subseteq \text{Candidates}} \Big[ \text{Benefit}_w(\mathcal{L}) - \gamma \cdot \text{Cost}(\mathcal{L}) \Big]$$

where:
- $\text{DL}(P_i \mid \varnothing)$ is the description length without library abstractions.
- $\text{DL}(P_i \mid \mathcal{L})$ is the compressed length rewriting $P_i$ with library operators.
- $\gamma > 0$ is the complexity penalty preventing library bloat.
- $w_i$ measures **Task Diversity & Frequency**:
  $$w_i = \big| \text{TaskFamilies}(P_i) \big| \times \big(1 + \ln(1 + \text{ReuseCount}_i)\big)$$

---

### 2.3 Greedy Submodular Selection Algorithm

Because $\text{Benefit}_w(\mathcal{L})$ exhibits submodular (diminishing returns) properties over candidate sets, a greedy selection strategy guarantees a $(1 - 1/e)$ approximation bound:

```python
def select_optimal_library(candidates, programs, weights, gamma):
    library = []
    remaining = set(candidates)
    current_benefit = 0.0

    while remaining:
        best_abs, best_gain = None, 0.0
        for a in remaining:
            new_benefit = compute_weighted_benefit(library + [a], programs, weights)
            gain = new_benefit - current_benefit - gamma * a.cost
            if gain > best_gain:
                best_gain = gain
                best_abs = a

        if best_abs is None:
            break  # Marginal gain cannot offset complexity penalty gamma

        library.append(best_abs)
        remaining.remove(best_abs)
        current_benefit += best_gain + gamma * best_abs.cost

    return library
```

---

## 3. Theoretical Connection to Generalized Binary Search & RSI

1. **Generalized Binary Search (GBS)**: System 2's active prober exactly reduces to Generalized Binary Search under noiseless discrete domains, which Nowak (2011) proved achieves near-optimal query complexity $O(H(b))$ for version space disambiguation.
2. **Recursive Self-Improvement (RSI)**: By storing exploration trajectories as structured **Discovery Trees**, the system turns historical exploration into a **Replay Simulator** (Dream-RSI, arXiv:2609.14858), enabling offline policy evaluation and exploration strategy optimization with zero marginal environment evaluation costs.
