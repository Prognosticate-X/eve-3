"""Configuration settings for EVE-3 runtime."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EveConfig:
    # Storage & Persistence
    workspace_root: Path = field(default_factory=lambda: Path.cwd())
    db_path: Path = field(default_factory=lambda: Path.cwd() / "eve3_knowledge.sqlite")
    
    # System 1: Hypothesis Proposer
    model_name: str = "mlx-community/Qwen2.5-Coder-3B-Instruct-4bit"
    max_hypotheses_per_round: int = 16
    generation_temperature: float = 0.7
    sandbox_timeout_seconds: float = 1.0
    max_ast_depth: int = 8
    
    # System 2: Bayesian Active Falsification
    probe_cost_penalty_lambda: float = 0.05
    laplace_smoothing_epsilon: float = 1e-6
    max_falsification_rounds: int = 15
    falsification_probe_pool_size: int = 32
    
    # System 3: Knowledge Crystallization & Compression
    crystallization_threshold_rounds: int = 5
    library_size_penalty_gamma: float = 1.2
    enable_task_family_weighting: bool = True
