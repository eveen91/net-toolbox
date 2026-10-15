import sqlite3
from concurrent.futures import ThreadPoolExecutor
import auth
import auth_db
import db
import pytest
from dc_inventory import repository as inventory
from device_visualization import repository as devices

ROOT='/api/dc-inventory'
DV='/api/device-visualization/devices'


def dc(client,name='DC Warsaw',headers=None):
    response=client.post(ROOT+'/datacenters',json={'name':name},headers=headers)
    assert response.status_code==201,response.text
    return response.json()


def rack(client,center=None,name='Rack A',height=42,headers=None):
    center=center or dc(client,headers=headers)
    response=client.post(ROOT+'/racks',json={'dataCenterId':center['id'],'name':name,'heightU':height},headers=headers)
    assert response.status_code==201,response.text
    return response.json()


def device(client,name='Switch A',headers=None,**location):
    response=client.post(DV,json={'deviceType':'switch','name':name,'portGroups':[{'family':family,'count':2 if family=='ethernet' else 0,'speedGbps':speed} for family,speed in [('ethernet',1),('sfp',10),('qsfp',40)]],**location},headers=headers)
    assert response.status_code==201,response.text
    return response.json()


def place(client,item,**values):
    return client.put(f"{ROOT}/devices/{item['id']}/placement",json={'expectedVersion':item['version'],**values})


def resource_update(client,kind,item,**changes):
    payload={'name':item['name'],'description':item['description'],'expectedVersion':item['version']}
    if kind=='racks':payload['heightU']=item['heightU']
    return client.put(f"{ROOT}/{kind}/{item['id']}",json={**payload,**changes})


def test_locations_crud_versions_pagination_and_safe_delete(client):
    center=dc(client);cabinet=rack(client,center)
    assert client.get(ROOT+'/datacenters').json()['items'][0]['rackCount']==1
    assert resource_update(client,'datacenters',center).json()['version']==1
    renamed=resource_update(client,'datacenters',center,name='DC North').json()
    assert renamed['version']==2
    assert resource_update(client,'datacenters',center,name='Stale').status_code==409
    assert client.post(ROOT+'/datacenters',json={'name':'dc north'}).status_code==400
    assert client.post(ROOT+'/racks',json={'name':'rack a','dataCenterId':center['id'],'heightU':42}).status_code==400
    assert client.get(ROOT+'/racks',params={'dataCenterId':center['id'],'limit':1,'offset':0}).json()['total']==1
    assert client.request('DELETE',f"{ROOT}/datacenters/{center['id']}",json={'expectedVersion':2,'confirmDelete':True}).status_code==409
    assert client.request('DELETE',f"{ROOT}/racks/{cabinet['id']}",json={'expectedVersion':1}).status_code==409
    assert client.request('DELETE',f"{ROOT}/racks/{cabinet['id']}",json={'expectedVersion':1,'confirmDelete':True}).status_code==200
    assert client.request('DELETE',f"{ROOT}/datacenters/{center['id']}",json={'expectedVersion':2,'confirmDelete':True}).status_code==200
    assert client.get(ROOT+'/audit').json()['total']==5


