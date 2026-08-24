import re
from typing import Dict, Any, List

def compute_metric_diff(pre_metrics: Dict[str, Any], post_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compares pre-change baseline metrics with post-change metrics,
    stripping transient noise (timestamps, uptime counters).
    """
    diffs = {
        "added": {},
        "removed": {},
        "modified": {},
        "unchanged": {}
    }
    
    all_keys = set(pre_metrics.keys()).union(set(post_metrics.keys()))
    
    for key in all_keys:
        if key in pre_metrics and key not in post_metrics:
            diffs["removed"][key] = pre_metrics[key]
        elif key not in pre_metrics and key in post_metrics:
            diffs["added"][key] = post_metrics[key]
        else:
            val_pre = pre_metrics[key]
            val_post = post_metrics[key]
            if val_pre == val_post:
                diffs["unchanged"][key] = val_pre
            else:
                diffs["modified"][key] = {"pre": val_pre, "post": val_post}
                
    return diffs
