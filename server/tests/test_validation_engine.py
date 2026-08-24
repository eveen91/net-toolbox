import sys
from unittest.mock import MagicMock
from validation_engine.base import TestResult
from validation_engine.tests_control_l2 import TestCPClusterHealth

def test_t01_execution():
    mock_dev = MagicMock()
    mock_dev.session.send_command.return_value = "HA Cluster Status: Active / Standby"
    
    test = TestCPClusterHealth(mock_dev, "T-01", "Control Plane")
    res = test.run()
    
    assert res.status == "PASS"
    assert res.test_id == "T-01"
