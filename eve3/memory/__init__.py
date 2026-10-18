"""EVE-3 Memory Management: Three-Tier Cognitive Memory, Retention Decay, and Provenance.

Implements Phase 8 Memory Management & Library Compaction:
- WorkingMemory: Volatile short-term execution scratchpad.
- EpisodicMemory: Search trajectory management and lossless summarization.
- SemanticMemory: Two-tier Hot/Cold knowledge store with dynamic retention decay.
- MemoryProvenanceManager: Lineage recording, snapshots, and transactional rollback.
"""

from eve3.memory.provenance import (
    MemoryProvenanceManager,
    MemorySnapshot,
    ProvenanceEvent,
    ProvenanceRecord,
)
from eve3.memory.tiers import (
    EpisodicMemory,
    EpisodicSummary,
    RetentionConfig,
    SemanticMemory,
    WorkingMemory,
)

__all__ = [
    "WorkingMemory",
    "EpisodicMemory",
    "EpisodicSummary",
    "SemanticMemory",
    "RetentionConfig",
    "MemoryProvenanceManager",
    "MemorySnapshot",
    "ProvenanceEvent",
    "ProvenanceRecord",
]
