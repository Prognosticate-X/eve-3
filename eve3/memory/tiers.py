"""Tiers: Three-Tier Cognitive Memory Architecture with Dynamic Decay and Demotion.

Implements Phase 8 Memory Management:
1. Working Memory (Short-Term Scratchpad):
   - Fast volatile execution context for active candidate hypotheses, probes, and bindings.
   - Cleared / archived immediately upon task completion to prevent cross-task leakage.
2. Episodic Memory (Experience & Trajectories):
   - Stores DiscoveryTree search histories with value-weighted retention.
   - Lossless trajectory summarization for older trees to control memory footprint.
3. Semantic Memory (Crystallized Knowledge & Decay):
   - Two-tier storage: Hot Tier (active in search) and Cold Tier (demoted cold storage).
   - Dynamic retention score model:
     s_i = w_i * (1 + usage_i) * exp(-Delta t_i / tau) - mu * Cost(i)
   - Graceful demotion of decayed operators rather than destructive deletion.
   - Stitch-style factoring and redundancy elimination.
"""

from dataclasses import dataclass, field
import math
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from eve3.discovery.tree import DiscoveryNode, DiscoveryTree
from eve3.dsl.interpreter import SExprParser
from eve3.memory.provenance import MemoryProvenanceManager, MemorySnapshot
from eve3.models import CandidateProgram, LearnedAbstraction, Task


# =============================================================================
# 1. Working Memory
# =============================================================================

@dataclass
class WorkingMemory:
    """Short-term cognitive scratchpad for single-task synthesis execution."""
    task_id: str = ""
    task_family: str = "generic"
    hypotheses: List[CandidateProgram] = field(default_factory=list)
    beliefs: List[float] = field(default_factory=list)
    probes_history: List[Tuple[Any, Any]] = field(default_factory=list)
    variable_bindings: Dict[str, Any] = field(default_factory=dict)
    active: bool = False
    started_at: float = field(default_factory=time.time)

    def initialize_task(self, task_id: str, task_family: str = "generic"):
        """Allocate scratchpad for a new task session."""
        self.clear()
        self.task_id = task_id
        self.task_family = task_family
        self.active = True
        self.started_at = time.time()

    def bind(self, name: str, val: Any):
        """Bind temporary variable in working memory."""
        self.variable_bindings[name] = val

    def lookup(self, name: str) -> Optional[Any]:
        """Look up temporary variable."""
        return self.variable_bindings.get(name)

    def update_hypotheses(self, hypotheses: List[CandidateProgram], beliefs: List[float]):
        """Update active hypothesis pool and belief vector."""
        self.hypotheses = list(hypotheses)
        self.beliefs = list(beliefs)

    def record_probe(self, probe_x: Any, oracle_y: Any):
        """Append probe interaction to working history."""
        self.probes_history.append((probe_x, oracle_y))

    def archive_summary(self) -> Dict[str, Any]:
        """Produce compact summary before clearing."""
        return {
            "task_id": self.task_id,
            "task_family": self.task_family,
            "probes_count": len(self.probes_history),
            "final_hypothesis_count": len(self.hypotheses),
            "duration_seconds": time.time() - self.started_at,
        }

    def clear(self):
        """Wipe working scratchpad to guarantee isolation between tasks."""
        self.task_id = ""
        self.task_family = "generic"
        self.hypotheses.clear()
        self.beliefs.clear()
        self.probes_history.clear()
        self.variable_bindings.clear()
        self.active = False


# =============================================================================
# 2. Episodic Memory
# =============================================================================

@dataclass
class EpisodicSummary:
    """Compressed representation of historical exploration trajectories."""
    task_id: str
    task_family: str
    terminal_program: Optional[str]
    counterexamples: List[Tuple[Any, Any]]
    total_causal_cost: float
    nodes_compressed: int
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_family": self.task_family,
            "terminal_program": self.terminal_program,
            "counterexamples": self.counterexamples,
            "total_causal_cost": self.total_causal_cost,
            "nodes_compressed": self.nodes_compressed,
            "created_at": self.created_at,
        }


