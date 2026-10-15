import json
from concurrent.futures import ThreadPoolExecutor
import auth
import auth_db
import db
import pytest


def host(client,name='router-a',interfaces=None,routes=None,headers=None):
    response=client.put(f'/api/routing/hosts/{name}',json={'interfaces':interfaces or [],'routes':routes or []},headers=headers)
    assert response.status_code==200,response.text
    return response.json()


def interface(name,address,description=None):
    return {'name':name,'ipAddress':address,'description':description}


def importing(client,item,names=None,headers=None):
    return client.post(f"/api/routing/hosts/{item['host']}/ipam-import",json={'expectedUpdatedAt':item['updatedAt'],'interfaces':names},headers=headers)


def subnets():
    conn=db.get_connection()
    try:return [dict(row) for row in conn.execute('SELECT * FROM ipam_subnets ORDER BY cidr')]
    finally:conn.close()


def test_gateway_normalization_deduplication_and_audit(client):
    item=host(client,interfaces=[interface('eth0','192.0.2.129/25','Branch gateway'),interface('eth1','192.0.2.130/25'),interface('eth2','198.51.100.1/24')])
    result=importing(client,item).json()
    assert result['summary']=={'created':2,'skipped':1,'interfaces':3}
    assert [row['cidr'] for row in subnets()]==['192.0.2.128/25','198.51.100.0/24']
    assert result['skipped'][0]['reason']=='duplicate_network'
    assert 'Branch gateway' in subnets()[0]['description']
    conn=db.get_connection()
    rows=conn.execute("SELECT * FROM ipam_audit_log WHERE change_type='subnet_create'").fetchall()
    assert len(rows)==2
    state=json.loads(rows[0]['new_value'])
    assert state['sourceHost']=='router-a'
    assert [entry['name'] for entry in state['sourceInterfaces']]==['eth0','eth1']
    assert rows[0]['user_id'] is None
    assert conn.execute('SELECT COUNT(*) FROM ipam_addresses').fetchone()[0]==0
    conn.close()
    again=importing(client,item)
    assert again.status_code==200
    assert again.json()['summary']=={'created':0,'skipped':3,'interfaces':3}
    assert client.get(f"/api/routing/hosts/{item['host']}").json()==item


@pytest.mark.parametrize('address,cidr',[('203.0.113.77/24','203.0.113.0/24'),('10.0.0.3/31','10.0.0.2/31'),('10.0.0.3/32','10.0.0.3/32'),('10.0.2.127/255.255.255.128','10.0.2.0/25')])
def test_masks_and_point_to_point(client,address,cidr):
    item=host(client,interfaces=[interface('eth0',address)])
    response=importing(client,item,['eth0'])
    assert response.status_code==200,response.text
    assert response.json()['created'][0]['cidr']==cidr


def test_selected_interfaces_existing_metadata_and_hierarchy(client):
    parent=db.create_subnet('10.0.0.0/8',vlan=88,description='Existing parent')
    existing=db.create_subnet('192.0.2.0/24',vlan=100,description='Keep metadata')
    item=host(client,interfaces=[interface('one','10.20.30.1/24'),interface('two','198.51.100.1/24'),interface('three','192.0.2.254/24','Do not overwrite')])
    result=importing(client,item,['one','three']).json()
    assert result['summary']=={'created':1,'skipped':1,'interfaces':2}
    child=next(row for row in subnets() if row['cidr']=='10.20.30.0/24')
    assert child['parent_id']==parent['id']
    assert db.get_subnet(existing['id'])['description']=='Keep metadata'
    assert db.get_subnet(existing['id'])['vlan']==100
    assert not any(row['cidr']=='198.51.100.0/24' for row in subnets())


def test_ipv6_and_missing_masks_are_reported_not_guessed(client):
    item=host(client,interfaces=[interface('v6','2001:db8::1/64'),interface('bare','192.0.2.1'),interface('good','198.51.100.1/24')])
    response=importing(client,item)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['summary']=={'created':1,'skipped':2,'interfaces':3}
    assert all(entry['reason']=='unsupported_address' for entry in result['skipped'])
    assert [row['cidr'] for row in subnets()]==['198.51.100.0/24']


def test_connected_routes_stale_snapshot_and_unknown_interface(client):
    item=host(client,routes=[{'network':'192.0.2.0/24','nextHop':'directly connected','interface':'eth0'}])
    changed=host(client,interfaces=[interface('eth0','198.51.100.254/24')])
    assert importing(client,item).status_code==409
    assert subnets()==[]
    assert importing(client,changed,['missing']).status_code==404
    assert importing(client,changed,[]).status_code==422
    assert subnets()==[]
    derived=host(client,name='connected',routes=[{'network':'192.0.2.0/24','nextHop':'directly connected','interface':'eth0'}])
    assert importing(client,derived).json()['created'][0]['cidr']=='192.0.2.0/24'


def test_audit_failure_rolls_back_entire_import(client):
    item=host(client,interfaces=[interface('eth0','192.0.2.1/24'),interface('eth1','198.51.100.1/24')])
    conn=db.get_connection()
    conn.execute("CREATE TRIGGER reject_routing_import BEFORE INSERT ON ipam_audit_log WHEN NEW.subnet_cidr='198.51.100.0/24' BEGIN SELECT RAISE(ABORT,'audit failure'); END")
    conn.commit();conn.close()
    assert importing(client,item).status_code==503
    assert subnets()==[]
    conn=db.get_connection()
    assert conn.execute('SELECT COUNT(*) FROM ipam_audit_log').fetchone()[0]==0
    conn.close()


def test_concurrent_imports_do_not_duplicate_subnets(client):
    item=host(client,interfaces=[interface('eth0','192.0.2.1/24')])
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses=list(executor.map(lambda _:importing(client,item),range(2)))
    assert [response.status_code for response in responses]==[200,200]
    assert sorted(response.json()['summary']['created'] for response in responses)==[0,1]
    assert len(subnets())==1


def test_tenant_permissions_actor_and_csrf(client):
    admin=auth_db.create_user('platform',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'platform','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Other tenant'}).json()['id']
    headers={'X-Tenant-ID':tenant}
    first=host(client,interfaces=[interface('eth0','192.0.2.1/24')])
    other=host(client,interfaces=[interface('eth0','198.51.100.1/24')],headers=headers)
    assert importing(client,other,headers=headers).status_code==200
    assert subnets()==[]
    assert client.get('/api/ipam/subnets',headers=headers).json()[0]['cidr']=='198.51.100.0/24'
    assert importing(client,first,headers=headers).status_code==409
    assert importing(client,first).status_code==200
    conn=db.get_connection()
    assert conn.execute('SELECT user_id FROM ipam_audit_log').fetchone()[0]==admin['id'];conn.close()
    auth_db.create_role('route-only',['routing-map'])
    user=auth_db.create_user('restricted',auth.hash_password('Password123'),role='route-only')
    client.post('/api/auth/login',json={'username':'restricted','password':'Password123'})
    assert importing(client,first).status_code==403
    auth_db.create_role('ipam-only',['ipam.write'])
    auth_db.set_tenant_membership('default',user['id'],'ipam-only')
    assert importing(client,first).status_code==403
    auth_db.create_role('both',['routing-map','ipam.write'])
    auth_db.set_tenant_membership('default',user['id'],'both')
    assert importing(client,first).status_code==200
    assert importing(client,other,headers=headers).status_code==403
    response=client.post('/api/routing/hosts/router-a/ipam-import',json={'expectedUpdatedAt':first['updatedAt']},headers={'X-CSRF-TOKEN':''})
    assert response.status_code==403
