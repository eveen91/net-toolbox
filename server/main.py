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
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Literal, Optional

import paramiko
import winrm
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db
import ipam_scan

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

HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9.\-]+$")
EXECUTOR = ThreadPoolExecutor(max_workers=16)

# IPAM subnet scanning (ping_host + reverse_dns per address) is a distinct
# workload from Connection Test's SSH/WinRM sessions — one scan can fan out
# over hundreds of addresses, so it gets its own bounded pool rather than
# competing with EXECUTOR's 16 slots.
SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=32)

# subnet_id's currently being scanned, so a second scan on the same subnet
# can be rejected/deduped instead of running concurrently with the first.
SCANS_IN_PROGRESS: set[int] = set()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class Source(BaseModel):
    host: str
    os: Literal["linux", "windows"]


class Credentials(BaseModel):
    username: str
    password: str


class RunRequest(BaseModel):
    sources: List[Source]
    destinations: List[str]
    ports: List[int]
    linux_credentials: Optional[Credentials] = None
    windows_credentials: Optional[Credentials] = None
    connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    winrm_port: int = Field(default=5985, ge=1, le=65535)
    winrm_transport: Literal["ntlm", "kerberos", "basic", "credssp"] = "ntlm"
    winrm_scheme: Literal["http", "https"] = "http"


class ResultRow(BaseModel):
    source_host: str
    destination: str
    port: str
    status: str
    timestamp: str


class RunResponse(BaseModel):
    rows: List[ResultRow]
    csv: str


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_host(host: str) -> str:
    host = host.strip()
    if not HOSTNAME_RE.match(host):
        raise ValueError(f"Invalid hostname: {host}")
    return host


def validate_port(port: int) -> int:
    if not (0 < port < 65536):
        raise ValueError(f"Invalid port: {port}")
    return port


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Linux sources — SSH in, run a bash loop over destinations x ports
# ---------------------------------------------------------------------------

def build_linux_script(destinations: List[str], ports: List[int], timeout_seconds: int) -> str:
    dest_str = " ".join(destinations)
    port_str = " ".join(str(p) for p in ports)
    return f"""
DESTINATIONS="{dest_str}"
PORTS="{port_str}"
for DST in $DESTINATIONS; do
  for PORT in $PORTS; do
    if timeout {timeout_seconds} bash -c "</dev/tcp/$DST/$PORT" 2>/dev/null; then
      STATUS="OPEN"
    else
      STATUS="FAILED"
    fi
    echo "$(hostname),$DST,$PORT,$STATUS,$(date '+%F %T')"
  done
done
""".strip()


def test_linux_source(
    host: str,
    creds: Credentials,
    destinations: List[str],
    ports: List[int],
    timeout_seconds: int,
    ssh_port: int,
) -> List[ResultRow]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=ssh_port,
            username=creds.username,
            password=creds.password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        )
        script = build_linux_script(destinations, ports, timeout_seconds)
        _, stdout, stderr = client.exec_command(script, timeout=timeout_seconds * len(destinations) * len(ports) + 15)
        out = stdout.read().decode(errors="replace")
        rows = []
        for line in out.splitlines():
            parts = line.strip().split(",")
            if len(parts) == 5:
                rows.append(ResultRow(source_host=parts[0], destination=parts[1], port=parts[2], status=parts[3], timestamp=parts[4]))
        if not rows:
            rows.append(ResultRow(source_host=host, destination="-", port="-", status="NO_OUTPUT", timestamp=now_str()))
        return rows
    except Exception as exc:
        return [ResultRow(source_host=host, destination="-", port="-", status=f"UNREACHABLE ({exc})", timestamp=now_str())]
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Windows sources — WinRM in, run the PowerShell TcpClient equivalent
# ---------------------------------------------------------------------------

def build_windows_script(destinations: List[str], ports: List[int], timeout_ms: int) -> str:
    dest_ps = ",".join(f"'{d}'" for d in destinations)
    port_ps = ",".join(str(p) for p in ports)
    return f"""
$Destinations = @({dest_ps})
$Ports = @({port_ps})
$TimeoutMs = {timeout_ms}
foreach ($Destination in $Destinations) {{
    foreach ($Port in $Ports) {{
        $TcpClient = New-Object System.Net.Sockets.TcpClient
        try {{
            $Async = $TcpClient.BeginConnect($Destination, $Port, $null, $null)
            if ($Async.AsyncWaitHandle.WaitOne($TimeoutMs)) {{
                $TcpClient.EndConnect($Async)
                $Status = "OPEN"
            }} else {{
                $Status = "TIMEOUT"
            }}
        }} catch {{
            $Status = "FAILED"
        }} finally {{
            $TcpClient.Close()
        }}
        Write-Output "$($env:COMPUTERNAME),$Destination,$Port,$Status,$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    }}
}}
""".strip()


