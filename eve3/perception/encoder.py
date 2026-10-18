"""Perception Encoder: Visual & Sensor Front-End to Structured Scene Graphs.

Implements Phase 10 L3 Perception Front-End:
- Segmenting raw discrete visual grids into contiguous colored object entities.
- Encoding continuous simulation states into structured semantic entities and topological relations.
- Parametric perceptual noise modeling (attribute perturbation, spatial jitter, missed detections, false alarms).
- Calibrated confidence estimation and corrupted perception flagging for System 2 h_empty gating.
"""

from dataclasses import dataclass, field
import math
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from eve3.envs.grid_tasks import Grid
from eve3.perception.symbolic_state import ObjectNode, PredicateState, RelationEdge, SceneGraph


@dataclass
class PerceptionNoiseConfig:
    """Configures perceptual noise characteristics for VLM / sensory front-end."""
    attribute_noise_rate: float = 0.0       # Probability of corrupted attribute (e.g. color shift)
    spatial_jitter_std: float = 0.0         # Gaussian standard deviation added to positions
    missed_detection_rate: float = 0.0      # Probability of dropping a real object (False Negative)
    false_alarm_rate: float = 0.0           # Probability of hallucinating an object (False Positive)
    corruption_confidence_threshold: float = 0.40  # Below this, scene is flagged as corrupted (triggers h_empty)


