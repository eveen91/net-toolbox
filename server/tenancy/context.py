"""Verified, request-local tenant context. Never change a module DB_PATH per request."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    database_path: Path
    role: Optional[str] = None
    permissions: tuple = ()


current_tenant: ContextVar[Optional[TenantContext]] = ContextVar("current_tenant", default=None)


@contextmanager
def tenant_scope(context: TenantContext):
    token = current_tenant.set(context)
    try:
        yield context
    finally:
        current_tenant.reset(token)


def database_path(legacy_path):
    context = current_tenant.get()
    return context.database_path if context else legacy_path


def run_in_executor(loop, executor, function, *args):
    """ThreadPoolExecutor does not propagate ContextVars by itself."""
    return loop.run_in_executor(executor, partial(copy_context().run, function, *args))
