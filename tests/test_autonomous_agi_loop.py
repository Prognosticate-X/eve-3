"""Unit tests for Phase 11: End-to-End Autonomous AGI Loop Engine."""

from pathlib import Path
import tempfile
import unittest

from eve3.loop.autonomous_engine import AutonomousEngine


class TestAutonomousAGILoop(unittest.TestCase):
    """Test suite for Phase 11 AutonomousEngine end-to-end self-evolution loop."""

    def test_autonomous_evolution_cycles(self):
        """Verify multi-cycle continuous self-directed wake/sleep discovery loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_autonomous_kb.db"
            engine = AutonomousEngine(db_path=db_path, seed=42)

            # Run 2 complete evolution cycles
            reports = engine.run_multi_cycle_evolution(num_cycles=2, tasks_per_cycle=3)

            self.assertEqual(len(reports), 2)

            for report in reports:
                # 1. Proposed tasks must be non-zero and matched
                self.assertEqual(report.tasks_proposed, 3)

                # 2. Daytime synthesis solved tasks
                self.assertGreater(report.tasks_solved, 0)
                self.assertGreater(report.abstractions_crystallized, 0)

                # 3. Nighttime consolidation status & regression gate passed
                self.assertIn("successfully", report.sleep_consolidation_status)
                self.assertTrue(report.regression_gate_passed)

                # 4. Strict zero false verification rate
                self.assertEqual(report.false_verification_rate, 0.0)

            # 5. Working memory must be cleanly wiped at the end of cycle
            self.assertFalse(engine.working_memory.active)
            self.assertEqual(len(engine.working_memory.hypotheses), 0)

            # 6. Audit ledger integrity verified
            self.assertTrue(engine.audit.verify_ledger_integrity())
            self.assertGreater(len(engine.audit.ledger), 4)

            # 7. Semantic memory tiered structure active
            self.assertGreater(len(engine.semantic_memory.hot_tier), 0)


if __name__ == "__main__":
    unittest.main()
