import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from db import get_connection

def create_plan(name: str, change_ticket: Optional[str] = None, category: Optional[str] = None, 
                description: Optional[str] = None, target_devices: List[str] = None, 
                scenario_modules: List[str] = None, config_parameters: Dict[str, Any] = None) -> int:
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO validation_test_plans (
                name, change_ticket, category, description, target_devices, 
                scenario_modules, config_parameters, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, change_ticket, category, description, json.dumps(target_devices or []),
                json.dumps(scenario_modules or []), json.dumps(config_parameters or {}), now, now
            )
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_plan(plan_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM validation_test_plans WHERE id = ?", (plan_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["target_devices"] = json.loads(res["target_devices"] or "[]")
        res["scenario_modules"] = json.loads(res["scenario_modules"] or "[]")
        res["config_parameters"] = json.loads(res["config_parameters"] or "{}")
        return res
    finally:
        conn.close()

def list_plans() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM validation_test_plans ORDER BY created_at DESC").fetchall()
        plans = []
        for r in rows:
            res = dict(r)
            res["target_devices"] = json.loads(res["target_devices"] or "[]")
            res["scenario_modules"] = json.loads(res["scenario_modules"] or "[]")
            res["config_parameters"] = json.loads(res["config_parameters"] or "{}")
            plans.append(res)
        return plans
    finally:
        conn.close()

def delete_plan(plan_id: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM validation_test_plans WHERE id = ?", (plan_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def save_baseline(plan_id: int, ticket_number: str, captured_by: str, 
                  raw_outputs: Dict[str, Any], parsed_metrics: Dict[str, Any]) -> int:
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO validation_baselines (
                plan_id, ticket_number, captured_at, captured_by, raw_outputs, parsed_metrics
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id, ticket_number, now, captured_by, 
                json.dumps(raw_outputs or {}), json.dumps(parsed_metrics or {})
            )
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_baseline(baseline_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM validation_baselines WHERE id = ?", (baseline_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["raw_outputs"] = json.loads(res["raw_outputs"] or "{}")
        res["parsed_metrics"] = json.loads(res["parsed_metrics"] or "{}")
        return res
    finally:
        conn.close()

def create_run(plan_id: int, baseline_id: Optional[int], run_type: str, status: str, 
               executor_username: str) -> int:
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO validation_runs (
                plan_id, baseline_id, run_type, status, started_at, executor_username
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (plan_id, baseline_id, run_type, status, now, executor_username)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_run(run_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM validation_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()

def update_run_status(run_id: int, status: str, overall_result: Optional[str] = None) -> None:
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        if overall_result is not None:
            conn.execute(
                """
                UPDATE validation_runs 
                SET status = ?, overall_result = ?, completed_at = ? 
                WHERE id = ?
                """,
                (status, overall_result, now, run_id)
            )
        else:
            conn.execute(
                "UPDATE validation_runs SET status = ? WHERE id = ?",
                (status, run_id)
            )
        conn.commit()
    finally:
        conn.close()

def save_test_result(run_id: int, test_id: str, layer: Optional[str], target_device: str, 
                     command_executed: str, raw_output: Optional[str], status: str, 
                     pass_criteria: Optional[str], delta_summary: Optional[str] = None, 
                     error_message: Optional[str] = None) -> int:
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO validation_test_results (
                run_id, test_id, layer, target_device, command_executed, 
                raw_output, status, pass_criteria, delta_summary, error_message, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, test_id, layer, target_device, command_executed, 
                raw_output, status, pass_criteria, delta_summary, error_message, now
            )
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_test_results(run_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM validation_test_results WHERE run_id = ? ORDER BY id ASC",
            (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def save_pir_report(run_id: int, signoff_user: Optional[str], signoff_status: Optional[str], 
                    signoff_notes: Optional[str], report_data: Dict[str, Any]) -> int:
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO validation_pir_reports (
                run_id, signoff_user, signoff_status, signoff_notes, generated_at, report_data
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, signoff_user, signoff_status, signoff_notes, now, json.dumps(report_data))
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_pir_report(run_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM validation_pir_reports WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["report_data"] = json.loads(res["report_data"] or "{}")
        return res
    finally:
        conn.close()
