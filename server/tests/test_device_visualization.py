import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import auth
import auth_db
import db
from device_visualization import repository

BASE='/api/device-visualization/devices'


def appliance(kind='switch',vendor=None):
    return {'deviceType':kind,'vendor':vendor,'name':'Core-01','description':'Documented',
            'portGroups':[{'family':'ethernet','count':4,'speedGbps':1},{'family':'sfp','count':2,'speedGbps':10},{'family':'qsfp','count':0,'speedGbps':40}]}


def server():
    return {'deviceType':'server','name':'Compute-01','networkCards':[
        {'id':None,'slotNumber':1,'name':'LAN','family':'ethernet','count':4,'speedGbps':1},
        {'id':None,'slotNumber':2,'name':'Storage','family':'sfp','count':2,'speedGbps':25},
        {'id':None,'slotNumber':3,'name':None,'family':'qsfp','count':1,'speedGbps':100}]}


def create(client,data=None,headers=None):
    response=client.post(BASE,json=data or appliance(),headers=headers)
    assert response.status_code==201,response.text
    return response.json()


def config(device):
    result={key:device[key] for key in ('deviceType','vendor','name','model','description')}
    key='networkCards' if device['deviceType']=='server' else 'portGroups'
    result[key]=[{k:v for k,v in g.items() if k!='id' or key=='networkCards'} for g in device[key]]
    result['expectedVersion']=device['version']
    return result


def assign(client,device,port=None,label='uplink',destination='Core SFP 1'):
    port=port or device['ports'][0]
    response=client.put(f"{BASE}/{device['id']}/ports/{port['id']}",json={'label':label,'leadsTo':destination,'expectedVersion':device['version']})
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.parametrize('kind,vendor',[('switch',None),('firewall','checkpoint'),('firewall','fortigate'),('firewall','generic'),('server',None)])
def test_create_list_and_noop(client,kind,vendor):
    d=create(client,server() if kind=='server' else appliance(kind,vendor))
    assert d['version']==1
    assert d['portCount']==(7 if kind=='server' else 6)
    page=client.get(BASE).json()
    assert page['total']==1 and page['items'][0]['assignedPortCount']==0
    response=client.put(f"{BASE}/{d['id']}",json=config(d))
    assert response.status_code==200,response.text
    assert response.json()==d
    assert client.get(f"{BASE}/{d['id']}/audit").json()['total']==1
    assert client.post(BASE,json={**(server() if kind=='server' else appliance(kind,vendor)),'name':d['name'].lower()}).status_code==400


def test_reconciliation_confirmation_stale_and_history(client):
    d=create(client)
    d=assign(client,d,d['ports'][3],destination='AP-é')
    candidate=config(d);candidate['portGroups'][0]['count']=2
    preview=client.post(f"{BASE}/{d['id']}/update-preview",json=candidate)
    assert preview.status_code==200 and preview.json()['removedAssignedPortCount']==1
    response=client.put(f"{BASE}/{d['id']}",json=candidate)
    assert response.status_code==409 and response.json()['detail']['code']=='confirmation_required'
    d2=assign(client,d,d['ports'][0],label='new',destination='new endpoint')
    assert client.put(f"{BASE}/{d['id']}",json={**candidate,'confirmPortDataRemoval':True}).status_code==409
    candidate['expectedVersion']=d2['version']
    candidate['confirmPortDataRemoval']=True
    result=client.put(f"{BASE}/{d['id']}",json=candidate).json()
    assert result['ports'][0]['id']==d['ports'][0]['id']
    assert result['portCount']==4
    assert client.request("DELETE",f"{BASE}/{d['id']}",json={'expectedVersion':result['version'],'confirmDelete':True}).status_code==200
    assert client.get(f"{BASE}/{d['id']}").status_code==404
    assert client.get(f"{BASE}/{d['id']}/audit").json()['items'][0]['action']=='device_delete'
    conn=db.get_connection()
    assert conn.execute('SELECT COUNT(*) FROM dv_ports').fetchone()[0]==0
    assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    conn.close()


