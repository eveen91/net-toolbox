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
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Literal, Optional

import paramiko
import winrm
from fastapi import FastAPI, HTTPException, Response, Request, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
import auth
import auth_db
import ipam_scan

app = FastAPI(title="net::toolbox API")


@app.on_event("startup")
def _init_db():
    db.init_db()
    auth_db.init_auth_db()


# In development the frontend runs on a different port (Vite), so allow it.
# Lock this down to your actual frontend origin in production.
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
}


@app.middleware("http")
async def require_auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    if not auth_db.is_login_required():
        return await call_next(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token or auth_db.get_user_by_session_token(token) is None:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return await call_next(request)

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

# Background scan jobs, keyed by job id. Each value:
# {"subnet_id": int, "completed": int, "total": int,
#  "status": "running" | "done" | "error",
#  "result": dict | None, "error": str | None, "created_at": float}
SCAN_JOBS: dict[str, dict] = {}

# Reverse lookup from subnet_id to the job_id currently scanning it, so a
# subnet's active job can be found without scanning all of SCAN_JOBS.
SCAN_JOBS_BY_SUBNET: dict[int, str] = {}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class Source(BaseModel):
    host: str
    os: Literal["linux", "windows"]


class Credentials(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    id: int
    username: str
    role: str


class SessionInfoResponse(BaseModel):
    loginRequired: bool
    user: Optional[UserPublic] = None


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


SESSION_COOKIE_NAME = "session_token"


@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    user = auth_db.get_user_by_username(req.username)
    if user is None or not auth.verify_password(req.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth.generate_session_token()
    auth_db.create_session(user["id"], token)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=auth.SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return UserPublic(id=user["id"], username=user["username"], role=user["role"])


@app.post("/api/auth/logout")
def logout(response: Response, session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
    if session_token:
        auth_db.delete_session_by_token(session_token)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/session", response_model=SessionInfoResponse)
def get_session_info(session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
    login_required = auth_db.is_login_required()
    user = None
    if session_token:
        found = auth_db.get_user_by_session_token(session_token)
        if found:
            user = UserPublic(id=found["id"], username=found["username"], role=found["role"])
    return SessionInfoResponse(loginRequired=login_required, user=user)


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
    locked: bool = False
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
    locked: bool = False


class BulkAddressUpdateRequest(BaseModel):
    """
    Bulk-edit a set of addresses (by id) within one subnet.

    Every field below besides addressIds is optional so a request only
    touches what it explicitly sends. This depends on Pydantic v2's
    exclude_unset behavior: a field key that's simply absent from the
    request body never lands in `model_fields_set`, while a field sent
    as `null` DOES land in `model_fields_set` (with a value of None) -
    so `req.model_dump(exclude_unset=True)` distinguishes "leave this
    field alone" (key absent) from "clear this field" (key present,
    value null) from "set this field" (key present, real value).
    Do NOT special-case any of these fields with `is not None` checks
    downstream - that collapses "not sent" and "explicitly cleared"
    into the same branch, which is exactly what this model exists to
    avoid.
    """

    addressIds: List[int]
    status: Optional[Literal["used", "free", "reserved"]] = None
    team: Optional[str] = None
    machineType: Optional[Literal["physical", "vm"]] = None
    vmCluster: Optional[str] = None
    environment: Optional[Literal["prod", "test", "dev"]] = None
    locked: Optional[bool] = None


class ScanExcludeEntry(BaseModel):
    id: int
    address: str


class ScanExcludeRequest(BaseModel):
    address: str


class AutodiscoverResult(BaseModel):
    address: str
    alive: bool
    hostname: Optional[str] = None


class HostnameChange(BaseModel):
    address: str
    oldHostname: Optional[str] = None
    newHostname: Optional[str] = None


class ScanDiff(BaseModel):
    newlyUsed: List[str]
    wentQuiet: List[str]
    hostnameChanged: List[HostnameChange]


class AutodiscoverResponse(BaseModel):
    scanId: int
    scannedCount: int
    usedCount: int
    freeCount: int
    skippedCount: int
    results: List[AutodiscoverResult]
    diff: ScanDiff


class ScanSummary(BaseModel):
    id: int
    subnet_id: int
    startedAt: str
    finishedAt: str
    scannedCount: int
    usedCount: int
    freeCount: int
    skippedCount: int
    newlyUsedCount: int
    wentQuietCount: int
    hostnameChangedCount: int
    diff: ScanDiff


class DashboardEntry(BaseModel):
    id: int
    cidr: str
    vlan: Optional[int] = None
    description: Optional[str] = None
    totalAddresses: int
    usedCount: int
    freeCount: int
    reservedCount: int
    recordedCount: int
    lastScannedAt: Optional[str] = None
    lastScanNewlyUsed: Optional[int] = None
    lastScanWentQuiet: Optional[int] = None
    lastScanHostnameChanged: Optional[int] = None


@app.get("/api/ipam/dashboard", response_model=List[DashboardEntry])
def get_ipam_dashboard():
    subnets = db.list_subnets()
    entries = []
    for s in subnets:
        last_scan = db.get_last_scan(s["id"])
        entries.append({
            "id": s["id"],
            "cidr": s["cidr"],
            "vlan": s["vlan"],
            "description": s["description"],
            "totalAddresses": s["totalAddresses"],
            "usedCount": s["usedCount"],
            "freeCount": s["freeCount"],
            "reservedCount": s["reservedCount"],
            "recordedCount": s["recordedCount"],
            "lastScannedAt": last_scan["finishedAt"] if last_scan else None,
            "lastScanNewlyUsed": last_scan["newlyUsedCount"] if last_scan else None,
            "lastScanWentQuiet": last_scan["wentQuietCount"] if last_scan else None,
            "lastScanHostnameChanged": last_scan["hostnameChangedCount"] if last_scan else None,
        })
    return entries


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
            req.team, req.machineType, req.vmCluster, req.environment, req.locked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetDetail)
def edit_address(subnet_id: int, address_id: int, req: AddressRequest):
    try:
        return db.update_address(
            subnet_id, address_id, req.address, req.status, req.hostname, req.description,
            req.team, req.machineType, req.vmCluster, req.environment, req.locked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetDetail)
def remove_address(subnet_id: int, address_id: int):
    try:
        return db.delete_address(subnet_id, address_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.patch("/api/ipam/subnets/{subnet_id}/addresses/bulk", response_model=SubnetDetail)
def bulk_edit_addresses(subnet_id: int, req: BulkAddressUpdateRequest):
    if not req.addressIds:
        raise HTTPException(status_code=400, detail="No addresses selected")
    try:
        fields = req.dict(exclude_unset=True, exclude={"addressIds"})
        return db.bulk_update_addresses(subnet_id, req.addressIds, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/ipam/subnets/{subnet_id}/addresses/{address_id}/rescan", response_model=SubnetDetail)
async def rescan_address(subnet_id: int, address_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    address_row = next((addr for addr in data["addresses"] if addr["id"] == address_id), None)
    if address_row is None:
        raise HTTPException(status_code=404, detail="Address not found")

    if subnet_id in SCANS_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="A scan is already running for this subnet")

    if address_row["status"] == "reserved":
        # Reserved addresses are intentionally never pinged.
        return db.get_subnet(subnet_id)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        SCAN_EXECUTOR,
        ipam_scan.scan_one,
        address_row["address"],
        ipam_scan.DEFAULT_PING_TIMEOUT,
        ipam_scan.DEFAULT_PING_ATTEMPTS,
        ipam_scan.DEFAULT_DNS_TIMEOUT,
    )
    db.apply_scan_result(subnet_id, address_row["address"], result["alive"], result["hostname"])
    return db.get_subnet(subnet_id)


@app.get("/api/ipam/subnets/{subnet_id}/scan-excludes", response_model=List[ScanExcludeEntry])
def list_subnet_scan_excludes(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return db.list_scan_excludes_detailed(subnet_id)


@app.post("/api/ipam/subnets/{subnet_id}/scan-excludes", response_model=List[ScanExcludeEntry])
def create_subnet_scan_exclude(subnet_id: int, req: ScanExcludeRequest):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    try:
        db.validate_address_in_subnet(req.address, data["cidr"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.add_scan_exclude(subnet_id, req.address.strip())
    return db.list_scan_excludes_detailed(subnet_id)


@app.delete("/api/ipam/subnets/{subnet_id}/scan-excludes/{exclude_id}", response_model=List[ScanExcludeEntry])
def remove_subnet_scan_exclude(subnet_id: int, exclude_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    db.remove_scan_exclude_by_id(subnet_id, exclude_id)
    return db.list_scan_excludes_detailed(subnet_id)


async def perform_scan(subnet_id: int, on_progress=None, on_targets_ready=None, on_address_update=None) -> dict:
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    excludes = set(db.list_scan_excludes(subnet_id))
    excludes.update(
        addr["address"]
        for addr in data["addresses"]
        if addr["status"] == "reserved" or addr["locked"]
    )

    try:
        targets = ipam_scan.enumerate_scan_targets(data["cidr"], excludes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if on_targets_ready is not None:
        on_targets_ready(targets)

    started_at = now_str()
    existing_by_address = {a["address"]: a for a in db.get_addresses_by_subnet(subnet_id)}
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
    for address in targets:
        if on_address_update is not None:
            on_address_update(address, "in_progress")
        tasks.append(
            loop.run_in_executor(
                SCAN_EXECUTOR,
                ipam_scan.scan_one,
                address,
                ipam_scan.DEFAULT_PING_TIMEOUT,
                ipam_scan.DEFAULT_PING_ATTEMPTS,
                ipam_scan.DEFAULT_DNS_TIMEOUT,
            )
        )
    for coro in asyncio.as_completed(tasks):
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
        address = result["address"]
        db.apply_scan_result(subnet_id, address, result["alive"], result["hostname"])
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
    scan_record = db.record_scan(
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


@app.post("/api/ipam/subnets/{subnet_id}/autodiscover", response_model=AutodiscoverResponse)
async def autodiscover_subnet(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    if subnet_id in SCANS_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="A scan is already running for this subnet")
    SCANS_IN_PROGRESS.add(subnet_id)
    try:
        return await perform_scan(subnet_id)
    finally:
        SCANS_IN_PROGRESS.discard(subnet_id)


def cleanup_old_scan_jobs(max_age_seconds: float = 300.0) -> None:
    now = time.time()
    stale_ids = [
        job_id
        for job_id, job in SCAN_JOBS.items()
        if job["status"] in ("done", "error") and now - job["created_at"] > max_age_seconds
    ]
    for job_id in stale_ids:
        del SCAN_JOBS[job_id]


@app.post("/api/ipam/subnets/{subnet_id}/autodiscover/start")
async def start_autodiscover_job(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    if subnet_id in SCANS_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="A scan is already running for this subnet")

    cleanup_old_scan_jobs()

    job_id = str(uuid.uuid4())
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

            def on_targets_ready(targets):
                SCAN_JOBS[job_id]["addresses"] = {
                    addr: {"status": "pending", "alive": None, "hostname": None}
                    for addr in targets
                }

            def on_address_update(address, status, alive=None, hostname=None):
                entry = SCAN_JOBS[job_id]["addresses"].get(address)
                if entry is not None:
                    entry["status"] = status
                    if alive is not None:
                        entry["alive"] = alive
                    if hostname is not None:
                        entry["hostname"] = hostname

            result = await perform_scan(
                subnet_id,
                on_progress=on_progress,
                on_targets_ready=on_targets_ready,
                on_address_update=on_address_update,
            )
            SCAN_JOBS[job_id]["status"] = "done"
            SCAN_JOBS[job_id]["result"] = result
        except Exception as exc:
            SCAN_JOBS[job_id]["status"] = "error"
            SCAN_JOBS[job_id]["error"] = str(exc)
        finally:
            SCANS_IN_PROGRESS.discard(subnet_id)
            if SCAN_JOBS_BY_SUBNET.get(subnet_id) == job_id:
                del SCAN_JOBS_BY_SUBNET[subnet_id]

    asyncio.create_task(run_job())
    return {"jobId": job_id}


@app.get("/api/ipam/subnets/{subnet_id}/autodiscover/active")
def get_active_scan(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    job_id = SCAN_JOBS_BY_SUBNET.get(subnet_id)
    if job_id is None:
        return {"jobId": None}

    job = SCAN_JOBS[job_id]
    return {"jobId": job_id, "completed": job["completed"], "total": job["total"]}


@app.get("/api/ipam/subnets/{subnet_id}/autodiscover/stream/{job_id}")
async def stream_autodiscover_job(subnet_id: int, job_id: str):
    if job_id not in SCAN_JOBS:
        raise HTTPException(status_code=404, detail="Scan job not found")

    async def event_generator():
        while True:
            job = SCAN_JOBS.get(job_id)
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


@app.get("/api/ipam/subnets/{subnet_id}/scans", response_model=List[ScanSummary])
def get_subnet_scans(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return db.list_scans(subnet_id)