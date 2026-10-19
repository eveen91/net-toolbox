"""Physical cabling must remain consistent across inventory and device edits."""
from concurrent.futures import ThreadPoolExecutor
import pytest
import auth
import auth_db
from device_visualization import repository as devices
from dc_inventory import connections
from dc_inventory.schemas import ConnectionCreate
from tests.test_dc_inventory import ROOT,DV,dc,rack,device,place


def current(client,item):return client.get(f"{DV}/{item['id']}").json()


def connect(client,a,b,source=0,target=0,**changes):
    a=current(client,a);b=current(client,b)
    return client.post(ROOT+'/connections',json={'sourcePortId':a['ports'][source]['id'],'targetPortId':b['ports'][target]['id'],
        'sourceVersion':a['version'],'targetVersion':b['version'],**changes})


def test_graph_local_remote_unassigned_and_move_preserves_connection(client):
    center=dc(client);r1=rack(client,center);r2=rack(client,center,name='Rack B')
    a=device(client,'Switch A',rackId=r1['id'],rackPosition=1,heightU=1)
    b=device(client,'Switch B',rackId=r1['id'],rackPosition=3,heightU=2)
    c=device(client,'Switch C',rackId=r2['id'],rackPosition=5,heightU=1)
    loose=device(client,'Unassigned')
    local=connect(client,a,b,label='Local copper');assert local.status_code==201,local.text
    remote=connect(client,a,c,source=1);assert remote.status_code==201,remote.text
    unassigned=connect(client,b,loose,source=1);assert unassigned.status_code==201
    graph=client.get(f"{ROOT}/racks/{r1['id']}/connections").json()
    assert graph['total']==3 and len(graph['items'])==3
    assert [r['id'] for r in graph['racks']]==[r1['id'],r2['id']]
    assert graph['unassigned'][0]['id']==loose['id']
    assert graph['items'][0]['source']['portName']=='Eth 1'
    assert client.get(f"{ROOT}/racks/{r1['id']}/connections",params={'deviceId':a['id'],'limit':1,'offset':1}).json()['total']==2
    assert client.get(f"{ROOT}/racks/{r1['id']}/connections",params={'deviceId':c['id']}).status_code==400
    assert client.get(f"{ROOT}/devices/{a['id']}/ports").json()['items'][0]['connectionId']==local.json()['id']
    c=current(client,c)
    assert place(client,c,rackId=r1['id'],rackPosition=8).status_code==200
    graph=client.get(f"{ROOT}/racks/{r1['id']}/connections").json()
    assert len(graph['racks'])==1 and graph['items'][1]['target']['rackPosition']==8
    a=current(client,a)
    assert a['ports'][0]['leadsTo'] is None # Free-text documentation is never rewritten.
    records=client.get(ROOT+'/audit').json()['items']
    assert sum(e['action']=='connect' for e in records)==3


def test_single_port_occupancy_reverse_pairs_versions_and_self_links(client):
    a=device(client,'A');b=device(client,'B');c=device(client,'C')
    first=connect(client,a,b);assert first.status_code==201
    assert connect(client,b,a).json()['detail']['code']=='port_connected'
    assert connect(client,c,a).status_code==409
    assert connect(client,a,a,source=0,target=1).status_code==400
    assert connect(client,a,c,source=1,sourceVersion=a['version']).json()['detail']['code']=='stale_version'
    assert connect(client,a,c,source=1,targetPortId=9999999).status_code==404
    assert current(client,a)['version']==a['version']+1
    # Database protection works regardless of which endpoint column contains the port.
    with pytest.raises(devices.Invalid):
        with devices.connection(write=True) as conn:
            conn.execute('INSERT INTO dc_connections(source_port_id,target_port_id,snapshot,created_at) VALUES(?,?,?,?)',
                         (c['ports'][0]['id'],a['ports'][0]['id'],'{}',devices.now()))


def test_disconnect_confirmation_audit_and_versioning(client):
    a=device(client,'A');b=device(client,'B');link=connect(client,a,b).json()
    url=f"{ROOT}/connections/{link['id']}"
    assert client.request('DELETE',url,json={'expectedVersion':1}).status_code==409
    assert client.request('DELETE',url,json={'expectedVersion':2,'confirmDelete':True}).status_code==409
    assert client.request('DELETE',url,json={'expectedVersion':1,'confirmDelete':True}).status_code==200
    assert all(p['connectionId'] is None for p in current(client,a)['ports'])
    assert current(client,a)['version']==a['version']+2
    assert current(client,b)['version']==b['version']+2
    history=client.get(ROOT+'/audit').json()['items']
    assert history[0]['action']=='disconnect' and history[0]['oldValue']['id']==link['id']
    assert connect(client,b,a).status_code==201


def test_removing_connected_port_requires_preview_and_cleans_both_ends(client):
    r=rack(client);a=device(client,'A',rackId=r['id'],rackPosition=1,heightU=1);b=device(client,'B')
    link=connect(client,a,b,source=1).json();a=current(client,a)
    payload={'deviceType':'switch','name':a['name'],'expectedVersion':a['version'],
             'portGroups':[{'family':f,'count':1 if f=='ethernet' else 0,'speedGbps':s} for f,s in [('ethernet',1),('sfp',10),('qsfp',40)]]}
    preview=client.post(f"{DV}/{a['id']}/update-preview",json=payload).json()
    assert preview['removedConfiguredPortCount']==1
    assert preview['removedPorts'][0]['connectionId']==link['id']
    assert client.put(f"{DV}/{a['id']}",json=payload).status_code==409
    assert client.put(f"{DV}/{a['id']}",json={**payload,'confirmPortDataRemoval':True}).status_code==200
    assert current(client,b)['ports'][0]['connectionId'] is None
    assert current(client,b)['version']==b['version']+2
    assert client.get(f"{ROOT}/racks/{r['id']}/connections").json()['total']==0
    assert client.get(ROOT+'/audit').json()['items'][0]['action']=='endpoint_removed'
    with devices.connection() as conn:assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_device_delete_cascades_cables_but_keeps_history(client):
    a=device(client,'A');b=device(client,'B');link=connect(client,a,b).json();a=current(client,a)
    assert client.request('DELETE',f"{DV}/{a['id']}",json={'expectedVersion':a['version'],'confirmDelete':True}).status_code==200
    assert current(client,b)['ports'][0]['connectionId'] is None
    assert any(e['entityType']=='connection' and e['entityId']==link['id'] and e['action']=='endpoint_removed' for e in client.get(ROOT+'/audit').json()['items'])


