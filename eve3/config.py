"""Configuration settings for EVE-3 runtime."""

from dataclasses import dataclass, field
from pathlib import Path


VALID_PROPOSER_MODES = (
    "leaky_templates",
    "generic_enumeration",
    "llm_only",
    "llm_plus_enumeration",
)

VALID_PROBE_STRATEGIES = (
    "bayesian_ig",
    "random",
    "none",
)

VALID_PRIOR_MODES = (
    "mdl",
    "uniform",
    "llm",
)


@dataclass
class EveConfig:
    # Storage & Persistence
    workspace_root: Path = field(default_factory=lambda: Path.cwd())
    db_path: Path = field(default_factory=lambda: Path.cwd() / "eve3_knowledge.sqlite")
    
    # System 1: Hypothesis Proposer
    proposer_mode: str = "generic_enumeration"
    enumerator_max_depth: int = 4
    model_name: str = "mlx-community/Qwen2.5-Coder-3B-Instruct-4bit"
    max_hypotheses_per_round: int = 16
    generation_temperature: float = 0.7
    sandbox_timeout_seconds: float = 1.0
    max_ast_depth: int = 8
    sandbox_max_output_size: int = 1000
    sandbox_max_integer_bits: int = 2048
    sandbox_max_recursion_depth: int = 50
    sandbox_step_budget: int = 20000
    
    # System 2: Bayesian Active Falsification
    noise_model: str = "deterministic"
    probe_strategy: str = "bayesian_ig"
    prior_mode: str = "mdl"
    mdl_prior_decay: float = 1.0
    probe_cost_penalty_lambda: float = 0.05
    laplace_smoothing_epsilon: float = 1e-6
    max_falsification_rounds: int = 15
    max_repropose_rounds: int = 3
    falsification_probe_pool_size: int = 32
    
    # System 3: Knowledge Crystallization & Compression
    crystallization_threshold_rounds: int = 5
    library_size_penalty_gamma: float = 1.2
    enable_task_family_weighting: bool = True
    max_active_library_operators: int = 8

    def __post_init__(self) -> None:
        if self.proposer_mode not in VALID_PROPOSER_MODES:
            raise ValueError(
                f"Invalid proposer_mode {self.proposer_mode!r}; must be one of {VALID_PROPOSER_MODES}"
            )
        if self.probe_strategy not in VALID_PROBE_STRATEGIES:
            raise ValueError(
                f"Invalid probe_strategy {self.probe_strategy!r}; must be one of {VALID_PROBE_STRATEGIES}"
            )
        if self.prior_mode not in VALID_PRIOR_MODES:
            raise ValueError(
                f"Invalid prior_mode {self.prior_mode!r}; must be one of {VALID_PRIOR_MODES}"
            )
        if self.noise_model != "deterministic" and not self.noise_model.startswith("noisy"):
            raise ValueError(
                f"Invalid noise_model {self.noise_model!r}; must be 'deterministic' or 'noisy(eps)'"
            )
