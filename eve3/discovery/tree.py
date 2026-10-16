"""Discovery Tree & Replay Simulator.

Implements the Recursive Self-Improvement (RSI) insight from Dream-RSI:
discovery histories as structured trees enabling zero-marginal-cost counterfactual
policy replay and exploration strategy refinement.
"""

import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


class DiscoveryNode:
    """A node in the structured exploration search tree."""

    def __init__(
        self,
        node_id: str,
        parent_id: Optional[str],
        action_type: str,  # 'propose', 'probe', 'falsify', 'verify'
        payload: Dict[str, Any],  # code, probe_input, observation, etc.
        cost: float = 1.0,
        outcome: str = "pending",  # 'success', 'falsified', 'timeout'
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

        return node_id

    def total_cost(self) -> float:
        return sum(node.cost for node in self.nodes.values())

    def to_json(self) -> str:
        return json.dumps({
            "task_id": self.task_id,
            "root_id": self.root_id,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()}
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

    Allows assessing: 'What if we prioritized shorter programs first?',
    'What if we probed with boundary inputs earlier?',
    without re-running expensive LLM generators or slow environments.
    """

    def __init__(self, tree: DiscoveryTree):
        self.tree = tree

    def evaluate_policy_sample_efficiency(
        self,
        policy_priority_fn: Callable[[DiscoveryNode], float],
    ) -> Dict[str, Any]:
        """Simulate an alternative exploration order and calculate cumulative cost to first verified hit."""
        # Rank all proposal/probe nodes by policy priority
        nodes = list(self.tree.nodes.values())
        sorted_nodes = sorted(nodes, key=policy_priority_fn, reverse=True)

        simulated_cost = 0.0
        found_verified = False
        steps = 0

        for node in sorted_nodes:
            simulated_cost += node.cost
            steps += 1
            if node.outcome == "verified" or node.action_type == "verify":
                found_verified = True
                break

        return {
            "found_verified": found_verified,
            "simulated_cost": simulated_cost,
            "simulated_steps": steps,
            "tree_total_cost": self.tree.total_cost(),
        }