def test_placement_device_form_roundtrip_catalog_and_history(client):
    cabinet=rack(client,height=12)
    d=device(client,heightU=2,rackId=cabinet['id'],rackPosition=3)
    assert d['dataCenterName']=='DC Warsaw' and d['rackName']=='Rack A' and d['rackPosition']==3
    detail=client.get(f"{ROOT}/racks/{cabinet['id']}").json()
    assert detail['usedU']==2 and detail['devices'][0]['id']==d['id']
    assert client.get(ROOT+'/devices',params={'unassigned':True}).json()['total']==0
    assert client.get('/api/device-visualization/inventory/datacenters').json()['total']==1
    assert client.get('/api/device-visualization/inventory/racks',params={'dataCenterId':cabinet['dataCenterId']}).json()['items'][0]['heightU']==12
    same=place(client,d,rackId=cabinet['id'],rackPosition=3,heightU=2)
    assert same.status_code==200 and same.json()['version']==d['version']
    moved=place(client,d,rackId=cabinet['id'],rackPosition=9,heightU=3).json()
    assert moved['version']==d['version']+1
    latest=client.get(f"{DV}/{d['id']}").json()
    assert latest['ports']==d['ports'] and latest['heightU']==3
    assert client.get(f"{DV}/{d['id']}/audit").json()['items'][0]['action']=='device_location_update'
    assert client.get(ROOT+'/audit').json()['items'][0]['action']=='placement'
    assert place(client,d,rackId=None).status_code==409
    cleared=place(client,latest,rackId=None).json()
    assert cleared['rackId'] is None and cleared['rackPosition'] is None and cleared['heightU']==3
    assert client.get(ROOT+'/devices',params={'unassigned':True}).json()['total']==1
    assert client.get(f"{ROOT}/racks/{cabinet['id']}").json()['usedU']==0


def test_unassigned_legacy_unknown_height_and_paging(client):
    device(client,name='First');device(client,name='Percent%');device(client,name='Third',heightU=2)
    page=client.get(ROOT+'/devices',params={'unassigned':True,'limit':1,'offset':1}).json()
    assert page['total']==3 and page['items'][0]['name']=='Percent%'
    assert page['items'][0]['heightU'] is None
    assert client.get(ROOT+'/devices',params={'query':'%'}).json()['total']==1
    assert client.get(ROOT+'/devices',params={'limit':101}).status_code==422


@pytest.mark.parametrize('start,height,status',[(2,2,409),(4,1,409),(5,1,200),(10,2,400),(None,1,400),(1,None,400),(0,1,422),(1,0,422),(True,1,422)])
def test_range_overlap_and_bounds(client,start,height,status):
    cabinet=rack(client,height=10)
    device(client,rackId=cabinet['id'],rackPosition=2,heightU=3)
    other=device(client,name='Other')
    response=place(client,other,rackId=cabinet['id'],rackPosition=start,heightU=height)
    assert response.status_code==status,response.text
    if status!=200:assert client.get(f"{DV}/{other['id']}").json()['version']==1


def test_device_create_and_edit_share_collision_rules_atomicity(client):
    cabinet=rack(client,height=10);a=device(client,rackId=cabinet['id'],rackPosition=1,heightU=2)
    data={'deviceType':'switch','name':'Collision','heightU':2,'rackId':cabinet['id'],'rackPosition':2,'portGroups':[{'family':f,'count':2 if f=='ethernet' else 0,'speedGbps':s} for f,s in [('ethernet',1),('sfp',10),('qsfp',40)]]}
    assert client.post(DV,json=data).status_code==409
    assert client.get(DV).json()['total']==1
    b=device(client,name='Other',heightU=1)
    config={**data,'name':'Other','expectedVersion':b['version']}
    assert client.post(f"{DV}/{b['id']}/update-preview",json=config).status_code==409
    assert client.put(f"{DV}/{b['id']}",json=config).status_code==409
    assert client.get(f"{DV}/{b['id']}").json()==b
    config.update(rackPosition=5)
    updated=client.put(f"{DV}/{b['id']}",json=config)
    assert updated.status_code==200,updated.text
    assert client.get(ROOT+'/audit').json()['items'][0]['newValue']['rackPosition']==5
    assert client.request('DELETE',f"{DV}/{b['id']}",json={'expectedVersion':updated.json()['version'],'confirmDelete':True}).status_code==200
    assert client.get(f"{ROOT}/racks/{cabinet['id']}").json()['usedU']==2
    with devices.connection() as conn:assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_shrink_and_delete_occupied_rack_rejected(client):
    cabinet=rack(client,height=12);d=device(client,rackId=cabinet['id'],rackPosition=10,heightU=3)
    response=resource_update(client,'racks',cabinet,heightU=11)
    assert response.status_code==409
    assert client.get(f"{ROOT}/racks/{cabinet['id']}").json()['heightU']==12
    assert client.request('DELETE',f"{ROOT}/racks/{cabinet['id']}",json={'expectedVersion':1,'confirmDelete':True}).status_code==409
    assert resource_update(client,'racks',cabinet,heightU=20).json()['heightU']==20
    with pytest.raises(devices.Invalid):
        with devices.connection(write=True) as conn:conn.execute('UPDATE dc_racks SET height_u=5 WHERE id=?',(cabinet['id'],))


