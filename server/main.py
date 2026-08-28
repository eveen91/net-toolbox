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
import ipaddress
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Literal, Optional

import paramiko
import winrm
from fastapi import FastAPI, HTTPException, Response, Request, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from pydantic_core import ValidationError

import db
import auth
import auth_db
import ldap_auth
import ipam_scan
import rate_limit
import ssh_security
import troubleshoot_devices
import troubleshoot_logic
import troubleshoot_audit
import validation_routes
from device_drivers.base import DeviceSession
from device_drivers import get_driver
from logging_config import setup_logging

logger = logging.getLogger("net_toolbox.main")

app = FastAPI(title="net::toolbox API")


@app.on_event("startup")
def _init_db():
    setup_logging()
    db.init_db()
    auth_db.init_auth_db()
    troubleshoot_devices.init_db()
    troubleshoot_audit.init_db()


# Browser origins allowed to make credentialed cross-origin requests.
# Dev (Vite, :5173) and Docker (serve, :3000) both serve the frontend from
# localhost/loopback, so those are allowed by default. If you browse from
# another machine via a LAN IP/hostname (e.g. http://192.168.1.10:3000), add
# it explicitly via the CORS_ORIGINS env var (comma-separated). Never use a
# wildcard or broad regex together with allow_credentials=True — that would
# let any page on a matching port make authenticated requests as the user.
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://[::1]:3000",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
FRONTEND_ORIGINS.extend(_extra_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(validation_routes.router)

PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
    "/api/admin/bootstrap-status",
    "/api/admin/bootstrap",
}


@app.middleware("http")
async def combined_middleware(request: Request, call_next):
    # CSRF protection: enforce header on state-changing methods
    if request.method not in ["GET", "HEAD", "OPTIONS"]:
        # We allow a custom header; frontend must provide it.
        # For this internal tool, a fixed header constant is a sufficient 
        # deterrent against browser-based automated CSRF.
        if request.headers.get("X-CSRF-TOKEN") != "fixed-csrf-token":
            return JSONResponse(status_code=403, content={"detail": "Missing or invalid CSRF token"})
    
    # Auth protection
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


