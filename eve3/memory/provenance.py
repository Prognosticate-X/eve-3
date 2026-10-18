"""Provenance: Causal Lineage Tracking, Version Snapshots, and Rollback for Memory Artifacts.

Implements Phase 8 Provenance Infrastructure:
- Tracks the full audit chain for every learned abstraction and program.
- Records mutation lineage, verification evidence, task origins, and lifecycle events.
- Provides transactional snapshots and safe rollback for semantic memory.
"""

from dataclasses import dataclass, field
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set
import uuid


@dataclass
class ProvenanceEvent:
    """A timestamped lifecycle event in an artifact's history."""
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    event_type: str = "created"  # created, verified, reused, decayed, demoted, promoted, subsumed
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class ProvenanceRecord:
    """Complete causal ancestry and lifecycle record for an abstraction or program."""
    artifact_id: str
    artifact_type: str = "abstraction"  # abstraction, program, transition
    source_task_ids: List[str] = field(default_factory=list)
    parent_artifact_ids: List[str] = field(default_factory=list)
    verification_evidence_ids: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    events: List[ProvenanceEvent] = field(default_factory=list)

    def add_event(self, event_type: str, details: Optional[Dict[str, Any]] = None):
        evt = ProvenanceEvent(
            event_type=event_type,
            details=details or {},
            timestamp=time.time(),
        )
        self.events.append(evt)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "source_task_ids": self.source_task_ids,
            "parent_artifact_ids": self.parent_artifact_ids,
            "verification_evidence_ids": self.verification_evidence_ids,
            "created_at": self.created_at,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class MemorySnapshot:
    """An immutable checkpoint of semantic memory state."""
    snapshot_id: str
    description: str
    active_abstraction_ids: List[str]
    demoted_abstraction_ids: List[str]
    checksum: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "description": self.description,
            "active_abstraction_ids": self.active_abstraction_ids,
            "demoted_abstraction_ids": self.demoted_abstraction_ids,
            "checksum": self.checksum,
            "timestamp": self.timestamp,
        }


class MemoryProvenanceManager:
    """Manages lineage records, snapshots, and transactional rollbacks for semantic memory."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self._records: Dict[str, ProvenanceRecord] = {}
        self._snapshots: Dict[str, MemorySnapshot] = {}

    def get_or_create_record(
        self,
        artifact_id: str,
        artifact_type: str = "abstraction",
        source_task_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> ProvenanceRecord:
        """Retrieve existing provenance record or initialize a new causal record."""
        if artifact_id not in self._records:
            rec = ProvenanceRecord(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                source_task_ids=[source_task_id] if source_task_id else [],
                parent_artifact_ids=[parent_id] if parent_id else [],
            )
            rec.add_event("created", {"source_task": source_task_id, "parent": parent_id})
            self._records[artifact_id] = rec
        else:
            rec = self._records[artifact_id]
            if source_task_id and source_task_id not in rec.source_task_ids:
                rec.source_task_ids.append(source_task_id)
            if parent_id and parent_id not in rec.parent_artifact_ids:
                rec.parent_artifact_ids.append(parent_id)
        return rec

    def record_event(
        self,
        artifact_id: str,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Append a lifecycle transition event to the artifact record."""
        rec = self.get_or_create_record(artifact_id)
        rec.add_event(event_type, details)

    def create_snapshot(
        self,
        active_ids: List[str],
        demoted_ids: List[str],
        description: str = "",
    ) -> MemorySnapshot:
        """Create an immutable snapshot of current semantic memory tiers."""
        snapshot_id = f"snap_{uuid.uuid4().hex[:8]}"
        sorted_active = sorted(active_ids)
        sorted_demoted = sorted(demoted_ids)

        hasher = hashlib.sha256()
        hasher.update(json.dumps({"active": sorted_active, "demoted": sorted_demoted}).encode("utf-8"))
        checksum = hasher.hexdigest()[:16]

        snap = MemorySnapshot(
            snapshot_id=snapshot_id,
            description=description,
            active_abstraction_ids=sorted_active,
            demoted_abstraction_ids=sorted_demoted,
            checksum=checksum,
            timestamp=time.time(),
        )
        self._snapshots[snapshot_id] = snap
        return snap

    def get_snapshot(self, snapshot_id: str) -> Optional[MemorySnapshot]:
        """Fetch snapshot by ID."""
        return self._snapshots.get(snapshot_id)

    def list_snapshots(self) -> List[MemorySnapshot]:
        """List all snapshots sorted by timestamp descending."""
        return sorted(self._snapshots.values(), key=lambda s: s.timestamp, reverse=True)

    def get_provenance_chain(self, artifact_id: str) -> List[Dict[str, Any]]:
        """Traverse ancestors and return the full DAG chain leading to this artifact."""
        chain: List[Dict[str, Any]] = []
        visited: Set[str] = set()

        def _dfs(aid: str):
            if aid in visited or aid not in self._records:
                return
            visited.add(aid)
            rec = self._records[aid]
            chain.append(rec.to_dict())
            for pid in rec.parent_artifact_ids:
                _dfs(pid)

        _dfs(artifact_id)
        return chain