def test_concurrent_placement_has_one_winner(client):
    cabinet=rack(client,height=10);a=device(client);b=device(client,name='Other')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda item:place(client,item,rackId=cabinet['id'],rackPosition=3,heightU=2).status_code,[a,b]))
    assert sorted(results)==[200,409]
    assert client.get(f"{ROOT}/racks/{cabinet['id']}").json()['usedU']==2


def test_audit_failure_rolls_back_assignment_and_device_version(client,monkeypatch):
    cabinet=rack(client);d=device(client)
    def fail(*args,**kwargs):raise sqlite3.OperationalError('audit unavailable')
    monkeypatch.setattr(inventory,'log',fail)
    assert place(client,d,rackId=cabinet['id'],rackPosition=1,heightU=1).status_code==503
    assert client.get(f"{DV}/{d['id']}").json()==d
    assert client.get(f"{DV}/{d['id']}/audit").json()['total']==1


def test_inventory_permissions_and_tenant_namespace(client):
    admin=auth_db.create_user('inventory-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'inventory-admin','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Other tenant'}).json()['id'];headers={'X-Tenant-ID':tenant}
    cabinet=rack(client);d=device(client)
    assert client.get(ROOT+'/datacenters',headers=headers).json()['total']==0
    other=dc(client,headers=headers);foreign=rack(client,other,headers=headers);foreign2=rack(client,other,name='Foreign rack 2',headers=headers)
    assert place(client,d,rackId=foreign2['id'],rackPosition=1,heightU=1).status_code==404
    for role,permissions in [('dv-only',['device-visualization']),('inventory-only',['dc-inventory']),('denied',['ipam.read'])]:
        auth_db.create_role(role,permissions);auth_db.create_user(role,auth.hash_password('Password123'),role=role)
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'dv-only','password':'Password123'})
    assert client.get(ROOT+'/racks').status_code==403
    assert client.get('/api/device-visualization/inventory/racks').status_code==200
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'inventory-only','password':'Password123'})
    assert client.get(DV).status_code==403
    result=place(client,d,rackId=cabinet['id'],rackPosition=2,heightU=1)
    assert result.status_code==200 and 'ports' not in result.json()
    assert client.get(ROOT+'/racks',headers=headers).status_code==403
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'denied','password':'Password123'})
    assert client.get(ROOT+'/devices').status_code==403
    assert place(client,d,rackId=cabinet['id'],rackPosition=1,heightU=1).status_code==403


