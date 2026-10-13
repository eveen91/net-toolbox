import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import db
from .naming import port_name
from .service import proposals, preview_data


class Missing(Exception):
    pass


class Conflict(Exception):
    def __init__(self, detail):
        self.detail = detail


class Invalid(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with connection(write=True) as conn:
        conn.executescript('''
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS dv_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_type TEXT NOT NULL CHECK(device_type IN ('switch','firewall','server')),
            vendor TEXT CHECK(vendor IN ('checkpoint','fortigate','generic')),
            name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 100),
            model TEXT CHECK(model IS NULL OR length(model)<=100),
            description TEXT CHECK(description IS NULL OR length(description)<=500),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version>=1),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK((device_type='firewall' AND vendor IS NOT NULL) OR (device_type!='firewall' AND vendor IS NULL))
        );
        CREATE TABLE IF NOT EXISTS dv_port_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES dv_devices(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK(kind IN ('family','nic')),
            group_key TEXT NOT NULL,
            slot_number INTEGER, name TEXT CHECK(name IS NULL OR length(name)<=60),
            family TEXT NOT NULL CHECK(family IN ('ethernet','sfp','qsfp')),
            port_count INTEGER NOT NULL, speed_gbps INTEGER NOT NULL,
            UNIQUE(device_id,group_key), UNIQUE(device_id,slot_number), UNIQUE(id,device_id),
            CHECK((kind='nic' AND slot_number BETWEEN 1 AND 16 AND slot_number IS NOT NULL AND port_count BETWEEN 1 AND 8)
               OR (kind='family' AND slot_number IS NULL AND port_count>=0 AND
                    ((family='ethernet' AND port_count<=96) OR (family='sfp' AND port_count<=48) OR (family='qsfp' AND port_count<=16)))),
            CHECK((family='ethernet' AND speed_gbps IN (1,10)) OR (family='sfp' AND speed_gbps IN (10,25)) OR (family='qsfp' AND speed_gbps IN (40,100)))
        );
        CREATE TABLE IF NOT EXISTS dv_ports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES dv_devices(id) ON DELETE CASCADE,
            group_id INTEGER NOT NULL,
            port_number INTEGER NOT NULL CHECK(port_number BETWEEN 1 AND 96),
            label TEXT CHECK(label IS NULL OR length(label)<=50),
            leads_to TEXT CHECK(leads_to IS NULL OR length(leads_to)<=200),
            UNIQUE(group_id,port_number),
            FOREIGN KEY(group_id,device_id) REFERENCES dv_port_groups(id,device_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS dv_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, device_id INTEGER NOT NULL,
            actor_id INTEGER, action TEXT NOT NULL,
            old_value TEXT, new_value TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dv_ports_device ON dv_ports(device_id);
        CREATE INDEX IF NOT EXISTS idx_dv_ports_group ON dv_ports(group_id);
        CREATE INDEX IF NOT EXISTS idx_dv_audit_device ON dv_audit(device_id,id);
        COMMIT;
        ''')

    migrate_sfp_limit()
    migrate_port_vlans()
    migrate_port_naming()


def migrate_port_naming():
    with connection(write=True) as conn:
        columns={r['name'] for r in conn.execute('PRAGMA table_info(dv_devices)')}
        for name, definition in [
            ('port_naming', "TEXT NOT NULL DEFAULT 'family' CHECK(port_naming IN ('family','unit-slot-port','unit-zero-port','unit-port','port'))"),
            ('port_unit', "INTEGER NOT NULL DEFAULT 1 CHECK(typeof(port_unit)='integer' AND port_unit BETWEEN 1 AND 16)"),
            ('port_slot', "INTEGER NOT NULL DEFAULT 1 CHECK(typeof(port_slot)='integer' AND port_slot BETWEEN 0 AND 16)"),
        ]:
            if name not in columns:
                conn.execute(f'ALTER TABLE dv_devices ADD COLUMN {name} {definition}')


def migrate_port_vlans():
    with connection(write=True) as conn:
        columns={r['name'] for r in conn.execute('PRAGMA table_info(dv_ports)')}
        for name, definition in [
            ('port_mode', "TEXT CHECK(port_mode IS NULL OR port_mode IN ('access','trunk'))"),
            ('access_vlan', "INTEGER CHECK(access_vlan IS NULL OR (typeof(access_vlan)='integer' AND access_vlan BETWEEN 1 AND 4094))"),
            ('trunk_vlans', 'TEXT CHECK(trunk_vlans IS NULL OR length(trunk_vlans)<=2000)'),
            ('native_vlan', "INTEGER CHECK(native_vlan IS NULL OR (typeof(native_vlan)='integer' AND native_vlan BETWEEN 1 AND 4094))"),
        ]:
            if name not in columns:
                conn.execute(f'ALTER TABLE dv_ports ADD COLUMN {name} {definition}')
        invalid="""NOT ((NEW.port_mode IS NULL AND NEW.access_vlan IS NULL AND NEW.trunk_vlans IS NULL AND NEW.native_vlan IS NULL)
             OR (NEW.port_mode IS 'access' AND NEW.access_vlan IS NOT NULL AND NEW.trunk_vlans IS NULL AND NEW.native_vlan IS NULL)
             OR (NEW.port_mode IS 'trunk' AND NEW.access_vlan IS NULL AND NEW.trunk_vlans IS NOT NULL AND length(trim(NEW.trunk_vlans))>0))"""
        for action in ('INSERT','UPDATE'):
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS dv_ports_vlan_{action.lower()} BEFORE {action} ON dv_ports WHEN {invalid} BEGIN SELECT RAISE(ABORT,'Invalid VLAN configuration'); END")


def migrate_sfp_limit():
    """Rebuild the old CHECK without changing group/port IDs or child rows."""
    conn = db.get_connection()
    try:
        # SQLite requires disabling FK enforcement before starting a table rebuild.
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='dv_port_groups'").fetchone()
        if row is None:
            return
        sql = row[0]
        updated = re.sub(r"(family\s*=\s*'sfp'\s+AND\s+port_count\s*<=\s*)32\b", r"\g<1>48", sql)
        if updated == sql:
            return
        schema_objects = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='dv_port_groups' AND type IN ('index','trigger') AND sql IS NOT NULL")]
        seq_row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='dv_port_groups'").fetchone()
        previous_sequence = seq_row[0] if seq_row else 0
        updated = re.sub(r'CREATE TABLE(?: IF NOT EXISTS)?\s+(?:"dv_port_groups"|dv_port_groups)(?=\s*\()', 'CREATE TABLE dv_port_groups_new', updated, count=1, flags=re.I)
        conn.execute(updated)
        conn.execute('INSERT INTO dv_port_groups_new SELECT * FROM dv_port_groups')
        conn.execute('DROP TABLE dv_port_groups')
        conn.execute('ALTER TABLE dv_port_groups_new RENAME TO dv_port_groups')
        conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='dv_port_groups'", (previous_sequence,))
        for statement in schema_objects:
            conn.execute(statement)
        if conn.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise sqlite3.IntegrityError('Foreign key validation failed during SFP limit migration')
        conn.commit()
    finally:
        conn.rollback()
        conn.execute('PRAGMA foreign_keys=ON')
        conn.close()


@contextmanager
def connection(write=False):
    conn = db.get_connection()
    try:
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        if write:
            conn.commit()
    except sqlite3.IntegrityError as exc:
        if 'dv_devices.name' in str(exc):
            raise Invalid('A device with this name already exists in this tenant') from exc
        raise Invalid('Device configuration violates a database constraint') from exc
    finally:
        conn.close()


def summary(row):
    return {out: row[col] for out, col in [('id','id'),('deviceType','device_type'),('vendor','vendor'),('name','name'),
        ('portNaming','port_naming'),('portUnit','port_unit'),('portSlot','port_slot'),('model','model'),('description','description'),('version','version'),('createdAt','created_at'),('updatedAt','updated_at'),
        ('portCount','port_count'),('assignedPortCount','assigned_count'),('cardCount','card_count')]}


SUMMARY_SQL = '''SELECT d.*,
 (SELECT COUNT(*) FROM dv_ports p WHERE p.device_id=d.id) port_count,
 (SELECT COUNT(*) FROM dv_ports p WHERE p.device_id=d.id AND p.leads_to IS NOT NULL) assigned_count,
 (SELECT COUNT(*) FROM dv_port_groups g WHERE g.device_id=d.id AND g.kind='nic') card_count FROM dv_devices d'''


def detail(conn, device_id):
    row = conn.execute(SUMMARY_SQL+' WHERE d.id=?', (device_id,)).fetchone()
    if row is None:
        raise Missing()
    data = summary(row)
    groups = [dict(g) for g in conn.execute("SELECT * FROM dv_port_groups WHERE device_id=? ORDER BY slot_number, CASE family WHEN 'ethernet' THEN 0 WHEN 'sfp' THEN 1 ELSE 2 END", (device_id,))]
    ports = []
    ordinal = 0
    for g in groups:
        for p in conn.execute('SELECT * FROM dv_ports WHERE group_id=? ORDER BY port_number', (g['id'],)):
            ordinal += 1
            name = f"NIC {g['slot_number']} / Port {p['port_number']}"
            if g['kind']=='family':
                name = port_name(row,g['family'],p['port_number'],ordinal)
            ports.append({'id':p['id'],'groupId':g['id'],'family':g['family'],'number':p['port_number'],'name':name,
                          'slotNumber':g['slot_number'],'speedGbps':g['speed_gbps'],'label':p['label'],'leadsTo':p['leads_to'],
                          'portMode':p['port_mode'],'accessVlan':p['access_vlan'],'trunkVlans':p['trunk_vlans'],'nativeVlan':p['native_vlan']})
    data['ports'] = ports
    mapped = [{'id':g['id'],'family':g['family'],'count':g['port_count'],'speedGbps':g['speed_gbps'],
               **({'slotNumber':g['slot_number'],'name':g['name']} if g['kind']=='nic' else {})} for g in groups]
    data['networkCards' if row['device_type']=='server' else 'portGroups'] = mapped
    return data


def get_device(device_id):
    with connection() as conn:
        return detail(conn, device_id)


def list_devices(query='', device_type=None, vendor=None, limit=50, offset=0):
    clauses, args = [], []
    if query:
        escaped = query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clauses.append("(d.name LIKE ? ESCAPE '\\' OR d.model LIKE ? ESCAPE '\\' OR d.description LIKE ? ESCAPE '\\')")
        args.extend([f'%{escaped}%']*3)
    if device_type:
        clauses.append('d.device_type=?'); args.append(device_type)
    if vendor:
        clauses.append('d.vendor=?'); args.append(vendor)
    where = ' WHERE '+' AND '.join(clauses) if clauses else ''
    with connection() as conn:
        total = conn.execute('SELECT COUNT(*) FROM dv_devices d'+where, args).fetchone()[0]
        rows = conn.execute(SUMMARY_SQL+where+' ORDER BY d.name COLLATE NOCASE,d.id LIMIT ? OFFSET ?', (*args,limit,offset))
        return {'items':[summary(r) for r in rows],'total':total,'limit':limit,'offset':offset}


def check_version(current, expected):
    if current['version'] != expected:
        raise Conflict({'code':'stale_version','message':'Device changed. Reload current data and review your edits again'})


def audit(conn, device_id, actor_id, action, old, new):
    conn.execute('INSERT INTO dv_audit(device_id,actor_id,action,old_value,new_value,created_at) VALUES(?,?,?,?,?,?)',
                 (device_id,actor_id,action,json.dumps(old) if old is not None else None,json.dumps(new) if new is not None else None,now()))


def apply_groups(conn, device_id, proposed):
    existing = {g['id']:dict(g) for g in conn.execute('SELECT * FROM dv_port_groups WHERE device_id=?',(device_id,))}
    retained = {g['id'] for g in proposed if g['id'] is not None}
    for group_id in existing.keys()-retained:
        conn.execute('DELETE FROM dv_port_groups WHERE id=? AND device_id=?',(group_id,device_id))
    for g in proposed:
        group_id=g['id']
        if group_id is None:
            cursor=conn.execute('INSERT INTO dv_port_groups(device_id,kind,group_key,slot_number,name,family,port_count,speed_gbps) VALUES(?,?,?,?,?,?,?,?)',
                (device_id,g['kind'],str(uuid.uuid4()) if g['kind']=='nic' else g['family'],g['slot'],g['name'],g['family'],g['count'],g['speedGbps']))
            group_id=cursor.lastrowid
        else:
            if existing[group_id]['family'] != g['family']:
                conn.execute('DELETE FROM dv_ports WHERE group_id=?',(group_id,))
            conn.execute('UPDATE dv_port_groups SET family=?,port_count=?,speed_gbps=?,name=? WHERE id=? AND device_id=?',
                         (g['family'],g['count'],g['speedGbps'],g['name'],group_id,device_id))
        conn.execute('DELETE FROM dv_ports WHERE group_id=? AND port_number>?',(group_id,g['count']))
        present={p[0] for p in conn.execute('SELECT port_number FROM dv_ports WHERE group_id=?',(group_id,))}
        conn.executemany('INSERT INTO dv_ports(device_id,group_id,port_number) VALUES(?,?,?)',
                         [(device_id,group_id,n) for n in range(1,g['count']+1) if n not in present])


def create_device(config, actor_id=None):
    with connection(write=True) as conn:
        stamp=now()
        cursor=conn.execute('INSERT INTO dv_devices(device_type,vendor,name,model,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (config.deviceType,config.vendor,config.name,config.model,config.description,stamp,stamp))
        device_id=cursor.lastrowid
        conn.execute("UPDATE dv_devices SET port_naming=?,port_unit=?,port_slot=? WHERE id=?", (config.portNaming,config.portUnit,config.portSlot,device_id))
        apply_groups(conn,device_id,proposals(config))
        result=detail(conn,device_id)
        audit(conn,device_id,actor_id,'device_create',None,result)
        return result


def update_device(device_id, config, actor_id=None, preview=False):
    with connection(write=not preview) as conn:
        current=detail(conn,device_id)
        check_version(current,config.expectedVersion)
        if current['deviceType'] != config.deviceType:
            raise Invalid('Device type cannot be changed')
        proposed=proposals(config,current)
        review=preview_data(current,proposed)
        if preview:
            return review
        if (review['removedAssignedPortCount'] or review['removedLabelledPortCount'] or review['removedConfiguredPortCount']) and not config.confirmPortDataRemoval:
            raise Conflict({'code':'confirmation_required','message':'Review and confirm removal of port labels or assignments',**review})
        apply_groups(conn,device_id,proposed)
        naming={key:getattr(config,key) if key in config.model_fields_set else current[key] for key in ('portNaming','portUnit','portSlot')}
        conn.execute('UPDATE dv_devices SET port_naming=?,port_unit=?,port_slot=? WHERE id=?',
                     (naming['portNaming'],naming['portUnit'],naming['portSlot'],device_id))
        conn.execute('UPDATE dv_devices SET vendor=?,name=?,model=?,description=? WHERE id=?',
                     (config.vendor,config.name,config.model,config.description,device_id))
        candidate=detail(conn,device_id)
        if candidate == current:
            return current
        conn.execute('UPDATE dv_devices SET version=version+1,updated_at=? WHERE id=?',(now(),device_id))
        result=detail(conn,device_id)
        audit(conn,device_id,actor_id,'device_update',current,result)
        return result


def update_port(device_id,port_id,request,actor_id=None):
    with connection(write=True) as conn:
        current=detail(conn,device_id)
        port=next((p for p in current['ports'] if p['id']==port_id),None)
        if port is None:
            raise Missing()
        check_version(current,request.expectedVersion)
        fields={'portMode':'port_mode','accessVlan':'access_vlan','trunkVlans':'trunk_vlans','nativeVlan':'native_vlan'}
        vlan={key:getattr(request,key) for key in fields} if set(fields).intersection(request.model_fields_set) else {key:port[key] for key in fields}
        if port['label']==request.label and port['leadsTo']==request.leadsTo and all(port[k]==v for k,v in vlan.items()):
            return current
        conn.execute('UPDATE dv_ports SET label=?,leads_to=?,port_mode=?,access_vlan=?,trunk_vlans=?,native_vlan=? WHERE id=? AND device_id=?',
                     (request.label,request.leadsTo,vlan['portMode'],vlan['accessVlan'],vlan['trunkVlans'],vlan['nativeVlan'],port_id,device_id))
        conn.execute('UPDATE dv_devices SET version=version+1,updated_at=? WHERE id=?',(now(),device_id))
        result=detail(conn,device_id)
        updated=next(p for p in result['ports'] if p['id']==port_id)
        audit(conn,device_id,actor_id,'port_update',{'name':current['name'],'port':port},{'name':result['name'],'port':updated})
        return result


def delete_device(device_id,request,actor_id=None):
    with connection(write=True) as conn:
        current=detail(conn,device_id)
        check_version(current,request.expectedVersion)
        if not request.confirmDelete:
            raise Conflict({'code':'confirmation_required','message':'Confirm deletion of this device'})
        audit(conn,device_id,actor_id,'device_delete',current,None)
        conn.execute('DELETE FROM dv_devices WHERE id=?',(device_id,))
        return {'deleted':True,'id':device_id}


def list_audit(device_id,limit=50,offset=0):
    with connection() as conn:
        total=conn.execute('SELECT COUNT(*) FROM dv_audit WHERE device_id=?',(device_id,)).fetchone()[0]
        if not total and not conn.execute('SELECT 1 FROM dv_devices WHERE id=?',(device_id,)).fetchone():
            raise Missing()
        rows=conn.execute('SELECT * FROM dv_audit WHERE device_id=? ORDER BY id DESC LIMIT ? OFFSET ?',(device_id,limit,offset))
        items=[{'id':r['id'],'deviceId':r['device_id'],'actorId':r['actor_id'],'action':r['action'],
                'oldValue':json.loads(r['old_value']) if r['old_value'] else None,'newValue':json.loads(r['new_value']) if r['new_value'] else None,'createdAt':r['created_at']} for r in rows]
        return {'items':items,'total':total,'limit':limit,'offset':offset}
