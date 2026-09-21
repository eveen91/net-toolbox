import asyncio
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

import ipam_scan
from .repository import IpamRepository
from .schemas import ScanScheduleRequest

logger = logging.getLogger("net_toolbox.ipam.scan")
SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=256)
SCANS_IN_PROGRESS: set[int] = set()
SCAN_JOBS: dict[str, dict] = {}
SCAN_JOBS_BY_SUBNET: dict[int, str] = {}
SCAN_SCHEDULER_TASK: Optional[asyncio.Task] = None
repository: IpamRepository


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def configure(value: IpamRepository) -> None:
    global repository
    repository = value


async def perform_scan(
    subnet_id: int,
    on_progress=None,
    on_targets_ready=None,
    on_address_update=None,
    is_cancelled=None,
) -> dict:
    data = repository.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    addresses = repository.get_addresses_by_subnet(subnet_id)
    excludes = set(repository.list_scan_excludes(subnet_id))
    excludes.update(
        addr["address"]
        for addr in addresses
        if addr["status"] == "reserved" or addr["locked"]
    )

    try:
        targets = ipam_scan.enumerate_scan_targets(data["cidr"], excludes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if on_targets_ready is not None:
        on_targets_ready(targets)

    started_at = now_str()
    existing_by_address = {a["address"]: a for a in repository.get_addresses_by_subnet(subnet_id)}
    snapshot = {
        address: {
            "status": existing_by_address[address]["status"] if address in existing_by_address else "free",
            "hostname": existing_by_address[address]["hostname"] if address in existing_by_address else None,
        }
        for address in targets
    }

    loop = asyncio.get_event_loop()
    total_count = len(targets)
    completed_count = 0
    results = []
    tasks = []

    concurrency_limit = repository.get_scan_concurrency_limit()
    semaphore = asyncio.Semaphore(concurrency_limit)

    async def scan_one_task(address):
        async with semaphore:
            return await loop.run_in_executor(
                SCAN_EXECUTOR,
                ipam_scan.scan_one,
                address,
                ipam_scan.DEFAULT_PING_TIMEOUT,
                ipam_scan.DEFAULT_PING_ATTEMPTS,
                ipam_scan.DEFAULT_DNS_TIMEOUT,
            )

    for address in targets:
        if on_address_update is not None:
            on_address_update(address, "in_progress")
        tasks.append(asyncio.create_task(scan_one_task(address)))
    for coro in asyncio.as_completed(tasks):
        if is_cancelled is not None and is_cancelled():
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise asyncio.CancelledError("Scan cancelled")
        result = await coro
        results.append(result)
        completed_count += 1
        if on_progress is not None:
            on_progress(completed_count, total_count)
        if on_address_update is not None:
            on_address_update(result["address"], "done", alive=result["alive"], hostname=result["hostname"])

    alive_count = 0
    free_count = 0
    newly_used = []
    went_quiet = []
    hostname_changed = []
    for result in results:
        if is_cancelled is not None and is_cancelled():
            raise asyncio.CancelledError("Scan cancelled")
        address = result["address"]
        repository.apply_scan_result(subnet_id, address, result["alive"], result["hostname"])
        if result["alive"]:
            alive_count += 1
        else:
            free_count += 1

        prior = snapshot[address]
        if prior["status"] != "used" and result["alive"]:
            newly_used.append(address)
        if prior["status"] == "used" and not result["alive"]:
            went_quiet.append(address)
        if result["hostname"] != prior["hostname"]:
            hostname_changed.append(
                {
                    "address": address,
                    "oldHostname": prior["hostname"],
                    "newHostname": result["hostname"],
                }
            )

    diff = {
        "newlyUsed": newly_used,
        "wentQuiet": went_quiet,
        "hostnameChanged": hostname_changed,
    }

    finished_at = now_str()
    scan_record = repository.record_scan(
        subnet_id, started_at, finished_at, len(targets), alive_count, free_count, len(excludes), diff
    )

    return {
        "scanId": scan_record["id"],
        "scannedCount": len(targets),
        "usedCount": alive_count,
        "freeCount": free_count,
        "skippedCount": len(excludes),
        "results": results,
        "diff": diff,
    }


async def rescan_address(subnet_id: int, address_id: int):
    if not repository.subnet_exists(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")

    address_row = repository.get_subnet_address(subnet_id, address_id)
    if address_row is None:
        raise HTTPException(status_code=404, detail="Address not found")
    if subnet_id in SCANS_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="A scan is already running for this subnet")
    if address_row["status"] == "reserved":
        return repository.get_subnet(subnet_id)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        SCAN_EXECUTOR,
        ipam_scan.scan_one,
        address_row["address"],
        ipam_scan.DEFAULT_PING_TIMEOUT,
        ipam_scan.DEFAULT_PING_ATTEMPTS,
        ipam_scan.DEFAULT_DNS_TIMEOUT,
    )
    repository.apply_scan_result(
        subnet_id,
        address_row["address"],
        result["alive"],
        result["hostname"],
    )
    return repository.get_subnet(subnet_id)


