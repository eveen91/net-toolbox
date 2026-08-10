"""
net::toolbox backend.

Serves two tools that need server-side work the browser can't do itself:

  - Connection Test: SSHes into Linux sources / opens a WinRM session to
    Windows sources and runs a remote TCP-connectivity check against each
    destination:port, same approach as the original .sh / .ps1 scripts.
  - Routing Map: persists each host's routing table (CIDR network + next
    hop) and interface list to a local SQLite database so it survives across sessions.

Run it with:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List, Literal, Optional

import paramiko
import winrm
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db

app = FastAPI(title="net::toolbox API")


@app.on_event("startup")
def _init_db():
    db.init_db()


# In development the frontend runs on a different port (Vite), so allow it.
# Lock this down to your actual frontend origin in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EXECUTOR = ThreadPoolExecutor(max_workers=16)


# --- Routing Map Models ---

class RouteEntry(BaseModel):
    network: str
    nextHop: str


class InterfaceEntry(BaseModel):
    name: str
    ipAddress: str
    description: Optional[str] = None


class SaveRoutingHostRequest(BaseModel):
    routes: List[RouteEntry] = []
    interfaces: List[InterfaceEntry] = []


class RoutingHostDetail(BaseModel):
    host: str
    updatedAt: str
    routes: List[RouteEntry] = []
    interfaces: List[InterfaceEntry] = []


# --- Connection Test Models ---

class Credentials(BaseModel):
    username: str
    password: str


class SourceHost(BaseModel):
    host: str
    os: Literal["linux", "windows"]


class ConnectionTestRequest(BaseModel):
    sources: List[SourceHost]
    destinations: List[str]
    ports: List[int]
    linux_credentials: Optional[Credentials] = None
    windows_credentials: Optional[Credentials] = None
    connect_timeout_seconds: int = 5
    ssh_port: int = 22
    winrm_port: int = 5985
    winrm_transport: str = "ntlm"
    winrm_scheme: str = "http"


# --- Routing Map Endpoints ---

@app.get("/api/routing/hosts")
def list_routing_hosts():
    return db.list_hosts()


@app.get("/api/routing/hosts/{host}")
def get_routing_host(host: str):
    data = db.get_host(host)
    if not data:
        raise HTTPException(status_code=404, detail="Host not found")
    return data


@app.put("/api/routing/hosts/{host}")
def save_routing_host(host: str, request: SaveRoutingHostRequest):
    try:
        routes_data = [r.model_dump() for r in request.routes]
        interfaces_data = [i.model_dump() for i in request.interfaces]
        saved = db.save_host(host, routes_data, interfaces_data)
        return saved
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/routing/hosts/{host}")
def delete_routing_host(host: str):
    deleted = db.delete_host(host)
    if not deleted:
        raise HTTPException(status_code=404, detail="Host not found")
    return {"message": f"Deleted host {host}"}


@app.get("/api/routing/export")
def export_routing_hosts():
    return db.export_all()


# --- Connection Test Helpers & Endpoint ---

def _test_linux_source(src: SourceHost, req: ConnectionTestRequest) -> List[dict]:
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    if not req.linux_credentials:
        for dst in req.destinations:
            for port in req.ports:
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": "NO_CREDENTIALS",
                    "timestamp": now,
                })
        return rows

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=src.host,
            port=req.ssh_port,
            username=req.linux_credentials.username,
            password=req.linux_credentials.password,
            timeout=req.connect_timeout_seconds,
            banner_timeout=req.connect_timeout_seconds,
        )
    except Exception as e:
        for dst in req.destinations:
            for port in req.ports:
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": f"UNREACHABLE ({type(e).__name__})",
                    "timestamp": now,
                })
        return rows

    try:
        cmd_parts = []
        for dst in req.destinations:
            for port in req.ports:
                cmd_parts.append(
                    f'echo -n "{dst}:{port}:"; timeout {req.connect_timeout_seconds} bash -c "</dev/tcp/{dst}/{port}" 2>/dev/null && echo "OPEN" || echo "CLOSED"'
                )
        script = " ; ".join(cmd_parts)
        stdin, stdout, stderr = ssh.exec_command(script, timeout=req.connect_timeout_seconds * len(cmd_parts) + 5)
        output = stdout.read().decode("utf-8", errors="replace")
        ssh.close()

        results_map = {}
        for line in output.splitlines():
            parts = line.strip().split(":")
            if len(parts) == 3:
                d, p_str, st = parts[0], parts[1], parts[2]
                try:
                    results_map[(d, int(p_str))] = st
                except ValueError:
                    pass

        for dst in req.destinations:
            for port in req.ports:
                st = results_map.get((dst, port), "NO_OUTPUT")
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": st,
                    "timestamp": now,
                })
    except Exception as e:
        ssh.close()
        for dst in req.destinations:
            for port in req.ports:
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": f"FAILED ({type(e).__name__})",
                    "timestamp": now,
                })
    return rows


def _test_windows_source(src: SourceHost, req: ConnectionTestRequest) -> List[dict]:
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    if not req.windows_credentials:
        for dst in req.destinations:
            for port in req.ports:
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": "NO_CREDENTIALS",
                    "timestamp": now,
                })
        return rows

    endpoint = f"{req.winrm_scheme}://{src.host}:{req.winrm_port}/wsman"
    try:
        session = winrm.Session(
            endpoint,
            auth=(req.windows_credentials.username, req.windows_credentials.password),
            transport=req.winrm_transport,
            server_cert_validation="ignore",
        )
    except Exception as e:
        for dst in req.destinations:
            for port in req.ports:
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": f"UNREACHABLE ({type(e).__name__})",
                    "timestamp": now,
                })
        return rows

    timeout_ms = req.connect_timeout_seconds * 1000
    ps_lines = []
    for dst in req.destinations:
        for port in req.ports:
            ps_lines.append(
                f"$c = New-Object System.Net.Sockets.TcpClient; $a = $c.BeginConnect('{dst}', {port}, $null, $null); if ($a.AsyncWaitHandle.WaitOne({timeout_ms}, $false)) {{ try {{ $c.EndConnect($a); Write-Host '{dst}:{port}:OPEN' }} catch {{ Write-Host '{dst}:{port}:CLOSED' }} }} else {{ Write-Host '{dst}:{port}:TIMEOUT' }}; $c.Close()"
            )
    ps_script = "\n".join(ps_lines)

    try:
        res = session.run_ps(ps_script)
        output = res.std_out.decode("utf-8", errors="replace")
        results_map = {}
        for line in output.splitlines():
            parts = line.strip().split(":")
            if len(parts) == 3:
                d, p_str, st = parts[0], parts[1], parts[2]
                try:
                    results_map[(d, int(p_str))] = st
                except ValueError:
                    pass

        for dst in req.destinations:
            for port in req.ports:
                st = results_map.get((dst, port), "NO_OUTPUT")
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": st,
                    "timestamp": now,
                })
    except Exception as e:
        for dst in req.destinations:
            for port in req.ports:
                rows.append({
                    "source_host": src.host,
                    "destination": dst,
                    "port": port,
                    "status": f"FAILED ({type(e).__name__})",
                    "timestamp": now,
                })
    return rows


def _run_single_source(src: SourceHost, req: ConnectionTestRequest) -> List[dict]:
    if src.os == "linux":
        return _test_linux_source(src, req)
    elif src.os == "windows":
        return _test_windows_source(src, req)
    return []


@app.post("/api/connection-test/run")
async def run_connection_test(req: ConnectionTestRequest):
    loop = asyncio.get_running_loop()
    futures = [
        loop.run_in_executor(EXECUTOR, _run_single_source, src, req)
        for src in req.sources
    ]
    results = await asyncio.gather(*futures)
    all_rows = [row for sublist in results for row in sublist]
    return {"rows": all_rows}