@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    # Logs every API call: 4xx/5xx at warning/error (so problems surface
    # even at the default INFO level), successful calls at debug (to avoid
    # noise unless DEBUG is on). Unhandled exceptions propagate to the
    # exception handler below, which logs the full traceback.
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        raise
    duration_ms = (time.time() - start) * 1000
    if response.status_code >= 500:
        logger.error(
            "%s %s -> %s (%.0fms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
    elif response.status_code >= 400:
        logger.warning(
            "%s %s -> %s (%.0fms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
    else:
        logger.debug(
            "%s %s -> %s (%.0fms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Last line of defense: any exception that escaped an endpoint handler
    # gets logged with its full traceback (module/function/line) and a 500
    # returned. HTTPExceptions are handled by FastAPI separately and never
    # land here.
    logger.error(
        "Unhandled exception in %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9.\-]+$")
EXECUTOR = ThreadPoolExecutor(max_workers=16)

# IPAM subnet scanning (ping_host + reverse_dns per address) is a distinct
# workload from Connection Test's SSH/WinRM sessions — one scan can fan out
# over hundreds of addresses, so it gets its own bounded pool rather than
# competing with EXECUTOR's 16 slots.
SCAN_EXECUTOR = ThreadPoolExecutor(max_workers=256)

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
    authMethod: Literal["local", "ad"] = "local"


class UserPublic(BaseModel):
    id: int
    username: str
    role: str
    authSource: str
    permissions: List[str] = []


class SessionInfoResponse(BaseModel):
    loginRequired: bool
    adEnabled: bool
    user: Optional[UserPublic] = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"

    @field_validator("password")
    @classmethod
    def validate_pw(cls, v):
        validate_password_strength(v)
        return v


class UpdateUserRoleRequest(BaseModel):
    role: str


class ResetPasswordRequest(BaseModel):
    newPassword: str

    @field_validator("newPassword")
    @classmethod
    def validate_pw(cls, v):
        validate_password_strength(v)
        return v


class RolePublic(BaseModel):
    id: int
    name: str
    permissions: List[str]
    isBuiltin: bool
    adGroups: List[str] = []


class CreateRoleRequest(BaseModel):
    name: str
    permissions: List[str] = []


class UpdateRoleRequest(BaseModel):
    permissions: List[str]


class RoleAdGroupRequest(BaseModel):
    groupDn: str


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str

    @field_validator("newPassword")
    @classmethod
    def validate_pw(cls, v):
        validate_password_strength(v)
        return v


class RequireLoginRequest(BaseModel):
    enabled: bool


class AdSettingsResponse(BaseModel):
    enabled: bool
    host: str
    port: int
    useTls: bool
    domainSuffix: str
    requiredGroupDn: Optional[str] = None
    adminGroupDn: Optional[str] = None


class UpdateAdSettingsRequest(BaseModel):
    enabled: bool
    host: str
    port: int = 636
    useTls: bool = True
    domainSuffix: str
    requiredGroupDn: Optional[str] = None
    adminGroupDn: Optional[str] = None


class TestAdConnectionRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    useTls: Optional[bool] = None


class TestAdConnectionResponse(BaseModel):
    reachable: bool
    tlsValid: Optional[bool] = None
    error: Optional[str] = None


class BootstrapStatusResponse(BaseModel):
    adminExists: bool
    bootstrapSecretRequired: bool


class BootstrapAdminRequest(BaseModel):
    username: str
    password: str
    secret: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_pw(cls, v):
        validate_password_strength(v)
        return v


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

DEVICE_PORT_RE = re.compile(r"^[A-Za-z0-9./:_-]+$")


def validate_host(host: str) -> str:
    host = host.strip()
    if not HOSTNAME_RE.match(host):
        raise ValueError(f"Invalid hostname: {host}")
    return host


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one digit")
    if not any(char.isupper() for char in password):
        raise ValueError("Password must contain at least one uppercase letter")




def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
def validate_port_identifier(port: str) -> str:
    if not DEVICE_PORT_RE.match(port):
        raise ValueError("Invalid port format")
    return port

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
    ssh_security.configure_ssh_client(client)
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
        logger.warning("Connection test failed for Linux source %s: %s", host, exc)
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
        # Fail closed on TLS: validate the server certificate instead of
        # ignoring it. Point WINRM_CA_TRUST_PATH at a CA bundle (e.g. your
        # internal issuing CA) to trust self-signed WinRM hosts securely.
        winrm_kwargs = {
            "transport": winrm_transport,
            "server_cert_validation": "validate",
        }
        ca_trust_path = os.environ.get("WINRM_CA_TRUST_PATH")
        if ca_trust_path:
            winrm_kwargs["ca_trust_path"] = ca_trust_path
        session = winrm.Session(
            endpoint,
            auth=(creds.username, creds.password),
            **winrm_kwargs,
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
        logger.warning("Connection test failed for Windows source %s: %s", host, exc)
        return [ResultRow(source_host=host, destination="-", port="-", status=f"UNREACHABLE ({exc})", timestamp=now_str())]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


SESSION_COOKIE_NAME = "session_token"


def is_cookie_secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_cookie_secure(),
        max_age=auth.SESSION_TTL_DAYS * 24 * 60 * 60,
    )


def require_admin_user(
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Optional[Dict]:
    # The Config Panel has its own access gate, separate from the site-wide
    # "require login" toggle: once an admin user has been created, opening
    # or calling into the Config Panel always needs a real admin session —
    # even while regular tools are left open to everyone. The only window
    # left unauthenticated is before any admin exists yet, which mirrors
    # the frontend's "create admin" screen and is what lets that screen's
    # first save go through. Once that first admin is created this branch
    # never opens again, so every other admin API call requires a session.
    if not auth_db.is_login_required() and auth_db.count_admin_users() == 0:
        return None
    user = None
    if session_token:
        user = auth_db.get_user_by_session_token(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_logged_in_user(
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Dict:
    user = None
    if session_token:
        user = auth_db.get_user_by_session_token(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def user_permissions(user: Dict) -> List[str]:
    return auth_db.role_permissions_for_name(user["role"])


def _user_public(user: Dict) -> UserPublic:
    return UserPublic(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        authSource=user["authSource"],
        permissions=user_permissions(user),
    )


def require_feature(feature_id: str):
    """Dependency factory: gates a tool's backend endpoints behind the
    caller's role permissions, the same permissions the Config Panel's
    Roles editor manages. A no-op when login isn't required, matching the
    rest of the app's behavior in that mode."""

    def _dependency(
        session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> Optional[Dict]:
        if not auth_db.is_login_required():
            return None
        user = None
        if session_token:
            user = auth_db.get_user_by_session_token(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        permissions = user_permissions(user)
        if "*" not in permissions and feature_id not in permissions:
            raise HTTPException(
                status_code=403, detail=f'Your role does not have access to "{feature_id}"'
            )
        return user

    return _dependency


def _login_via_ad(username: str, password: str) -> Optional[Dict]:
    config = auth_db.get_ad_config()
    if not config["enabled"]:
        return None

    bindings = auth_db.list_all_role_group_bindings()
    candidate_group_dns = [b["groupDn"] for b in bindings]

    result = ldap_auth.authenticate_ad_user(
        username,
        password,
        config["host"],
        config["port"],
        config["useTls"],
        config["domainSuffix"],
        required_group_dn=config["requiredGroupDn"],
        admin_group_dn=config["adminGroupDn"],
        candidate_group_dns=candidate_group_dns,
    )
    if result is None:
        return None

    if not result["isRequiredMember"]:
        return None

    existing = auth_db.get_user_by_username_and_source(username, "ad")
    if existing is not None:
        return existing

    # .get(...) with a default, not result["matchedGroupDns"] — some callers
    # (existing tests) mock authenticate_ad_user's return value and won't
    # include this key, so this must not KeyError on them.
    matched_group_dns = result.get("matchedGroupDns", [])
    role = ldap_auth.resolve_role_from_bindings(matched_group_dns, bindings) or auth_db.DEFAULT_ROLE_NAME
    return auth_db.create_user(username, "", role=role, auth_source="ad")


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    if not rate_limit.check_allowed(request, req.username):
        logger.warning(
            "Rate limit exceeded for IP %s / user %s",
            rate_limit.client_ip(request),
            req.username,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
        )

    if req.authMethod == "ad":
        user = _login_via_ad(req.username, req.password)
    else:
        user = auth_db.get_user_by_username_and_source(req.username, "local")
        if user is None:
            # Dummy verify to mitigate timing-based username enumeration
            auth.verify_password(req.password, "$2b$12$R9h/cIPz0gi.URNNX3kh2OPST9/zBsqquzaFA4o9x1Gg13x2P9c7m")
            user = None
        elif not auth.verify_password(req.password, user["passwordHash"]):
            user = None

    if user is None:
        logger.warning("Login failed for user %s (method=%s)", req.username, req.authMethod)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    logger.info("Login succeeded for user %s (method=%s)", user["username"], user["authSource"])
    token = auth.generate_session_token()
    auth_db.create_session(user["id"], token)
    set_session_cookie(response, token)
    return _user_public(user)


@app.post("/api/auth/logout")
def logout(response: Response, session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
    if session_token:
        auth_db.delete_session_by_token(session_token)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        samesite="lax",
        httponly=True,
        secure=is_cookie_secure(),
    )
    return {"ok": True}


@app.get("/api/auth/session", response_model=SessionInfoResponse)
def get_session_info(session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
    login_required = auth_db.is_login_required()
    ad_enabled = auth_db.get_ad_config()["enabled"]
    user = None
    if session_token:
        found = auth_db.get_user_by_session_token(session_token)
        if found:
            user = _user_public(found)
    return SessionInfoResponse(loginRequired=login_required, adEnabled=ad_enabled, user=user)


@app.post("/api/auth/change-password")
def change_own_password(req: ChangePasswordRequest, user: Dict = Depends(require_logged_in_user)):
    if not auth.verify_password(req.currentPassword, user["passwordHash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    new_hash = auth.hash_password(req.newPassword)
    auth_db.update_user_password(user["id"], new_hash)
    auth_db.revoke_all_sessions_for_user(user["id"])
    return {"ok": True}


@app.post("/api/admin/bootstrap-status", response_model=BootstrapStatusResponse)
def admin_bootstrap_status():
    bootstrap_secret = os.environ.get("BOOTSTRAP_SECRET")
    return BootstrapStatusResponse(
        adminExists=auth_db.count_admin_users() > 0,
        bootstrapSecretRequired=bool(bootstrap_secret),
    )


@app.post("/api/admin/bootstrap", response_model=UserPublic)
def bootstrap_admin_user(req: BootstrapAdminRequest, response: Response):
    if auth_db.count_admin_users() > 0:
        raise HTTPException(status_code=400, detail="An admin user already exists")

    bootstrap_secret = os.environ.get("BOOTSTRAP_SECRET")
    if bootstrap_secret:
        if not req.secret or not secrets.compare_digest(req.secret, bootstrap_secret):
            raise HTTPException(status_code=403, detail="Invalid or missing bootstrap secret")

    username = req.username.strip()
    if not username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    password_hash = auth.hash_password(req.password)
    try:
        user = auth_db.create_user(username, password_hash, role=auth_db.ADMIN_ROLE_NAME)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Log the new admin straight in so the Config Panel opens immediately
    # instead of bouncing them to a second login screen.
    token = auth.generate_session_token()
    auth_db.create_session(user["id"], token)
    set_session_cookie(response, token)
    return _user_public(user)


@app.get("/api/admin/users", response_model=List[UserPublic])
def list_admin_users(admin: Optional[Dict] = Depends(require_admin_user)):
    users = auth_db.list_users()
    return [_user_public(u) for u in users]


@app.post("/api/admin/users", response_model=UserPublic)
def create_admin_user(req: CreateUserRequest, admin: Optional[Dict] = Depends(require_admin_user)):
    role = req.role.strip()
    if role != auth_db.ADMIN_ROLE_NAME and auth_db.get_role_by_name(role) is None:
        raise HTTPException(status_code=400, detail=f'Role "{role}" does not exist')
    try:
        password_hash = auth.hash_password(req.password)
        user = auth_db.create_user(req.username, password_hash, role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _user_public(user)


@app.patch("/api/admin/users/{user_id}/role", response_model=UserPublic)
def update_admin_user_role(
    user_id: int, req: UpdateUserRoleRequest, admin: Optional[Dict] = Depends(require_admin_user)
):
    target = auth_db.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target["authSource"] == "ad":
        raise HTTPException(
            status_code=400,
            detail="Role is managed by Active Directory group membership for this account and cannot be changed manually",
        )
    role = req.role.strip()
    if role != auth_db.ADMIN_ROLE_NAME and auth_db.get_role_by_name(role) is None:
        raise HTTPException(status_code=400, detail=f'Role "{role}" does not exist')
    if (
        target["role"] == auth_db.ADMIN_ROLE_NAME
        and role != auth_db.ADMIN_ROLE_NAME
        and auth_db.count_admin_users() <= 1
    ):
        raise HTTPException(status_code=400, detail="Cannot demote the last remaining admin user")
    auth_db.update_user_role(user_id, role)
    return _user_public(auth_db.get_user_by_id(user_id))


@app.delete("/api/admin/users/{user_id}")
def delete_admin_user(user_id: int, admin: Optional[Dict] = Depends(require_admin_user)):
    target = auth_db.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if admin is not None and admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if target["role"] == "admin" and auth_db.count_admin_users() <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last remaining admin user")
    auth_db.delete_user(user_id)
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/reset-password")
def reset_user_password(user_id: int, req: ResetPasswordRequest, admin: Optional[Dict] = Depends(require_admin_user)):
    target = auth_db.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    password_hash = auth.hash_password(req.newPassword)
    auth_db.update_user_password(user_id, password_hash)
    auth_db.revoke_all_sessions_for_user(user_id)
    return {"ok": True}


@app.get("/api/admin/roles", response_model=List[RolePublic])
def list_admin_roles(admin: Optional[Dict] = Depends(require_admin_user)):
    roles = auth_db.list_roles()
    for role in roles:
        role["adGroups"] = auth_db.list_role_groups(role["id"])
    return roles


@app.post("/api/admin/roles", response_model=RolePublic)
def create_admin_role(req: CreateRoleRequest, admin: Optional[Dict] = Depends(require_admin_user)):
    try:
        role = auth_db.create_role(req.name, req.permissions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    role["adGroups"] = []
    return role


@app.put("/api/admin/roles/{role_id}", response_model=RolePublic)
def update_admin_role(
    role_id: int, req: UpdateRoleRequest, admin: Optional[Dict] = Depends(require_admin_user)
):
    try:
        return auth_db.update_role_permissions(role_id, req.permissions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/admin/roles/{role_id}")
def delete_admin_role(role_id: int, admin: Optional[Dict] = Depends(require_admin_user)):
    try:
        auth_db.delete_role(role_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@app.get("/api/admin/roles/{role_id}/ad-groups", response_model=List[str])
def list_role_ad_groups(role_id: int, admin: Optional[Dict] = Depends(require_admin_user)):
    if auth_db.get_role_by_id(role_id) is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return auth_db.list_role_groups(role_id)


@app.post("/api/admin/roles/{role_id}/ad-groups", response_model=List[str])
def add_role_ad_group(
    role_id: int, req: RoleAdGroupRequest, admin: Optional[Dict] = Depends(require_admin_user)
):
    try:
        auth_db.add_role_group(role_id, req.groupDn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return auth_db.list_role_groups(role_id)


@app.delete("/api/admin/roles/{role_id}/ad-groups", response_model=List[str])
def remove_role_ad_group(
    role_id: int, req: RoleAdGroupRequest, admin: Optional[Dict] = Depends(require_admin_user)
):
    if auth_db.get_role_by_id(role_id) is None:
        raise HTTPException(status_code=404, detail="Role not found")
    auth_db.remove_role_group(role_id, req.groupDn)
    return auth_db.list_role_groups(role_id)


@app.post("/api/admin/settings/require-login")
def set_require_login(
    payload: RequireLoginRequest,
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    if auth_db.count_admin_users() == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot change login requirement: no admin users exist yet",
        )

    current_user = None
    if session_token:
        current_user = auth_db.get_user_by_session_token(session_token)

    if auth_db.is_login_required():
        if current_user is None or current_user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

    if payload.enabled:
        if current_user is None or current_user["role"] != "admin":
            raise HTTPException(
                status_code=403,
                detail="You must be logged in as an admin to enable login requirement",
            )
        if auth_db.count_admin_users() < 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot enable login requirement: no admin users exist yet",
            )

    auth_db.set_setting("require_login", "true" if payload.enabled else "false")
    return {"loginRequired": auth_db.is_login_required()}


@app.get("/api/admin/settings/ad", response_model=AdSettingsResponse)
def get_ad_settings(admin: Optional[Dict] = Depends(require_admin_user)):
    config = auth_db.get_ad_config()
    return AdSettingsResponse(**config)


@app.put("/api/admin/settings/ad", response_model=AdSettingsResponse)
def update_ad_settings(req: UpdateAdSettingsRequest, admin: Optional[Dict] = Depends(require_admin_user)):
    if req.enabled:
        if not req.useTls:
            raise HTTPException(
                status_code=400,
                detail="LDAPS (TLS) is required for secure AD authentication. Please enable TLS.",
            )
        if not req.host.strip():
            raise HTTPException(status_code=400, detail="Host is required when AD login is enabled")
        if not req.domainSuffix.strip():
            raise HTTPException(status_code=400, detail="Domain suffix is required when AD login is enabled")
    if req.port < 1 or req.port > 65535:
        raise HTTPException(status_code=400, detail="Port must be between 1 and 65535")

    auth_db.set_ad_config({
        "enabled": req.enabled,
        "host": req.host,
        "port": req.port,
        "useTls": req.useTls,
        "domainSuffix": req.domainSuffix,
        "requiredGroupDn": req.requiredGroupDn,
        "adminGroupDn": req.adminGroupDn,
    })
    return AdSettingsResponse(**auth_db.get_ad_config())


@app.post("/api/admin/settings/ad/test-connection", response_model=TestAdConnectionResponse)
def test_ad_connection_endpoint(
    req: TestAdConnectionRequest, admin: Optional[Dict] = Depends(require_admin_user)
):
    saved = auth_db.get_ad_config()
    host = req.host if req.host is not None else saved["host"]
    port = req.port if req.port is not None else saved["port"]
    use_tls = req.useTls if req.useTls is not None else saved["useTls"]

    if not host:
        raise HTTPException(status_code=400, detail="No host to test — provide one or save AD settings first")

    result = ldap_auth.test_ad_connection(host, port, use_tls)
    return TestAdConnectionResponse(**result)


@app.post(
    "/api/connection-test/run",
    response_model=RunResponse,
    dependencies=[Depends(require_feature("connection-test"))],
)
async def run_connection_test(req: RunRequest):
    destinations = [validate_host(d) for d in req.destinations]
    ports = [validate_port(p) for p in req.ports]

    loop = asyncio.get_event_loop()
    tasks = []

    for source in req.sources:
        host = validate_host(source.host)
        ports = [validate_port_identifier(str(p)) for p in req.ports]
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


@app.get(
    "/api/routing/hosts",
    response_model=List[RoutingHostSummary],
    dependencies=[Depends(require_feature("routing-map"))],
)
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


@app.get(
    "/api/routing/export",
    response_model=List[RoutingHostDetail],
    dependencies=[Depends(require_feature("routing-map"))],
)
def export_routing_hosts():
    return db.export_all()


@app.get(
    "/api/routing/hosts/{host}",
    response_model=RoutingHostDetail,
    dependencies=[Depends(require_feature("routing-map"))],
)
def get_routing_host(host: str):
    data = db.get_host(host)
    if data is None:
        raise HTTPException(status_code=404, detail=f'No saved routing table for "{host}"')
    return data


@app.put(
    "/api/routing/hosts/{host}",
    response_model=RoutingHostDetail,
    dependencies=[Depends(require_feature("routing-map"))],
)
def put_routing_host(host: str, req: SaveRoutingHostRequest):
    try:
        return db.save_host(
            host,
            [r.dict() for r in req.routes],
            [i.dict() for i in req.interfaces],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete(
    "/api/routing/hosts/{host}",
    dependencies=[Depends(require_feature("routing-map"))],
)
def delete_routing_host(host: str):
    deleted = db.delete_host(host)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'No saved routing table for "{host}"')
    return {"deleted": host}


# ---------------------------------------------------------------------------
# Troubleshoot — device inventory
# ---------------------------------------------------------------------------

class DeviceRequest(BaseModel):
    name: str
    mgmtIp: str
    vendor: str
    model: str
    osVersion: Optional[str] = None
    deviceType: str


@app.get("/api/devices", dependencies=[Depends(require_feature("troubleshoot"))])
def list_devices_endpoint():
    return troubleshoot_devices.list_devices()


@app.post("/api/devices", dependencies=[Depends(require_feature("troubleshoot"))])
def add_device_endpoint(req: DeviceRequest):
    try:
        return troubleshoot_devices.add_device(
            req.name, req.mgmtIp, req.vendor, req.model, req.osVersion, req.deviceType
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/devices/{device_id}", dependencies=[Depends(require_feature("troubleshoot"))])
def update_device_endpoint(device_id: int, req: DeviceRequest):
    try:
        return troubleshoot_devices.update_device(
            device_id, req.name, req.mgmtIp, req.vendor, req.model, req.osVersion, req.deviceType
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/devices/{device_id}", dependencies=[Depends(require_feature("troubleshoot"))])
def delete_device_endpoint(device_id: int):
    return troubleshoot_devices.delete_device(device_id)


class TestConnectionRequest(BaseModel):
    deviceId: int
    username: str
    password: str


class LocateRequest(BaseModel):
    ip: str
    username: str
    password: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v):
        ipaddress.ip_address(v)
        return v


class PortHealthRequest(BaseModel):
    deviceName: str
    port: str
    username: str
    password: str

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if not DEVICE_PORT_RE.match(v):
            raise ValueError("Invalid port format")
        return v


class CableTestRequest(BaseModel):
    deviceName: str
    port: str
    username: str
    password: str
    confirm: bool

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if not DEVICE_PORT_RE.match(v):
            raise ValueError("Invalid port format")
        return v


class TransceiverHealthRequest(BaseModel):
    deviceName: str
    port: str
    username: str
    password: str

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if not DEVICE_PORT_RE.match(v):
            raise ValueError("Invalid port format")
        return v


class StpReportRequest(BaseModel):
    username: str
    password: str


class AccessCheckRequest(BaseModel):
    deviceName: str
    port: str
    username: str
    password: str

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if not DEVICE_PORT_RE.match(v):
            raise ValueError("Invalid port format")
        return v


class PingRequest(BaseModel):
    ip: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v):
        ipaddress.ip_address(v)
        return v


class RouteCheckRequest(BaseModel):
    ip: str
    username: str
    password: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v):
        ipaddress.ip_address(v)
        return v


class FullRunRequest(BaseModel):
    ip: str
    username: str
    password: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v):
        ipaddress.ip_address(v)
        return v


@app.post("/api/troubleshoot/test-connection", dependencies=[Depends(require_feature("troubleshoot"))])
async def test_device_connection(req: TestConnectionRequest):
    devices = troubleshoot_devices.list_devices()
    device = next((d for d in devices if d["id"] == req.deviceId), None)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    def _run():
        try:
            with DeviceSession(device["deviceType"], device["mgmtIp"], req.username, req.password) as session:
                driver = get_driver(device["deviceType"])
                output = driver.get_version(session)
                return {"success": True, "output": output}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/locate", dependencies=[Depends(require_feature("troubleshoot"))])
async def locate_device(req: LocateRequest):
    def _run():
        try:
            devices = troubleshoot_devices.list_devices()
            gateway_device = next(
                (d for d in devices if d["deviceType"] == "checkpoint_gaia"), None
            )
            if gateway_device is None:
                return {"success": False, "error": "No gateway device configured"}
            switch_devices = [
                d for d in devices if d["deviceType"] in ("cisco_ios", "aruba_aoscx")
            ]
            mac = troubleshoot_logic.resolve_ip_to_mac(
                req.ip, gateway_device, req.username, req.password
            )
            if mac is None:
                return {"success": False, "error": "IP not found in ARP table"}
            result = troubleshoot_logic.locate_mac_on_switches(
                mac, switch_devices, req.username, req.password
            )
            if result is None:
                return {
                    "success": False,
                    "error": f"MAC {mac} not found on any switch",
                }
            return {
                "success": True,
                "mac": mac,
                "device": result["device"],
                "port": result["port"],
                "vlan": result["vlan"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/port-health", dependencies=[Depends(require_feature("troubleshoot"))])
async def port_health(req: PortHealthRequest):
    def _run():
        try:
            devices = troubleshoot_devices.list_devices()
            device = next((d for d in devices if d["name"] == req.deviceName), None)
            if device is None:
                return {"success": False, "error": f"Device {req.deviceName} not found"}
            result = troubleshoot_logic.get_port_health(
                device, req.port, req.username, req.password
            )
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/cable-test", dependencies=[Depends(require_feature("troubleshoot"))])
async def cable_test(req: CableTestRequest):
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Cable diagnostics can briefly interrupt link. Set confirm=true to proceed.",
        )

    def _run():
        try:
            devices = troubleshoot_devices.list_devices()
            device = next((d for d in devices if d["name"] == req.deviceName), None)
            if device is None:
                return {"success": False, "error": f"Device {req.deviceName} not found"}
            result = troubleshoot_logic.run_cable_test(
                device, req.port, req.username, req.password
            )
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/transceiver-health", dependencies=[Depends(require_feature("troubleshoot"))])
async def transceiver_health(req: TransceiverHealthRequest):
    def _run():
        try:
            devices = troubleshoot_devices.list_devices()
            device = next((d for d in devices if d["name"] == req.deviceName), None)
            if device is None:
                return {"success": False, "error": f"Device {req.deviceName} not found"}
            result = troubleshoot_logic.get_transceiver_health(
                device, req.port, req.username, req.password
            )
            return {"success": True, "metrics": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/stp-report", dependencies=[Depends(require_feature("troubleshoot"))])
async def stp_report(req: StpReportRequest):
    def _run():
        try:
            devices = troubleshoot_devices.list_devices()
            result = troubleshoot_logic.get_stp_report_all(
                devices, req.username, req.password
            )
            return {"success": True, "entries": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/access-check", dependencies=[Depends(require_feature("troubleshoot"))])
async def access_check(req: AccessCheckRequest):
    def _run():
        try:
            devices = troubleshoot_devices.list_devices()
            device = next((d for d in devices if d["name"] == req.deviceName), None)
            if device is None:
                return {"success": False, "error": f"Device {req.deviceName} not found"}
            result = troubleshoot_logic.get_port_access_status(
                device, req.port, req.username, req.password
            )
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/ping", dependencies=[Depends(require_feature("troubleshoot"))])
async def ping(req: PingRequest):
    def _run():
        try:
            raw = troubleshoot_logic.ping_host(req.ip)
            result = troubleshoot_logic.parse_ping_output(raw)
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/route-check", dependencies=[Depends(require_feature("troubleshoot"))])
async def route_check(req: RouteCheckRequest):
    def _run():
        try:
            devices = troubleshoot_devices.list_devices()
            gateway_device = next(
                (d for d in devices if d["deviceType"] == "checkpoint_gaia"), None
            )
            if gateway_device is None:
                return {"success": False, "error": "No gateway device configured"}
            result = troubleshoot_logic.get_route_check(
                req.ip, gateway_device, req.username, req.password
            )
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.post("/api/troubleshoot/run", dependencies=[Depends(require_feature("troubleshoot"))])
async def full_run(req: FullRunRequest):
    def _run():
        try:
            return troubleshoot_logic.run_full_diagnostic(
                req.ip, req.username, req.password
            )
        except Exception as e:
            return {"ip": req.ip, "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(EXECUTOR, _run)


@app.get("/api/troubleshoot/audit-log", dependencies=[Depends(require_admin_user)])
def get_audit_log(limit: int = 50):
    return troubleshoot_audit.get_recent_audit_log(limit)


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


class SearchAddressEntry(AddressEntry):
    subnetId: int
    subnetCidr: str
    subnetVlan: Optional[int] = None


class IpamSettingsResponse(BaseModel):
    scanConcurrencyLimit: int
    scanConcurrencyMin: int
    scanConcurrencyMax: int


class UpdateIpamSettingsRequest(BaseModel):
    scanConcurrencyLimit: int


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


class BulkAddressDeleteRequest(BaseModel):
    addressIds: List[int]


class BulkMoveAddressesRequest(BaseModel):
    addressIds: List[int]
    targetSubnetId: int


class BulkMoveSkippedEntry(BaseModel):
    addressId: int
    address: Optional[str] = None
    reason: str


class BulkMoveAddressesResponse(BaseModel):
    fromSubnet: SubnetDetail
    toSubnet: SubnetDetail
    movedCount: int
    skipped: List[BulkMoveSkippedEntry] = []


class DhcpPoolCreate(BaseModel):
    start_ip: str
    end_ip: str
    name: Optional[str] = None
    description: Optional[str] = None


class BulkMoveDhcpPoolsRequest(BaseModel):
    poolIds: List[int]
    targetSubnetId: int


class BulkMoveDhcpPoolsResponse(BaseModel):
    movedCount: int


class DhcpPoolResponse(BaseModel):
    id: int
    subnet_id: int
    start_ip: str
    end_ip: str
    name: Optional[str] = None
    description: Optional[str] = None
    updated_at: str


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


class MisplacedAddressEntry(BaseModel):
    addressId: int
    address: str
    status: str
    hostname: Optional[str] = None
    currentSubnetId: int
    currentSubnetCidr: str
    proposedSubnetId: int
    proposedSubnetCidr: str


class MisplacedDhcpPoolEntry(BaseModel):
    poolId: int
    startIp: str
    endIp: str
    name: Optional[str] = None
    description: Optional[str] = None
    currentSubnetId: int
    currentSubnetCidr: str
    proposedSubnetId: int
    proposedSubnetCidr: str


class MoveAddressRequest(BaseModel):
    targetSubnetId: int


class MoveAddressResponse(BaseModel):
    fromSubnet: SubnetDetail
    toSubnet: SubnetDetail


# ---------------------------------------------------------------------------
# Custom Tags
# ---------------------------------------------------------------------------

class TagCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = "#6366f1"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        import re
        if not v or len(v) > 50:
            raise ValueError("Tag name must be 2-50 characters")
        if not re.match(r'^[a-zA-Z0-9_-]{2,50}$', v):
            raise ValueError("Tag name must be alphanumeric, hyphens, and underscores only")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        if v is None:
            return "#6366f1"
        v = v.strip()
        if not re.match(r'^#[0-9a-fA-F]{6}$', v):
            raise ValueError("Color must be a hex value (e.g. #6366f1)")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        if v is not None and len(v) > 200:
            raise ValueError("Description must be at most 200 characters")
        return v


class TagResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str
    createdAt: str
    updatedAt: str


class TagListResponse(BaseModel):
    tags: List[TagResponse]
    count: int


class TagSummary(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str


@app.get("/api/ipam/dashboard", response_model=List[DashboardEntry], dependencies=[Depends(require_feature("ipam"))])
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


@app.get("/api/ipam/subnets", response_model=List[SubnetSummary], dependencies=[Depends(require_feature("ipam"))])
def get_subnets():
    return db.list_subnets()


@app.get(
    "/api/ipam/misplaced-addresses",
    response_model=List[MisplacedAddressEntry],
    dependencies=[Depends(require_feature("ipam"))],
)
def get_misplaced_addresses():
    return db.list_misplaced_addresses()


class NextAvailableIpResponse(BaseModel):
    subnetId: int
    nextAvailableIp: Optional[str] = None


@app.get(
    "/api/ipam/subnets/{subnet_id}/next-available",
    response_model=NextAvailableIpResponse,
    dependencies=[Depends(require_feature("ipam"))],
)
def get_next_available_ip(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    try:
        ip = db.get_next_available_ip(subnet_id)
        return NextAvailableIpResponse(subnetId=subnet_id, nextAvailableIp=ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get(
    "/api/ipam/misplaced-dhcp-pools",
    response_model=List[MisplacedDhcpPoolEntry],
    dependencies=[Depends(require_feature("ipam"))],
)
def get_misplaced_dhcp_pools():
    return db.list_misplaced_dhcp_pools()


@app.get(
    "/api/ipam/addresses/search",
    response_model=List[SearchAddressEntry],
    dependencies=[Depends(require_feature("ipam"))],
)
def search_ipam_addresses(q: str = ""):
    return db.search_addresses(q)


@app.get("/api/ipam/settings", response_model=IpamSettingsResponse, dependencies=[Depends(require_feature("ipam"))])
def get_ipam_settings():
    return IpamSettingsResponse(
        scanConcurrencyLimit=db.get_scan_concurrency_limit(),
        scanConcurrencyMin=db.SCAN_CONCURRENCY_MIN,
        scanConcurrencyMax=db.SCAN_CONCURRENCY_MAX,
    )


@app.put("/api/ipam/settings", response_model=IpamSettingsResponse, dependencies=[Depends(require_feature("ipam"))])
def update_ipam_settings(req: UpdateIpamSettingsRequest):
    try:
        db.set_scan_concurrency_limit(req.scanConcurrencyLimit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return IpamSettingsResponse(
        scanConcurrencyLimit=db.get_scan_concurrency_limit(),
        scanConcurrencyMin=db.SCAN_CONCURRENCY_MIN,
        scanConcurrencyMax=db.SCAN_CONCURRENCY_MAX,
    )


@app.post("/api/ipam/subnets", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def create_subnet(req: SubnetRequest):
    try:
        return db.create_subnet(req.cidr, req.vlan, req.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ipam/subnets/{subnet_id}", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def get_subnet(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return data


@app.put("/api/ipam/subnets/{subnet_id}", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def update_subnet(subnet_id: int, req: SubnetRequest):
    try:
        return db.update_subnet(subnet_id, req.cidr, req.vlan, req.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/ipam/subnets/{subnet_id}", dependencies=[Depends(require_feature("ipam"))])
def delete_subnet(subnet_id: int):
    deleted = db.delete_subnet(subnet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return {"deleted": subnet_id}


@app.post("/api/ipam/subnets/{subnet_id}/addresses", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def create_address(subnet_id: int, req: AddressRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
    try:
        if db.check_ip_in_dhcp_pool(req.address, subnet_id):
            raise HTTPException(status_code=400, detail="IP is within DHCP pool range")
        user_id = user["id"] if user else None
        return db.add_address(
            subnet_id, req.address, req.status, req.hostname, req.description,
            req.team, req.machineType, req.vmCluster, req.environment, req.locked,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def edit_address(subnet_id: int, address_id: int, req: AddressRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
    try:
        user_id = user["id"] if user else None
        return db.update_address(
            subnet_id, address_id, req.address, req.status, req.hostname, req.description,
            req.team, req.machineType, req.vmCluster, req.environment, req.locked,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def remove_address(subnet_id: int, address_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
    try:
        user_id = user["id"] if user else None
        return db.delete_address(subnet_id, address_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post(
    "/api/ipam/subnets/{subnet_id}/addresses/{address_id}/move",
    response_model=MoveAddressResponse,
    dependencies=[Depends(require_feature("ipam"))],
)
def move_ipam_address(subnet_id: int, address_id: int, req: MoveAddressRequest):
    try:
        return db.move_address(subnet_id, address_id, req.targetSubnetId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.patch("/api/ipam/subnets/{subnet_id}/addresses/bulk", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def bulk_edit_addresses(subnet_id: int, req: BulkAddressUpdateRequest):
    if not req.addressIds:
        raise HTTPException(status_code=400, detail="No addresses selected")
    try:
        fields = req.dict(exclude_unset=True, exclude={"addressIds"})
        return db.bulk_update_addresses(subnet_id, req.addressIds, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/ipam/subnets/{subnet_id}/addresses/bulk-delete", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
def bulk_delete_addresses(subnet_id: int, req: BulkAddressDeleteRequest):
    if not req.addressIds:
        raise HTTPException(status_code=400, detail="No addresses selected")
    try:
        return db.bulk_delete_addresses(subnet_id, req.addressIds)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post(
    "/api/ipam/subnets/{subnet_id}/addresses/bulk-move",
    response_model=BulkMoveAddressesResponse,
    dependencies=[Depends(require_feature("ipam"))],
)
def bulk_move_addresses(subnet_id: int, req: BulkMoveAddressesRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
    if not req.addressIds:
        raise HTTPException(status_code=400, detail="No addresses selected")
    user_id = user["id"] if user else None
    try:
        return db.bulk_move_addresses(subnet_id, req.addressIds, req.targetSubnetId, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/ipam/subnets/{subnet_id}/addresses/{address_id}/rescan", response_model=SubnetDetail, dependencies=[Depends(require_feature("ipam"))])
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


@app.get("/api/ipam/subnets/{subnet_id}/scan-excludes", response_model=List[ScanExcludeEntry], dependencies=[Depends(require_feature("ipam"))])
def list_subnet_scan_excludes(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return db.list_scan_excludes_detailed(subnet_id)


@app.post("/api/ipam/subnets/{subnet_id}/scan-excludes", response_model=List[ScanExcludeEntry], dependencies=[Depends(require_feature("ipam"))])
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


@app.delete("/api/ipam/subnets/{subnet_id}/scan-excludes/{exclude_id}", response_model=List[ScanExcludeEntry], dependencies=[Depends(require_feature("ipam"))])
def remove_subnet_scan_exclude(subnet_id: int, exclude_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    db.remove_scan_exclude_by_id(subnet_id, exclude_id)
    return db.list_scan_excludes_detailed(subnet_id)


@app.post("/api/ipam/subnets/{subnet_id}/dhcp-pools", response_model=DhcpPoolResponse, dependencies=[Depends(require_feature("ipam"))])
def create_dhcp_pool(subnet_id: int, req: DhcpPoolCreate):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    try:
        return db.add_dhcp_pool(subnet_id, req.start_ip, req.end_ip, req.name, req.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ipam/subnets/{subnet_id}/dhcp-pools", response_model=List[DhcpPoolResponse], dependencies=[Depends(require_feature("ipam"))])
def list_dhcp_pools(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return db.get_dhcp_pools(subnet_id)


@app.delete("/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool_id}", dependencies=[Depends(require_feature("ipam"))])
def delete_dhcp_pool(subnet_id: int, pool_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    deleted = db.delete_dhcp_pool(pool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="DHCP pool not found")
    return {"deleted": pool_id}


@app.put(
    "/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool_id}",
    response_model=DhcpPoolResponse,
    dependencies=[Depends(require_feature("ipam"))],
)
def update_dhcp_pool(subnet_id: int, pool_id: int, req: DhcpPoolCreate):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    try:
        return db.update_dhcp_pool(pool_id, req.start_ip, req.end_ip, req.name, req.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post(
    "/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool_id}/move",
    dependencies=[Depends(require_feature("ipam"))],
)
def move_dhcp_pool(subnet_id: int, pool_id: int, req: MoveAddressRequest):
    try:
        return db.move_dhcp_pool(subnet_id, pool_id, req.targetSubnetId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post(
    "/api/ipam/dhcp-pools/bulk-move",
    response_model=BulkMoveDhcpPoolsResponse,
    dependencies=[Depends(require_feature("ipam"))],
)
def bulk_move_dhcp_pools(req: BulkMoveDhcpPoolsRequest):
    try:
        return db.bulk_move_dhcp_pools(req.poolIds, req.targetSubnetId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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

    concurrency_limit = db.get_scan_concurrency_limit()
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
        tasks.append(scan_one_task(address))
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


@app.post("/api/ipam/subnets/{subnet_id}/autodiscover", response_model=AutodiscoverResponse, dependencies=[Depends(require_feature("ipam"))])
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


@app.post("/api/ipam/subnets/{subnet_id}/autodiscover/start", dependencies=[Depends(require_feature("ipam"))])
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


@app.get("/api/ipam/subnets/{subnet_id}/autodiscover/active", dependencies=[Depends(require_feature("ipam"))])
def get_active_scan(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")

    job_id = SCAN_JOBS_BY_SUBNET.get(subnet_id)
    if job_id is None:
        return {"jobId": None}

    job = SCAN_JOBS[job_id]
    return {"jobId": job_id, "completed": job["completed"], "total": job["total"]}


@app.get("/api/ipam/subnets/{subnet_id}/autodiscover/stream/{job_id}", dependencies=[Depends(require_feature("ipam"))])
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


@app.get("/api/ipam/subnets/{subnet_id}/scans", response_model=List[ScanSummary], dependencies=[Depends(require_feature("ipam"))])
def get_subnet_scans(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return db.list_scans(subnet_id)


# ---------------------------------------------------------------------------
# Custom Tags API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/ipam/tags", response_model=TagListResponse, dependencies=[Depends(require_feature("ipam"))])
def get_tags():
    tags = db.get_tags()
    return TagListResponse(tags=tags, count=len(tags))


@app.post("/api/ipam/tags", response_model=TagResponse, dependencies=[Depends(require_feature("ipam"))])
def create_tag(req: TagCreateRequest):
    try:
        return db.create_tag(req.name, req.description, req.color)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f'Tag "{req.name}" already exists')


@app.delete("/api/ipam/tags/{tag_id}", dependencies=[Depends(require_feature("ipam"))])
def delete_tag(tag_id: int):
    deleted = db.delete_tag(tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"deleted": tag_id}


@app.get("/api/ipam/tags/search", response_model=List[TagSummary], dependencies=[Depends(require_feature("ipam"))])
def search_tags(q: str = ""):
    if not q or not q.strip():
        return []
    return db.search_tags(q.strip())


@app.get("/api/ipam/subnets/{subnet_id}/tags", response_model=List[TagSummary], dependencies=[Depends(require_feature("ipam"))])
def get_subnet_tags(subnet_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return db.get_subnet_tags(subnet_id)


@app.post("/api/ipam/subnets/{subnet_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_feature("ipam"))])
def add_subnet_tag(subnet_id: int, tag_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    try:
        db.add_subnet_tag(subnet_id, tag_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return db.get_subnet_tags(subnet_id)


@app.delete("/api/ipam/subnets/{subnet_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_feature("ipam"))])
def remove_subnet_tag(subnet_id: int, tag_id: int):
    data = db.get_subnet(subnet_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Subnet not found")
    db.remove_subnet_tag(subnet_id, tag_id)
    return db.get_subnet_tags(subnet_id)


@app.get("/api/ipam/addresses/{address_id}/tags", response_model=List[TagSummary], dependencies=[Depends(require_feature("ipam"))])
def get_address_tags(address_id: int):
    return db.get_address_tags(address_id)


@app.post("/api/ipam/addresses/{address_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_feature("ipam"))])
def add_address_tag(address_id: int, tag_id: int):
    try:
        db.add_address_tag(address_id, tag_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return db.get_address_tags(address_id)


@app.delete("/api/ipam/addresses/{address_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_feature("ipam"))])
def remove_address_tag(address_id: int, tag_id: int):
    db.remove_address_tag(address_id, tag_id)
    return db.get_address_tags(address_id)


@app.get("/api/ipam/tags/{tag_id}/subnets", response_model=List[SubnetSummary], dependencies=[Depends(require_feature("ipam"))])
def get_subnets_by_tag(tag_id: int):
    try:
        return db.get_subnets_by_tag(tag_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/ipam/tags/{tag_id}/addresses", response_model=List[SearchAddressEntry], dependencies=[Depends(require_feature("ipam"))])
def get_addresses_by_tag(tag_id: int):
    try:
        return db.get_addresses_by_tag(tag_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Subnet Allocation Assistant
# ---------------------------------------------------------------------------

class SubnetAllocationResponse(BaseModel):
    parent: str
    requestedPrefix: int
    recommendation: Optional[str] = None
    availableFrom: Optional[str] = None
    availableTo: Optional[str] = None
    totalAddresses: int = 0
    nextAvailableAfter: Optional[str] = None


@app.get("/api/ipam/subnet-allocation", response_model=SubnetAllocationResponse, dependencies=[Depends(require_feature("ipam"))])
def get_subnet_allocation(parent: str, prefix: int):
    try:
        result = db.find_next_contiguous_subnet(parent, prefix)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLogEntry(BaseModel):
    id: int
    addressId: int
    userId: Optional[int] = None
    username: Optional[str] = None
    changeType: str
    oldValue: Optional[Dict] = None
    newValue: Optional[Dict] = None
    description: Optional[str] = None
    ipAddress: Optional[str] = None
    subnetCidr: Optional[str] = None
    createdAt: str


@app.get("/api/ipam/audit/address/{address_id}", response_model=List[AuditLogEntry], dependencies=[Depends(require_feature("ipam"))])
def get_address_audit_log(address_id: int, limit: int = 100, offset: int = 0):
    return db.get_address_audit_log(address_id, limit=limit, offset=offset)


@app.get("/api/ipam/audit/subnet/{subnet_id}", response_model=List[AuditLogEntry], dependencies=[Depends(require_feature("ipam"))])
def get_subnet_audit_log(
    subnet_id: int,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
):
    return db.get_subnet_audit_log(subnet_id, start_time=start_time, end_time=end_time, limit=limit)


@app.get("/api/ipam/audit/export", response_model=List[AuditLogEntry], dependencies=[Depends(require_feature("ipam"))])
def export_audit_log(
    subnet_id: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 1000,
):
    rows = db.export_audit_log_csv(
        subnet_id=subnet_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    result = []
    for r in rows:
        entry = AuditLogEntry(
            id=r["id"],
            addressId=r["address_id"],
            userId=r["user_id"],
            changeType=r["change_type"],
            oldValue=json.loads(r["old_value"]) if r["old_value"] else None,
            newValue=json.loads(r["new_value"]) if r["new_value"] else None,
            description=r["description"],
            ipAddress=r["ip_address"],
            subnetCidr=r["subnet_cidr"],
            createdAt=r["created_at"],
        )
        if r["user_id"]:
            user = auth_db.get_user_by_id(r["user_id"])
            entry.username = user["username"] if user else None
        result.append(entry)
    return result