def test_windows_source(
    host: str,
    creds: Credentials,
    destinations: List[str],
    ports: List[int],
    timeout_seconds: int,
    winrm_port: int,
    winrm_transport: str,
    winrm_scheme: str,
) -> List[ResultRow]:
    try:
        endpoint = f"{winrm_scheme}://{host}:{winrm_port}/wsman"
        session = winrm.Session(
            endpoint,
            auth=(creds.username, creds.password),
            transport=winrm_transport,
            server_cert_validation="ignore",
        )
        script = build_windows_script(destinations, ports, timeout_seconds * 1000)
        result = session.run_ps(script)
        out = result.std_out.decode(errors="replace")
        rows = []
        for line in out.splitlines():
            parts = line.strip().split(",")
            if len(parts) == 5:
                rows.append(ResultRow(source_host=parts[0], destination=parts[1], port=parts[2], status=parts[3], timestamp=parts[4]))
        if not rows:
            err = result.std_err.decode(errors="replace").strip()
            status = f"NO_OUTPUT ({err[:120]})" if err else "NO_OUTPUT"
            rows.append(ResultRow(source_host=host, destination="-", port="-", status=status, timestamp=now_str()))
        return rows
    except Exception as exc:
        return [ResultRow(source_host=host, destination="-", port="-", status=f"UNREACHABLE ({exc})", timestamp=now_str())]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/connection-test/run", response_model=RunResponse)
async def run_connection_test(req: RunRequest):
    destinations = [validate_host(d) for d in req.destinations]
    ports = [validate_port(p) for p in req.ports]

    loop = asyncio.get_event_loop()
    tasks = []

    for source in req.sources:
        host = validate_host(source.host)
        if source.os == "linux":
            if req.linux_credentials is None:
                tasks.append(_error_row(host, "Missing Linux credentials"))
                continue
            tasks.append(
                loop.run_in_executor(
                    EXECUTOR,
                    test_linux_source,
                    host,
                    req.linux_credentials,
                    destinations,
                    ports,
                    req.connect_timeout_seconds,
                    req.ssh_port,
                )
            )
        else:
            if req.windows_credentials is None:
                tasks.append(_error_row(host, "Missing Windows credentials"))
                continue
            tasks.append(
                loop.run_in_executor(
                    EXECUTOR,
                    test_windows_source,
                    host,
                    req.windows_credentials,
                    destinations,
                    ports,
                    req.connect_timeout_seconds,
                    req.winrm_port,
                    req.winrm_transport,
                    req.winrm_scheme,
                )
            )

    results = await asyncio.gather(*tasks)
    rows: List[ResultRow] = [row for group in results for row in group]

    csv_lines = ["SourceHost,DestinationHost,Port,Status,Timestamp"]
    for r in rows:
        csv_lines.append(f"{r.source_host},{r.destination},{r.port},{r.status},{r.timestamp}")

    return RunResponse(rows=rows, csv="\n".join(csv_lines))


async def _error_row(host: str, message: str) -> List[ResultRow]:
    return [ResultRow(source_host=host, destination="-", port="-", status=message, timestamp=now_str())]


# ---------------------------------------------------------------------------
# Routing Map — persisted routing tables (SQLite, see db.py)
# ---------------------------------------------------------------------------

class RouteEntry(BaseModel):
    network: str  # CIDR, e.g. "10.0.1.0/24"
    nextHop: str  # e.g. "10.0.1.1", or "directly connected" for local routes
    interface: Optional[str] = None  # e.g. "eth0", "eth4.355"


class InterfaceEntry(BaseModel):
    name: str  # e.g. "eth1", "eth1.301"
    ipAddress: str  # CIDR, e.g. "10.226.0.64/26"
    description: Optional[str] = None


class SaveRoutingHostRequest(BaseModel):
    routes: List[RouteEntry] = []
    interfaces: List[InterfaceEntry] = []


class RoutingHostSummary(BaseModel):
    host: str
    routeCount: int
    interfaceCount: int = 0
    updatedAt: str


class RoutingHostDetail(BaseModel):
    host: str
    updatedAt: str
    routes: List[RouteEntry] = []
    interfaces: List[InterfaceEntry] = []


