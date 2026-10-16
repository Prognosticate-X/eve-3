"""Discovery Tree & Replay Simulator.

Implements the Recursive Self-Improvement (RSI) insight from Dream-RSI:
discovery histories as structured trees enabling zero-marginal-cost counterfactual
policy replay with strict causal reachability and topological dependencies.
"""

from dataclasses import dataclass, field
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from eve3.discovery.policy import ExplorationPolicy


@dataclass
class ExplorationTransition:
    """Rigorous state transition record tracking decision context and costs without future leakage."""
    transition_id: str = field(default_factory=lambda: f"trans_{uuid.uuid4().hex[:8]}")
    parent_state_id: Optional[str] = None
    state_id: str = ""
    policy_version: str = "v1.0.0"
    available_actions: List[str] = field(default_factory=list)
    chosen_action: str = ""
    visible_observations: List[str] = field(default_factory=list)
    outcome_ids: List[str] = field(default_factory=list)
    costs: Dict[str, float] = field(default_factory=dict)
    terminal_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "parent_state_id": self.parent_state_id,
            "state_id": self.state_id,
            "policy_version": self.policy_version,
            "available_actions": self.available_actions,
            "chosen_action": self.chosen_action,
            "visible_observations": self.visible_observations,
            "outcome_ids": self.outcome_ids,
            "costs": self.costs,
            "terminal_reason": self.terminal_reason,
        }


class DiscoveryNode:
    """A node in the structured exploration search tree."""

    def __init__(
        self,
        node_id: str,
        parent_id: Optional[str],
        action_type: str,  # 'propose', 'probe', 'falsify', 'verify'
        payload: Dict[str, Any],  # code, probe_input, observation, etc.
        cost: float = 1.0,
        outcome: str = "pending",  # 'success', 'falsified', 'verified', 'timeout'
    ):
        self.node_id = node_id
        self.parent_id = parent_id
        self.action_type = action_type
        self.payload = payload
        self.cost = cost
        self.outcome = outcome
        self.timestamp = time.time()
        self.children: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "action_type": self.action_type,
            "payload": self.payload,
            "cost": self.cost,
            "outcome": self.outcome,
            "timestamp": self.timestamp,
            "children": self.children,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryNode":
        node = cls(
            node_id=data["node_id"],
            parent_id=data["parent_id"],
            action_type=data["action_type"],
            payload=data["payload"],
            cost=data.get("cost", 1.0),
            outcome=data.get("outcome", "pending"),
        )
        node.timestamp = data.get("timestamp", time.time())
        node.children = data.get("children", [])
        return node


class DiscoveryTree:
    """Structured tree representing complete exploration and falsification trajectories."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.nodes: Dict[str, DiscoveryNode] = {}
        self.transitions: List[ExplorationTransition] = []
        self.root_id: Optional[str] = None

    def add_node(
        self,
        action_type: str,
        payload: Dict[str, Any],
        parent_id: Optional[str] = None,
        cost: float = 1.0,
        outcome: str = "pending",
    ) -> str:
        node_id = str(uuid.uuid4())[:8]
        node = DiscoveryNode(
            node_id=node_id,
            parent_id=parent_id,
            action_type=action_type,
            payload=payload,
            cost=cost,
            outcome=outcome,
        )
        self.nodes[node_id] = node

        if parent_id is None and self.root_id is None:
            self.root_id = node_id
        elif parent_id in self.nodes:
            self.nodes[parent_id].children.append(node_id)

        # Record formal exploration transition
        trans = ExplorationTransition(
            parent_state_id=parent_id,
            state_id=node_id,
            available_actions=[action_type],
            chosen_action=action_type,
            costs={"cost": cost},
            terminal_reason="verified" if outcome == "verified" else None,
        )
        self.transitions.append(trans)

        return node_id

    def get_path_from_root(self, target_node_id: str) -> List[str]:
        """Return the directed causal path of node IDs from root to target."""
        path = []
        curr = target_node_id
        while curr is not None and curr in self.nodes:
            path.append(curr)
            curr = self.nodes[curr].parent_id
        return list(reversed(path))

    def total_cost(self) -> float:
        return sum(node.cost for node in self.nodes.values())

    def to_json(self) -> str:
        return json.dumps({
            "task_id": self.task_id,
            "root_id": self.root_id,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "transitions": [t.to_dict() for t in self.transitions],
        }, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "DiscoveryTree":
        data = json.loads(json_str)
        tree = cls(data["task_id"])
        tree.root_id = data.get("root_id")
        for nid, ndata in data.get("nodes", {}).items():
            tree.nodes[nid] = DiscoveryNode.from_dict(ndata)
        return tree


class ReplaySimulator:
    """Evaluates counterfactual exploration policies using recorded discovery trees.

    Enforces strict causal reachability: a node can ONLY be evaluated if its
    ancestor lineage from the root has already been explored.
    """

    def __init__(self, tree: DiscoveryTree):
        self.tree = tree

    def evaluate_policy(self, policy: ExplorationPolicy) -> Dict[str, Any]:
        """Convenience method to evaluate a versioned ExplorationPolicy."""
        return self.evaluate_policy_sample_efficiency(
            policy_priority_fn=lambda n: policy.score_node(n.action_type, n.cost)
        )

    def evaluate_policy_sample_efficiency(
        self,
        policy_priority_fn: Callable[[DiscoveryNode], float],
    ) -> Dict[str, Any]:
        """Simulate an alternative exploration policy by rolling out the tree along its causal frontier."""
        if not self.tree.nodes or self.tree.root_id is None:
            return {
                "found_verified": False,
                "simulated_cost": 0.0,
                "simulated_steps": 0,
                "causal_path_cost": 0.0,
                "tree_total_cost": 0.0,
            }

        # Initialize frontier strictly at the root
        frontier: Set[str] = {self.tree.root_id}
        explored: Set[str] = set()

        simulated_cost = 0.0
        steps = 0
        found_verified = False
        target_node_id: Optional[str] = None

        while frontier:
            # Policy chooses highest priority node among CURRENTLY REACHABLE frontier nodes
            candidates = [self.tree.nodes[nid] for nid in frontier]
            best_node = max(candidates, key=policy_priority_fn)

            frontier.remove(best_node.node_id)
            explored.add(best_node.node_id)

            simulated_cost += best_node.cost
            steps += 1

            if best_node.outcome in ("verified", "success") or best_node.action_type == "verify":
                found_verified = True
                target_node_id = best_node.node_id
                break

            # Add newly unlocked child nodes whose parent is now explored
            for child_id in best_node.children:
                if child_id not in explored and child_id in self.tree.nodes:
                    frontier.add(child_id)

        causal_path_cost = 0.0
        if target_node_id:
            path_from_root = self.tree.get_path_from_root(target_node_id)
            causal_path_cost = sum(self.tree.nodes[nid].cost for nid in path_from_root)

        return {
            "found_verified": found_verified,
            "simulated_cost": simulated_cost,
            "simulated_steps": steps,
            "causal_path_cost": causal_path_cost,
            "tree_total_cost": self.tree.total_cost(),
        }
