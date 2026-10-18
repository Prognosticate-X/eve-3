"""Sim Adapter: L2 Physical Simulation Environment & Policy Interface.

Implements Phase 9 L2 Physical Simulation Substrate:
- Continuous 2D dynamical agent simulation with Gaussian process/observation noise.
- Direct integration with ActionLimiter safety layer (workspace bounds, velocity caps, E-stop).
- Formal task success predicates (target acquisition, stability).
- Policy evaluation harness over multi-episode stochastic rollouts.
"""

from dataclasses import dataclass, field
import math
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from eve3.safety.action_limiter import ActionLimiter, SafetyConfig


@dataclass
class SimConfig:
    """Simulation physical parameters and noise characteristics."""
    dt: float = 0.1                      # Time step (seconds)
    damping: float = 0.2                 # Velocity friction / damping coefficient
    process_noise_std: float = 0.05      # Standard deviation of dynamic actuation noise
    obs_noise_std: float = 0.02          # Standard deviation of sensor observation noise
    target_pos: Tuple[float, float] = (5.0, 5.0)  # Goal location
    target_radius: float = 0.8           # Goal acceptance radius
    max_steps_per_episode: int = 50      # Horizon limit


@dataclass
class SimStepResult:
    """Single-step simulation transition record."""
    state: Tuple[float, float, float, float]  # (x, y, vx, vy)
    observation: Tuple[float, float]          # (noisy_x, noisy_y)
    action_taken: Tuple[float, float]
    reward: float
    done: bool
    success: bool
    info: Dict[str, Any] = field(default_factory=dict)


class PhysicalSimAdapter:
    """Simulates 2D physical control dynamics under noise, governed by ActionLimiter."""

    def __init__(
        self,
        config: Optional[SimConfig] = None,
        safety_limiter: Optional[ActionLimiter] = None,
        seed: Optional[int] = None,
    ):
        self.config = config or SimConfig()
        self.limiter = safety_limiter or ActionLimiter(
            SafetyConfig(
                max_action_magnitude=1.5,
                workspace_min=(-10.0, -10.0),
                workspace_max=(10.0, 10.0),
            )
        )
        self.rng = random.Random(seed if seed is not None else 42)
        
        # State: x, y, vx, vy
        self.state: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.step_count: int = 0

    def reset(self, initial_pos: Optional[Tuple[float, float]] = None) -> Tuple[float, float]:
        """Reset simulation state to origin or specified start."""
        if initial_pos is not None:
            x, y = initial_pos
        else:
            x, y = 0.0, 0.0
        self.state = (x, y, 0.0, 0.0)
        self.step_count = 0
        self.limiter.set_state((x, y))
        return self._get_observation()

    def step(self, action: Tuple[float, float]) -> SimStepResult:
        """Step physics simulation forward by dt with safety clamping and noise."""
        self.step_count += 1
        x, y, vx, vy = self.state

        # 1. Pass action through safety limiter
        safe_action = self.limiter.sanitize_action(action, current_position=(x, y))
        ax, ay = safe_action[0], safe_action[1]

        # 2. Physics update with process noise
        dt = self.config.dt
        gamma = self.config.damping
        noise_x = self.rng.gauss(0.0, self.config.process_noise_std)
        noise_y = self.rng.gauss(0.0, self.config.process_noise_std)

        # Acceleration with damping and perturbation
        acc_x = ax - gamma * vx + noise_x
        acc_y = ay - gamma * vy + noise_y

        new_vx = vx + acc_x * dt
        new_vy = vy + acc_y * dt

        new_x = x + new_vx * dt
        new_y = y + new_vy * dt

        self.state = (new_x, new_y, new_vx, new_vy)
        self.limiter.set_state((new_x, new_y))

        # 3. Check goal distance and termination
        tx, ty = self.config.target_pos
        dist_to_goal = math.sqrt((new_x - tx) ** 2 + (new_y - ty) ** 2)
        success = dist_to_goal <= self.config.target_radius
        done = success or (self.step_count >= self.config.max_steps_per_episode)

        reward = 10.0 if success else -0.1 * dist_to_goal
        obs = self._get_observation()

        return SimStepResult(
            state=self.state,
            observation=obs,
            action_taken=(ax, ay),
            reward=reward,
            done=done,
            success=success,
            info={"distance_to_goal": dist_to_goal, "step": self.step_count},
        )

    def _get_observation(self) -> Tuple[float, float]:
        """Generate noisy sensor observation of agent's current position."""
        x, y, _, _ = self.state
        nx = self.rng.gauss(0.0, self.config.obs_noise_std)
        ny = self.rng.gauss(0.0, self.config.obs_noise_std)
        return (x + nx, y + ny)

    def rollout_policy(
        self,
        policy_fn: Callable[[Tuple[float, float], Tuple[float, float]], Tuple[float, float]],
        initial_pos: Optional[Tuple[float, float]] = None,
    ) -> List[SimStepResult]:
        """Execute a full closed-loop trajectory rollout under policy_fn(obs, goal)."""
        obs = self.reset(initial_pos)
        trajectory: List[SimStepResult] = []
        done = False

        while not done:
            action = policy_fn(obs, self.config.target_pos)
            step_res = self.step(action)
            trajectory.append(step_res)
            obs = step_res.observation
            done = step_res.done

        return trajectory

    def evaluate_policy_success_rate(
        self,
        policy_fn: Callable[[Tuple[float, float], Tuple[float, float]], Tuple[float, float]],
        num_episodes: int = 10,
    ) -> Tuple[float, float]:
        """Evaluate policy over multiple stochastic episodes.
        
        Returns (success_rate, avg_steps).
        """
        successes = 0
        total_steps = 0

        for _ in range(num_episodes):
            traj = self.rollout_policy(policy_fn)
            if traj and traj[-1].success:
                successes += 1
            total_steps += len(traj)

        success_rate = successes / num_episodes if num_episodes > 0 else 0.0
        avg_steps = total_steps / num_episodes if num_episodes > 0 else 0.0
        return success_rate, avg_steps
