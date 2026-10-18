"""Core Data Models and Verification Evidence Architecture for EVE-3.

Defines rigorous metadata tracking for candidates, verification evidence,
and audit trails, preventing false claims of verification.
"""

from dataclasses import dataclass, field
import datetime
import time
from typing import Any, Dict, List, Optional
import uuid

from eve3.dsl.ast import ASTNode
from eve3.dsl.interpreter import SExprParser


class CandidateStatus:
    CANDIDATE = "candidate"                       # Proposed, unverified
    CONSISTENT = "consistent"                     # Consistent with visible/observed examples
    HELD_OUT_PASSED = "held_out_passed"           # Passed independent hidden test suite
    FORMALLY_VERIFIED = "formally_verified"       # Formally proved across domain via SMT
    REJECTED = "rejected"                         # Falsified by counterexample


@dataclass
class VerificationEvidence:
    """Rigorous verification record specifying testing method, scope, and evidence artifact."""
    evidence_id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:8]}")
    candidate_id: str = ""
    method: str = "unit_test"  # unit_test, property_test, differential, smt, proof
    scope: str = "observed_examples"  # observed_examples, held_out_suite, bounded_domain, full_domain
    passed: bool = False
    assumptions: List[str] = field(default_factory=list)
    testset_version: Optional[str] = None
    artifact_uri: Optional[str] = None
    runtime_ms: Optional[float] = None
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "candidate_id": self.candidate_id,
            "method": self.method,
            "scope": self.scope,
            "passed": self.passed,
            "assumptions": self.assumptions,
            "testset_version": self.testset_version,
            "artifact_uri": self.artifact_uri,
            "runtime_ms": self.runtime_ms,
            "created_at": self.created_at,
        }


class CandidateProgram:
    """Represents a hypothesized program with verified provenance and audit chain."""

    def __init__(
        self,
        code_str: str,
        ast: Optional[ASTNode] = None,
        candidate_id: Optional[str] = None,
        type_signature: Optional[str] = None,
        status: str = CandidateStatus.CANDIDATE,
        created_by: str = "heuristic",  # llm, enumerator, library, heuristic
        parent_candidate_ids: Optional[List[str]] = None,
    ):
        self.code_str = code_str.strip()
        self.ast = ast if ast is not None else SExprParser.parse(self.code_str)
        self.candidate_id = candidate_id or f"cand_{uuid.uuid4().hex[:8]}"
        self.type_signature = type_signature
        self.status = status
        self.created_by = created_by
        self.parent_candidate_ids = parent_candidate_ids or []
        self.evidence_ids: List[str] = []
        self.counterexample_ids: List[str] = []

    @property
    def description_length(self) -> int:
        return self.ast.description_length

    @property
    def depth(self) -> int:
        return self.ast.depth

    def evaluate(self, input_val: Any, timeout: float = 1.0) -> Any:
        from eve3.dsl.interpreter import DSLInterpreter
        interp = DSLInterpreter()
        return interp.run(self.ast, input_val, timeout_seconds=timeout)

    def attach_evidence(self, evidence: VerificationEvidence):
        """Link an evidence record and update candidate status if applicable."""
        evidence.candidate_id = self.candidate_id
        self.evidence_ids.append(evidence.evidence_id)
        if evidence.passed:
            if evidence.method == "smt" and evidence.scope == "full_domain":
                self.status = CandidateStatus.FORMALLY_VERIFIED
            elif evidence.scope == "held_out_suite":
                self.status = CandidateStatus.HELD_OUT_PASSED
            elif self.status == CandidateStatus.CANDIDATE:
                self.status = CandidateStatus.CONSISTENT
        else:
            self.status = CandidateStatus.REJECTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "code_str": self.code_str,
            "description_length": self.description_length,
            "depth": self.depth,
            "type_signature": self.type_signature,
            "status": self.status,
            "created_by": self.created_by,
            "parent_candidate_ids": self.parent_candidate_ids,
            "evidence_ids": self.evidence_ids,
            "counterexample_ids": self.counterexample_ids,
        }

    def __str__(self) -> str:
        return self.code_str

    def __repr__(self) -> str:
        return f"CandidateProgram({self.candidate_id}: {self.code_str!r}, status={self.status})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CandidateProgram):
            return False
        return self.code_str == other.code_str

    def __hash__(self) -> int:
        return hash(self.code_str)


@dataclass
class LearnedAbstraction:
    """Represents a verified, reusable symbolic operator with full evidence linkage."""
    abstraction_id: str = field(default_factory=lambda: f"abs_{uuid.uuid4().hex[:8]}")
    name: str = ""
    definition_ast: Optional[ASTNode] = None
    pattern_sexpr: str = ""
    type_signature: str = "(List[Int]) -> List[Int]"
    arity: int = 1
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    verification_evidence_ids: List[str] = field(default_factory=list)
    source_program_ids: List[str] = field(default_factory=list)
    applicable_task_families: List[str] = field(default_factory=list)
    reuse_count: int = 0
    search_cost_delta: Optional[float] = None
    version: int = 1
    status: str = "verified"  # candidate, verified, deprecated
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "abstraction_id": self.abstraction_id,
            "name": self.name,
            "pattern_sexpr": self.pattern_sexpr,
            "type_signature": self.type_signature,
            "arity": self.arity,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "verification_evidence_ids": self.verification_evidence_ids,
            "source_program_ids": self.source_program_ids,
            "applicable_task_families": self.applicable_task_families,
            "reuse_count": self.reuse_count,
            "search_cost_delta": self.search_cost_delta,
            "version": self.version,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class Task:
    """Represents a synthesis problem specification with visible and hidden examples."""
    task_id: str
    task_family: str
    description: str
    visible_examples: List[Dict[str, Any]]
    hidden_tests: List[Dict[str, Any]]
    reference_program: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "benchmark"  # benchmark, mutation, decomposition, anchor
    difficulty_estimate: float = 0.5
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_family": self.task_family,
            "description": self.description,
            "visible_examples": self.visible_examples,
            "hidden_tests": self.hidden_tests,
            "reference_program": self.reference_program,
            "metadata": self.metadata,
            "source": self.source,
            "difficulty_estimate": self.difficulty_estimate,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            task_id=data["task_id"],
            task_family=data.get("task_family", "generic"),
            description=data.get("description", ""),
            visible_examples=data.get("visible_examples", []),
            hidden_tests=data.get("hidden_tests", []),
            reference_program=data.get("reference_program"),
            metadata=data.get("metadata", {}),
            source=data.get("source", "benchmark"),
            difficulty_estimate=data.get("difficulty_estimate", 0.5),
            created_at=data.get("created_at", time.time()),
        )

