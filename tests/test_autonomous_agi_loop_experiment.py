"""Unit test for Phase 11 Experiment: Autonomous AGI Loop & Safety Audit."""

import unittest
from experiments.run_autonomous_agi_loop import run_autonomous_agi_loop_experiment


class TestAutonomousAGILoopExperiment(unittest.TestCase):
    """Verifies that the Phase 11 experiment executes and passes all criteria."""

    def test_run_experiment_acceptance(self):
        results = run_autonomous_agi_loop_experiment()
        self.assertTrue(results["acceptance_gates_passed"])
        self.assertGreater(results["total_tasks_solved"], 0)
        self.assertGreater(results["total_abstractions_crystallized"], 0)
        self.assertTrue(results["audit_ledger_valid"])
        self.assertTrue(results["tamper_detection_successful"])
        self.assertTrue(results["sensor_anomaly_detected"])
        self.assertTrue(results["working_memory_clean"])
        self.assertLessEqual(results["bwt_regression_pct"], 2.0)
        self.assertGreaterEqual(results["fwt_boost_pct"], 10.0)
        self.assertEqual(results["false_verification_rate"], 0.00)


if __name__ == "__main__":
    unittest.main()