class PerceptionEncoder:
    """Encodes discrete grids and physical states into SceneGraphs with noise modeling."""

    def __init__(
        self,
        noise_config: Optional[PerceptionNoiseConfig] = None,
        seed: Optional[int] = None,
    ):
        self.noise_config = noise_config or PerceptionNoiseConfig()
        self.rng = random.Random(seed if seed is not None else 42)

    def set_noise_level(self, noise_scale: float):
        """Linearly scale perceptual noise parameters in [0, 1]."""
        scale = max(0.0, min(1.0, float(noise_scale)))
        self.noise_config.attribute_noise_rate = 0.15 * scale
        self.noise_config.spatial_jitter_std = 0.20 * scale
        self.noise_config.missed_detection_rate = 0.10 * scale
        self.noise_config.false_alarm_rate = 0.10 * scale

    def encode_grid(self, grid: Grid, scene_id: str = "grid_scene") -> Tuple[SceneGraph, bool]:
        """Convert a 2D integer Grid into a segmented SceneGraph.
        
        Returns (scene_graph, is_corrupted).
        """
        sg = SceneGraph(scene_id=scene_id, global_attributes={"height": grid.height, "width": grid.width})
        h, w = grid.height, grid.width
        visited: Set[Tuple[int, int]] = set()
        object_idx = 0

        # Connected component segmentation (4-connectivity)
        for r in range(h):
            for c in range(w):
                val = grid.cells[r][c]
                if val == 0 or (r, c) in visited:
                    continue

                # BFS to discover contiguous component
                component_cells = []
                queue = [(r, c)]
                visited.add((r, c))

                while queue:
                    curr_r, curr_c = queue.pop(0)
                    component_cells.append((curr_r, curr_c))
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = curr_r + dr, curr_c + dc
                        if 0 <= nr < h and 0 <= nc < w:
                            if grid.cells[nr][nc] == val and (nr, nc) not in visited:
                                visited.add((nr, nc))
                                queue.append((nr, nc))

                # Entity attributes
                object_idx += 1
                obj_id = f"obj_{object_idx}_{val}"
                mean_r = sum(p[0] for p in component_cells) / len(component_cells)
                mean_c = sum(p[1] for p in component_cells) / len(component_cells)
                min_r = min(p[0] for p in component_cells)
                max_r = max(p[0] for p in component_cells)
                min_c = min(p[1] for p in component_cells)
                max_c = max(p[1] for p in component_cells)

                node = ObjectNode(
                    object_id=obj_id,
                    category="colored_block",
                    position=(mean_c, mean_r),  # (x, y) mapping
                    bbox=(min_c, min_r, max_c, max_r),
                    attributes={"color": val, "area": len(component_cells)},
                    confidence=1.0,
                )
                sg.add_node(node)

        # Apply perceptual noise
        is_corrupted = self._apply_perceptual_noise(sg)
        sg.compute_spatial_relations(proximity_threshold=1.5)
        return sg, is_corrupted

    def encode_sim_state(
        self,
        agent_pos: Tuple[float, float],
        target_pos: Tuple[float, float],
        obstacles: Optional[List[Tuple[float, float]]] = None,
        scene_id: str = "sim_scene",
    ) -> Tuple[SceneGraph, bool]:
        """Convert 2D continuous physical simulation positions into a structured SceneGraph."""
        sg = SceneGraph(scene_id=scene_id)

        # 1. Agent node
        sg.add_node(
            ObjectNode(
                object_id="agent",
                category="agent",
                position=agent_pos,
                bbox=(agent_pos[0] - 0.2, agent_pos[1] - 0.2, agent_pos[0] + 0.2, agent_pos[1] + 0.2),
                attributes={"status": "navigating"},
                confidence=1.0,
            )
        )

        # 2. Target node
        sg.add_node(
            ObjectNode(
                object_id="target",
                category="target",
                position=target_pos,
                bbox=(target_pos[0] - 0.4, target_pos[1] - 0.4, target_pos[0] + 0.4, target_pos[1] + 0.4),
                attributes={"radius": 0.8},
                confidence=1.0,
            )
        )

        # 3. Obstacle nodes
        if obstacles:
            for idx, obs_pos in enumerate(obstacles):
                sg.add_node(
                    ObjectNode(
                        object_id=f"obs_{idx}",
                        category="obstacle",
                        position=obs_pos,
                        bbox=(obs_pos[0] - 0.3, obs_pos[1] - 0.3, obs_pos[0] + 0.3, obs_pos[1] + 0.3),
                        attributes={"type": "barrier"},
                        confidence=1.0,
                    )
                )

        # Apply perceptual noise
        is_corrupted = self._apply_perceptual_noise(sg)
        sg.compute_spatial_relations(proximity_threshold=1.0)
        return sg, is_corrupted

    def _apply_perceptual_noise(self, sg: SceneGraph) -> bool:
        """Inject stochastic VLM/perceptual noise into the generated scene graph."""
        cfg = self.noise_config
        nodes_to_remove: List[str] = []
        is_corrupted = False

        for node_id, node in list(sg.nodes.items()):
            # 1. Missed detection (False Negative)
            if self.rng.random() < cfg.missed_detection_rate:
                nodes_to_remove.append(node_id)
                continue

            # 2. Attribute noise
            if self.rng.random() < cfg.attribute_noise_rate:
                if "color" in node.attributes:
                    old_c = node.attributes["color"]
                    new_c = ((old_c + self.rng.randint(1, 3) - 1) % 8) + 1
                    node.attributes["color"] = new_c
                node.confidence *= 0.80

            # 3. Spatial jitter
            if cfg.spatial_jitter_std > 0.0:
                jx = self.rng.gauss(0.0, cfg.spatial_jitter_std)
                jy = self.rng.gauss(0.0, cfg.spatial_jitter_std)
                new_x = node.position[0] + jx
                new_y = node.position[1] + jy
                node.position = (new_x, new_y)
                node.bbox = (node.bbox[0] + jx, node.bbox[1] + jy, node.bbox[2] + jx, node.bbox[3] + jy)
                dist_shift = math.sqrt(jx * jx + jy * jy)
                node.confidence *= max(0.1, 1.0 - 0.5 * dist_shift)

            if node.confidence < cfg.corruption_confidence_threshold:
                is_corrupted = True

        for nid in nodes_to_remove:
            del sg.nodes[nid]
            if "agent" in nid or "target" in nid:
                is_corrupted = True

        # 4. False alarm / Hallucination (False Positive)
        if self.rng.random() < cfg.false_alarm_rate:
            ghost_id = f"ghost_{self.rng.randint(100, 999)}"
            gx = self.rng.uniform(0.0, 5.0)
            gy = self.rng.uniform(0.0, 5.0)
            sg.add_node(
                ObjectNode(
                    object_id=ghost_id,
                    category="hallucination",
                    position=(gx, gy),
                    bbox=(gx - 0.2, gy - 0.2, gx + 0.2, gy + 0.2),
                    attributes={"artifact": True},
                    confidence=0.35,  # Low confidence
                )
            )
            is_corrupted = True

        return is_corrupted
