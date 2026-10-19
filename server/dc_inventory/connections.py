"""Explicit physical port pairs; all reads and writes use the active tenant DB."""
import json
from device_visualization import repository as devices
from . import repository as inventory


def init_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS dc_connections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_port_id INTEGER NOT NULL REFERENCES dv_ports(id) ON DELETE CASCADE,
        target_port_id INTEGER NOT NULL REFERENCES dv_ports(id) ON DELETE CASCADE,
        label TEXT CHECK(label IS NULL OR length(label)<=100),
        version INTEGER NOT NULL DEFAULT 1,
        snapshot TEXT NOT NULL,
        deleted_by INTEGER, delete_reason TEXT NOT NULL DEFAULT 'endpoint_removed',
        created_at TEXT NOT NULL,
        CHECK(source_port_id!=target_port_id))''')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS dc_connection_source ON dc_connections(source_port_id)')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS dc_connection_target ON dc_connections(target_port_id)')
    for event in ('INSERT','UPDATE OF source_port_id,target_port_id'):
        name='dc_connection_insert' if event=='INSERT' else 'dc_connection_update'
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {name} BEFORE {event} ON dc_connections
          WHEN EXISTS(SELECT 1 FROM dc_connections c WHERE c.id!=NEW.id AND
            (c.source_port_id IN (NEW.source_port_id,NEW.target_port_id) OR
             c.target_port_id IN (NEW.source_port_id,NEW.target_port_id)))
          BEGIN SELECT RAISE(ABORT,'Port already connected'); END''')
    # This also records FK cascades caused by a confirmed port/card/device removal.
    conn.execute('''CREATE TRIGGER IF NOT EXISTS dc_connection_deleted AFTER DELETE ON dc_connections BEGIN
        INSERT INTO dc_audit(entity_type,entity_id,actor_id,action,old_value,new_value,created_at)
          VALUES('connection',OLD.id,OLD.deleted_by,OLD.delete_reason,OLD.snapshot,NULL,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
        UPDATE dv_devices SET version=version+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
          WHERE id IN (SELECT device_id FROM dv_ports WHERE id IN (OLD.source_port_id,OLD.target_port_id));
        END''')


def endpoint(conn,port_id,cache):
    row=conn.execute('SELECT device_id FROM dv_ports WHERE id=?',(port_id,)).fetchone()
    if row is None:raise devices.Missing()
    device_id=row['device_id']
    if device_id not in cache:cache[device_id]=devices.detail(conn,device_id)
    device=cache[device_id]
    port=next(port for port in device['ports'] if port['id']==port_id)
    return {**inventory.device_snapshot(device),'portId':port_id,'portName':port['name'],
            'family':port['family'],'speedGbps':port['speedGbps'],'transceiver':port['transceiver'],'effectiveFamily':port['effectiveFamily'],'effectiveSpeedGbps':port['effectiveSpeedGbps'],'portLabel':port['label']}


def connection_detail(conn,row,cache=None):
    cache={} if cache is None else cache
    return {'id':row['id'],'version':row['version'],'label':row['label'],'createdAt':row['created_at'],
            'source':endpoint(conn,row['source_port_id'],cache),'target':endpoint(conn,row['target_port_id'],cache)}


def ports(device_id):
    with devices.connection() as conn:
        device=devices.detail(conn,device_id)
        return {'device':inventory.device_snapshot(device),'items':[
            {key:p[key] for key in ('id','name','family','speedGbps','label','connectionId','transceiver','effectiveFamily','effectiveSpeedGbps')}
            for p in device['ports']]}


