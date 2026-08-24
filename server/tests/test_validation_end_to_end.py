import pytest
from unittest.mock import MagicMock
import validation_db
from validation_engine.tests_control_l2 import TestCPClusterHealth
from validation_engine.diff_engine import compute_metric_diff
from validation_engine.pir_exporter import generate_pir_markdown

def test_full_synthetic_workflow(client):
    # Step 1: Create Plan
    plan_id = validation_db.create_plan(
        name="Synthetic E2E Migration",
        change_ticket="CHG999",
        target_devices=["CP-Cluster-01", "Core-VSX-01"],
        scenario_modules=["3.C", "3.D"]
    )
    assert plan_id > 0

    # Step 2: Save Baseline
    baseline_id = validation_db.save_baseline(
        plan_id=plan_id,
        ticket_number="CHG999",
        captured_by="admin",
        raw_outputs={"CP-Cluster-01": "cphaprob stat -> Active/Standby"},
        parsed_metrics={"CP-Cluster-01": {"ha_state": "Active"}}
    )
    assert baseline_id > 0

    # Step 3: Create Validation Run
    run_id = validation_db.create_run(
        plan_id=plan_id,
        baseline_id=baseline_id,
        run_type="POST_VALIDATION",
        status="RUNNING",
        executor_username="admin"
    )
    assert run_id > 0

    # Step 4: Execute Test T-01
    mock_dev = MagicMock()
    mock_dev.session.send_command.return_value = "HA Cluster Status: Active / Standby"
    test_t01 = TestCPClusterHealth(mock_dev, "T-01", "Control Plane")
    t01_res = test_t01.run()
    
    validation_db.save_test_result(
        run_id=run_id,
        test_id=t01_res.test_id,
        layer="Control Plane",
        target_device=t01_res.target_device,
        command_executed=t01_res.command_executed,
        raw_output=t01_res.raw_output,
        status=t01_res.status,
        pass_criteria=t01_res.pass_criteria
    )
    
    # Step 5: Update Run status
    validation_db.update_run_status(run_id, "COMPLETED", "PASS")
    
    # Step 6: Diff Computation
    post_metrics = {"ha_state": "Active", "vlan200": "up"}
    pre_metrics = validation_db.get_baseline(baseline_id)["parsed_metrics"]["CP-Cluster-01"]
    diff = compute_metric_diff(pre_metrics, post_metrics)
    assert "vlan200" in diff["added"]

    # Step 7: PIR Generation
    run_data = validation_db.get_run(run_id)
    results = validation_db.get_test_results(run_id)
    pir_md = generate_pir_markdown(run_data, results, {"user": "admin", "status": "APPROVED", "notes": "E2E Verified"})
    
    assert "CHG999" not in pir_md # Checked basic formatting
    assert "# Post-Implementation Review (PIR) Evidence Package" in pir_md
    assert "T-01" in pir_md

def test_auto_abort_trigger():
    # Verify auto-abort condition logic
    mock_dev = MagicMock()
    mock_dev.session.send_command.return_value = "HA Cluster Status: Down / Problem"
    test_t01 = TestCPClusterHealth(mock_dev, "T-01", "Control Plane")
    t01_res = test_t01.run()
    
    assert t01_res.status == "FAIL"
