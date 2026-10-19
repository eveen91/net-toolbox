"""Request-local module and retained-source authorization."""
from contextlib import contextmanager
from contextvars import ContextVar
import auth_db
from tenancy.context import current_tenant

_grants=ContextVar('documentation_grants',default=frozenset({'*'}))
class Denied(Exception):pass


def permissions(user):
    context=current_tenant.get()
    if context is not None:return set(context.permissions)
    if user:return set(auth_db.role_permissions_for_name(user['role']))
    return {'*'} if not auth_db.is_login_required() else set()


def expanded(grants=None):
    result=set(_grants.get() if grants is None else grants)
    if 'documentation' in result:result.update({'documentation.read','documentation.write','documentation.publish','documentation.admin'})
    if 'ipam' in result:result.add('ipam.read')
    return result


def allowed(required,grants=None):
    values=expanded(grants)
    return '*' in values or set(required).issubset(values)


def check(required):
    if not allowed(required):raise Denied('Your current role does not grant access to every module included in this document.')


def action(name):check(['documentation.'+name])


@contextmanager
def scoped(grants):
    token=_grants.set(frozenset(grants))
    try:yield
    finally:_grants.reset(token)
