"""Exploration Policy & Configuration Versioning for EVE-3.

Defines parameterizable exploration heuristics, stopping rules, and probe priorities,
enabling principled off-policy evaluation and versioned rollback.
"""

from dataclasses import dataclass, field
import datetime
from typing import Any, Callable, Dict, Optional
import uuid


@dataclass
class ExplorationPolicy:
    """Configurable, versioned exploration and probe selection policy."""
    policy_id: str = field(default_factory=lambda: f"pol_{uuid.uuid4().hex[:8]}")
    version: str = "v1.0.0"
    name: str = "balanced_bayesian"
    probe_cost_penalty_lambda: float = 0.05
    max_falsification_rounds: int = 8
    stop_confidence_threshold: float = 0.95
    verification_priority_weight: float = 5.0
    probe_priority_weight: float = 1.0
    proposal_priority_weight: float = 0.5
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def score_node(self, action_type: str, cost: float = 1.0) -> float:
        """Score an available action under this policy."""
        base_priority = 1.0
        if action_type in ("verify", "verified"):
            base_priority = self.verification_priority_weight
        elif action_type in ("probe", "falsify"):
            base_priority = self.probe_priority_weight
        elif action_type == "propose":
            base_priority = self.proposal_priority_weight

        # Trade off priority against cost
        return base_priority - self.probe_cost_penalty_lambda * cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "name": self.name,
            "probe_cost_penalty_lambda": self.probe_cost_penalty_lambda,
            "max_falsification_rounds": self.max_falsification_rounds,
            "stop_confidence_threshold": self.stop_confidence_threshold,
            "verification_priority_weight": self.verification_priority_weight,
            "probe_priority_weight": self.probe_priority_weight,
            "proposal_priority_weight": self.proposal_priority_weight,
            "created_at": self.created_at,
        }
