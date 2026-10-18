"""EVE-3 Explorer: Autonomous Curriculum, Task Generation, and Coverage Guards.

Implements Phase 7 Autonomous Discovery capabilities:
- Task generation via operator combination, mutation, and failed task decomposition.
- Zone of Proximal Development (ZPD) learnability filtering [0.2, 0.8].
- Multi-objective task scoring (IG, Compression, Learning Progress, Redundancy).
- Coverage clustering entropy tracking and anti-collapse guardrails.
- Metamorphic blindspot testing for candidate programs.
"""

from eve3.explorer.curriculum import Curriculum, CurriculumConfig
from eve3.explorer.coverage import CoverageGuard, CoverageConfig, MetamorphicValidator

__all__ = [
    "Curriculum",
    "CurriculumConfig",
    "CoverageGuard",
    "CoverageConfig",
    "MetamorphicValidator",
]
