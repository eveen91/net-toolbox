"""Separate bounded capacity: connection tests cannot occupy diagnostic workers."""
import asyncio
import csv
import io
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from tenancy.context import run_in_executor

EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="connection-test")
RUN_SLOTS = threading.BoundedSemaphore(2)


async def run_sources(req, linux_probe, windows_probe, error_row):
    if not RUN_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Connection tests are busy. Retry shortly", headers={"Retry-After": "5"})
    tasks = []
    loop = asyncio.get_running_loop()
    try:
        for source in req.sources:
            if source.os == "linux":
                if req.linux_credentials is None:
                    tasks.append(asyncio.create_task(error_row(source.host, "Missing Linux credentials")))
                else:
                    tasks.append(run_in_executor(loop, EXECUTOR, linux_probe, source.host, req.linux_credentials,
                                                 req.destinations, req.ports, req.connect_timeout_seconds, req.ssh_port))
            else:
                if req.windows_credentials is None:
                    tasks.append(asyncio.create_task(error_row(source.host, "Missing Windows credentials")))
                else:
                    tasks.append(run_in_executor(loop, EXECUTOR, windows_probe, source.host, req.windows_credentials,
                                                 req.destinations, req.ports, req.connect_timeout_seconds,
                                                 req.winrm_port, req.winrm_transport, req.winrm_scheme))
    except BaseException:
        if tasks:
            pending = asyncio.gather(*tasks, return_exceptions=True)
            pending.add_done_callback(lambda _: RUN_SLOTS.release())
        else:
            RUN_SLOTS.release()
        raise
    pending = asyncio.gather(*tasks, return_exceptions=True)
    # A disconnected/cancelled request keeps its slot until its probes finish.
    pending.add_done_callback(lambda _: RUN_SLOTS.release())
    results = await asyncio.shield(pending)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return [row for group in results for row in group]


def results_csv(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["SourceHost", "DestinationHost", "Port", "Status", "Timestamp"])
    writer.writerows((row.source_host, row.destination, row.port, row.status, row.timestamp) for row in rows)
    return output.getvalue()
