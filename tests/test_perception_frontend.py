"""Unit tests for Phase 10: L3 Perception Front-End & Symbolic State.

Verifies:
1. SceneGraph representation, ObjectNode, RelationEdge, and PredicateState.
2. Spatial topology computation (left_of, right_of, above, below, touching).
3. PerceptionEncoder grid connected-component segmentation.
4. Continuous simulation state encoding to SceneGraph.
5. Perceptual noise injection, confidence discounting, and corruption detection.
"""

import unittest

from eve3.envs.grid_tasks import Grid
from eve3.perception.encoder import PerceptionEncoder, PerceptionNoiseConfig
from eve3.perception.symbolic_state import (
    ObjectNode,
    PredicateState,
    RelationEdge,
    SceneGraph,
)


class TestPerceptionFrontend(unittest.TestCase):
    """Test suite for Phase 10 L3 Perception Front-End and Scene Graph representations."""

    def test_scenegraph_and_spatial_relations(self):
        """Verify SceneGraph construction and spatial relationship derivation."""
        sg = SceneGraph("test_scene")

        # Add two objects: n1 at (1.0, 1.0) and n2 at (3.0, 1.0)
        n1 = ObjectNode("obj1", "block", position=(1.0, 1.0), bbox=(0.8, 0.8, 1.2, 1.2))
        n2 = ObjectNode("obj2", "block", position=(3.0, 1.0), bbox=(2.8, 0.8, 3.2, 1.2))
        sg.add_node(n1)
        sg.add_node(n2)

        sg.compute_spatial_relations(proximity_threshold=2.5)

        # n1 is left_of n2 (dx = 2.0 > 0.2)
        rel_left = sg.get_relations_between("obj1", "obj2")
        self.assertTrue(any(e.relation_type == "left_of" for e in rel_left))

        # n2 is right_of n1
        rel_right = sg.get_relations_between("obj2", "obj1")
        self.assertTrue(any(e.relation_type == "right_of" for e in rel_right))

        # Distance is 2.0 <= 2.5 proximity threshold -> touching relation exists
        self.assertTrue(any(e.relation_type == "touching" for e in rel_left))

    def test_predicate_state_evaluation(self):
        """Verify high-level predicate extraction from SceneGraph."""
        sg = SceneGraph("nav_scene")
        # Agent touching target
        ag = ObjectNode("agent", "agent", position=(2.0, 2.0), bbox=(1.8, 1.8, 2.2, 2.2), confidence=0.95)
        tg = ObjectNode("target", "target", position=(2.2, 2.0), bbox=(2.0, 1.8, 2.4, 2.2), confidence=0.90)
        sg.add_node(ag)
        sg.add_node(tg)
        sg.compute_spatial_relations(proximity_threshold=0.5)

        pred_state = sg.evaluate_predicate_state()
        self.assertTrue(pred_state.is_satisfied("goal_reached"))
        self.assertTrue(pred_state.is_satisfied("aligned"))
        self.assertTrue(pred_state.is_satisfied("collision_free"))

    def test_grid_segmentation_encoding(self):
        """Verify PerceptionEncoder parses a 2D integer Grid into discrete connected objects."""
        encoder = PerceptionEncoder(seed=42)

        # Grid with two distinct colored components:
        # 1 1 0
        # 1 0 0
        # 0 2 2
        cells = [
            [1, 1, 0],
            [1, 0, 0],
            [0, 2, 2],
        ]
        grid = Grid(cells)
        sg, is_corrupted = encoder.encode_grid(grid)

        self.assertFalse(is_corrupted)
        self.assertEqual(len(sg.nodes), 2)  # Two connected components: color 1 and color 2

        # Check color 1 component (area = 3)
        node_c1 = [n for n in sg.nodes.values() if n.attributes.get("color") == 1][0]
        self.assertEqual(node_c1.attributes["area"], 3)

        # Check color 2 component (area = 2)
        node_c2 = [n for n in sg.nodes.values() if n.attributes.get("color") == 2][0]
        self.assertEqual(node_c2.attributes["area"], 2)

    def test_sim_state_encoding_and_noise_corruption(self):
        """Verify simulation state encoding and perceptual noise degradation."""
        # 1. Clean encoding
        encoder_clean = PerceptionEncoder(PerceptionNoiseConfig(), seed=42)
        sg_clean, is_corrupted = encoder_clean.encode_sim_state(
            agent_pos=(0.0, 0.0),
            target_pos=(5.0, 5.0),
            obstacles=[(2.0, 2.0)],
        )
        self.assertFalse(is_corrupted)
        self.assertEqual(len(sg_clean.nodes), 3)

        # 2. Noisy encoding with spatial jitter and attribute corruption
        noise_cfg = PerceptionNoiseConfig(
            spatial_jitter_std=2.0,
            false_alarm_rate=1.0,
            corruption_confidence_threshold=0.6,
        )
        encoder_noisy = PerceptionEncoder(noise_cfg, seed=123)
        sg_noisy, is_corrupted_noisy = encoder_noisy.encode_sim_state(
            agent_pos=(0.0, 0.0),
            target_pos=(5.0, 5.0),
        )
        # Jitter and false alarm should trigger corruption flag (ready for h_empty)
        self.assertTrue(is_corrupted_noisy)

    def test_scenegraph_serialization_and_distance(self):
        """Verify SceneGraph dict serialization and graph edit distance."""
        sg1 = SceneGraph("scene_a")
        sg1.add_node(ObjectNode("n1", "cat_a", (0.0, 0.0), (0, 0, 1, 1)))
        sg1.add_node(ObjectNode("n2", "cat_b", (2.0, 0.0), (2, 0, 3, 1)))
        sg1.compute_spatial_relations(proximity_threshold=3.0)

        # Roundtrip serialization
        data = sg1.to_dict()
        sg2 = SceneGraph.from_dict(data)
        self.assertEqual(len(sg2.nodes), 2)
        self.assertEqual(len(sg2.edges), len(sg1.edges))

        # Identical graph distance must be 0.0
        dist_same = sg1.compute_graph_distance(sg2)
        self.assertEqual(dist_same, 0.0)

        # Distinct graph distance must be > 0.0
        sg3 = SceneGraph("scene_c")
        sg3.add_node(ObjectNode("n1", "cat_z", (0.0, 0.0), (0, 0, 1, 1)))
        dist_diff = sg1.compute_graph_distance(sg3)
        self.assertGreater(dist_diff, 0.5)


if __name__ == "__main__":
    unittest.main()
