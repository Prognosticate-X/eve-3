"""Unit tests for Phase 9: Safety Action Limiter and L1/L2 Environments.

Verifies:
1. ActionLimiter magnitude clamping, workspace bounds, E-stop, and human enable switch.
2. Grid spatial operations (rotate, reflect, gravity, color shift).
3. PhysicalSimAdapter 2D dynamics, process noise, and policy rollouts.
"""

import unittest

from eve3.envs.grid_tasks import Grid, GridTaskSuite, generate_random_grid
from eve3.envs.sim_adapter import PhysicalSimAdapter, SimConfig
from eve3.safety.action_limiter import (
    ActionLimiter,
    EmergencyStopActiveError,
    SafetyConfig,
    SafetyViolationError,
)


class TestSafetyAndEnvs(unittest.TestCase):
    """Test suite for safety action limiter and perception/simulation environments."""

    def test_action_limiter_clamping_and_bounds(self):
        """Verify ActionLimiter clamps excessive magnitudes and halts boundary penetration."""
        config = SafetyConfig(
            max_action_magnitude=1.0,
            workspace_min=(-5.0, -5.0),
            workspace_max=(5.0, 5.0),
        )
        limiter = ActionLimiter(config)

        # 1. Magnitude clamping for scalar
        clamped_scalar = limiter.sanitize_action(2.5)
        self.assertEqual(clamped_scalar, 1.0)
        self.assertEqual(limiter.get_incident_count(), 1)

        # 2. Magnitude clamping for 2D vector
        clamped_vec = limiter.sanitize_action([3.0, -2.0], current_position=(0.0, 0.0))
        self.assertEqual(clamped_vec, [1.0, -1.0])

        # 3. Workspace boundary halt: at (4.5, 0.0), commanding (+1.0, 0.0) would exceed +5.0
        limiter.set_state((4.5, 0.0))
        safe_at_boundary = limiter.sanitize_action([1.0, 0.5])
        self.assertEqual(safe_at_boundary[0], 0.0)  # X-velocity halted
        self.assertEqual(safe_at_boundary[1], 0.5)  # Y-velocity permitted

    def test_action_limiter_estop_and_human_enable(self):
        """Verify Emergency Stop and Human Enable switches strictly gate execution."""
        limiter = ActionLimiter()

        # Normal execution
        res = limiter.sanitize_action(0.5)
        self.assertEqual(res, 0.5)

        # 1. Engage Emergency Stop
        limiter.trigger_emergency_stop()
        with self.assertRaises(EmergencyStopActiveError):
            limiter.sanitize_action(0.5)

        # Reset Emergency Stop
        limiter.reset_emergency_stop()
        res = limiter.sanitize_action(0.5)
        self.assertEqual(res, 0.5)

        # 2. Disable Human Enable
        limiter.set_human_enable(False)
        with self.assertRaises(SafetyViolationError):
            limiter.sanitize_action(0.5)

    def test_l1_grid_operations(self):
        """Verify L1 2D visual grid spatial transformations."""
        raw_cells = [
            [1, 2],
            [3, 4],
        ]
        grid = Grid(raw_cells)

        # 1. Rotate 90 CW: [[3, 1], [4, 2]]
        rotated = grid.rotate90_cw()
        self.assertEqual(rotated.cells, [[3, 1], [4, 2]])

        # 2. Reflect Horizontal: [[2, 1], [4, 3]]
        reflected_h = grid.reflect_horizontal()
        self.assertEqual(reflected_h.cells, [[2, 1], [4, 3]])

        # 3. Gravity Down: non-zero blocks drop
        grav_raw = [
            [1, 0],
            [0, 2],
            [3, 0],
        ]
        grav_grid = Grid(grav_raw).gravity_down()
        expected_grav = [
            [0, 0],
            [1, 0],
            [3, 2],
        ]
        self.assertEqual(grav_grid.cells, expected_grav)

        # 4. Standard Grid Suite Tasks
        suite = GridTaskSuite.get_standard_suite()
        self.assertEqual(len(suite), 4)
        for task in suite:
            self.assertEqual(task.task_family, "grid_perception")
            self.assertTrue(len(task.visible_examples) >= 2)
            self.assertTrue(len(task.hidden_tests) >= 4)

    def test_l2_physical_simulation_adapter(self):
        """Verify L2 physical simulation runs dynamics and measures task success predicate."""
        cfg = SimConfig(
            dt=0.1,
            target_pos=(2.0, 2.0),
            target_radius=0.5,
            max_steps_per_episode=20,
        )
        sim = PhysicalSimAdapter(cfg, seed=123)

        # Proportional controller policy: drive towards goal
        def p_controller(obs, goal):
            dx = goal[0] - obs[0]
            dy = goal[1] - obs[1]
            return (0.8 * dx, 0.8 * dy)

        # Evaluate over 5 episodes
        success_rate, avg_steps = sim.evaluate_policy_success_rate(p_controller, num_episodes=5)
        self.assertGreaterEqual(success_rate, 0.80)
        self.assertLess(avg_steps, 20.0)


if __name__ == "__main__":
    unittest.main()