def test_server_middle_card_and_connector_replacement(client):
    d=create(client,server()); d=assign(client,d,d['ports'][4])
    candidate=config(d)
    candidate['networkCards']=[candidate['networkCards'][0],candidate['networkCards'][2]]
    assert client.put(f"{BASE}/{d['id']}",json=candidate).status_code==409
    result=client.put(f"{BASE}/{d['id']}",json={**candidate,'confirmPortDataRemoval':True}).json()
    assert [g['slotNumber'] for g in result['networkCards']]==[1,3]
    assert result['ports'][-1]['id']==d['ports'][-1]['id']
    candidate=config(result)
    candidate['networkCards'].append({'id':None,'slotNumber':2,'name':'replacement','family':'sfp','count':4,'speedGbps':10})
    result=client.put(f"{BASE}/{d['id']}",json=candidate).json()
    assert result['networkCards'][1]['id']!=d['networkCards'][1]['id']
    assert result['assignedPortCount']==0
    result=assign(client,result)
    candidate=config(result);candidate['networkCards'][0].update(family='sfp',speedGbps=25)
    response=client.post(f"{BASE}/{d['id']}/update-preview",json=candidate).json()
    assert response['removedPortCount']==4
    updated=client.put(f"{BASE}/{d['id']}",json={**candidate,'confirmPortDataRemoval':True}).json()
    assert updated['ports'][0]['id']!=result['ports'][0]['id']
    assert updated['assignedPortCount']==0


def test_speed_growth_label_clear_and_parent_scoping(client):
    d=create(client);other=create(client,{**appliance(),'name':'Other'})
    d=assign(client,d,label=' WAN-é ',destination=' endpoint ')
    assert d['ports'][0]['label']=='WAN-é'
    candidate=config(d);candidate['portGroups'][0].update(count=6,speedGbps=10)
    updated=client.put(f"{BASE}/{d['id']}",json=candidate).json()
    assert updated['ports'][0]['leadsTo']=='endpoint'
    assert updated['ports'][0]['id']==d['ports'][0]['id']
    assert updated['ports'][0]['speedGbps']==10
    assert client.put(f"{BASE}/{other['id']}/ports/{d['ports'][0]['id']}",json={'label':None,'leadsTo':None,'expectedVersion':1}).status_code==404
    cleared=assign(client,updated,label='WAN-é',destination='   ')
    assert cleared['ports'][0]['leadsTo'] is None and cleared['ports'][0]['label']=='WAN-é'


def test_audit_failure_rolls_back(client):
    d=create(client);candidate=config(d);candidate['name']='Changed'
    conn=db.get_connection()
    conn.execute("CREATE TRIGGER reject_device_audit BEFORE INSERT ON dv_audit BEGIN SELECT RAISE(ABORT,'audit failure'); END")
    conn.commit();conn.close()
    assert client.put(f"{BASE}/{d['id']}",json=candidate).status_code==400
    assert client.get(f"{BASE}/{d['id']}").json()==d


def test_concurrent_updates_one_success(client):
    d=create(client);candidate=config(d);candidate['name']='Changed'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:client.put(f"{BASE}/{d['id']}",json=candidate).status_code,range(2)))
    assert sorted(responses)==[200,409]


@pytest.mark.parametrize('change',[{'name':' '},{'name':'x'*101},{'vendor':'fortigate'},
    {'portGroups':[]},{'portGroups':[{'family':'ethernet','count':1,'speedGbps':1}]*3},
    {'portGroups':[{'family':'ethernet','count':True,'speedGbps':1},{'family':'sfp','count':0,'speedGbps':10},{'family':'qsfp','count':0,'speedGbps':40}]},
    {'portGroups':[{'family':'ethernet','count':96,'speedGbps':1},{'family':'sfp','count':32,'speedGbps':10},{'family':'qsfp','count':16,'speedGbps':40}]},
    {'portGroups':[{'family':'ethernet','count':0,'speedGbps':1},{'family':'sfp','count':0,'speedGbps':10},{'family':'qsfp','count':0,'speedGbps':40}]},
    {'networkCards':None}])
def test_invalid_configuration(client,change):
    assert client.post(BASE,json={**appliance(),**change}).status_code==422


