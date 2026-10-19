"""Tenant-local Confluence profiles, audit, destination identities and previews."""
import json
import sqlite3
from . import access
from .repository import connection,now,dump,Missing,Conflict,Invalid
from .confluence_secrets import seal


def init_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS documentation_confluence_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        settings TEXT NOT NULL,credential TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
        last_check TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS documentation_confluence_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,profile_id INTEGER NOT NULL,document_id INTEGER,
        actor_id INTEGER,action TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS documentation_confluence_pages (
        id TEXT PRIMARY KEY,profile_id INTEGER NOT NULL REFERENCES documentation_confluence_profiles(id),
        document_id INTEGER NOT NULL REFERENCES documentation_dc_forms(id),page_key TEXT NOT NULL,
        remote_id TEXT,remote_version INTEGER,last_published_revision INTEGER,last_published_hash TEXT,
        last_remote_hash TEXT,last_attachments TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,
        UNIQUE(profile_id,document_id,page_key),UNIQUE(profile_id,remote_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS documentation_confluence_previews (
        id TEXT PRIMARY KEY,profile_id INTEGER NOT NULL REFERENCES documentation_confluence_profiles(id),
        document_id INTEGER NOT NULL,version_number INTEGER NOT NULL,profile_version INTEGER NOT NULL,
        payload TEXT NOT NULL,actor_id INTEGER,created_at TEXT NOT NULL,required_permissions TEXT NOT NULL DEFAULT '[]',
        FOREIGN KEY(document_id,version_number) REFERENCES documentation_dc_versions(document_id,number))''')
    if 'required_permissions' not in {r['name'] for r in conn.execute('PRAGMA table_info(documentation_confluence_previews)')}:
        conn.execute("ALTER TABLE documentation_confluence_previews ADD COLUMN required_permissions TEXT NOT NULL DEFAULT '[]'")
    from .confluence_jobs import init_schema as init_jobs
    init_jobs(conn)
    conn.execute('CREATE INDEX IF NOT EXISTS documentation_confluence_previews_document ON documentation_confluence_previews(document_id,created_at DESC)')


def audit(conn,profile_id,actor,action,metadata,document_id=None):
    # Only explicitly constructed metadata enters this log, never profile inputs,
    # HTTP response bodies, request headers or encrypted/plaintext credentials.
    conn.execute('''INSERT INTO documentation_confluence_audit(profile_id,document_id,actor_id,action,metadata,created_at)
        VALUES(?,?,?,?,?,?)''',(profile_id,document_id,actor,action,dump(metadata),now()))


def use_profiles():
    if not (access.allowed(['documentation.publish']) or access.allowed(['documentation.admin'])):raise access.Denied('Documentation Publish or Manage Confluence permission is required.')


def row(conn,identifier):
    result=conn.execute('SELECT * FROM documentation_confluence_profiles WHERE id=?',(identifier,)).fetchone()
    if result is None:raise Missing()
    return result


def public(item,full=False):
    result={'id':item['id'],**json.loads(item['settings']),'name':item['name'],'version':item['version'],
            'hasToken':bool(item['credential']),'lastCheck':json.loads(item['last_check']) if item['last_check'] else None,
            'createdAt':item['created_at'],'updatedAt':item['updated_at']}
    result['hasCustomCA']=bool(result.get('caPem'))
    if not full:result.pop('caPem',None)
    return result


def listing():
    use_profiles()
    with connection() as conn:return {'items':[public(item) for item in conn.execute('SELECT * FROM documentation_confluence_profiles ORDER BY name COLLATE NOCASE,id LIMIT 50')]}


def detail(identifier):
    access.action('admin')
    with connection() as conn:return public(row(conn,identifier),True)


def save(request,actor,identifier=None):
    access.action('admin')
    data=request.model_dump(exclude={'token','expectedVersion'})
    supplied=request.token.get_secret_value().strip() if request.token else ''
    if supplied and any(ord(char)<33 or ord(char)>126 for char in supplied):raise Invalid('Use an ASCII personal access token without whitespace.')
    try:
        with connection(True) as conn:
            old=row(conn,identifier) if identifier else None
            if old and request.expectedVersion!=old['version']:raise Conflict()
            if not old and conn.execute('SELECT COUNT(*) FROM documentation_confluence_profiles').fetchone()[0]>=50:raise Invalid('At most 50 Confluence profiles are allowed per tenant.')
            if not old and not supplied:raise Invalid('Enter a personal access token.')
            if old:
                previous=json.loads(old['settings'])
                if previous['baseUrl']!=data['baseUrl'] and not supplied:raise Invalid('Enter the token again when changing the Confluence base URL.')
                moved=any(previous[k]!=data[k] for k in ('baseUrl','spaceKey','parentPageId'))
                if moved and conn.execute('SELECT 1 FROM documentation_confluence_jobs WHERE profile_id=? AND active=1 LIMIT 1',(identifier,)).fetchone():raise Invalid('An active publication reserves this URL, space and parent. Resolve or abandon it before moving the destination.')
                if moved and conn.execute('SELECT 1 FROM documentation_confluence_pages WHERE profile_id=? AND remote_id IS NOT NULL LIMIT 1',(identifier,)).fetchone():raise Invalid('This destination already has remote page mappings. Create a separate profile for a different URL, space or parent.')
                credential=seal(supplied,identifier,data['baseUrl']) if supplied else old['credential']
                conn.execute('UPDATE documentation_confluence_profiles SET name=?,settings=?,credential=?,version=version+1,last_check=NULL,updated_at=? WHERE id=?',
                             (data['name'],dump(data),credential,now(),identifier))
            else:
                stamp=now()
                identifier=conn.execute('INSERT INTO documentation_confluence_profiles(name,settings,credential,created_at,updated_at) VALUES(?,?,?,?,?)',
                                        (data['name'],dump(data),'',stamp,stamp)).lastrowid
                conn.execute('UPDATE documentation_confluence_profiles SET credential=? WHERE id=?',(seal(supplied,identifier,data['baseUrl']),identifier))
            audit(conn,identifier,actor,'update_profile' if old else 'create_profile',{'version':(old['version']+1) if old else 1,'credentialChanged':bool(supplied)})
            return public(row(conn,identifier),True)
    except sqlite3.IntegrityError as exc:
        if 'documentation_confluence_profiles.name' in str(exc):raise Invalid('A Confluence connection with this name already exists.') from exc
        raise


def load(identifier,expected):
    use_profiles()
    with connection() as conn:
        item=row(conn,identifier)
        if item['version']!=expected:raise Conflict()
        result=public(item,True)
        if not result['enabled']:raise Invalid('This Confluence connection is disabled.')
        return result,item['credential']
