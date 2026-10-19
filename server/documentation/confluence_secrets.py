"""Encrypted tenant/profile-bound PATs; the key lives outside database backups."""
import json
import os
import stat
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
import db
from tenancy.context import current_tenant
from .repository import Invalid


def tenant_id():
    context=current_tenant.get()
    return context.tenant_id if context else 'default'


def key_path():
    return Path(os.environ.get('TENANT_DATA_ROOT',Path(db.DB_PATH).parent/'tenants'))/'.documentation-confluence.key'


def cipher(create=False):
    configured=os.environ.get('DOCUMENTATION_SECRET_KEY')
    if configured:
        try:return Fernet(configured.encode())
        except (ValueError,TypeError):raise Invalid('DOCUMENTATION_SECRET_KEY must be a valid Fernet key.')
    path=key_path()
    if create and not path.exists():
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            descriptor,temporary=tempfile.mkstemp(prefix='.documentation-key-',dir=path.parent)
            try:
                with os.fdopen(descriptor,'wb') as file:
                    file.write(Fernet.generate_key());file.flush();os.fsync(file.fileno())
                try:os.link(temporary,path)
                except FileExistsError:pass
            finally:os.unlink(temporary)
        except OSError:raise Invalid('Cannot create the private Confluence credential key. Make the tenant data directory writable or configure DOCUMENTATION_SECRET_KEY.') from None
    try:
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(descriptor,'rb') as file:
            info=os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or info.st_uid!=os.geteuid():raise OSError()
            key=file.read(100)
        return Fernet(key)
    except (OSError,ValueError):raise Invalid('The Confluence credential key is missing, unreadable or not private (0600). Restore the original key before using saved profiles.')


def seal(token,profile_id,base_url):
    value={'tenant':tenant_id(),'profile':profile_id,'baseUrl':base_url,'token':token}
    return cipher(True).encrypt(json.dumps(value).encode()).decode()


def unseal(value,profile_id,base_url):
    try:
        secret=json.loads(cipher().decrypt(value.encode()))
        if (secret['tenant'],secret['profile'],secret['baseUrl'])!=(tenant_id(),profile_id,base_url):raise InvalidToken()
        return secret['token']
    except (InvalidToken,ValueError,KeyError):raise Invalid('The Confluence credential cannot be decrypted for this tenant/profile. Restore its key or enter a new token.')