def test_pagination_search_and_filter(client):
    for name in ['A%','Beta','Zebra']:
        create(client,{**appliance(),'name':name})
    page=client.get(BASE,params={'limit':1,'offset':1}).json()
    assert page['total']==3 and page['items'][0]['name']=='Beta'
    assert client.get(BASE,params={'query':'%'}).json()['total']==1
    assert client.get(BASE,params={'deviceType':'server','vendor':'fortigate'}).status_code==422
    assert client.get(BASE,params={'limit':101}).status_code==422


def test_tenants_permissions_and_actor(client):
    admin=auth_db.create_user('dv-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'dv-admin','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Devices'}).json()['id']
    first=create(client)
    second=create(client,headers={'X-Tenant-ID':tenant})
    assert first['id']==second['id']
    assign(client,first)
    assert client.get(f"{BASE}/{second['id']}",headers={'X-Tenant-ID':tenant}).json()['assignedPortCount']==0
    assert client.get(f"{BASE}/{first['id']}/audit").json()['items'][0]['actorId']==admin['id']
    auth_db.create_role('dv-denied',['ipam.read'])
    auth_db.create_user('dv-reader',auth.hash_password('Password123'),role='dv-denied')
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'dv-reader','password':'Password123'})
    assert client.get(BASE).status_code==403
    assert client.get(BASE,headers={'X-Tenant-ID':tenant}).status_code==403


@pytest.mark.parametrize('family,speed',[('ethernet',1),('ethernet',10),('sfp',10),('sfp',25),('qsfp',40),('qsfp',100)])
def test_every_connector_speed(client,family,speed):
    data=appliance()
    for group in data['portGroups']:
        group['count']=1 if group['family']==family else 0
        if group['family']==family:group['speedGbps']=speed
    d=create(client,data)
    assert len(d['ports'])==1 and d['ports'][0]['speedGbps']==speed
    assert len(d['portGroups'])==3


@pytest.mark.parametrize('change',[
    {'networkCards':[]}, {'networkCards':[{'id':None,'slotNumber':1,'family':'ethernet','count':9,'speedGbps':1}]},
    {'networkCards':[{'id':1,'slotNumber':1,'family':'ethernet','count':2,'speedGbps':1}]},
    {'networkCards':[{'id':None,'slotNumber':1,'family':'ethernet','count':2,'speedGbps':1}]*2},
    {'portGroups':None}, {'vendor':'fortigate'}, {'networkCards':[{'id':None,'slotNumber':17,'family':'ethernet','count':2,'speedGbps':1}]},
])
def test_invalid_server_shapes(client,change):
    assert client.post(BASE,json={**server(),**change}).status_code==422


def test_foreign_card_duplicate_slot_and_immutable_type(client):
    d=create(client,server());other=create(client,{**server(),'name':'Other server'})
    candidate=config(d);candidate['networkCards'][0]['id']=other['networkCards'][0]['id']
    assert client.put(f"{BASE}/{d['id']}",json=candidate).status_code==404
    candidate=config(d);candidate['networkCards'][0]['slotNumber']=4
    assert client.put(f"{BASE}/{d['id']}",json=candidate).status_code==400
    candidate=config(d);candidate['networkCards'][1]['slotNumber']=1
    assert client.put(f"{BASE}/{d['id']}",json=candidate).status_code==422
    changed=appliance('firewall','checkpoint');changed['expectedVersion']=1
    assert client.put(f"{BASE}/{d['id']}",json=changed).status_code==400


def test_database_checks_parent_fk_and_schema_preservation(client):
    import sqlite3
    d=create(client);other=create(client,{**appliance(),'name':'Other'})
    repository.init_db();repository.init_db()
    assert client.get(f"{BASE}/{d['id']}").json()==d
    conn=db.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('UPDATE dv_port_groups SET speed_gbps=25 WHERE id=?',(d['portGroups'][0]['id'],))
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('INSERT INTO dv_ports(device_id,group_id,port_number) VALUES(?,?,?)',(other['id'],d['portGroups'][0]['id'],20))
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('INSERT INTO dv_ports(device_id,group_id,port_number) VALUES(?,?,?)',(d['id'],d['portGroups'][0]['id'],1))
    finally:conn.close()


