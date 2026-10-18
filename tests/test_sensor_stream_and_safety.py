"""Unit tests for Phase 11: L4 Sensor Stream, Redundant Cross-Verification, and Safety Audit Protocol."""

import time
import unittest

from eve3.perception.sensor_stream import (
    FusedSensorState,
    RedundantSensorStream,
    SensorReading,
)
from eve3.safety.audit_protocol import AuditRecord, SafetyAuditProtocol


class TestSensorStreamAndSafety(unittest.TestCase):
    """Test suite for Phase 11 L4 redundant sensor streams and safety audit protocol."""

    def test_redundant_sensor_fusion_and_disparity(self):
        """Verify multi-sensor Bayesian fusion and disparity fault gating."""
        stream = RedundantSensorStream(max_disparity_threshold=0.30)
        now = time.time()

        # Case 1: Normal coherent readings (disparity = 0.05 < 0.30)
        s1 = SensorReading(sensor_id="primary_pos", modality="odometry", value=(2.0, 3.0), variance=0.04, timestamp=now)
        s2 = SensorReading(sensor_id="audit_pos", modality="vision", value=(2.03, 3.04), variance=0.04, timestamp=now)

        state = stream.fuse_and_verify(s1, s2, current_time=now)
        self.assertFalse(state.sensor_fault_detected)
        self.assertTrue(state.is_safe_to_actuate)
        self.assertLess(state.disparity, 0.10)
        # Fused variance must be lower than either individual sensor: 1 / (1/0.04 + 1/0.04) = 0.02
        self.assertAlmostEqual(state.fused_variance, 0.02, places=4)

        # Case 2: Excessive disparity (e.g., sensor spoofing or hardware failure: disparity = 2.0 > 0.30)
        s_fault = SensorReading(sensor_id="audit_pos", modality="vision", value=(4.0, 3.0), variance=0.04, timestamp=now)
        state_fault = stream.fuse_and_verify(s1, s_fault, current_time=now)
        self.assertTrue(state_fault.sensor_fault_detected)
        self.assertFalse(state_fault.is_safe_to_actuate)
        self.assertGreater(state_fault.disparity, 1.0)

    def test_sensor_staleness_rejection(self):
        """Verify stale sensor data is rejected and blocks physical actuation."""
        stream = RedundantSensorStream(stale_data_timeout_sec=0.5)
        old_time = time.time() - 2.0  # 2 seconds old

        s1 = SensorReading(sensor_id="s1", modality="lidar", value=(1.0,), timestamp=old_time)
        s2 = SensorReading(sensor_id="s2", modality="sonar", value=(1.0,), timestamp=time.time())

        state = stream.fuse_and_verify(s1, s2)
        self.assertTrue(state.sensor_fault_detected)
        self.assertFalse(state.is_safe_to_actuate)

    def test_safety_audit_ledger_integrity(self):
        """Verify tamper-evident hash-chained audit ledger and tamper detection."""
        audit = SafetyAuditProtocol()

        # Append records
        audit.append_audit_record("adapter_commit", "engine", {"version": "v1"})
        audit.append_audit_record("actuation_command", "engine", {"action": [0.5, 0.5]})
        self.assertEqual(len(audit.ledger), 3)  # Genesis + 2 records

        # Hash chain must be intact
        self.assertTrue(audit.verify_ledger_integrity())

        # Tampering with a record must break the chain
        audit.ledger[1].payload_hash = "corrupted_hash_tampered"
        self.assertFalse(audit.verify_ledger_integrity())

    def test_human_authorization_token(self):
        """Verify time-bounded cryptographic token generation and validation."""
        audit = SafetyAuditProtocol(secret_key="secret-key-test")

        # 1. Valid token
        token = audit.generate_authorization_token("override_e_stop", valid_duration_sec=10.0)
        is_valid = audit.verify_authorization_token(token, "override_e_stop")
        self.assertTrue(is_valid)

        # 2. Wrong operation
        self.assertFalse(audit.verify_authorization_token(token, "other_operation"))

        # 3. Expired token
        expired_token = audit.generate_authorization_token("override_e_stop", valid_duration_sec=-1.0)
        self.assertFalse(audit.verify_authorization_token(expired_token, "override_e_stop"))

        # 4. Tampered token signature
        tampered_token = token[:-4] + "ffff"
        self.assertFalse(audit.verify_authorization_token(tampered_token, "override_e_stop"))


if __name__ == "__main__":
    unittest.main()
