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
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Literal, Optional

import paramiko
import winrm
from fastapi import FastAPI, HTTPException, Response, Request, Cookie, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from pydantic_core import ValidationError

import db
import auth
import auth_db
import ldap_auth
import rate_limit
import ssh_security
import troubleshoot_devices
import troubleshoot_logic
import troubleshoot_audit
import validation_routes
from ipam import IpamRepository, IpamService
from ipam import scan_service as ipam_scan_service
from ipam.router import build_router as build_ipam_router
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
) -> Optional[Dict]:
    user = None
    if session_token:
        user = auth_db.get_user_by_session_token(session_token)
    if user is not None:
        return user
    if not auth_db.is_login_required():
        return None
    raise HTTPException(status_code=401, detail="Not authenticated")


def require_authenticated_user(
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Dict:
    if session_token:
        user = auth_db.get_user_by_session_token(session_token)
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="Not authenticated")


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


def require_ipam_permission(permission: Literal["read", "write", "scan", "admin"]):
    """Gate IPAM actions while preserving existing roles that grant `ipam`."""
    permission_id = f"ipam.{permission}"

    def _dependency(
        session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> Optional[Dict]:
        if not auth_db.is_login_required():
            return None
        user = auth_db.get_user_by_session_token(session_token) if session_token else None
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        permissions = user_permissions(user)
        if "*" not in permissions and "ipam" not in permissions and permission_id not in permissions:
            raise HTTPException(status_code=403, detail=f'Your role does not have access to "{permission_id}"')
        return user

    return _dependency


ipam_repository = IpamRepository(db)
ipam_service = IpamService(ipam_repository, auth_db.get_user_by_id)
ipam_scan_service.configure(ipam_repository)
app.include_router(build_ipam_router(ipam_service, require_ipam_permission, require_logged_in_user))


@app.on_event("startup")
async def _start_ipam_scan_scheduler():
    await ipam_scan_service.start_scan_scheduler()


@app.on_event("shutdown")
async def _stop_ipam_scan_scheduler():
    await ipam_scan_service.stop_scan_scheduler()


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
def change_own_password(req: ChangePasswordRequest, user: Dict = Depends(require_authenticated_user)):
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
