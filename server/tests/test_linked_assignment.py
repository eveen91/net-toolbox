from concurrent.futures import ThreadPoolExecutor
import pytest
from device_visualization import repository as repo
from device_visualization.schemas import PortAssignment
from dc_inventory import repository as inventory
from tests.test_dc_inventory import device,DV,ROOT,rack


def get(client,d):return client.get(f"{DV}/{d['id']}").json()


def payload(client,a,b,source=0,target=0,**changes):
    a=get(client,a);b=get(client,b)
    return {'expectedVersion':a['version'],'label':a['ports'][source]['label'],'leadsTo':a['ports'][source]['leadsTo'],
            'targetPortId':b['ports'][target]['id'],'targetVersion':b['version'],**changes}


def write(client,a,data,source=0):
    return client.put(f"{DV}/{a['id']}/ports/{a['ports'][source]['id']}",json=data)


def pair(client,a,b):
    response=write(client,a,payload(client,a,b))
    assert response.status_code==200,response.text
    return response.json()


def test_free_port_sets_both_destinations_and_physical_cable_preserving_target_settings(client):
    cabinet=rack(client);a=device(client,'Switch A',rackId=cabinet['id'],rackPosition=1,heightU=1);b=device(client,'Server B')
    b=client.put(f"{DV}/{b['id']}/ports/{b['ports'][0]['id']}",json={'label':'Production','leadsTo':None,'ipAddress':'192.0.2.2/24','portMode':'access','accessVlan':20,'expectedVersion':b['version']}).json()
    original=b['ports'][0].copy()
    result=write(client,a,payload(client,a,b,label='Uplink',ipAddress='192.0.2.1/24'))
    assert result.status_code==200,result.text
    a=result.json();b=get(client,b)
    assert a['ports'][0]['leadsTo']=='Server B / Eth 1'
    assert b['ports'][0]['leadsTo']=='Switch A / Eth 1'
    assert a['ports'][0]['connectionId']==b['ports'][0]['connectionId'] is not None
    for key in ('label','ipAddress','portMode','accessVlan','trunkVlans','nativeVlan'):assert b['ports'][0][key]==original[key]
    graph=client.get(f"{ROOT}/racks/{cabinet['id']}/connections").json()
    assert graph['total']==1


def test_occupied_text_requires_review_with_configuration_and_no_changes_before_confirmation(client):
    a=device(client,'A');b=device(client,'B')
    b=client.put(f"{DV}/{b['id']}/ports/{b['ports'][0]['id']}",json={'label':'WAN','leadsTo':'ISP handoff','ipAddress':'198.51.100.1/30','portMode':'trunk','trunkVlans':'10,20','nativeVlan':10,'expectedVersion':b['version']}).json()
    data=payload(client,a,b);before=get(client,a)
    response=write(client,a,data)
    assert response.status_code==409
    review=response.json()['detail'];assert review['code']=='connection_change_required'
    assert review['target']['port']['leadsTo']=='ISP handoff'
    assert review['target']['port']['ipAddress']=='198.51.100.1/30'
    assert review['target']['port']['nativeVlan']==10
    assert get(client,a)==before and get(client,b)==b
    assert write(client,a,{**data,'replacementToken':review['token']}).status_code==200
    assert get(client,b)['ports'][0]['leadsTo']=='A / Eth 1'
    assert get(client,b)['ports'][0]['trunkVlans']=='10,20'


def test_rewire_two_existing_pairs_frees_old_peers_and_preserves_custom_notes(client):
    a,b,c,d=[device(client,name) for name in ('A','B','C','D')]
    pair(client,a,b);pair(client,c,d)
    b=get(client,b)
    # A custom note must not be erased just because its physical cable is displaced.
    client.put(f"{DV}/{b['id']}/ports/{b['ports'][0]['id']}",json={'expectedVersion':b['version'],'label':None,'leadsTo':'Keep custom rack note'})
    data=payload(client,a,d);review=write(client,a,data).json()['detail']
    assert len(review['connections'])==2 and len(review['ports'])==4
    assert write(client,a,{**data,'replacementToken':review['token']}).status_code==200
    aa,bb,cc,dd=[get(client,x) for x in (a,b,c,d)]
    assert aa['ports'][0]['leadsTo']=='D / Eth 1' and dd['ports'][0]['leadsTo']=='A / Eth 1'
    assert bb['ports'][0]['connectionId'] is None and cc['ports'][0]['connectionId'] is None
    assert bb['ports'][0]['leadsTo']=='Keep custom rack note' and cc['ports'][0]['leadsTo'] is None
    with repo.connection() as conn:assert conn.execute('SELECT COUNT(*) FROM dc_connections').fetchone()[0]==1


