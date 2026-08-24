from validation_engine.diff_engine import compute_metric_diff
from validation_engine.pir_exporter import generate_pir_markdown

def test_diff_engine():
    pre = {"vlan200": "down", "route": "10.0.0.0/8"}
    post = {"vlan200": "up", "route": "10.0.0.0/8", "vip": "10.200.0.1"}
    
    diff = compute_metric_diff(pre, post)
    assert "vip" in diff["added"]
    assert "vlan200" in diff["modified"]
    assert "route" in diff["unchanged"]

def test_pir_exporter():
    run = {"executor_username": "admin", "overall_result": "PASS"}
    results = [{"test_id": "T-01", "layer": "L2", "target_device": "SW1", "status": "PASS", "pass_criteria": "OK"}]
    signoff = {"user": "lead", "status": "APPROVED", "notes": "LGTM"}
    
    md = generate_pir_markdown(run, results, signoff)
    assert "# Post-Implementation Review (PIR) Evidence Package" in md
    assert "| T-01 | L2 | SW1 | PASS | OK |" in md
