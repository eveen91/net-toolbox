"""Global access groups and dynamically resolved tenant grants.

Direct user roles override group roles. Otherwise permissions from matching
local/verified AD groups are combined. Group changes apply on the next request.
"""
import json
import sqlite3
from contextlib import contextmanager
import auth_db


def init_schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS access_groups (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
      source TEXT NOT NULL CHECK(source IN ('local','ad')),
      group_dn TEXT COLLATE NOCASE UNIQUE, created_at TEXT NOT NULL,
      CHECK((source='local' AND group_dn IS NULL) OR (source='ad' AND group_dn IS NOT NULL))
    );
    CREATE TABLE IF NOT EXISTS access_group_members (
      group_id INTEGER NOT NULL REFERENCES access_groups(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      PRIMARY KEY(group_id,user_id)
    );
    CREATE INDEX IF NOT EXISTS access_group_members_user ON access_group_members(user_id);
    CREATE TABLE IF NOT EXISTS tenant_group_access (
      tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      group_id INTEGER NOT NULL REFERENCES access_groups(id) ON DELETE CASCADE,
      role_name TEXT NOT NULL REFERENCES roles(name),
      PRIMARY KEY(tenant_id,group_id)
    );
    CREATE TABLE IF NOT EXISTS ad_group_observations (
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      group_dn TEXT NOT NULL COLLATE NOCASE,
      observed_at TEXT NOT NULL, PRIMARY KEY(user_id,group_dn)
    );
    ''')


@contextmanager
def transaction():
    conn = auth_db.get_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError('Duplicate group name/DN or invalid assignment') from exc
    finally:
        conn.close()


def record(conn, tenant_id, actor_id, action, details):
    conn.execute('INSERT INTO tenant_audit(tenant_id,actor_id,action,details,created_at) VALUES (?,?,?,?,?)',
                 (tenant_id,actor_id,action,json.dumps(details),auth_db._now()))


def group(conn, identifier):
    row = conn.execute('SELECT id,name,source,group_dn AS groupDn FROM access_groups WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise ValueError('Group not found')
    return dict(row)


def groups(query='', limit=25, offset=0):
    conn = auth_db.get_connection()
    try:
        term = '%' + query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        where = "WHERE name LIKE ? ESCAPE '\\' OR group_dn LIKE ? ESCAPE '\\'"
        total = conn.execute('SELECT COUNT(*) FROM access_groups '+where, (term,term)).fetchone()[0]
        rows = conn.execute('SELECT id,name,source,group_dn AS groupDn FROM access_groups '+where+' ORDER BY name LIMIT ? OFFSET ?', (term,term,limit,offset))
        return {'items':[dict(row) for row in rows], 'total':total, 'offset':offset, 'limit':limit}
    finally:
        conn.close()


def create_group(name, source, group_dn, actor_id):
    name = name.strip()
    dn = group_dn.strip() if group_dn else None
    if not name or (source == 'ad' and not dn) or (source == 'local' and dn):
        raise ValueError('Name is required; only AD groups require a group DN')
    with transaction() as conn:
        cursor = conn.execute('INSERT INTO access_groups(name,source,group_dn,created_at) VALUES (?,?,?,?)', (name,source,dn,auth_db._now()))
        item = group(conn,cursor.lastrowid)
        record(conn,None,actor_id,'group_create',item)
        return item


def delete_group(identifier, actor_id):
    with transaction() as conn:
        item = group(conn,identifier)
        tenants = conn.execute('SELECT tenant_id,role_name FROM tenant_group_access WHERE group_id=?', (identifier,)).fetchall()
        for tenant in tenants:
            record(conn,tenant['tenant_id'],actor_id,'group_access_remove',{**item,'previousRole':tenant['role_name'],'reason':'group_deleted'})
        record(conn,None,actor_id,'group_delete',item)
        conn.execute('DELETE FROM access_groups WHERE id=?', (identifier,))


def members(identifier, limit=25, offset=0):
    conn = auth_db.get_connection()
    try:
        item = group(conn,identifier)
        if item['source'] == 'local':
            sql = 'FROM access_group_members m JOIN users u ON u.id=m.user_id WHERE m.group_id=?'
            args = (identifier,)
        else:
            sql = "FROM ad_group_observations m JOIN users u ON u.id=m.user_id WHERE m.group_dn=? COLLATE NOCASE AND u.auth_source='ad'"
            args = (item['groupDn'],)
        total = conn.execute('SELECT COUNT(*) '+sql,args).fetchone()[0]
        rows = conn.execute('SELECT u.id,u.username,u.auth_source AS authSource '+sql+' ORDER BY u.username,u.id LIMIT ? OFFSET ?', (*args,limit,offset))
        return {'group':item,'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset}
    finally:
        conn.close()


def member_change(identifier, user_id, actor_id, remove=False):
    with transaction() as conn:
        item = group(conn,identifier)
        if item['source'] != 'local':
            raise ValueError('AD membership is verified at login and cannot be edited here')
        account = conn.execute('SELECT username FROM users WHERE id=?', (user_id,)).fetchone()
        if not account:
            raise ValueError('User not found')
        if remove:
            conn.execute('DELETE FROM access_group_members WHERE group_id=? AND user_id=?', (identifier,user_id))
        else:
            conn.execute('INSERT OR IGNORE INTO access_group_members(group_id,user_id) VALUES (?,?)', (identifier,user_id))
        details = {**item,'userId':user_id,'username':account['username']}
        record(conn,None,actor_id,'group_member_remove' if remove else 'group_member_add',details)
        for tenant in conn.execute('SELECT tenant_id FROM tenant_group_access WHERE group_id=?', (identifier,)).fetchall():
            record(conn,tenant['tenant_id'],actor_id,'group_member_remove' if remove else 'group_member_add',details)


def bindings(tenant_id):
    conn = auth_db.get_connection()
    try:
        return [dict(row) for row in conn.execute('''SELECT g.id,g.name,g.source,g.group_dn AS groupDn,a.role_name AS role
            FROM tenant_group_access a JOIN access_groups g ON g.id=a.group_id WHERE a.tenant_id=? ORDER BY g.name''', (tenant_id,))]
    finally:
        conn.close()


def set_binding(tenant_id, identifier, role, actor_id, remove=False):
    with transaction() as conn:
        item = group(conn,identifier)
        if not conn.execute('SELECT 1 FROM tenants WHERE id=?', (tenant_id,)).fetchone():
            raise ValueError('Tenant not found')
        previous = conn.execute('SELECT role_name FROM tenant_group_access WHERE tenant_id=? AND group_id=?', (tenant_id,identifier)).fetchone()
        if remove:
            conn.execute('DELETE FROM tenant_group_access WHERE tenant_id=? AND group_id=?', (tenant_id,identifier))
        else:
            if role == 'admin' or not conn.execute('SELECT 1 FROM roles WHERE name=?', (role,)).fetchone():
                raise ValueError('Choose an existing tenant role; platform admin cannot be granted through a tenant')
            conn.execute('''INSERT INTO tenant_group_access(tenant_id,group_id,role_name) VALUES (?,?,?)
                ON CONFLICT(tenant_id,group_id) DO UPDATE SET role_name=excluded.role_name''', (tenant_id,identifier,role))
        record(conn,tenant_id,actor_id,'group_access_remove' if remove else 'group_access_set',
               {**item,'role':None if remove else role,'previousRole':previous['role_name'] if previous else None})


def ad_candidates():
    conn = auth_db.get_connection()
    try:
        return [row[0] for row in conn.execute("SELECT DISTINCT g.group_dn FROM access_groups g JOIN tenant_group_access a ON a.group_id=g.id WHERE g.source='ad'")]
    finally:
        conn.close()


def observe_ad(user_id, matched_dns):
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id=? AND auth_source='ad'", (user_id,)).fetchone():
            raise ValueError('AD observations require an AD account')
        conn.execute('DELETE FROM ad_group_observations WHERE user_id=?', (user_id,))
        conn.executemany('INSERT OR IGNORE INTO ad_group_observations(user_id,group_dn,observed_at) VALUES (?,?,?)',
                         [(user_id,dn,auth_db._now()) for dn in matched_dns])


MATCH = '''((g.source='local' AND EXISTS(SELECT 1 FROM access_group_members m WHERE m.group_id=g.id AND m.user_id=?))
    OR (g.source='ad' AND EXISTS(SELECT 1 FROM ad_group_observations o JOIN users u ON u.id=o.user_id
         WHERE o.user_id=? AND u.auth_source='ad' AND o.group_dn=g.group_dn COLLATE NOCASE)))'''


def access(tenant_id, user_id):
    conn = auth_db.get_connection()
    try:
        direct = conn.execute('SELECT role_name FROM tenant_memberships WHERE tenant_id=? AND user_id=?', (tenant_id,user_id)).fetchone()
        if direct:
            names = [direct['role_name']]
        else:
            names = [row[0] for row in conn.execute('''SELECT DISTINCT a.role_name FROM tenant_group_access a
                JOIN access_groups g ON g.id=a.group_id WHERE a.tenant_id=? AND '''+MATCH, (tenant_id,user_id,user_id))]
        if not names:
            return None
        permissions = set()
        for name in names:
            # Roles are current on every request; no cached permission expansion.
            row = conn.execute('SELECT permissions FROM roles WHERE name=?', (name,)).fetchone()
            if row:
                permissions.update(json.loads(row[0]))
        return {'role':'tenant-admin' if 'tenant-admin' in names else names[0] if len(names)==1 else 'group-member',
                'roles':sorted(names),'permissions':sorted(permissions),'source':'individual' if direct else 'groups'}
    finally:
        conn.close()


def tenant_ids(user_id):
    conn = auth_db.get_connection()
    try:
        return {row[0] for row in conn.execute('SELECT tenant_id FROM tenant_memberships WHERE user_id=?', (user_id,))} | {
            row[0] for row in conn.execute('SELECT DISTINCT a.tenant_id FROM tenant_group_access a JOIN access_groups g ON g.id=a.group_id WHERE '+MATCH, (user_id,user_id))}
    finally:
        conn.close()
