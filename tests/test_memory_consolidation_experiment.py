"""Unit test running Phase 8 Tiered Memory & Consolidation experiment."""

import unittest

from experiments.run_memory_consolidation import run_memory_consolidation_experiment


class TestMemoryConsolidationExperiment(unittest.TestCase):
    """Verifies that Tiered Cognitive Memory meets Phase 8 requirements."""

    def test_memory_consolidation_meets_requirements(self):
        results = run_memory_consolidation_experiment()

        metrics = results["metrics"]
        tiered = results["tiered_memory"]
        baseline = results["baseline"]

        # 1. Hot tier operator count must be bounded (less than unbounded baseline)
        self.assertTrue(metrics["hot_tier_bounded"])
        self.assertLess(tiered["hot_tier_operators"], baseline["active_operators"])

        # 2. Total retained equals hot + cold (lossless demotion)
        self.assertEqual(
            tiered["total_retained_operators"],
            tiered["hot_tier_operators"] + tiered["cold_tier_operators"],
        )

        # 3. Exactly zero physical deletions
        self.assertEqual(tiered["physical_deletions"], 0)
        self.assertTrue(metrics["zero_deletions"])

        # 4. Episodic trajectories summarized
        self.assertGreater(tiered["episodic_summary_count"], 0)

        # 5. Snapshot rollback integrity verified
        self.assertTrue(metrics["rollback_passed"])
        self.assertTrue(tiered["rollback_verified"])

        # 6. Strict zero false verification
        self.assertTrue(metrics["zero_false_verification"])
        self.assertEqual(tiered["false_verification_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
