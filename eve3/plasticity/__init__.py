"""EVE-3 Plasticity Module.

Provides multi-timescale parameter plasticity, adapter banking,
regression gatekeeping, and sleep consolidation interfaces.
"""

from eve3.plasticity.regression_gate import (
    RegressionGate,
    RegressionGateConfig,
    GateResult,
    FamilyEvaluationResult,
)
from eve3.plasticity.adapter_bank import (
    AdapterBank,
    AdapterMetadata,
    BankVersion,
)
from eve3.plasticity.consolidator import (
    Consolidator,
    ConsolidationConfig,
    ConsolidationSample,
    ConsolidationResult,
)

__all__ = [
    "RegressionGate",
    "RegressionGateConfig",
    "GateResult",
    "FamilyEvaluationResult",
    "AdapterBank",
    "AdapterMetadata",
    "BankVersion",
    "Consolidator",
    "ConsolidationConfig",
    "ConsolidationSample",
    "ConsolidationResult",
]
