"""Tests for LearnedAbstraction data model and SQLite persistence."""

from pathlib import Path
import tempfile
import unittest

from eve3.models import LearnedAbstraction
from eve3.system3_crystallizer.library import KnowledgeLibrary


class TestLearnedAbstraction(unittest.TestCase):

    def test_learned_abstraction_persistence_and_retrieval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_abstractions.sqlite"
            lib = KnowledgeLibrary(db_path)

            abs_obj = LearnedAbstraction(
                name="map_add_one",
                pattern_sexpr="(map (lambda (a) (+ a 1)) x)",
                type_signature="(List[Int]) -> List[Int]",
                arity=1,
                preconditions=["is_list(x)"],
                postconditions=["len(result) == len(x)"],
                applicable_task_families=["list_mapping"],
                reuse_count=3,
                search_cost_delta=-2.5,
            )

            lib.record_learned_abstraction(abs_obj)

            retrieved = lib.get_learned_abstractions()
            self.assertEqual(len(retrieved), 1)
            row = retrieved[0]
            self.assertEqual(row["name"], "map_add_one")
            self.assertEqual(row["pattern_sexpr"], "(map (lambda (a) (+ a 1)) x)")
            self.assertEqual(row["reuse_count"], 3)
            self.assertEqual(row["search_cost_delta"], -2.5)

            # Check that it mirrored to crystallized_operators
            ops = lib.get_crystallized_operators()
            self.assertTrue(any(o["operator_name"] == "map_add_one" for o in ops))


if __name__ == "__main__":
    unittest.main()