def test_connection_audit_failure_rolls_back_and_concurrent_port_claim_has_one_winner(client,monkeypatch):
    from dc_inventory import repository as inventory
    a=device(client,'A');b=device(client,'B');c=device(client,'C')
    real=inventory.log
    def fail(*args,**kwargs):raise RuntimeError('audit failed')
    monkeypatch.setattr(inventory,'log',fail)
    req=ConnectionCreate(sourcePortId=a['ports'][0]['id'],targetPortId=b['ports'][0]['id'],sourceVersion=a['version'],targetVersion=b['version'])
    with pytest.raises(RuntimeError):connections.create(req)
    assert current(client,a)['version']==a['version'] and current(client,a)['ports'][0]['connectionId'] is None
    monkeypatch.setattr(inventory,'log',real)
    def claim(target):
        req=ConnectionCreate(sourcePortId=a['ports'][0]['id'],targetPortId=target['ports'][0]['id'],sourceVersion=a['version'],targetVersion=target['version'])
        try:return connections.create(req)['id']
        except devices.Conflict:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,[b,c]))
    assert sum(result is not None for result in results)==1


def test_connection_permissions_and_tenant_isolation(client):
    auth_db.create_user('cabling-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'cabling-admin','password':'Password123'})
    r=rack(client);a=device(client,'A',rackId=r['id'],rackPosition=1,heightU=1);b=device(client,'B');link=connect(client,a,b).json()
    tenant=client.post('/api/tenants',json={'name':'Isolated'}).json()['id'];headers={'X-Tenant-ID':tenant}
    assert client.get(f"{ROOT}/devices/{a['id']}/ports",headers=headers).status_code==404
    assert client.get(f"{ROOT}/racks/{r['id']}/connections",headers=headers).status_code==404
    assert client.request('DELETE',f"{ROOT}/connections/{link['id']}",json={'expectedVersion':1,'confirmDelete':True},headers=headers).status_code==404
    for role,permissions in [('inventory-user',['dc-inventory']),('dv-user',['device-visualization'])]:
        auth_db.create_role(role,permissions);auth_db.create_user(role,auth.hash_password('Password123'),role=role)
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'inventory-user','password':'Password123'})
    assert client.get(f"{ROOT}/devices/{a['id']}/ports").status_code==200
    assert client.get(DV).status_code==403
    pa=client.get(f"{ROOT}/devices/{a['id']}/ports").json();pb=client.get(f"{ROOT}/devices/{b['id']}/ports").json()
    payload={'sourcePortId':pa['items'][1]['id'],'targetPortId':pb['items'][1]['id'],'sourceVersion':pa['device']['version'],'targetVersion':pb['device']['version']}
    assert client.post(ROOT+'/connections',json=payload).status_code==201
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'dv-user','password':'Password123'})
    assert client.get(f"{ROOT}/devices/{a['id']}/ports").status_code==403
    assert client.get(f"{ROOT}/racks/{r['id']}/connections").status_code==403
    assert client.post(ROOT+'/connections',json=payload).status_code==403
    assert client.request('DELETE',f"{ROOT}/connections/{link['id']}",json={'expectedVersion':1,'confirmDelete':True}).status_code==403


def test_controller_port_names_and_cross_data_center_graph(client):
    first=rack(client);second=rack(client,dc(client,name='Remote DC'),name='Remote rack')
    a=device(client,'Core',rackId=first['id'],rackPosition=2,heightU=1)
    storage=client.post(DV,json={'name':'Array','deviceType':'storage','heightU':2,'rackId':second['id'],'rackPosition':4,
        'managementPort':True,'networkCards':[{'controller':c,'slotNumber':1,'family':'sfp','speedGbps':10,'count':2} for c in ('A','B')]}).json()
    port=next(p for p in storage['ports'] if p['controller']=='B' and p['isManagement'])
    response=connect(client,a,storage,targetPortId=port['id'])
    assert response.status_code==201,response.text
    assert response.json()['target']['portName']=='Controller B / MGMT'
    graph=client.get(f"{ROOT}/racks/{first['id']}/connections").json()
    assert graph['racks'][1]['dataCenterName']=='Remote DC'
    assert graph['items'][0]['target']['portId']==port['id']
    devices.init_db();devices.init_db()
    assert client.get(f"{ROOT}/racks/{first['id']}/connections").json()==graph


def test_disconnect_failure_rolls_back_cable_versions_and_history(client,monkeypatch):
    a=device(client,'A');b=device(client,'B');link=connect(client,a,b).json();before=current(client,a)
    history=client.get(ROOT+'/audit').json()
    def fail(*args,**kwargs):raise RuntimeError('device audit unavailable')
    monkeypatch.setattr(devices,'audit',fail)
    from dc_inventory.schemas import ResourceDelete
    with pytest.raises(RuntimeError):connections.delete(link['id'],ResourceDelete(expectedVersion=1,confirmDelete=True))
    assert current(client,a)==before
    assert client.get(ROOT+'/audit').json()==history