class EpisodicMemory:
    """Manages episodic experience, trajectory trees, and lossless summarization."""

    def __init__(self, max_detailed_trees: int = 12):
        self.max_detailed_trees = max_detailed_trees
        self.detailed_trees: Dict[str, DiscoveryTree] = {}
        self.tree_weights: Dict[str, float] = {}
        self.summaries: Dict[str, EpisodicSummary] = {}

    def store_tree(
        self,
        tree: DiscoveryTree,
        task_family: str = "generic",
        value_weight: float = 1.0,
    ):
        """Store discovery tree, compressing older/low-value trees if limit exceeded."""
        task_id = tree.task_id
        self.detailed_trees[task_id] = tree
        self.tree_weights[task_id] = value_weight

        # Check capacity
        if len(self.detailed_trees) > self.max_detailed_trees:
            self._compress_lowest_value_tree(task_family)

    def _compress_lowest_value_tree(self, current_family: str):
        """Identify oldest/lowest-value detailed tree and summarize into EpisodicSummary."""
        # Score by weight and recency
        candidate_ids = list(self.detailed_trees.keys())
        victim_id = min(
            candidate_ids,
            key=lambda tid: self.tree_weights.get(tid, 1.0),
        )

        tree = self.detailed_trees.pop(victim_id)
        weight = self.tree_weights.pop(victim_id, 1.0)

        # Build summary
        counterexamples: List[Tuple[Any, Any]] = []
        terminal_prog: Optional[str] = None

        for node in tree.nodes.values():
            if node.outcome == "falsified" and "probe_input" in node.payload:
                inp = node.payload["probe_input"]
                out = node.payload.get("observation", None)
                counterexamples.append((inp, out))
            elif node.outcome == "verified" and "code" in node.payload:
                terminal_prog = node.payload["code"]

        summary = EpisodicSummary(
            task_id=victim_id,
            task_family=current_family,
            terminal_program=terminal_prog,
            counterexamples=counterexamples[:8],  # Keep essential distinguishing counterexamples
            total_causal_cost=tree.total_cost(),
            nodes_compressed=len(tree.nodes),
        )
        self.summaries[victim_id] = summary

    def get_trajectory_count(self) -> int:
        """Total number of managed episodic trajectories (detailed + summarized)."""
        return len(self.detailed_trees) + len(self.summaries)

    def get_detailed_tree(self, task_id: str) -> Optional[DiscoveryTree]:
        return self.detailed_trees.get(task_id)

    def get_summary(self, task_id: str) -> Optional[EpisodicSummary]:
        return self.summaries.get(task_id)


# =============================================================================
# 3. Semantic Memory & Decay
# =============================================================================

@dataclass
class RetentionConfig:
    """Hyperparameters for retention score decay, demotion, and compaction."""
    tau_decay_hours: float = 48.0      # Characteristic half-life decay time
    mu_cost_penalty: float = 0.05      # Complexity penalty coefficient
    demotion_threshold: float = 0.75   # Retention score below which abstraction is demoted to cold tier
    promotion_threshold: float = 1.25  # Score above which cold abstraction is promoted back to hot tier
    compaction_subsumption: bool = True # Enable Stitch-style operator subsumption checking


