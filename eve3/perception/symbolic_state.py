"""Symbolic State: Structured Scene Graphs, Object Nodes, Relations, and Predicates.

Implements Phase 10 L3 Perception Front-End representations:
- ObjectNode: Discrete visual/physical entity with spatial bounds, features, and detection confidence.
- RelationEdge: Spatial/topological relational predicates between entities (e.g., above, left_of, inside).
- SceneGraph: Unified neurosymbolic scene representation bridging raw pixels/sensors and formal predicates.
- PredicateState: Evaluated high-level symbolic predicates with hard and soft/calibrated truth values.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ObjectNode:
    """Represents a discrete segmented object in a visual or simulated scene."""
    object_id: str
    category: str
    position: Tuple[float, float]               # (x, y) centroid
    bbox: Tuple[float, float, float, float]     # (x_min, y_min, x_max, y_max)
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0                     # Detection confidence c in [0, 1]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "category": self.category,
            "position": list(self.position),
            "bbox": list(self.bbox),
            "attributes": dict(self.attributes),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ObjectNode":
        return cls(
            object_id=data["object_id"],
            category=data["category"],
            position=tuple(data["position"]),
            bbox=tuple(data["bbox"]),
            attributes=data.get("attributes", {}),
            confidence=data.get("confidence", 1.0),
        )


@dataclass
class RelationEdge:
    """Represents a spatial or topological relationship between two object nodes."""
    source_id: str
    target_id: str
    relation_type: str                          # e.g., "left_of", "right_of", "above", "below", "touching"
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0                     # Relational confidence in [0, 1]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "attributes": dict(self.attributes),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationEdge":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation_type=data["relation_type"],
            attributes=data.get("attributes", {}),
            confidence=data.get("confidence", 1.0),
        )


@dataclass
class PredicateState:
    """Evaluated symbolic predicates with both boolean and soft confidence truth values."""
    predicates: Dict[str, bool] = field(default_factory=dict)
    soft_confidences: Dict[str, float] = field(default_factory=dict)

    def is_satisfied(self, predicate_name: str, threshold: float = 0.5) -> bool:
        """Query if a predicate is satisfied with confidence above threshold."""
        if predicate_name in self.predicates:
            return self.predicates[predicate_name] and (self.soft_confidences.get(predicate_name, 1.0) >= threshold)
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicates": dict(self.predicates),
            "soft_confidences": dict(self.soft_confidences),
        }


class SceneGraph:
    """Unified scene graph encapsulating objects, spatial topology, and predicate extraction."""

    def __init__(
        self,
        scene_id: str = "scene_0",
        global_attributes: Optional[Dict[str, Any]] = None,
    ):
        self.scene_id = scene_id
        self.nodes: Dict[str, ObjectNode] = {}
        self.edges: List[RelationEdge] = []
        self.global_attributes: Dict[str, Any] = global_attributes or {}

    def add_node(self, node: ObjectNode):
        self.nodes[node.object_id] = node

    def add_edge(self, edge: RelationEdge):
        self.edges.append(edge)

    def get_node(self, object_id: str) -> Optional[ObjectNode]:
        return self.nodes.get(object_id)

    def get_nodes_by_category(self, category: str) -> List[ObjectNode]:
        return [node for node in self.nodes.values() if node.category == category]

    def get_relations_between(self, source_id: str, target_id: str) -> List[RelationEdge]:
        return [e for e in self.edges if e.source_id == source_id and e.target_id == target_id]

    def compute_spatial_relations(self, proximity_threshold: float = 1.0):
        """Automatically derive spatial edges (left_of, right_of, above, below, touching) from node positions."""
        self.edges.clear()
        node_ids = list(self.nodes.keys())

        for i in range(len(node_ids)):
            for j in range(len(node_ids)):
                if i == j:
                    continue
                n1 = self.nodes[node_ids[i]]
                n2 = self.nodes[node_ids[j]]

                dx = n2.position[0] - n1.position[0]
                dy = n2.position[1] - n1.position[1]
                dist = math.sqrt(dx * dx + dy * dy)
                pair_conf = min(n1.confidence, n2.confidence)

                # Horizontal relationships
                if dx > 0.2:
                    self.add_edge(RelationEdge(n1.object_id, n2.object_id, "left_of", {"dx": dx}, pair_conf))
                elif dx < -0.2:
                    self.add_edge(RelationEdge(n1.object_id, n2.object_id, "right_of", {"dx": -dx}, pair_conf))

                # Vertical relationships
                if dy > 0.2:
                    self.add_edge(RelationEdge(n1.object_id, n2.object_id, "below", {"dy": dy}, pair_conf))
                elif dy < -0.2:
                    self.add_edge(RelationEdge(n1.object_id, n2.object_id, "above", {"dy": -dy}, pair_conf))

                # Proximity / touching
                if dist <= proximity_threshold:
                    self.add_edge(RelationEdge(n1.object_id, n2.object_id, "touching", {"distance": dist}, pair_conf))

    def evaluate_predicate_state(self) -> PredicateState:
        """Derive standard formal scene predicates from nodes and relational topology."""
        state = PredicateState()

        # 1. Check goal reaching: agent touching target
        agents = self.get_nodes_by_category("agent")
        targets = self.get_nodes_by_category("target")

        if agents and targets:
            ag = agents[0]
            tg = targets[0]
            touching_edges = [
                e for e in self.edges
                if (e.source_id == ag.object_id and e.target_id == tg.object_id and e.relation_type == "touching")
                or (e.source_id == tg.object_id and e.target_id == ag.object_id and e.relation_type == "touching")
            ]
            goal_reached = len(touching_edges) > 0
            conf = touching_edges[0].confidence if goal_reached else min(ag.confidence, tg.confidence)
            state.predicates["goal_reached"] = goal_reached
            state.soft_confidences["goal_reached"] = conf if goal_reached else (1.0 - conf)
        else:
            state.predicates["goal_reached"] = False
            state.soft_confidences["goal_reached"] = 0.0

        # 2. Check alignment: horizontally or vertically aligned
        if agents and targets:
            ag = agents[0]
            tg = targets[0]
            dx = abs(ag.position[0] - tg.position[0])
            dy = abs(ag.position[1] - tg.position[1])
            is_aligned = (dx < 0.3) or (dy < 0.3)
            conf = min(ag.confidence, tg.confidence)
            state.predicates["aligned"] = is_aligned
            state.soft_confidences["aligned"] = conf if is_aligned else (1.0 - conf)

        # 3. Obstacle clearance
        obstacles = self.get_nodes_by_category("obstacle")
        if agents and obstacles:
            ag = agents[0]
            in_collision = any(
                math.sqrt((ag.position[0] - obs.position[0]) ** 2 + (ag.position[1] - obs.position[1]) ** 2) < 0.5
                for obs in obstacles
            )
            state.predicates["collision_free"] = not in_collision
            state.soft_confidences["collision_free"] = 0.95 if not in_collision else 0.05
        else:
            state.predicates["collision_free"] = True
            state.soft_confidences["collision_free"] = 1.0

        return state

    def compute_graph_distance(self, other: "SceneGraph") -> float:
        """Compute normalized graph edit distance / structural dissimilarity in [0, 1]."""
        # Node category Jaccard distance
        cats1 = set((n.category, n.attributes.get("color", 0)) for n in self.nodes.values())
        cats2 = set((n.category, n.attributes.get("color", 0)) for n in other.nodes.values())
        if not cats1 and not cats2:
            node_dist = 0.0
        else:
            node_dist = 1.0 - (len(cats1.intersection(cats2)) / len(cats1.union(cats2)))

        # Edge relation Jaccard distance
        edges1 = set((e.relation_type, e.source_id, e.target_id) for e in self.edges)
        edges2 = set((e.relation_type, e.source_id, e.target_id) for e in other.edges)
        if not edges1 and not edges2:
            edge_dist = 0.0
        else:
            edge_dist = 1.0 - (len(edges1.intersection(edges2)) / len(edges1.union(edges2)))

        return 0.6 * node_dist + 0.4 * edge_dist

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "global_attributes": dict(self.global_attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneGraph":
        sg = cls(scene_id=data.get("scene_id", "scene_0"), global_attributes=data.get("global_attributes"))
        for k, v in data.get("nodes", {}).items():
            sg.add_node(ObjectNode.from_dict(v))
        for e in data.get("edges", []):
            sg.add_edge(RelationEdge.from_dict(e))
        return sg