def test_default_open_mode_csrf_and_required_login(client):
    assert client.get(BASE).status_code==200
    request=client.post(BASE,json=appliance(),headers={'X-CSRF-TOKEN':'wrong'})
    assert request.status_code==403
    auth_db.set_setting('require_login','true')
    assert client.get(BASE).status_code==401


def test_member_permissions_revocation_and_tenant_admin(client):
    admin=auth_db.create_user('dv-platform',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'dv-platform','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Member tenant'}).json()['id']
    auth_db.create_role('dv-access',['device-visualization'])
    member=auth_db.create_user('dv-member',auth.hash_password('Password123'),role='dv-access')
    auth_db.set_tenant_membership(tenant,member['id'],'tenant-admin')
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'dv-member','password':'Password123'})
    headers={'X-Tenant-ID':tenant}
    create(client,headers=headers)
    auth_db.remove_tenant_membership(tenant,member['id'])
    assert client.get(BASE,headers=headers).status_code==403
    assert client.get(BASE).status_code==200


@pytest.mark.parametrize('qsfp_count',[6,8])
def test_switch_48_sfp_with_qsfp_and_limits(client,qsfp_count):
    data=appliance()
    for group in data['portGroups']:
        group['count']=48 if group['family']=='sfp' else qsfp_count if group['family']=='qsfp' else 0
    d=create(client,data)
    assert d['portCount']==48+qsfp_count
    assert len([p for p in d['ports'] if p['family']=='sfp'])==48
    invalid=copy.deepcopy(data);invalid['portGroups'][1]['count']=49
    assert client.post(BASE,json=invalid).status_code==422
    firewall={**data,'deviceType':'firewall','vendor':'fortigate','name':'Firewall'}
    assert client.post(BASE,json=firewall).status_code==422


def test_existing_32_sfp_schema_upgrade_preserves_ids_and_assignments(client):
    import sqlite3
    d=create(client)
    d=assign(client,d,destination='Preserve this endpoint')
    conn=db.get_connection()
    sql=conn.execute("SELECT sql FROM sqlite_master WHERE name='dv_port_groups'").fetchone()[0]
    conn.execute('PRAGMA foreign_keys=OFF')
    conn.execute('BEGIN IMMEDIATE')
    conn.execute(sql.replace('CREATE TABLE dv_port_groups','CREATE TABLE old_groups').replace('port_count<=48','port_count<=32'))
    conn.execute('INSERT INTO old_groups SELECT * FROM dv_port_groups')
    conn.execute('DROP TABLE dv_port_groups')
    conn.execute('ALTER TABLE old_groups RENAME TO dv_port_groups')
    conn.execute("UPDATE sqlite_sequence SET seq=1000 WHERE name='dv_port_groups'")
    conn.commit();conn.close()
    repository.init_db();repository.init_db()
    assert client.get(f"{BASE}/{d['id']}").json()==d
    candidate=config(d);candidate['portGroups'][1]['count']=48
    result=client.put(f"{BASE}/{d['id']}",json=candidate)
    assert result.status_code==200,result.text
    assert result.json()['ports'][0]['leadsTo']=='Preserve this endpoint'
    conn=db.get_connection()
    assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name='dv_port_groups'").fetchone()[0]>=1000
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE dv_port_groups SET port_count=49 WHERE family='sfp'")
    conn.close()


def test_port_vlan_access_trunk_audit_and_legacy_preservation(client):
    d=create(client);port=d['ports'][0];path=f"{BASE}/{d['id']}/ports/{port['id']}"
    request={'label':None,'leadsTo':None,'expectedVersion':1,'portMode':'access','accessVlan':100}
    response=client.put(path,json=request)
    assert response.status_code==200,response.text
    d=response.json();assert d['ports'][0]['accessVlan']==100
    legacy=client.put(path,json={'label':'new','leadsTo':None,'expectedVersion':d['version']}).json()
    assert legacy['ports'][0]['accessVlan']==100
    trunk=client.put(path,json={'label':'new','leadsTo':None,'expectedVersion':legacy['version'],'portMode':'trunk','trunkVlans':'20,10,100-110,10','nativeVlan':10}).json()
    assert trunk['ports'][0]['trunkVlans']=='10,20,100-110'
    assert trunk['ports'][0]['accessVlan'] is None
    assert client.put(path,json=request).status_code==409
    assert client.get(f"{BASE}/{d['id']}/audit").json()['items'][0]['newValue']['port']['portMode']=='trunk'
    candidate=config(trunk);candidate['portGroups'][0]['count']=0
    preview=client.post(f"{BASE}/{d['id']}/update-preview",json=candidate).json()
    assert preview['removedConfiguredPortCount']==1
    assert client.put(f"{BASE}/{d['id']}",json=candidate).status_code==409
    cleared=client.put(path,json={'label':None,'leadsTo':None,'expectedVersion':trunk['version'],'portMode':None}).json()
    assert cleared['ports'][0]['trunkVlans'] is None


