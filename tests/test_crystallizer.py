"""Tests for System 3 SQLite Knowledge Base and Value-Weighted Compression."""

import tempfile
from pathlib import Path

from eve3.system1_proposer.sandbox import CandidateProgram
from eve3.system3_crystallizer.library import KnowledgeLibrary
from eve3.system3_crystallizer.value_compressor import CandidateAbstraction, ValueCompressor


def test_sqlite_library_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_knowledge.sqlite"
        lib = KnowledgeLibrary(db_path)

        prog = CandidateProgram("(map (lambda (a) (+ a 1)) x)")
        pid = lib.record_verified_program(prog, task_family="list_mapping")
        assert pid is not None

        # Record again to trigger reuse update
        pid2 = lib.record_verified_program(prog, task_family="list_mapping")
        assert pid == pid2

        progs = lib.get_all_verified_programs()
        assert len(progs) == 1
        assert progs[0]["verification_count"] == 2
        assert progs[0]["reuse_count"] == 1


def test_value_weighted_library_selection():
    compressor = ValueCompressor(gamma=0.5)

    programs = [
        {"code": "(map (lambda (a) (+ a 1)) x)", "description_length": 10, "reuse_count": 5, "task_family": "family_a"},
        {"code": "(map (lambda (a) (+ a 2)) x)", "description_length": 10, "reuse_count": 3, "task_family": "family_b"},
        {"code": "(reverse x)", "description_length": 2, "reuse_count": 0, "task_family": "family_c"},
    ]

    candidates = [
        CandidateAbstraction(
            name="map_add",
            pattern="(map (lambda (a) (+ a $k)) x)",
            arity=2,
            cost=2,
        ),
        CandidateAbstraction(
            name="dummy_costly",
            pattern="(filter (lambda (a) (gt a $k)) x)",
            arity=2,
            cost=20,
        ),
    ]

    selected = compressor.select_optimal_library(candidates, programs)
    # map_add brings high weighted benefit and low cost, so it should be selected
    names = [a.name for a in selected]
    assert "map_add" in names
    # dummy_costly has 0 benefit for these programs and high penalty, should not be selected
    assert "dummy_costly" not in names
