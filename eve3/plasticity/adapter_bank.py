"""AdapterBank: Multi-Timescale LoRA Adapter Management, Routing, and Rollback.

Implements Task Family Adapter Isolation and Versioned Rollbacks:
- Isolated adapters per task family to prevent cross-family interference.
- Routing via family classification / lexical heuristics.
- Snapshot and rollback mechanism governed by the Regression Gate.
"""

from dataclasses import dataclass, field
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from eve3.plasticity.regression_gate import GateResult


@dataclass
class BankVersion:
    """Immutable snapshot of the adapter bank state."""
    version_id: int
    timestamp: str
    description: str
    active_adapter_ids: Dict[str, str]  # family -> adapter_id
    checksum: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "timestamp": self.timestamp,
            "description": self.description,
            "active_adapter_ids": self.active_adapter_ids,
            "checksum": self.checksum,
        }


@dataclass
class AdapterMetadata:
    """Metadata describing an isolated task family LoRA adapter."""
    adapter_id: str
    family: str
    base_ckpt: str = "default_base"
    version: int = 1
    rank: int = 8
    alpha: float = 16.0
    status: str = "candidate"  # candidate, active, deprecated, reverted
    weights_path: Optional[str] = None
    gate_result: Optional[Dict[str, Any]] = None
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "family": self.family,
            "base_ckpt": self.base_ckpt,
            "version": self.version,
            "rank": self.rank,
            "alpha": self.alpha,
            "status": self.status,
            "weights_path": self.weights_path,
            "gate_result": self.gate_result,
            "created_at": self.created_at,
        }


