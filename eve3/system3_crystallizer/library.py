"""System 3: SQLite Persistent Knowledge Base and Operator Library."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from eve3.models import CandidateProgram


class KnowledgeLibrary:
    """Manages verified programs and crystallized operators in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verified_programs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    description_length INTEGER NOT NULL,
                    task_family TEXT NOT NULL,
                    verification_count INTEGER DEFAULT 1,
                    reuse_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    last_used_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crystallized_operators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator_name TEXT UNIQUE NOT NULL,
                    body_sexpr TEXT NOT NULL,
                    arity INTEGER NOT NULL,
                    benefit_score REAL NOT NULL,
                    task_diversity_score INTEGER DEFAULT 1,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovery_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    task_family TEXT NOT NULL,
                    rounds_executed INTEGER NOT NULL,
                    probes_used_json TEXT NOT NULL,
                    verified_code TEXT,
                    converged INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learned_abstractions (
                    abstraction_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pattern_sexpr TEXT NOT NULL,
                    type_signature TEXT NOT NULL,
                    arity INTEGER NOT NULL,
                    preconditions_json TEXT NOT NULL,
                    postconditions_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    source_program_ids_json TEXT NOT NULL,
                    applicable_task_families_json TEXT NOT NULL,
                    reuse_count INTEGER DEFAULT 0,
                    search_cost_delta REAL,
                    version INTEGER DEFAULT 1,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def record_verified_program(
        self,
        program: CandidateProgram,
        task_family: str,
    ) -> int:
        """Insert or update verified program record."""
        now = time.time()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, verification_count, reuse_count FROM verified_programs WHERE code = ?",
                (program.code_str,),
            )
            row = cursor.fetchone()
            if row:
                prog_id, v_count, r_count = row["id"], row["verification_count"], row["reuse_count"]
                cursor.execute(
                    """
                    UPDATE verified_programs 
                    SET verification_count = verification_count + 1,
                        reuse_count = reuse_count + 1,
                        last_used_at = ?
                    WHERE id = ?
                    """,
                    (now, prog_id),
                )
                conn.commit()
                return prog_id
            else:
                cursor.execute(
                    """
                    INSERT INTO verified_programs 
                    (code, description_length, task_family, verification_count, reuse_count, created_at, last_used_at)
                    VALUES (?, ?, ?, 1, 0, ?, ?)
                    """,
                    (program.code_str, program.description_length, task_family, now, now),
                )
                conn.commit()
                return cursor.lastrowid

    def get_all_verified_programs(self) -> List[Dict[str, Any]]:
        """Fetch all verified programs with metadata."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verified_programs ORDER BY reuse_count DESC, verification_count DESC")
            return [dict(row) for row in cursor.fetchall()]

    def record_crystallized_operator(
        self,
        operator_name: str,
        body_sexpr: str,
        arity: int,
        benefit_score: float,
        task_diversity: int = 1,
    ):
        """Insert or update crystallized operator."""
        now = time.time()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO crystallized_operators
                (operator_name, body_sexpr, arity, benefit_score, task_diversity_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (operator_name, body_sexpr, arity, benefit_score, task_diversity, now),
            )
            conn.commit()

    def get_crystallized_operators(self) -> List[Dict[str, Any]]:
        """Fetch crystallized library operators."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crystallized_operators ORDER BY benefit_score DESC")
            return [dict(row) for row in cursor.fetchall()]

    def record_learned_abstraction(self, abs_record: Any):
        """Insert or update structured LearnedAbstraction."""
        import json
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO learned_abstractions (
                    abstraction_id, name, pattern_sexpr, type_signature, arity,
                    preconditions_json, postconditions_json, evidence_ids_json,
                    source_program_ids_json, applicable_task_families_json,
                    reuse_count, search_cost_delta, version, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    abs_record.abstraction_id,
                    abs_record.name,
                    abs_record.pattern_sexpr,
                    abs_record.type_signature,
                    abs_record.arity,
                    json.dumps(abs_record.preconditions),
                    json.dumps(abs_record.postconditions),
                    json.dumps(abs_record.verification_evidence_ids),
                    json.dumps(abs_record.source_program_ids),
                    json.dumps(abs_record.applicable_task_families),
                    abs_record.reuse_count,
                    abs_record.search_cost_delta,
                    abs_record.version,
                    abs_record.status,
                    abs_record.created_at,
                ),
            )
            # Also mirror to crystallized_operators for execution
            conn.execute(
                """
                INSERT OR REPLACE INTO crystallized_operators
                (operator_name, body_sexpr, arity, benefit_score, task_diversity_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (abs_record.name, abs_record.pattern_sexpr, abs_record.arity, 10.0, len(abs_record.applicable_task_families) or 1, time.time()),
            )
            conn.commit()

    def get_learned_abstractions(self) -> List[Dict[str, Any]]:
        """Fetch all structured learned abstractions."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM learned_abstractions ORDER BY reuse_count DESC")
            return [dict(row) for row in cursor.fetchall()]