def test_inventory_schema_upgrade_preserves_existing_devices_and_ports(client):
    d=device(client)
    with devices.connection(write=True) as conn:
        conn.execute('DROP TRIGGER dc_rack_capacity')
        conn.execute('DROP TRIGGER dv_device_placement_insert');conn.execute('DROP TRIGGER dv_device_placement_update')
        conn.execute('DROP INDEX idx_dv_devices_rack')
        for column in ('rack_id','rack_position','height_u'):conn.execute(f'ALTER TABLE dv_devices DROP COLUMN {column}')
        for table in ('dc_racks','dc_datacenters','dc_audit'):conn.execute(f'DROP TABLE {table}')
    devices.init_db();devices.init_db()
    assert client.get(f"{DV}/{d['id']}").json()==d
    assert client.get(ROOT+'/devices',params={'unassigned':True}).json()['total']==1
    with devices.connection() as conn:assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_cable_panel_shares_rack_capacity_and_fixed_height(client):
    cabinet=rack(client,height=3)
    data={'name':'Cable management','rackId':cabinet['id'],'rackPosition':2}
    response=client.post(ROOT+'/cable-panels',json=data)
    assert response.status_code==201,response.text
    panel=response.json()
    assert panel['heightU']==1 and panel['deviceType']=='cable-management'
    detail=client.get(f"{DV}/{panel['id']}").json()
    assert detail['ports']==[] and detail['portGroups']==[] and not detail['managementPort']
    assert client.get(f"{ROOT}/racks/{cabinet['id']}").json()['usedU']==1
    assert client.post(ROOT+'/cable-panels',json={**data,'name':'Second panel'}).status_code==409
    assert client.post(ROOT+'/cable-panels',json={**data,'name':'Outside panel','rackPosition':4}).status_code==400
    assert place(client,panel,heightU=2).status_code==400
    assert client.put(f"{DV}/{panel['id']}",json={'deviceType':'cable-management','name':'Cable','heightU':2,'expectedVersion':panel['version'],'portGroups':[]}).status_code==422
    moved=place(client,panel,rackPosition=3)
    assert moved.status_code==200
    assert moved.json()['rackPosition']==3 and moved.json()['heightU']==1
    active=device(client)
    assert place(client,active,rackId=cabinet['id'],rackPosition=3,heightU=1).status_code==409
    devices.init_db();devices.init_db()
    assert client.get(f"{DV}/{panel['id']}").json()['ports']==[]


def test_inventory_only_can_add_panel_without_network_device_permission(client):
    cabinet=rack(client)
    auth_db.create_role('panel-editor',['dc-inventory'])
    auth_db.create_user('panel-editor',auth.hash_password('Password123'),role='panel-editor')
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'panel-editor','password':'Password123'})
    assert client.get(DV).status_code==403
    data={'name':'Cable panel','rackId':cabinet['id'],'rackPosition':1}
    response=client.post(ROOT+'/cable-panels',json=data)
    assert response.status_code==201 and 'ports' not in response.json()
    assert client.post(ROOT+'/cable-panels',json={**data,'deviceType':'switch'}).status_code==422
    auth_db.create_role('no-inventory',['device-visualization'])
    auth_db.create_user('no-inventory',auth.hash_password('Password123'),role='no-inventory')
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'no-inventory','password':'Password123'})
    assert client.post(ROOT+'/cable-panels',json=data).status_code==403


def test_cable_panel_upgrade_preserves_occupied_racks_and_ports(client):
    import re
    cabinet=rack(client,height=12)
    original=device(client,rackId=cabinet['id'],rackPosition=3,heightU=2)
    history=client.get(f"{DV}/{original['id']}/audit").json()
    conn=db.get_connection()
    try:
        conn.execute('PRAGMA foreign_keys=OFF');conn.execute('PRAGMA legacy_alter_table=ON');conn.execute('BEGIN IMMEDIATE')
        sql=conn.execute("SELECT sql FROM sqlite_master WHERE name='dv_devices'").fetchone()[0]
        objects=[row[0] for row in conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='dv_devices' AND type IN ('index','trigger') AND sql IS NOT NULL")]
        sql=re.sub(r",\s*'cable-management'",'',sql)
        conn.execute(sql.replace('dv_devices','dv_devices_previous',1))
        conn.execute('INSERT INTO dv_devices_previous SELECT * FROM dv_devices')
        conn.execute('DROP TABLE dv_devices');conn.execute('ALTER TABLE dv_devices_previous RENAME TO dv_devices')
        for statement in objects:conn.execute(statement)
        conn.commit()
    finally:conn.close()
    devices.init_db();devices.init_db()
    assert client.get(f"{DV}/{original['id']}").json()==original
    assert client.get(f"{DV}/{original['id']}/audit").json()==history
    assert client.get(f"{ROOT}/racks/{cabinet['id']}").json()['usedU']==2
    result=client.post(ROOT+'/cable-panels',json={'name':'New panel','rackId':cabinet['id'],'rackPosition':5})
    assert result.status_code==201,result.text
    with devices.connection() as conn:assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
