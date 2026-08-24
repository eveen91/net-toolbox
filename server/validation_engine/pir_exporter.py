from typing import Dict, Any, List
from datetime import datetime

def generate_pir_markdown(run_data: Dict[str, Any], test_results: List[Dict[str, Any]], signoff: Dict[str, Any]) -> str:
    md = []
    md.append("# Post-Implementation Review (PIR) Evidence Package")
    md.append(f"**Generated At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"**Executor:** {run_data.get('executor_username', 'Unknown')}")
    md.append(f"**Overall Result:** {run_data.get('overall_result', 'UNKNOWN')}\n")
    
    md.append("## Sign-Off Details")
    md.append(f"- **Sign-Off User:** {signoff.get('user', 'N/A')}")
    md.append(f"- **Status:** {signoff.get('status', 'N/A')}")
    md.append(f"- **Notes:** {signoff.get('notes', 'None')}\n")
    
    md.append("## Master Test Execution Results")
    md.append("| Test ID | Layer | Target Device | Status | Details |")
    md.append("|---|---|---|---|---|")
    for t in test_results:
        md.append(f"| {t.get('test_id')} | {t.get('layer')} | {t.get('target_device')} | {t.get('status')} | {t.get('pass_criteria')} |")
        
    return "\n".join(md)
