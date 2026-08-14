"""
Kick off an autodiscover scan for every (leaf) subnet known to the IPAM tool.

Fire-and-forget: this hits the /autodiscover/start endpoint added in
Session 7 for each subnet and moves on immediately — it does not wait for
scans to finish or stream progress. Run it directly:

    python server/scripts/scan_all_subnets.py

Configure the backend location with the IPAM_BASE_URL environment
variable; it defaults to http://localhost:8000, matching the default
`uvicorn main:app --host 0.0.0.0 --port 8000` from server/main.py.
"""

import os
import sys

import requests

DEFAULT_BASE_URL = "http://localhost:8000"


def get_base_url() -> str:
    return os.environ.get("IPAM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def fetch_subnets(base_url: str) -> list[dict]:
    resp = requests.get(f"{base_url}/api/ipam/subnets")
    resp.raise_for_status()
    return resp.json()


def leaf_subnets(subnets: list[dict]) -> list[dict]:
    """
    Filter to leaf subnets only.

    Subnets nest (see parentId / server/db.py's recompute_subnet_hierarchy):
    a parent entry is just a supernet aggregating its children, so scanning
    it would re-probe the same addresses its children already cover — and,
    being larger, it's also the one most likely to trip the backend's
    MAX_SCAN_ADDRESSES cap. Only subnets with no children are actual scan
    targets.
    """
    parent_ids = {s["parentId"] for s in subnets if s.get("parentId") is not None}
    return [s for s in subnets if s["id"] not in parent_ids]


def start_scan(base_url: str, subnet_id: int) -> requests.Response:
    return requests.post(f"{base_url}/api/ipam/subnets/{subnet_id}/autodiscover/start")


def main() -> None:
    base_url = get_base_url()

    try:
        subnets = fetch_subnets(base_url)
    except requests.RequestException as exc:
        print(f"Failed to fetch subnet list from {base_url}: {exc}")
        sys.exit(1)

    targets = leaf_subnets(subnets)
    print(f"Found {len(subnets)} subnet(s), {len(targets)} leaf subnet(s) to scan.")

    started = 0
    skipped = 0
    failed = 0

    for subnet in targets:
        subnet_id = subnet["id"]
        cidr = subnet.get("cidr", "?")
        try:
            resp = start_scan(base_url, subnet_id)
        except requests.RequestException as exc:
            print(f"[FAIL] subnet {subnet_id} ({cidr}): request error: {exc}")
            failed += 1
            continue

        if resp.status_code == 409:
            print(f"[SKIP] subnet {subnet_id} ({cidr}): scan already in progress")
            skipped += 1
        elif 200 <= resp.status_code < 300:
            print(f"[OK]   subnet {subnet_id} ({cidr}): scan started")
            started += 1
        else:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except ValueError:
                pass
            print(f"[FAIL] subnet {subnet_id} ({cidr}): HTTP {resp.status_code}: {detail}")
            failed += 1

    print()
    print("Summary:")
    print(f"  started: {started}")
    print(f"  skipped (already scanning): {skipped}")
    print(f"  failed:  {failed}")


if __name__ == "__main__":
    main()