class AdapterBank:
    """Manages versioned, task-family-isolated adapters with regression gatekeeping."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or ":memory:"
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()
        self._active_adapters: Dict[str, str] = {}  # family -> adapter_id
        self._version_counter: int = 0
        self._snapshots: Dict[int, BankVersion] = {}
        # Take initial base snapshot
        self.snapshot(description="Initial base model state")

    def close(self):
        """Close database connection."""
        if hasattr(self, "_conn") and self._conn:
            try:
                self._conn.close()
                self._conn = None
            except Exception:
                pass

    def __del__(self):
        self.close()

    def _init_db(self):
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS adapters (
                adapter_id TEXT PRIMARY KEY,
                family TEXT NOT NULL,
                base_ckpt TEXT NOT NULL,
                version INTEGER NOT NULL,
                rank INTEGER NOT NULL,
                alpha REAL NOT NULL,
                status TEXT NOT NULL,
                weights_path TEXT,
                gate_result TEXT,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                version_id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                description TEXT NOT NULL,
                active_adapter_ids TEXT NOT NULL,
                checksum TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def route(self, task_desc: str, family_hint: Optional[str] = None) -> Optional[str]:
        """Route task to active adapter ID based on family hint or task semantics."""
        target_family = family_hint
        if not target_family:
            desc_lower = task_desc.lower()
            if any(k in desc_lower for k in ["filter", "even", "odd", "positive", "greater", "gt"]):
                if any(k in desc_lower for k in ["sum", "count", "reverse"]):
                    target_family = "list_composition"
                else:
                    target_family = "list_filtering"
            elif any(k in desc_lower for k in ["map", "increment", "decrement", "double", "multiply"]):
                target_family = "list_mapping"
            elif any(k in desc_lower for k in ["sum", "total", "length", "count"]):
                target_family = "list_reduction"
            elif any(k in desc_lower for k in ["reverse", "tail", "head", "slice"]):
                target_family = "list_structural"
            elif any(k in desc_lower for k in ["then", "and", "compose"]):
                target_family = "list_composition"

        if target_family and target_family in self._active_adapters:
            return self._active_adapters[target_family]
        return None

    def create(
        self,
        family: str,
        base_ckpt: str = "default_base",
        rank: int = 8,
        alpha: float = 16.0,
        weights_path: Optional[str] = None,
    ) -> str:
        """Create a candidate adapter record in the bank."""
        adapter_id = f"lora_{family}_{uuid.uuid4().hex[:6]}"
        metadata = AdapterMetadata(
            adapter_id=adapter_id,
            family=family,
            base_ckpt=base_ckpt,
            version=1,
            rank=rank,
            alpha=alpha,
            status="candidate",
            weights_path=weights_path,
        )
        self._save_adapter(metadata)
        return adapter_id

    def commit(
        self,
        adapter_id: str,
        gate_result: GateResult,
        description: str = "",
    ) -> BankVersion:
        """Commit candidate adapter to active status if regression gate passed."""
        metadata = self.get_adapter(adapter_id)
        if metadata is None:
            raise KeyError(f"Adapter '{adapter_id}' not found.")

        metadata.gate_result = gate_result.to_dict()

        if not gate_result.passed:
            metadata.status = "reverted"
            self._save_adapter(metadata)
            raise ValueError(
                f"Regression gate failed for adapter '{adapter_id}': "
                f"{'; '.join(gate_result.rejection_reasons)}"
            )

        # Deprecate previous active adapter for this family if one exists
        old_active_id = self._active_adapters.get(metadata.family)
        if old_active_id and old_active_id != adapter_id:
            old_meta = self.get_adapter(old_active_id)
            if old_meta:
                old_meta.status = "deprecated"
                self._save_adapter(old_meta)

        metadata.status = "active"
        self._save_adapter(metadata)
        self._active_adapters[metadata.family] = adapter_id

        desc = description or f"Activated {adapter_id} for family {metadata.family}"
        return self.snapshot(description=desc)

    def snapshot(self, description: str = "") -> BankVersion:
        """Create an immutable versioned snapshot of currently active adapters."""
        self._version_counter += 1
        active_copy = dict(self._active_adapters)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        raw_repr = f"{self._version_counter}:{json.dumps(active_copy, sort_keys=True)}"
        checksum = hashlib.sha256(raw_repr.encode("utf-8")).hexdigest()[:16]

        snap = BankVersion(
            version_id=self._version_counter,
            timestamp=timestamp,
            description=description,
            active_adapter_ids=active_copy,
            checksum=checksum,
        )
        self._snapshots[self._version_counter] = snap

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO snapshots 
            (version_id, timestamp, description, active_adapter_ids, checksum)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                snap.version_id,
                snap.timestamp,
                snap.description,
                json.dumps(snap.active_adapter_ids),
                snap.checksum,
            ),
        )
        self._conn.commit()

        return snap

    def rollback(self, target_version_id: int) -> bool:
        """Rollback active adapters to a previously recorded snapshot."""
        if target_version_id not in self._snapshots:
            # Check db
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT timestamp, description, active_adapter_ids, checksum FROM snapshots WHERE version_id = ?",
                (target_version_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            self._snapshots[target_version_id] = BankVersion(
                version_id=target_version_id,
                timestamp=row[0],
                description=row[1],
                active_adapter_ids=json.loads(row[2]),
                checksum=row[3],
            )

        target_snap = self._snapshots[target_version_id]

        # Deactivate adapters that shouldn't be active
        for family, active_id in list(self._active_adapters.items()):
            if family not in target_snap.active_adapter_ids or target_snap.active_adapter_ids[family] != active_id:
                meta = self.get_adapter(active_id)
                if meta:
                    meta.status = "reverted"
                    self._save_adapter(meta)

        self._active_adapters = dict(target_snap.active_adapter_ids)
        for adapter_id in self._active_adapters.values():
            meta = self.get_adapter(adapter_id)
            if meta:
                meta.status = "active"
                self._save_adapter(meta)

        # Snapshot the rollback event
        self.snapshot(description=f"Rolled back to version {target_version_id}")
        return True

    def get_adapter(self, adapter_id: str) -> Optional[AdapterMetadata]:
        """Fetch adapter metadata by ID."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM adapters WHERE adapter_id = ?", (adapter_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return AdapterMetadata(
            adapter_id=row[0],
            family=row[1],
            base_ckpt=row[2],
            version=row[3],
            rank=row[4],
            alpha=row[5],
            status=row[6],
            weights_path=row[7],
            gate_result=json.loads(row[8]) if row[8] else None,
            created_at=row[9],
        )

    def get_active_adapter(self, family: str) -> Optional[AdapterMetadata]:
        """Fetch current active adapter metadata for a task family."""
        adapter_id = self._active_adapters.get(family)
        if adapter_id:
            return self.get_adapter(adapter_id)
        return None

    def list_adapters(self, family: Optional[str] = None) -> List[AdapterMetadata]:
        """List all adapters in the bank."""
        cursor = self._conn.cursor()
        if family:
            cursor.execute("SELECT * FROM adapters WHERE family = ?", (family,))
        else:
            cursor.execute("SELECT * FROM adapters")
        rows = cursor.fetchall()
        return [
            AdapterMetadata(
                adapter_id=r[0],
                family=r[1],
                base_ckpt=r[2],
                version=r[3],
                rank=r[4],
                alpha=r[5],
                status=r[6],
                weights_path=r[7],
                gate_result=json.loads(r[8]) if r[8] else None,
                created_at=r[9],
            )
            for r in rows
        ]

    def _save_adapter(self, meta: AdapterMetadata):
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO adapters
            (adapter_id, family, base_ckpt, version, rank, alpha, status, weights_path, gate_result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meta.adapter_id,
                meta.family,
                meta.base_ckpt,
                meta.version,
                meta.rank,
                meta.alpha,
                meta.status,
                meta.weights_path,
                json.dumps(meta.gate_result) if meta.gate_result else None,
                meta.created_at,
            ),
        )
        self._conn.commit()
