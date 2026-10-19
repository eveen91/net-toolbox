import re
import db
from device_visualization import repository
from tests.test_device_visualization import BASE, create, config, storage, appliance


def shelf(name='Shelf-01', **extra):
    return {'deviceType':'storage-shelf','name':name,'heightU':2,'driveBayCount':24,'occupiedBays':[1,4,24],**extra}


def expansion(device, number=1):
    return next(p for p in device['ports'] if p['family']=='sas' and p['number']==number)


def pair(client, a, b, source_number=1):
    response=client.put(f"{BASE}/{a['id']}/ports/{expansion(a,source_number)['id']}",json={
        'expectedVersion':a['version'],'targetPortId':expansion(b)['id'],
        'targetVersion':b['version'],'label':None,'leadsTo':None})
    assert response.status_code==200,response.text
    return response.json()


def test_chain_bays_identity_history_and_stale_writes(client):
    head=create(client,{**storage(),'driveBayCount':12,'occupiedBays':[2,3],'expansionPortCount':2})
    first=create(client,shelf());second=create(client,shelf('Shelf-02'))
    assert first['expansionPortCount']==2 and first['portCount']==2
    assert [p['name'] for p in first['ports']]==['Expansion 1','Expansion 2']
    assert first['portGroups']==[] and first['networkCards'] is None
    head=pair(client,head,first)
    first=client.get(f"{BASE}/{first['id']}").json()
    assert expansion(first)['leadsTo']=='Array-01 / Expansion 1'
    first=pair(client,first,second,2)
    assert all(p['connectionId'] for p in first['ports'])
    candidate={**config(first),'driveBayCount':36,'occupiedBays':[1,4,24,36]}
    response=client.put(f"{BASE}/{first['id']}",json=candidate)
    assert response.status_code==200,response.text
    updated=response.json()
    assert updated['occupiedBays']==[1,4,24,36] and updated['driveBayCount']==36
    assert [p['id'] for p in updated['ports']]==[p['id'] for p in first['ports']]
    assert client.get(f"{BASE}/{first['id']}").json()==updated
    change=next(e for e in client.get(f"{BASE}/{first['id']}/audit").json()['items'] if e['action']=='device_update')
    assert change['oldValue']['occupiedBays']==[1,4,24]
    assert change['newValue']['occupiedBays']==[1,4,24,36]
    assert client.put(f"{BASE}/{first['id']}",json=candidate).status_code==409
    assert client.put(f"{BASE}/{updated['id']}",json=config(updated)).json()==updated
    assert client.put(f"{BASE}/{head['id']}",json=config(head)).json()==head


def test_validation_and_shrink_preserve_occupied_disks(client):
    for patch in ({'occupiedBays':[True]},{'occupiedBays':[1,1]},{'occupiedBays':[25]},
                  {'occupiedBays':['2']},{'driveBayCount':121},{'expansionPortCount':3},{'managementPort':True}):
        assert client.post(BASE,json=shelf(**patch)).status_code==422
    d=create(client,shelf())
    before=client.get(f"{BASE}/{d['id']}/audit").json()['total']
    candidate={**config(d),'driveBayCount':12}
    assert client.post(f"{BASE}/{d['id']}/update-preview",json=candidate).status_code==400
    assert client.put(f"{BASE}/{d['id']}",json=candidate).status_code==400
    assert client.get(f"{BASE}/{d['id']}").json()==d
    assert client.get(f"{BASE}/{d['id']}/audit").json()['total']==before
    response=client.put(f"{BASE}/{d['id']}",json={**candidate,'occupiedBays':[1,4]})
    assert response.status_code==200 and response.json()['driveBayCount']==12
    assert client.post(BASE,json={**appliance(),'driveBayCount':4}).status_code==422


def test_removal_review_and_incompatible_port_rollback(client):
    head=create(client,{**storage(),'expansionPortCount':2})
    enclosure=create(client,shelf());network=create(client,appliance())
    source=expansion(enclosure)
    request={'expectedVersion':enclosure['version'],'label':None,'leadsTo':None}
    bad=client.put(f"{BASE}/{enclosure['id']}/ports/{source['id']}",json={**request,
        'targetPortId':network['ports'][0]['id'],'targetVersion':network['version']})
    assert bad.status_code==400
    assert client.get(f"{BASE}/{enclosure['id']}").json()==enclosure
    assert client.put(f"{BASE}/{enclosure['id']}/ports/{source['id']}",json={**request,'ipAddress':'192.0.2.1'}).status_code==400
    head=pair(client,head,enclosure)
    candidate={**config(head),'expansionPortCount':0}
    review=client.post(f"{BASE}/{head['id']}/update-preview",json=candidate).json()
    assert review['removedConfiguredPortCount']==1
    assert client.put(f"{BASE}/{head['id']}",json=candidate).status_code==409
    result=client.put(f"{BASE}/{head['id']}",json={**candidate,'confirmPortDataRemoval':True})
    assert result.status_code==200 and result.json()['expansionPortCount']==0
    assert client.get(f"{BASE}/{enclosure['id']}").json()['ports'][0]['connectionId'] is None


def test_legacy_group_migration_preserves_rows_and_is_idempotent(client):
    d=create(client,appliance())
    peer=create(client,{**appliance(),'name':'Migration peer'})
    response=client.post('/api/dc-inventory/connections',json={'sourcePortId':d['ports'][0]['id'],'targetPortId':peer['ports'][0]['id'],'sourceVersion':d['version'],'targetVersion':peer['version']})
    assert response.status_code==201,response.text
    d=client.get(f"{BASE}/{d['id']}").json()
    history=client.get(f"{BASE}/{d['id']}/audit").json()
    conn=db.get_connection();conn.execute('PRAGMA foreign_keys=OFF');conn.execute('BEGIN IMMEDIATE')
    sql=conn.execute("SELECT sql FROM sqlite_master WHERE name='dv_port_groups'").fetchone()[0]
    sql=sql.replace(",'sas'",'').replace(" OR (family='sas' AND port_count<=16)",'').replace(" OR (family='sas' AND speed_gbps=12)",'')
    sql=re.sub(r'CREATE TABLE(?: IF NOT EXISTS)?\s+"?dv_port_groups"?', 'CREATE TABLE legacy_groups',sql,count=1)
    conn.execute(sql);conn.execute('INSERT INTO legacy_groups SELECT * FROM dv_port_groups')
    conn.execute('DROP TABLE dv_port_groups');conn.execute('ALTER TABLE legacy_groups RENAME TO dv_port_groups')
    conn.commit();conn.close()
    repository.init_db();repository.init_db()
    assert client.get(f"{BASE}/{d['id']}").json()==d
    assert client.get(f"{BASE}/{d['id']}/audit").json()==history
    assert create(client,shelf())['portCount']==2
    with repository.connection() as conn:
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