@app.get("/api/routing/hosts", response_model=List[RoutingHostSummary])
def get_routing_hosts():
    rows = db.list_hosts()
    return [
        RoutingHostSummary(
            host=r["host"],
            routeCount=r["routeCount"],
            interfaceCount=r["interfaceCount"],
            updatedAt=r["updatedAt"],
        )
        for r in rows
    ]


@app.get("/api/routing/export", response_model=List[RoutingHostDetail])
def export_routing_hosts():
    return db.export_all()


@app.get("/api/routing/hosts/{host}", response_model=RoutingHostDetail)
def get_routing_host(host: str):
    data = db.get_host(host)
    if data is None:
        raise HTTPException(status_code=404, detail=f'No saved routing table for "{host}"')
    return data


@app.put("/api/routing/hosts/{host}", response_model=RoutingHostDetail)
def put_routing_host(host: str, req: SaveRoutingHostRequest):
    try:
        return db.save_host(
            host,
            [r.dict() for r in req.routes],
            [i.dict() for i in req.interfaces],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/routing/hosts/{host}")
def delete_routing_host(host: str):
    deleted = db.delete_host(host)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'No saved routing table for "{host}"')
    return {"deleted": host}


# ---------------------------------------------------------------------------
# IPAM — subnets and the individual IP addresses recorded within them
# ---------------------------------------------------------------------------

class SubnetRequest(BaseModel):
    cidr: str
    vlan: Optional[int] = None
    description: Optional[str] = None


class SubnetSummary(BaseModel):
    id: int
    cidr: str
    vlan: Optional[int] = None
    parentId: Optional[int] = None
    description: Optional[str] = None
    updatedAt: str
    totalAddresses: int
    usedCount: int
    freeCount: int
    reservedCount: int
    recordedCount: int


class AddressEntry(BaseModel):
    id: int
    address: str
    status: Literal["used", "free", "reserved"]
    hostname: Optional[str] = None
    description: Optional[str] = None
    team: Optional[str] = None
    machineType: Optional[Literal["physical", "vm"]] = None
    vmCluster: Optional[str] = None
    environment: Optional[Literal["prod", "test", "dev"]] = None
    updatedAt: str


class SubnetDetail(SubnetSummary):
    addresses: List[AddressEntry] = []


class AddressRequest(BaseModel):
    address: str
    status: Literal["used", "free", "reserved"] = "used"
    hostname: Optional[str] = None
    description: Optional[str] = None
    team: Optional[str] = None
    machineType: Optional[Literal["physical", "vm"]] = None
    vmCluster: Optional[str] = None
    environment: Optional[Literal["prod", "test", "dev"]] = None


@app.get("/api/ipam/subnets", response_model=List[SubnetSummary])
def get_subnets():
    return db.list_subnets()


@app.post("/api/ipam/subnets", response_model=SubnetDetail)
def create_subnet(req: SubnetRequest):
    try:
        return db.create_subnet(req.cidr, req.vlan, req.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ipam/subnets/{subnet_id}", response_model=SubnetDetail)
def get_subnet(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return data


@app.put("/api/ipam/subnets/{subnet_id}", response_model=SubnetDetail)
def update_subnet(subnet_id: int, req: SubnetRequest):
    try:
        return db.update_subnet(subnet_id, req.cidr, req.vlan, req.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/ipam/subnets/{subnet_id}")
def delete_subnet(subnet_id: int):
    deleted = db.delete_subnet(subnet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return {"deleted": subnet_id}


@app.post("/api/ipam/subnets/{subnet_id}/addresses", response_model=SubnetDetail)
def create_address(subnet_id: int, req: AddressRequest):
    try:
        return db.add_address(
            subnet_id, req.address, req.status, req.hostname, req.description,
            req.team, req.machineType, req.vmCluster, req.environment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetDetail)
def edit_address(subnet_id: int, address_id: int, req: AddressRequest):
    try:
        return db.update_address(
            subnet_id, address_id, req.address, req.status, req.hostname, req.description,
            req.team, req.machineType, req.vmCluster, req.environment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetDetail)
def remove_address(subnet_id: int, address_id: int):
    try:
        return db.delete_address(subnet_id, address_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/ipam/subnets/{subnet_id}/autodiscover")
async def autodiscover_subnet(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    if subnet_id in SCANS_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="A scan is already running for this subnet")
    SCANS_IN_PROGRESS.add(subnet_id)
    try:
        return {"status": "not implemented yet"}
    finally:
        SCANS_IN_PROGRESS.discard(subnet_id)