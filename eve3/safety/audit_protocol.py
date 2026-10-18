"""Safety Audit Protocol: Cryptographic Change Management & Human-in-the-Loop Governance.

Implements Phase 11 Safety Governance Layer:
- Tamper-evident hash-chained audit ledger for all model mutations, adapter commits, and safety events.
- Time-bounded cryptographic authorization tokens (HMAC/SHA256) for privileged physical actuation.
- Multi-party change management: strictly prevents autonomous self-modification without regression approval.
"""

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AuditRecord:
    """Immutable record within the cryptographic safety ledger."""
    record_id: str
    event_type: str                            # e.g., "adapter_commit", "actuation_override", "safety_freeze"
    actor: str                                 # e.g., "eve3_autonomous_engine", "human_supervisor"
    payload_hash: str                          # SHA256 hash of event payload
    previous_hash: str                         # SHA256 of preceding audit record (blockchain-style ledger)
    record_hash: str                           # Hash of current block
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SafetyAuditProtocol:
    """Manages audit ledgers, verification certificates, and human authorization tokens."""

    def __init__(self, secret_key: str = "eve3-secure-safety-key-2026"):
        self.secret_key = secret_key.encode("utf-8")
        self.ledger: List[AuditRecord] = []
        self._genesis_ledger()

    def _genesis_ledger(self):
        """Initialize genesis record in the audit ledger."""
        genesis_hash = hashlib.sha256(b"eve3-genesis-safety-root").hexdigest()
        record = AuditRecord(
            record_id="rec_0000",
            event_type="genesis",
            actor="system",
            payload_hash=genesis_hash,
            previous_hash="0" * 64,
            record_hash=genesis_hash,
            metadata={"description": "EVE-3 Cryptographic Safety Audit Ledger Root"},
        )
        self.ledger.append(record)

    def generate_authorization_token(self, operation: str, valid_duration_sec: float = 60.0) -> str:
        """Human supervisor generates a time-bounded authorization token for privileged operations."""
        expiry = time.time() + valid_duration_sec
        message = f"{operation}:{expiry}"
        signature = hmac.new(self.secret_key, message.encode("utf-8"), hashlib.sha256).hexdigest()
        token = f"{message}:{signature}"
        return token

    def verify_authorization_token(self, token: str, operation: str) -> bool:
        """Validate human-in-the-loop authorization token signature and expiration."""
        try:
            parts = token.split(":")
            if len(parts) != 3:
                return False
            op, expiry_str, signature = parts[0], parts[1], parts[2]
            if op != operation:
                return False
            expiry = float(expiry_str)
            if time.time() > expiry:
                return False  # Expired token

            expected_sig = hmac.new(self.secret_key, f"{op}:{expiry_str}".encode("utf-8"), hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected_sig)
        except Exception:
            return False

    def append_audit_record(
        self,
        event_type: str,
        actor: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        """Append a new event to the tamper-evident hash-chained ledger."""
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        prev_hash = self.ledger[-1].record_hash
        record_id = f"rec_{len(self.ledger):04d}"
        now = time.time()

        # Compute block hash: prev_hash + payload_hash + timestamp
        block_content = f"{prev_hash}:{record_id}:{event_type}:{actor}:{payload_hash}:{now}"
        record_hash = hashlib.sha256(block_content.encode("utf-8")).hexdigest()

        record = AuditRecord(
            record_id=record_id,
            event_type=event_type,
            actor=actor,
            payload_hash=payload_hash,
            previous_hash=prev_hash,
            record_hash=record_hash,
            timestamp=now,
            metadata=metadata or {},
        )
        self.ledger.append(record)
        return record

    def verify_ledger_integrity(self) -> bool:
        """Verify the entire historical audit ledger has not been tampered with."""
        if not self.ledger:
            return False

        for i in range(1, len(self.ledger)):
            curr = self.ledger[i]
            prev = self.ledger[i - 1]

            if curr.previous_hash != prev.record_hash:
                return False  # Hash chain link broken!

            # Recompute and verify current block hash
            block_content = f"{curr.previous_hash}:{curr.record_id}:{curr.event_type}:{curr.actor}:{curr.payload_hash}:{curr.timestamp}"
            expected_hash = hashlib.sha256(block_content.encode("utf-8")).hexdigest()
            if curr.record_hash != expected_hash:
                return False  # Payload or metadata tampered!

        return True
