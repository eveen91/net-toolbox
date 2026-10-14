"""Draft CAS, immutable artifacts and audit share the tenant SQLite transaction."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
import db


class Missing(Exception):
    pass


class Conflict(Exception):
    def __init__(self, code, message, revision=None):
        self.detail = {'code': code, 'message': message, 'currentRevision': revision}


class Invalid(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


@contextmanager
def connection(write=False):
    conn = db.get_connection()
    try:
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        if write:
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise Invalid('DHCP storage constraint failed; check for a duplicate firewall name') from exc
    finally:
        conn.close()


def init_db():
    conn = db.get_connection()
    try:
        conn.executescript('''
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS dhcp_configurations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL COLLATE NOCASE UNIQUE,
          profile TEXT NOT NULL CHECK(profile IN ('R81.10','R82.10')),
          revision INTEGER NOT NULL CHECK(revision>=1),
          configuration TEXT NOT NULL,
          subnet_count INTEGER NOT NULL, reservation_count INTEGER NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dhcp_versions (
          id TEXT PRIMARY KEY,
          configuration_id INTEGER NOT NULL REFERENCES dhcp_configurations(id),
          number INTEGER NOT NULL CHECK(number>=1), draft_revision INTEGER NOT NULL,
          configuration TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL,
          profile TEXT NOT NULL, generator_version TEXT NOT NULL, report TEXT NOT NULL,
          description TEXT NOT NULL, actor_id INTEGER, actor_name TEXT, created_at TEXT NOT NULL,
          UNIQUE(configuration_id,number), UNIQUE(configuration_id,draft_revision)
        );
        CREATE TABLE IF NOT EXISTS dhcp_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, configuration_id INTEGER NOT NULL,
          actor_id INTEGER, actor_name TEXT, action TEXT NOT NULL,
          old_value TEXT, new_value TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dhcp_versions_configuration ON dhcp_versions(configuration_id,number DESC);
        CREATE INDEX IF NOT EXISTS idx_dhcp_audit_configuration ON dhcp_audit(configuration_id,id DESC);
        CREATE TRIGGER IF NOT EXISTS dhcp_versions_no_update BEFORE UPDATE ON dhcp_versions
          BEGIN SELECT RAISE(ABORT,'Published DHCP versions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS dhcp_versions_no_delete BEFORE DELETE ON dhcp_versions
          BEGIN SELECT RAISE(ABORT,'Published DHCP versions are immutable'); END;
        COMMIT;
        ''')
    finally:
        conn.close()


def summary(row):
    return {'id': row['id'], 'name': row['name'], 'profile': row['profile'], 'revision': row['revision'],
            'subnetCount': row['subnet_count'], 'reservationCount': row['reservation_count'],
            'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


def detail(conn, identifier):
    row = conn.execute('SELECT * FROM dhcp_configurations WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise Missing()
    return {**summary(row), 'configuration': json.loads(row['configuration'])}


def get_configuration(identifier):
    with connection() as conn:
        return detail(conn, identifier)


def require_revision(current, expected):
    if current['revision'] != expected:
        raise Conflict('revision_conflict', 'Configuration changed; reload and review your draft before saving', current['revision'])


def audit(conn, identifier, actor, action, before, after):
    conn.execute('INSERT INTO dhcp_audit(configuration_id,actor_id,actor_name,action,old_value,new_value,created_at) VALUES (?,?,?,?,?,?,?)',
                 (identifier, (actor or {}).get('id'), (actor or {}).get('username'), action,
                  dump(before) if before is not None else None, dump(after) if after is not None else None, now()))


def listing(query, limit, offset):
    with connection() as conn:
        escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        args = (f'%{escaped}%',)
        where = "WHERE name LIKE ? ESCAPE '\\'"
        total = conn.execute('SELECT COUNT(*) FROM dhcp_configurations '+where, args).fetchone()[0]
        rows = conn.execute('SELECT id,name,profile,revision,subnet_count,reservation_count,created_at,updated_at FROM dhcp_configurations '+where+' ORDER BY name COLLATE NOCASE,id LIMIT ? OFFSET ?', (*args,limit,offset))
        return {'items': [summary(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}


def counts(configuration):
    return len(configuration['subnets']), sum(len(subnet.get('reservations', [])) for subnet in configuration['subnets'])


def create(configuration, actor):
    with connection(True) as conn:
        timestamp = now()
        result = conn.execute('INSERT INTO dhcp_configurations(name,profile,revision,configuration,subnet_count,reservation_count,created_at,updated_at) VALUES (?,?,1,?,?,?,?,?)',
                              (configuration['firewall'], configuration['profile'], dump(configuration), *counts(configuration), timestamp, timestamp))
        item = detail(conn, result.lastrowid)
        audit(conn, item['id'], actor, 'draft_create', None, item)
        return item


def save(configuration_id, expected, configuration, actor, source_version=None):
    with connection(True) as conn:
        old = detail(conn, configuration_id)
        require_revision(old, expected)
        if source_version is not None:
            configuration = version(conn, configuration_id, source_version, True)['configuration']
        elif dump(old['configuration']) == dump(configuration):
            return old
        conn.execute('UPDATE dhcp_configurations SET name=?,profile=?,revision=revision+1,configuration=?,subnet_count=?,reservation_count=?,updated_at=? WHERE id=?',
                     (configuration['firewall'], configuration['profile'], dump(configuration), *counts(configuration), now(), configuration_id))
        item = detail(conn, configuration_id)
        audit(conn, configuration_id, actor, 'draft_restore' if source_version else 'draft_save', old,
              {**item, **({'sourceVersion': source_version} if source_version else {})})
        return item


VERSION_COLUMNS = 'id,configuration_id,number,draft_revision,sha256,profile,generator_version,report,description,actor_id,actor_name,created_at,length(content) artifact_bytes'


def version_data(row):
    return {'id': row['id'], 'configurationId': row['configuration_id'], 'number': row['number'],
            'draftRevision': row['draft_revision'], 'sha256': row['sha256'], 'profile': row['profile'],
            'generatorVersion': row['generator_version'], 'report': json.loads(row['report']),
            'description': row['description'], 'actorId': row['actor_id'], 'actorName': row['actor_name'],
            'createdAt': row['created_at'], 'artifactBytes': row['artifact_bytes']}


def version(conn, configuration_id, version_id, with_configuration=False):
    row = conn.execute('SELECT '+VERSION_COLUMNS+(',configuration' if with_configuration else '')+' FROM dhcp_versions WHERE configuration_id=? AND id=?', (configuration_id,version_id)).fetchone()
    if row is None:
        raise Missing()
    result = version_data(row)
    if with_configuration:
        result['configuration'] = json.loads(row['configuration'])
    return result


def get_version(configuration_id, version_id):
    with connection() as conn:
        return version(conn, configuration_id, version_id, True)


def artifact(configuration_id, version_id):
    with connection() as conn:
        metadata = version(conn, configuration_id, version_id, True)
        content = conn.execute('SELECT content FROM dhcp_versions WHERE configuration_id=? AND id=?', (configuration_id,version_id)).fetchone()[0]
        return metadata, bytes(content)


def publish(configuration_id, expected, identifier, content, report, description, actor):
    with connection(True) as conn:
        item = detail(conn, configuration_id)
        require_revision(item, expected)
        if conn.execute('SELECT 1 FROM dhcp_versions WHERE configuration_id=? AND draft_revision=?', (configuration_id,expected)).fetchone():
            raise Conflict('already_published', 'This draft revision has already been published; edit or restore a draft before creating another version', expected)
        number = conn.execute('SELECT COALESCE(MAX(number),0)+1 FROM dhcp_versions WHERE configuration_id=?', (configuration_id,)).fetchone()[0]
        conn.execute('INSERT INTO dhcp_versions(id,configuration_id,number,draft_revision,configuration,content,sha256,profile,generator_version,report,description,actor_id,actor_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (identifier,configuration_id,number,expected,dump(item['configuration']),content,report['sha256'],item['profile'],'1.0.0',dump(report),description,(actor or {}).get('id'),(actor or {}).get('username'),now()))
        result = version(conn, configuration_id, identifier, True)
        audit(conn, configuration_id, actor, 'version_publish', None, {key:value for key,value in result.items() if key!='configuration'})
        return result


def versions(configuration_id, limit, offset):
    with connection() as conn:
        detail(conn, configuration_id)
        total = conn.execute('SELECT COUNT(*) FROM dhcp_versions WHERE configuration_id=?', (configuration_id,)).fetchone()[0]
        rows = conn.execute('SELECT '+VERSION_COLUMNS+' FROM dhcp_versions WHERE configuration_id=? ORDER BY number DESC LIMIT ? OFFSET ?', (configuration_id,limit,offset))
        return {'items': [version_data(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}


def history(configuration_id, limit, offset):
    with connection() as conn:
        detail(conn, configuration_id)
        total = conn.execute('SELECT COUNT(*) FROM dhcp_audit WHERE configuration_id=?', (configuration_id,)).fetchone()[0]
        rows = conn.execute('SELECT * FROM dhcp_audit WHERE configuration_id=? ORDER BY id DESC LIMIT ? OFFSET ?', (configuration_id,limit,offset))
        return {'items': [{'id': row['id'], 'actorId': row['actor_id'], 'actorName': row['actor_name'], 'action': row['action'],
                           'oldValue': json.loads(row['old_value']) if row['old_value'] else None,
                           'newValue': json.loads(row['new_value']) if row['new_value'] else None, 'createdAt': row['created_at']} for row in rows],
                'total': total, 'limit': limit, 'offset': offset}
