"""
Simple in-memory rate limiting to blunt brute-force / credential-stuffing
attacks on the login endpoint.

Why in-memory: this is a single-process internal tool, so a per-process
dict is adequate and needs no extra service. The limits are keyed by (1) the
client's remote IP and (2) the username being tried, so an attacker pounding
one account (or spraying many accounts from one host) gets throttled.

All limits are configurable through environment variables so deployments
can tune them (or disable rate limiting entirely for tests / low-traffic
CI by setting RATE_LIMIT_ENABLED=0).

Wrinkles worth knowing:
  - Behind a reverse proxy, the client IP comes from X-Forwarded-For; we
    only trust it when TRUST_PROXY_HEADERS=1 so we don't let anyone spoof
    their way around the limiter by setting the header themselves.
  - The state is in-memory and resets on restart. That is fine for an
    internal tool that runs as a single process.
"""

import os
import time
import threading
from typing import Dict, List, Tuple

# Default limits.
DEFAULT_MAX_ATTEMPTS_IP = 10
DEFAULT_MAX_ATTEMPTS_USER = 5
DEFAULT_WINDOW_SECONDS = 300        # 5 minutes
DEFAULT_BLOCK_SECONDS = 300         # 5 minutes

# How long a blocked client/username stays rejected after exceeding the limit.
_lock: threading.Lock = threading.Lock()
_attempts: Dict[str, List[float]] = {}   # key -> list of recent attempt timestamps
_blocked_until: Dict[str, float] = {}    # key -> timestamp when block expires


def _get_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")


def trust_proxy() -> bool:
    return os.environ.get("TRUST_PROXY_HEADERS", "true").lower() in ("true", "1", "yes")


def max_attempts_ip() -> int:
    return _get_int_env("RATE_LIMIT_MAX_IP", DEFAULT_MAX_ATTEMPTS_IP)


def max_attempts_user() -> int:
    return _get_int_env("RATE_LIMIT_MAX_USER", DEFAULT_MAX_ATTEMPTS_USER)


def window_seconds() -> int:
    return _get_int_env("RATE_LIMIT_WINDOW", DEFAULT_WINDOW_SECONDS)


def block_seconds() -> int:
    return _get_int_env("RATE_LIMIT_BLOCK", DEFAULT_BLOCK_SECONDS)


def _prune(key: str, now: float, window: int) -> None:
    """Drop attempts older than the window for key."""
    entries = _attempts.setdefault(key, [])
    cutoff = now - window
    _attempts[key] = [ts for ts in entries if ts >= cutoff]


def _blocked(key: str, now: float) -> bool:
    until = _blocked_until.get(key, 0)
    return until > now


def client_ip(request) -> str:
    """Best-effort client IP, honoring X-Forwarded-For only when configured."""
    if trust_proxy():
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_allowed(request, username: str) -> bool:
    """
    Return True if the login attempt is allowed, False if it should be
    rejected (rate limited). When rate limiting is disabled, always allows.
    """
    if not enabled():
        return True

    ip = client_ip(request)
    now = time.time()
    window = window_seconds()

    with _lock:
        # A currently-blocked key is rejected outright.
        if _blocked(ip, now) or _blocked(username, now):
            return False

        # Prune stale entries, then check counts.
        _prune(ip, now, window)
        _prune(username, now, window)

        ip_count = len(_attempts[ip])
        user_count = len(_attempts[username])

        if ip_count >= max_attempts_ip() or user_count >= max_attempts_user():
            _blocked_until[ip] = now + block_seconds()
            _blocked_until[username] = now + block_seconds()
            return False

        # Record this attempt and allow it.
        _attempts[ip].append(now)
        _attempts[username].append(now)
        return True


def record_ip(request) -> str:
    return client_ip(request)