async def autodiscover_subnet(subnet_id: int):
    if not repository.subnet_exists(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")

    job_id = str(uuid.uuid4())
    if not repository.create_scan_job(job_id, subnet_id):
        raise HTTPException(status_code=409, detail="A scan is already running for this subnet")
    SCANS_IN_PROGRESS.add(subnet_id)
    try:
        result = await perform_scan(subnet_id)
        repository.update_scan_job(job_id, status="done", result=result)
        return result
    except Exception as exc:
        repository.update_scan_job(job_id, status="error", error=str(exc))
        raise
    finally:
        SCANS_IN_PROGRESS.discard(subnet_id)


def cleanup_old_scan_jobs(max_age_seconds: float = 300.0) -> None:
    repository.expire_timed_out_scan_jobs()
    repository.cleanup_scan_jobs(max_age_seconds)
    now = time.time()
    stale_ids = [
        job_id
        for job_id, job in SCAN_JOBS.items()
        if job["status"] in ("done", "error", "cancelled") and now - job["created_at"] > max_age_seconds
    ]
    for job_id in stale_ids:
        del SCAN_JOBS[job_id]


async def run_due_scan_schedules() -> None:
    for schedule in repository.list_due_scan_schedules():
        try:
            await start_autodiscover_job(schedule["subnetId"])
            repository.mark_scan_schedule_started(schedule["subnetId"])
        except HTTPException as exc:
            # An active scan is expected occasionally; leave the schedule due
            # so it is retried by the next scheduler pass.
            if exc.status_code != 409:
                logger.warning("Could not start scheduled scan for subnet %s: %s", schedule["subnetId"], exc.detail)


async def scan_scheduler_loop() -> None:
    while True:
        try:
            cleanup_old_scan_jobs()
            await run_due_scan_schedules()
        except Exception:
            logger.exception("IPAM scan scheduler iteration failed")
        await asyncio.sleep(30)


async def start_scan_scheduler() -> None:
    global SCAN_SCHEDULER_TASK
    if SCAN_SCHEDULER_TASK is None:
        SCAN_SCHEDULER_TASK = asyncio.create_task(scan_scheduler_loop())


async def stop_scan_scheduler() -> None:
    global SCAN_SCHEDULER_TASK
    if SCAN_SCHEDULER_TASK is not None:
        SCAN_SCHEDULER_TASK.cancel()
        SCAN_SCHEDULER_TASK = None


async def start_autodiscover_job(subnet_id: int):
    if not repository.subnet_exists(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")

    cleanup_old_scan_jobs()

    job_id = str(uuid.uuid4())
    if not repository.create_scan_job(job_id, subnet_id):
        raise HTTPException(status_code=409, detail="A scan is already running for this subnet")
    SCANS_IN_PROGRESS.add(subnet_id)
    SCAN_JOBS_BY_SUBNET[subnet_id] = job_id
    SCAN_JOBS[job_id] = {
        "subnet_id": subnet_id,
        "completed": 0,
        "total": 0,
        "status": "running",
        "result": None,
        "error": None,
        "created_at": time.time(),
        "addresses": {},
    }

    async def run_job():
        try:
            def on_progress(completed, total):
                SCAN_JOBS[job_id]["completed"] = completed
                SCAN_JOBS[job_id]["total"] = total
                repository.update_scan_job(job_id, completed=completed, total=total)

            def on_targets_ready(targets):
                SCAN_JOBS[job_id]["addresses"] = {
                    addr: {"status": "pending", "alive": None, "hostname": None}
                    for addr in targets
                }
                repository.update_scan_job(job_id, addresses=SCAN_JOBS[job_id]["addresses"])

            def on_address_update(address, status, alive=None, hostname=None):
                entry = SCAN_JOBS[job_id]["addresses"].get(address)
                if entry is not None:
                    entry["status"] = status
                    if alive is not None:
                        entry["alive"] = alive
                    if hostname is not None:
                        entry["hostname"] = hostname
                    repository.update_scan_job(job_id, addresses=SCAN_JOBS[job_id]["addresses"])

            result = await asyncio.wait_for(
                perform_scan(
                    subnet_id,
                    on_progress=on_progress,
                    on_targets_ready=on_targets_ready,
                    on_address_update=on_address_update,
                    is_cancelled=lambda: repository.is_scan_job_cancel_requested(job_id),
                ),
                timeout=repository.scan_job_timeout_seconds,
            )
            SCAN_JOBS[job_id]["status"] = "done"
            SCAN_JOBS[job_id]["result"] = result
            repository.update_scan_job(job_id, status="done", result=result)
        except asyncio.CancelledError:
            SCAN_JOBS[job_id]["status"] = "cancelled"
            SCAN_JOBS[job_id]["error"] = "Scan cancelled"
            repository.update_scan_job(job_id, status="cancelled", error="Scan cancelled")
        except asyncio.TimeoutError:
            SCAN_JOBS[job_id]["status"] = "error"
            SCAN_JOBS[job_id]["error"] = "Scan timed out"
            repository.update_scan_job(job_id, status="error", error="Scan timed out")
        except Exception as exc:
            SCAN_JOBS[job_id]["status"] = "error"
            SCAN_JOBS[job_id]["error"] = str(exc)
            repository.update_scan_job(job_id, status="error", error=str(exc))
        finally:
            SCANS_IN_PROGRESS.discard(subnet_id)
            if SCAN_JOBS_BY_SUBNET.get(subnet_id) == job_id:
                del SCAN_JOBS_BY_SUBNET[subnet_id]

    asyncio.create_task(run_job())
    return {"jobId": job_id}


def cancel_autodiscover_job(subnet_id: int, job_id: str):
    job = repository.get_scan_job(job_id)
    if job is None or job["subnet_id"] != subnet_id:
        raise HTTPException(status_code=404, detail="Scan job not found")
    if job["status"] != "running":
        raise HTTPException(status_code=409, detail="Only running scan jobs can be cancelled")
    if not repository.request_scan_job_cancel(job_id, subnet_id):
        raise HTTPException(status_code=409, detail="Scan job can no longer be cancelled")
    return {"jobId": job_id, "cancelRequested": True}


async def retry_autodiscover_job(subnet_id: int, job_id: str):
    job = repository.get_scan_job(job_id)
    if job is None or job["subnet_id"] != subnet_id:
        raise HTTPException(status_code=404, detail="Scan job not found")
    if job["status"] == "running":
        raise HTTPException(status_code=409, detail="A running scan job cannot be retried")
    return await start_autodiscover_job(subnet_id)


def get_scan_schedule(subnet_id: int):
    if not repository.subnet_exists(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")
    return repository.get_scan_schedule(subnet_id)


def update_scan_schedule(subnet_id: int, req: ScanScheduleRequest):
    if not repository.subnet_exists(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")
    return repository.upsert_scan_schedule(subnet_id, req.intervalMinutes, req.enabled)


def get_active_scan(subnet_id: int):
    if not repository.subnet_exists(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")

    job = repository.get_active_scan_job(subnet_id)
    if job is None:
        return {"jobId": None}
    return {"jobId": job["id"], "completed": job["completed"], "total": job["total"]}


async def stream_autodiscover_job(subnet_id: int, job_id: str):
    job = repository.get_scan_job(job_id)
    if job is None or job["subnet_id"] != subnet_id:
        raise HTTPException(status_code=404, detail="Scan job not found")

    async def event_generator():
        while True:
            job = repository.get_scan_job(job_id)
            if job is None:
                break
            addresses = [
                {
                    "address": addr,
                    "status": entry["status"],
                    "alive": entry["alive"],
                    "hostname": entry["hostname"],
                }
                for addr, entry in job["addresses"].items()
            ]
            payload = json.dumps({
                "completed": job["completed"],
                "total": job["total"],
                "status": job["status"],
                "addresses": addresses,
            })
            yield f"data: {payload}\n\n"
            if job["status"] in ("done", "error"):
                final_payload = json.dumps({
                    "completed": job["completed"],
                    "total": job["total"],
                    "status": job["status"],
                    "result": job["result"],
                    "error": job["error"],
                    "addresses": addresses,
                })
                yield f"data: {final_payload}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def get_subnet_scans(subnet_id: int):
    if not repository.subnet_exists(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")
    return repository.list_scans(subnet_id)