def test_review_token_detects_changed_peer_and_changed_draft(client):
    a,b,c=[device(client,name) for name in ('A','B','C')]
    pair(client,a,b);data=payload(client,a,c)
    first=write(client,a,data).json()['detail']
    b=get(client,b)
    client.put(f"{DV}/{b['id']}/ports/{b['ports'][0]['id']}",json={'expectedVersion':b['version'],'label':'Changed after review','leadsTo':b['ports'][0]['leadsTo']})
    second=write(client,a,{**data,'replacementToken':first['token']}).json()['detail']
    assert second['code']=='connection_change_required' and second['token']!=first['token']
    assert any(p['port']['label']=='Changed after review' for p in second['ports'])
    third=write(client,a,{**data,'replacementToken':second['token'],'label':'New source label'}).json()['detail']
    assert third['code']=='connection_change_required' and third['token']!=second['token']
    assert get(client,a)['ports'][0]['leadsTo']=='B / Eth 1'


def test_same_pair_is_noop_and_manual_entry_remains_compatible(client):
    a=device(client,'A');b=device(client,'B');pair(client,a,b)
    before=get(client,a);history=client.get(ROOT+'/audit').json()
    assert write(client,a,payload(client,a,b)).json()==before
    assert client.get(ROOT+'/audit').json()==history
    manual=write(client,a,{'expectedVersion':before['version'],'label':None,'leadsTo':'Manual destination'})
    assert manual.status_code==200 and manual.json()['ports'][0]['leadsTo']=='Manual destination'
    assert manual.json()['ports'][0]['connectionId']==before['ports'][0]['connectionId']


def test_rewire_failure_rolls_back_notes_cables_versions_and_audits(client,monkeypatch):
    a,b,c=[device(client,name) for name in ('A','B','C')];pair(client,a,b)
    data=payload(client,a,c);review=write(client,a,data).json()['detail']
    before=[get(client,x) for x in (a,b,c)];history=client.get(ROOT+'/audit').json()
    original=inventory.log
    def fail(conn,kind,id,actor,action,*args):
        if action=='connect':raise RuntimeError('Audit unavailable')
        return original(conn,kind,id,actor,action,*args)
    monkeypatch.setattr(inventory,'log',fail)
    with pytest.raises(RuntimeError):write(client,a,{**data,'replacementToken':review['token']})
    assert [get(client,x) for x in (a,b,c)]==before
    assert client.get(ROOT+'/audit').json()==history


def test_port_parent_validation_versions_and_concurrent_claim(client):
    a,b,c=[device(client,name) for name in ('A','B','C')]
    data=payload(client,a,b)
    assert client.put(f"{DV}/{c['id']}/ports/{a['ports'][0]['id']}",json=data).status_code==404
    assert write(client,a,{**data,'targetPortId':9999999}).status_code==404
    assert write(client,a,{**data,'targetPortId':a['ports'][1]['id']}).status_code==400
    assert write(client,a,{**data,'targetVersion':999}).status_code==409
    assert write(client,a,{key:value for key,value in data.items() if key!='targetVersion'}).status_code==422
    requests=[(x,PortAssignment(**payload(client,x,b))) for x in (a,c)]
    def claim(entry):
        source,request=entry
        try:return repo.update_port(source['id'],source['ports'][0]['id'],request)['id']
        except repo.Conflict:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,requests))
    assert sum(result is not None for result in results)==1
    b=get(client,b);assert b['ports'][0]['leadsTo'] in ('A / Eth 1','C / Eth 1')
    loser=a if b['ports'][0]['leadsTo'].startswith('C') else c
    assert get(client,loser)['ports'][0]['leadsTo'] is None


def test_linked_assignment_uses_dv_permission_and_active_tenant(client):
    import auth,auth_db
    auth_db.create_user('link-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'link-admin','password':'Password123'})
    a=device(client,'A');b=device(client,'B');data=payload(client,a,b)
    other=client.post('/api/tenants',json={'name':'Other tenant'}).json()['id']
    assert client.put(f"{DV}/{a['id']}/ports/{a['ports'][0]['id']}",json=data,headers={'X-Tenant-ID':other}).status_code==404
    for name,perms in [('link-dv',['device-visualization']),('link-inventory',['dc-inventory'])]:
        auth_db.create_role(name,perms);auth_db.create_user(name,auth.hash_password('Password123'),role=name)
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'link-dv','password':'Password123'})
    assert write(client,a,data).status_code==200
    assert client.get(ROOT+'/racks').status_code==403
    client.post('/api/auth/logout');client.post('/api/auth/login',json={'username':'link-inventory','password':'Password123'})
    assert write(client,a,data).status_code==403