@pytest.mark.parametrize('vlan',[
    {'portMode':'access'}, {'portMode':'access','accessVlan':0}, {'portMode':'access','accessVlan':4095},
    {'portMode':'access','accessVlan':True},{'portMode':'access','accessVlan':10,'trunkVlans':'all'},
    {'portMode':'trunk'}, {'portMode':'trunk','trunkVlans':'10abc'}, {'portMode':'trunk','trunkVlans':'20-10'},
    {'portMode':'trunk','trunkVlans':'1-4095'}, {'accessVlan':20},
])
def test_invalid_vlan_configurations(client,vlan):
    d=create(client)
    assert client.put(f"{BASE}/{d['id']}/ports/{d['ports'][0]['id']}",json={'label':None,'leadsTo':None,'expectedVersion':1,**vlan}).status_code==422


def test_vlan_migration_preserves_old_ports_and_database_rejects_mixed_fields(client):
    import sqlite3
    d=assign(client,create(client))
    conn=db.get_connection()
    conn.execute('DROP TRIGGER dv_ports_vlan_insert');conn.execute('DROP TRIGGER dv_ports_vlan_update')
    for column in ('native_vlan','trunk_vlans','access_vlan','port_mode'):
        conn.execute(f'ALTER TABLE dv_ports DROP COLUMN {column}')
    conn.commit();conn.close()
    repository.init_db();repository.init_db()
    assert client.get(f"{BASE}/{d['id']}").json()==d
    conn=db.get_connection()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute('UPDATE dv_ports SET access_vlan=100 WHERE id=?',(d['ports'][0]['id'],))
    conn.close()


@pytest.mark.parametrize('naming,first,last',[
    ('family','Eth 1','SFP 2'),('unit-slot-port','2/3/1','2/3/6'),
    ('unit-zero-port','2/0/1','2/0/6'),('unit-port','2/1','2/6'),('port','1','6')])
def test_switch_port_naming(client,naming,first,last):
    d=create(client,{**appliance(),'portNaming':naming,'portUnit':2,'portSlot':3})
    assert d['ports'][0]['name']==first and d['ports'][-1]['name']==last
    assert len({p['name'] for p in d['ports']})==len(d['ports'])
    d=assign(client,d,destination='Preserved endpoint')
    original_ids=[p['id'] for p in d['ports']]
    candidate=config(d);candidate.update(portNaming='unit-zero-port',portUnit=1,portSlot=1)
    updated=client.put(f"{BASE}/{d['id']}",json=candidate).json()
    assert updated['ports'][0]['name']=='1/0/1'
    assert [p['id'] for p in updated['ports']]==original_ids
    assert updated['ports'][0]['leadsTo']=='Preserved endpoint'
    legacy=config(updated);legacy['description']='legacy edit'
    assert client.put(f"{BASE}/{d['id']}",json=legacy).json()['portNaming']=='unit-zero-port'


def test_naming_migration_and_validation(client):
    d=create(client)
    conn=db.get_connection()
    for column in ('port_naming','port_unit','port_slot'):
        conn.execute(f'ALTER TABLE dv_devices DROP COLUMN {column}')
    conn.commit();conn.close()
    repository.init_db();repository.init_db()
    assert client.get(f"{BASE}/{d['id']}").json()==d
    for extra in [{'portNaming':'unknown'},{'portUnit':0},{'portSlot':17},{'portUnit':True}]:
        assert client.post(BASE,json={**appliance(),**extra}).status_code==422
    assert client.post(BASE,json={**server(),'portNaming':'unit-zero-port'}).status_code==422