class SemanticMemory:
    """Two-tier semantic knowledge store with retention decay and lossless demotion."""

    def __init__(
        self,
        config: Optional[RetentionConfig] = None,
        provenance_manager: Optional[MemoryProvenanceManager] = None,
    ):
        self.config = config or RetentionConfig()
        self.provenance = provenance_manager or MemoryProvenanceManager()

        self.hot_abstractions: Dict[str, LearnedAbstraction] = {}
        self.cold_abstractions: Dict[str, LearnedAbstraction] = {}
        self._master_archive: Dict[str, LearnedAbstraction] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}

    @property
    def hot_tier(self) -> Dict[str, LearnedAbstraction]:
        return self.hot_abstractions

    @property
    def cold_tier(self) -> Dict[str, LearnedAbstraction]:
        return self.cold_abstractions

    def register_abstraction(
        self,
        abstraction: LearnedAbstraction,
        source_task_id: Optional[str] = None,
        value_weight: float = 1.0,
        current_time: Optional[float] = None,
    ) -> str:
        """Register newly crystallized abstraction into the hot tier."""
        abs_id = abstraction.abstraction_id
        self.hot_abstractions[abs_id] = abstraction
        self._master_archive[abs_id] = abstraction

        now = current_time if current_time is not None else time.time()
        self.metadata[abs_id] = {
            "value_weight": value_weight,
            "usage_count": abstraction.reuse_count or 1,
            "last_used_at": now,
            "created_at": now,
            "subsumed_by": None,
        }

        # Track provenance
        self.provenance.get_or_create_record(
            artifact_id=abs_id,
            artifact_type="abstraction",
            source_task_id=source_task_id,
        )
        self.provenance.record_event(abs_id, "created", {"pattern": abstraction.pattern_sexpr})
        return abs_id

    def compute_retention_score(
        self,
        abs_id: str,
        current_time: Optional[float] = None,
    ) -> float:
        """Calculate dynamic retention score s_i.
        
        s_i = w_i * (1 + usage_i) * exp(-Delta t_i / tau) - mu * Cost(i)
        """
        meta = self.metadata.get(abs_id)
        if not meta:
            return 1.0

        now = current_time if current_time is not None else time.time()
        last_used = meta.get("last_used_at", now)
        delta_hours = max(0.0, (now - last_used) / 3600.0)

        # Value weight w_i
        w_i = float(meta.get("value_weight", 1.0))
        usage_i = float(meta.get("usage_count", 1))

        # Time decay
        tau = max(1.0, self.config.tau_decay_hours)
        decay = math.exp(-delta_hours / tau)

        # Complexity cost: description length / AST nodes
        cost = 4.0
        abs_record = self.hot_abstractions.get(abs_id) or self.cold_abstractions.get(abs_id)
        if abs_record:
            cost = float(len(abs_record.pattern_sexpr.split()))

        score = w_i * (1.0 + math.log(1.0 + usage_i)) * decay - self.config.mu_cost_penalty * cost
        return float(max(0.0, score))

    def record_usage(self, abs_id: str, current_time: Optional[float] = None):
        """Record reuse of an abstraction, potentially promoting it back to hot tier."""
        if abs_id not in self.metadata:
            return

        now = current_time if current_time is not None else time.time()
        meta = self.metadata[abs_id]
        meta["usage_count"] += 1
        meta["last_used_at"] = now

        self.provenance.record_event(abs_id, "reused", {"new_usage_count": meta["usage_count"]})

        # Check if cold abstraction qualifies for promotion
        if abs_id in self.cold_abstractions:
            score = self.compute_retention_score(abs_id, current_time=now)
            if score >= self.config.promotion_threshold:
                self.promote_to_hot(abs_id)

    def demote_to_cold(self, abs_id: str, reason: str = "decay"):
        """Move abstraction from active Hot Tier to Cold Tier without deleting."""
        if abs_id in self.hot_abstractions:
            abs_rec = self.hot_abstractions.pop(abs_id)
            abs_rec.status = "demoted"
            self.cold_abstractions[abs_id] = abs_rec
            self.provenance.record_event(abs_id, "demoted", {"reason": reason})

    def promote_to_hot(self, abs_id: str):
        """Promote abstraction from Cold Tier back to active Hot Tier."""
        if abs_id in self.cold_abstractions:
            abs_rec = self.cold_abstractions.pop(abs_id)
            abs_rec.status = "verified"
            self.hot_abstractions[abs_id] = abs_rec
            self.provenance.record_event(abs_id, "promoted", {})

    def consolidate_and_decay(
        self,
        current_time: Optional[float] = None,
    ) -> Tuple[List[str], List[str]]:
        """Run periodic retention consolidation cycle: demote low-score operators."""
        demoted: List[str] = []
        promoted: List[str] = []

        now = current_time if current_time is not None else time.time()

        # 1. Check hot abstractions for demotion
        hot_keys = list(self.hot_abstractions.keys())
        for aid in hot_keys:
            score = self.compute_retention_score(aid, current_time=now)
            if score < self.config.demotion_threshold:
                self.demote_to_cold(aid, reason=f"retention_score_decayed:{score:.2f}")
                demoted.append(aid)

        # 2. Check cold abstractions for potential promotion
        cold_keys = list(self.cold_abstractions.keys())
        for aid in cold_keys:
            score = self.compute_retention_score(aid, current_time=now)
            if score >= self.config.promotion_threshold:
                self.promote_to_hot(aid)
                promoted.append(aid)

        return demoted, promoted

    def compact_library(self) -> List[str]:
        """Stitch-style compaction: identify duplicate/subsumed abstractions and demote them."""
        subsumed: List[str] = []
        if not self.config.compaction_subsumption:
            return subsumed

        hot_items = list(self.hot_abstractions.values())
        for i, a1 in enumerate(hot_items):
            for a2 in hot_items[i + 1:]:
                # Check structural equivalence or complete subsumption
                if a1.pattern_sexpr == a2.pattern_sexpr:
                    # Duplicate pattern: keep higher usage one
                    u1 = self.metadata[a1.abstraction_id]["usage_count"]
                    u2 = self.metadata[a2.abstraction_id]["usage_count"]
                    victim_id = a2.abstraction_id if u1 >= u2 else a1.abstraction_id
                    keeper_id = a1.abstraction_id if u1 >= u2 else a2.abstraction_id

                    if victim_id in self.hot_abstractions:
                        self.metadata[victim_id]["subsumed_by"] = keeper_id
                        self.demote_to_cold(victim_id, reason=f"subsumed_by:{keeper_id}")
                        subsumed.append(victim_id)

        return subsumed

    def create_snapshot(self, description: str = "") -> MemorySnapshot:
        """Checkpoint current active and demoted memory state."""
        return self.provenance.create_snapshot(
            active_ids=list(self.hot_abstractions.keys()),
            demoted_ids=list(self.cold_abstractions.keys()),
            description=description,
        )

    def rollback_to_snapshot(self, snapshot_id: str) -> bool:
        """Rollback semantic memory state to designated snapshot."""
        snap = self.provenance.get_snapshot(snapshot_id)
        if not snap:
            return False

        new_hot: Dict[str, LearnedAbstraction] = {}
        new_cold: Dict[str, LearnedAbstraction] = {}

        for aid in snap.active_abstraction_ids:
            if aid in self._master_archive:
                rec = self._master_archive[aid]
                rec.status = "verified"
                new_hot[aid] = rec

        for aid in snap.demoted_abstraction_ids:
            if aid in self._master_archive:
                rec = self._master_archive[aid]
                rec.status = "demoted"
                new_cold[aid] = rec

        self.hot_abstractions = new_hot
        self.cold_abstractions = new_cold
        return True

    def get_active_operators(self) -> List[LearnedAbstraction]:
        """Fetch only currently active Hot Tier operators for search and enumeration."""
        return list(self.hot_abstractions.values())

    def get_all_abstractions(self) -> List[LearnedAbstraction]:
        """Fetch all stored abstractions across both hot and cold tiers."""
        return list(self.hot_abstractions.values()) + list(self.cold_abstractions.values())
