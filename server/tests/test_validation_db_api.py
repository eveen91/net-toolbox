import json
import pytest
import validation_db

def test_init_db_validation_tables(client):
    # If init_db ran (which it does in conftest.py client fixture),
    # we should be able to create a plan.
    plan_id = validation_db.create_plan(name="Test Plan")
    assert plan_id > 0

def test_validation_db_crud(client):
    # Plan
    plan_id = validation_db.create_plan(
        name="L2/L3 Migration",
        change_ticket="CHG123",
        target_devices=["SW-01", "FW-01"],
        scenario_modules=["3.C", "3.D"]
    )
    assert plan_id is not None
    
    plan = validation_db.get_plan(plan_id)
    assert plan["name"] == "L2/L3 Migration"
    assert plan["target_devices"] == ["SW-01", "FW-01"]
    
    plans = validation_db.list_plans()
    assert len(plans) >= 1
    
    # Baseline
    baseline_id = validation_db.save_baseline(
        plan_id=plan_id,
        ticket_number="CHG123",
        captured_by="testuser",
        raw_outputs={"SW-01": "show version..."},
        parsed_metrics={"SW-01": {"version": "1.0"}}
    )
    assert baseline_id is not None
    
    baseline = validation_db.get_baseline(baseline_id)
    assert baseline["ticket_number"] == "CHG123"
    assert baseline["raw_outputs"]["SW-01"] == "show version..."
    
    # Run
    run_id = validation_db.create_run(
        plan_id=plan_id,
        baseline_id=baseline_id,
        run_type="POST_VALIDATION",
        status="RUNNING",
        executor_username="testuser"
    )
    assert run_id is not None
    
    # Result
    res_id = validation_db.save_test_result(
        run_id=run_id,
        test_id="T-01",
        layer="Control Plane",
        target_device="SW-01",
        command_executed="show version",
        raw_output="ver 1.0",
        status="PASS",
        pass_criteria="Version matches"
    )
    assert res_id is not None
    
    results = validation_db.get_test_results(run_id)
    assert len(results) == 1
    assert results[0]["test_id"] == "T-01"
    
    # Update Run
    validation_db.update_run_status(run_id, "COMPLETED", "PASS")
    run = validation_db.get_run(run_id)
    assert run["status"] == "COMPLETED"
    assert run["overall_result"] == "PASS"
    
    # PIR
    pir_id = validation_db.save_pir_report(
        run_id=run_id,
        signoff_user="admin",
        signoff_status="APPROVED",
        signoff_notes="All good",
        report_data={"summary": "Success"}
    )
    assert pir_id is not None
    
    pir = validation_db.get_pir_report(run_id)
    assert pir["signoff_user"] == "admin"
    assert pir["report_data"]["summary"] == "Success"
    
    # Delete
    assert validation_db.delete_plan(plan_id) is True
    assert validation_db.get_plan(plan_id) is None

def test_validation_api_endpoints(client, monkeypatch):
    # Mock require_feature to bypass permission check if needed, 
    # but conftest.py doesn't set up a user session by default.
    # We might need to mock auth_db.is_login_required to return False.
    import auth_db
    monkeypatch.setattr(auth_db, "is_login_required", lambda: False)
    
    # Create Plan
    resp = client.post("/api/validation/plans", json={
        "name": "API Test Plan",
        "target_devices": ["D1"]
    })
    assert resp.status_code == 201
    plan_id = resp.json()["id"]
    
    # List Plans
    resp = client.get("/api/validation/plans")
    assert resp.status_code == 200
    assert any(p["id"] == plan_id for p in resp.json())
    
    # Get Plan
    resp = client.get(f"/api/validation/plans/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "API Test Plan"
    
    # Create Baseline
    resp = client.post("/api/validation/baselines", json={
        "plan_id": plan_id,
        "ticket_number": "TKT-456",
        "raw_outputs": {"D1": "output"}
    })
    assert resp.status_code == 201
    
    # Delete Plan
    resp = client.delete(f"/api/validation/plans/{plan_id}")
    assert resp.status_code == 200
    
    # Check 404
    resp = client.get(f"/api/validation/plans/{plan_id}")
    assert resp.status_code == 404