def graph(rack_id,device_id=None,limit=20,offset=0):
    with devices.connection() as conn:
        rack=inventory.one(conn,'rack',rack_id)
        if device_id is not None:
            device=inventory.one(conn,'device',device_id)
            if device['rackId']!=rack_id:raise devices.Invalid('Choose a device in the selected rack')
        where='''(c.source_port_id IN (SELECT p.id FROM dv_ports p JOIN dv_devices d ON d.id=p.device_id WHERE d.rack_id=?)
          OR c.target_port_id IN (SELECT p.id FROM dv_ports p JOIN dv_devices d ON d.id=p.device_id WHERE d.rack_id=?))''';args=[rack_id,rack_id]
        if device_id is not None:
            where+=' AND (a.id=? OR b.id=?)';args.extend([device_id,device_id])
        base='''FROM dc_connections c JOIN dv_ports ap ON ap.id=c.source_port_id
          JOIN dv_devices a ON a.id=ap.device_id JOIN dv_ports bp ON bp.id=c.target_port_id
          JOIN dv_devices b ON b.id=bp.device_id WHERE '''+where
        total=conn.execute('SELECT COUNT(*) '+base,args).fetchone()[0]
        cache={}
        links=[connection_detail(conn,row,cache) for row in conn.execute('SELECT c.* '+base+' ORDER BY c.id LIMIT ? OFFSET ?',(*args,limit,offset))]
        rack_ids={rack_id}|{end['rackId'] for link in links for end in (link['source'],link['target']) if end['rackId'] is not None}
        racks=[]
        for id in sorted(rack_ids,key=lambda id:(id!=rack_id,id)):
            entry=rack if id==rack_id else inventory.one(conn,'rack',id)
            entry['devices']=[dict(row) for row in conn.execute(inventory.DEVICE_SQL+' WHERE d.rack_id=? ORDER BY d.rack_position DESC',(id,))]
            racks.append(entry)
        unassigned={end['id']:end for link in links for end in (link['source'],link['target']) if end['rackId'] is None}
        return {'rackId':rack_id,'racks':racks,'unassigned':list(unassigned.values()),'items':links,'total':total,'limit':limit,'offset':offset}


def create(request,actor=None):
    with devices.connection(write=True) as conn:
        return create_in_transaction(conn,request,actor)


def create_in_transaction(conn,request,actor=None):
    cache={};a=endpoint(conn,request.sourcePortId,cache);b=endpoint(conn,request.targetPortId,cache)
    if a['id']==b['id']:raise devices.Invalid('Choose ports on two different devices')
    devices.check_version(cache[a['id']],request.sourceVersion)
    devices.check_version(cache[b['id']],request.targetVersion)
    if conn.execute('SELECT 1 FROM dc_connections WHERE source_port_id IN (?,?) OR target_port_id IN (?,?)',
                    (request.sourcePortId,request.targetPortId)*2).fetchone():
        raise devices.Conflict({'code':'port_connected','message':'One of these ports is already connected. Reload the port lists and choose a free port.'})
    stamp=devices.now()
    id=conn.execute('INSERT INTO dc_connections(source_port_id,target_port_id,label,snapshot,created_at) VALUES(?,?,?,?,?)',
                    (request.sourcePortId,request.targetPortId,request.label,'{}',stamp)).lastrowid
    conn.execute('UPDATE dv_devices SET version=version+1,updated_at=? WHERE id IN (?,?)',(stamp,a['id'],b['id']))
    row=conn.execute('SELECT * FROM dc_connections WHERE id=?',(id,)).fetchone()
    result=connection_detail(conn,row)
    conn.execute('UPDATE dc_connections SET snapshot=? WHERE id=?',(json.dumps(result),id))
    inventory.log(conn,'connection',id,actor,'connect',None,result)
    for device in (a,b):devices.audit(conn,device['id'],actor,'cable_connect',None,result)
    return result


def delete(id,request,actor=None):
    with devices.connection(write=True) as conn:
        return delete_in_transaction(conn,id,request,actor)


def delete_in_transaction(conn,id,request,actor=None):
    row=conn.execute('SELECT * FROM dc_connections WHERE id=?',(id,)).fetchone()
    if row is None:raise devices.Missing()
    devices.check_version(dict(row),request.expectedVersion)
    if not request.confirmDelete:raise devices.Conflict({'code':'confirmation_required','message':'Confirm disconnection of this cable'})
    old=connection_detail(conn,row)
    conn.execute('UPDATE dc_connections SET deleted_by=?,delete_reason=?,snapshot=? WHERE id=?',(actor,'disconnect',json.dumps(old),id))
    conn.execute('DELETE FROM dc_connections WHERE id=?',(id,))
    for device in (old['source'],old['target']):devices.audit(conn,device['id'],actor,'cable_disconnect',old,None)
    return {'deleted':True,'id':id}


def refresh_for_device(conn,device_id,actor=None):
    """Capture current names/locations before a device edit can cascade cables."""
    rows=conn.execute('''SELECT c.* FROM dc_connections c WHERE
        c.source_port_id IN (SELECT id FROM dv_ports WHERE device_id=?) OR
        c.target_port_id IN (SELECT id FROM dv_ports WHERE device_id=?)''',(device_id,device_id)).fetchall()
    cache={}
    for row in rows:
        snapshot=connection_detail(conn,row,cache)
        conn.execute('UPDATE dc_connections SET snapshot=?,deleted_by=? WHERE id=?',(json.dumps(snapshot),actor,row['id']))
