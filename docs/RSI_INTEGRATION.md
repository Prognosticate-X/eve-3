# Recursive Self-Improvement (RSI) & Discovery Trees in EVE-3

## 1. Context: What Constitutes Genuine RSI?

As defined in recent foundational work (*The Last AI Built by Humans*, arXiv:2609.11873; *Dream-RSI*, arXiv:2609.14858):

> **A system that merely outputs better answers, writes synthetic data, or modifies its own source code is not necessarily improving itself recursively.**
> 
> The acid test of **Recursive Self-Improvement (RSI)** is whether a persistent change fundamentally alters how the system performs or organizes **future improvement processes**.

In traditional AI literature, RSI was often conceptualized as an agent modifying its own neural network weights or rewriting its own runtime logic—an approach fraught with instability, irreversible errors, and high verification costs.

**Dream-RSI (Google × DeepMind × UMD, 2026)** demonstrated an alternative, safer, and mathematically grounded path: **improving the exploration policy rather than changing the base model**.

---

## 2. Core Insight: History as a Replay Simulator

In complex synthesis tasks, the most expensive bottleneck is **Evaluation** (running compilers, sandboxes, SMT solvers, and external environments).

```
Traditional Online Search:
[ Propose Strategy A ] ---> [ Expensive Online Evaluation ] ---> Result
[ Propose Strategy B ] ---> [ Expensive Online Evaluation ] ---> Result
(Cost scales linearly with every policy iteration)

Dream-RSI / EVE-3 Replay Paradigm:
[ Discovery History Tree ] (Stored offline)
        │
        ├── Replay Strategy A (Zero marginal cost) ──> Metric A
        ├── Replay Strategy B (Zero marginal cost) ──> Metric B
        └── Optimized Exploration Policy ──> Deployed for Next Live Discovery
```

By structuring discovery history as a **Discovery Tree** rather than linear conversational text logs:
1. **Zero-Cost Counterfactuals**: We can simulate questions such as *"What if the active prober had prioritized boundary probes earlier?"* or *"What if short programs were weighted with higher temperature?"* by replaying existing outcomes along the tree.
2. **Preserving Exploration Diversity**: Text summaries injected back into LLM prompts often induce cognitive bias and premature convergence (as empirically verified in Dream-RSI). Structured execution graphs maintain full branch diversity.

---

## 3. Implementation in EVE-3

EVE-3 integrates this paradigm directly via `eve3.discovery`:

- `DiscoveryNode`: Stores `(node_id, parent_id, action_type, payload, cost, outcome)`.
- `DiscoveryTree`: Represents the topology of hypotheses proposed, probes selected, and verification milestones.
- `ReplaySimulator`: Computes simulated sample efficiency and cost to discovery for candidate ranking heuristics without re-running System 1 or the sandbox.

This bridges the gap between neurosymbolic synthesis and autonomous recursive self-improvement.
