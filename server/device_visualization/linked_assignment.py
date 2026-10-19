"""Atomically pair ports, with a state-bound review before replacing assignments."""
import hashlib
import json
from . import repository as repo
from dc_inventory import connections
from dc_inventory.schemas import ConnectionCreate,ResourceDelete


def describe(device,port):
    return {'deviceId':device['id'],'deviceName':device['name'],'version':device['version'],
            'port':port,'rackName':device['rackName'],'dataCenterName':device['dataCenterName']}


def destination(device,port):
    return f"{device['name']} / {port['name']}"


def assign(conn,source,port,request,actor):
    row=conn.execute('SELECT device_id FROM dv_ports WHERE id=?',(request.targetPortId,)).fetchone()
    if row is None:raise repo.Missing()
    if row['device_id']==source['id']:raise repo.Invalid('Choose a port on another device')
    target=repo.detail(conn,row['device_id'])
    repo.check_version(target,request.targetVersion)
    target_port=next(p for p in target['ports'] if p['id']==request.targetPortId)
    ids=(port['id'],target_port['id'])
    rows=conn.execute('SELECT * FROM dc_connections WHERE source_port_id IN (?,?) OR target_port_id IN (?,?)',ids*2).fetchall()
    same=next((row for row in rows if {row['source_port_id'],row['target_port_id']}==set(ids)),None)
    old_links=[connections.connection_detail(conn,row) for row in rows if same is None or row['id']!=same['id']]
    cache={source['id']:source,target['id']:target}
    affected={port['id']:describe(source,port),target_port['id']:describe(target,target_port)}
    for link in old_links:
        for end in (link['source'],link['target']):
            if end['id'] not in cache:cache[end['id']]=repo.detail(conn,end['id'])
            device=cache[end['id']]
            affected[end['portId']]=describe(device,next(p for p in device['ports'] if p['id']==end['portId']))
    forward,reverse=destination(target,target_port),destination(source,port)
    review={'source':describe(source,port),'target':describe(target,target_port),'ports':list(affected.values()),
            'connections':old_links,'proposedSourceDestination':forward,'proposedTargetDestination':reverse}
    state={**review,'request':request.model_dump(exclude={'replacementToken'})}
    token=hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    occupied=old_links or (port['leadsTo'] and port['leadsTo']!=forward) or (target_port['leadsTo'] and target_port['leadsTo']!=reverse)
    if occupied and request.replacementToken!=token:
        raise repo.Conflict({'code':'connection_change_required','message':'Review the current assignments before replacing this connection.',
                             'token':token,**review})
    # Delete old pairs and clear only reciprocal notes that still match those pairs.
    # Independently edited notes on displaced peers are retained and shown in the review.
    for link in old_links:
        connections.delete_in_transaction(conn,link['id'],ResourceDelete(expectedVersion=link['version'],confirmDelete=True),actor)
        for end,other in ((link['source'],link['target']),(link['target'],link['source'])):
            if end['portId'] in ids:continue
            before=affected[end['portId']]
            generated=f"{other['name']} / {other['portName']}"
            if before['port']['leadsTo']==generated:
                conn.execute('UPDATE dv_ports SET leads_to=NULL WHERE id=?',(end['portId'],))
                repo.audit(conn,end['id'],actor,'port_update',before,{'deviceName':end['name'],'port':{**before['port'],'leadsTo':None,'connectionId':None}})
    source=repo.detail(conn,source['id']);port=next(p for p in source['ports'] if p['id']==port['id'])
    repo.write_port_assignment(conn,source,port,request.model_copy(update={'leadsTo':forward}),actor)
    if target_port['leadsTo']!=reverse:
        conn.execute('UPDATE dv_ports SET leads_to=? WHERE id=?',(reverse,target_port['id']))
        conn.execute('UPDATE dv_devices SET version=version+1,updated_at=? WHERE id=?',(repo.now(),target['id']))
        repo.audit(conn,target['id'],actor,'port_update',describe(target,target_port),
                   {'deviceName':target['name'],'port':{**target_port,'leadsTo':reverse}})
    if same is None:
        a=repo.detail(conn,source['id']);b=repo.detail(conn,target['id'])
        connections.create_in_transaction(conn,ConnectionCreate(sourcePortId=port['id'],targetPortId=target_port['id'],
            sourceVersion=a['version'],targetVersion=b['version']),actor)
    return repo.detail(conn,source['id'])
