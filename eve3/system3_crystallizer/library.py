"""System 3: SQLite Persistent Knowledge Base and Operator Library."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eve3.system1_proposer.sandbox import CandidateProgram


class KnowledgeLibrary:
    """Manages verified programs and crystallized operators in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
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
            conn.commit()

    def record_verified_program(
        self,
        program: CandidateProgram,
        task_family: str,
    ) -> int:
        """Insert or update verified program record."""
        now = time.time()
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crystallized_operators ORDER BY benefit_score DESC")
            return [dict(row) for row in cursor.fetchall()]
