"""Shared tenant database schema and paginated inventory reads."""
import json
from device_visualization import repository as devices


def init_schema(conn):
    statements = [
        '''CREATE TABLE IF NOT EXISTS dc_datacenters (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE, description TEXT, version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS dc_racks (id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_center_id INTEGER NOT NULL REFERENCES dc_datacenters(id) ON DELETE RESTRICT,
        name TEXT NOT NULL COLLATE NOCASE, description TEXT,
        height_u INTEGER NOT NULL CHECK(typeof(height_u)='integer' AND height_u BETWEEN 1 AND 100),
        version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(data_center_id,name))''',
        '''CREATE TABLE IF NOT EXISTS dc_audit (id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, actor_id INTEGER, action TEXT NOT NULL,
        old_value TEXT, new_value TEXT, created_at TEXT NOT NULL)''',
    ]
    for sql in statements:
        conn.execute(sql)
    columns={row['name'] for row in conn.execute('PRAGMA table_info(dv_devices)')}
    for name,definition in [
        ('rack_id','INTEGER REFERENCES dc_racks(id) ON DELETE RESTRICT'),
        ('rack_position',"INTEGER CHECK(rack_position IS NULL OR (typeof(rack_position)='integer' AND rack_position BETWEEN 1 AND 100))"),
        ('height_u',"INTEGER CHECK(height_u IS NULL OR (typeof(height_u)='integer' AND height_u BETWEEN 1 AND 100))"),
    ]:
        if name not in columns:
            conn.execute(f'ALTER TABLE dv_devices ADD COLUMN {name} {definition}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dv_devices_rack ON dv_devices(rack_id,rack_position)')
    invalid='''(NEW.rack_id IS NULL AND NEW.rack_position IS NOT NULL) OR
        (NEW.rack_id IS NOT NULL AND (NEW.rack_position IS NULL OR NEW.height_u IS NULL OR
        NOT EXISTS(SELECT 1 FROM dc_racks WHERE id=NEW.rack_id AND NEW.rack_position+NEW.height_u-1<=height_u) OR
        EXISTS(SELECT 1 FROM dv_devices d WHERE d.id!=NEW.id AND d.rack_id=NEW.rack_id
        AND d.rack_position<=NEW.rack_position+NEW.height_u-1 AND d.rack_position+d.height_u-1>=NEW.rack_position)))'''
    for action in ('INSERT','UPDATE'):
        conn.execute(f"CREATE TRIGGER IF NOT EXISTS dv_device_placement_{action.lower()} BEFORE {action} ON dv_devices WHEN {invalid} BEGIN SELECT RAISE(ABORT,'Invalid or overlapping rack placement'); END")
    conn.execute('''CREATE TRIGGER IF NOT EXISTS dc_rack_capacity BEFORE UPDATE OF height_u ON dc_racks
        WHEN EXISTS(SELECT 1 FROM dv_devices WHERE rack_id=NEW.id AND rack_position+height_u-1>NEW.height_u)
        BEGIN SELECT RAISE(ABORT,'Rack resize would exclude installed devices'); END''')

    from .connections import init_schema as init_connections
    init_connections(conn)


DC_SQL='''SELECT c.id,c.name,c.description,c.version,c.created_at AS createdAt,c.updated_at AS updatedAt,
 (SELECT COUNT(*) FROM dc_racks WHERE data_center_id=c.id) rackCount FROM dc_datacenters c'''
RACK_SQL='''SELECT r.id,r.data_center_id AS dataCenterId,r.name,r.description,r.height_u AS heightU,r.version,
 r.created_at AS createdAt,r.updated_at AS updatedAt,c.name AS dataCenterName,
 (SELECT COUNT(*) FROM dv_devices WHERE rack_id=r.id) deviceCount,
 COALESCE((SELECT SUM(height_u) FROM dv_devices WHERE rack_id=r.id),0) usedU
 FROM dc_racks r JOIN dc_datacenters c ON c.id=r.data_center_id'''
DEVICE_SQL='''SELECT d.id,d.name,d.device_type AS deviceType,d.model,d.version,d.height_u AS heightU,
 d.rack_id AS rackId,d.rack_position AS rackPosition,r.name AS rackName,r.data_center_id AS dataCenterId,
 c.name AS dataCenterName FROM dv_devices d LEFT JOIN dc_racks r ON r.id=d.rack_id
 LEFT JOIN dc_datacenters c ON c.id=r.data_center_id'''


def one(conn,kind,entity_id):
    sql=DC_SQL if kind=='datacenter' else RACK_SQL if kind=='rack' else DEVICE_SQL
    alias='c' if kind=='datacenter' else 'r' if kind=='rack' else 'd'
    row=conn.execute(sql+f' WHERE {alias}.id=?',(entity_id,)).fetchone()
    if row is None:
        raise devices.Missing()
    return dict(row)


def page(sql,args,limit,offset,order):
    with devices.connection() as conn:
        total=conn.execute('SELECT COUNT(*) FROM ('+sql+')',args).fetchone()[0]
        rows=conn.execute(sql+' ORDER BY '+order+' LIMIT ? OFFSET ?',(*args,limit,offset))
        return {'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset}


def datacenters(limit=50,offset=0):
    return page(DC_SQL,(),limit,offset,'c.name COLLATE NOCASE,c.id')


def racks(data_center_id=None,limit=50,offset=0):
    return page(RACK_SQL+(' WHERE r.data_center_id=?' if data_center_id else ''),(data_center_id,) if data_center_id else (),limit,offset,'r.name COLLATE NOCASE,r.id')


def device_page(unassigned=False,rack_id=None,query='',limit=25,offset=0):
    clauses=[];args=[]
    if unassigned:clauses.append('d.rack_id IS NULL')
    if rack_id is not None:clauses.append('d.rack_id=?');args.append(rack_id)
    if query:
        clauses.append("d.name LIKE ? ESCAPE '\\'");args.append('%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    return page(DEVICE_SQL+(' WHERE '+' AND '.join(clauses) if clauses else ''),args,limit,offset,'d.name COLLATE NOCASE,d.id')


def rack_detail(rack_id):
    with devices.connection() as conn:
        rack=one(conn,'rack',rack_id)
        rack['devices']=[dict(row) for row in conn.execute(DEVICE_SQL+' WHERE d.rack_id=? ORDER BY d.rack_position DESC,d.id',(rack_id,))]
        return rack


def log(conn,kind,entity_id,actor,action,old,new):
    conn.execute('INSERT INTO dc_audit(entity_type,entity_id,actor_id,action,old_value,new_value,created_at) VALUES(?,?,?,?,?,?,?)',
        (kind,entity_id,actor,action,json.dumps(old) if old is not None else None,json.dumps(new) if new is not None else None,devices.now()))


def history(limit=25,offset=0):
    with devices.connection() as conn:
        total=conn.execute('SELECT COUNT(*) FROM dc_audit').fetchone()[0]
        items=[]
        for row in conn.execute('SELECT * FROM dc_audit ORDER BY id DESC LIMIT ? OFFSET ?',(limit,offset)):
            items.append({'id':row['id'],'entityType':row['entity_type'],'entityId':row['entity_id'],'actorId':row['actor_id'],'action':row['action'],'oldValue':json.loads(row['old_value']) if row['old_value'] else None,'newValue':json.loads(row['new_value']) if row['new_value'] else None,'createdAt':row['created_at']})
        return {'items':items,'total':total,'limit':limit,'offset':offset}


def device_snapshot(device):
    return {key:device[key] for key in ('id','name','deviceType','model','version','heightU','rackId','rackPosition','rackName','dataCenterId','dataCenterName')}
