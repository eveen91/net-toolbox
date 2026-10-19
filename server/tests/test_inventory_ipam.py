from concurrent.futures import ThreadPoolExecutor
import pytest
import auth
import auth_db
import db
from inventory_ipam import repository
from tests.test_dc_inventory import device,dc,rack,place
from tests.test_device_visualization import BASE


def subnet(client,cidr='10.20.0.0/16'):
    response=client.post('/api/ipam/subnets',json={'cidr':cidr})
    assert response.status_code==200,response.text
    return response.json()


def address_port(client,item,address='10.20.3.7/24',headers=None):
    response=client.put(f"{BASE}/{item['id']}/ports/{item['ports'][0]['id']}",json={
        'expectedVersion':item['version'],'ipAddress':address,'label':None,'leadsTo':None},headers=headers)
    assert response.status_code==200,response.text
    return response.json()


def sync(client,item,headers=None):
    return client.post(f"{BASE}/{item['id']}/ports/{item['ports'][0]['id']}/ipam-placement",json={'expectedVersion':item['version']},headers=headers)


def test_best_subnet_idempotence_location_move_and_ip_change(client):
    parent=subnet(client);child=subnet(client,'10.20.3.0/24')
    cabinet=rack(client,dc(client));item=address_port(client,device(client,rackId=cabinet['id'],rackPosition=9,heightU=2))
    result=sync(client,item)
    assert result.status_code==200,result.text
    result=result.json()
    assert result['status']=='created' and result['subnetId']==child['id'] and result['ip']=='10.20.3.7'
    assert sync(client,item).json()['status']=='existing'
    page=client.get(f"/api/ipam/subnets/{child['id']}/addresses").json()
    assert page['total']==1 and page['addresses'][0]['hostname']==item['name'] and page['addresses'][0]['machineType']=='physical'
    links=client.get('/api/ipam/inventory-links',params={'address':'10.20.3.7'}).json()
    assert links['total']==1 and links['items'][0]['rackPosition']==9 and links['items'][0]['rackId']==cabinet['id']
    moved=place(client,item,rackId=None,rackPosition=None,heightU=2).json()
    assert client.get('/api/ipam/inventory-links',params={'address':'10.20.3.7'}).json()['items'][0]['rackId'] is None
    fresh=client.get(f"{BASE}/{item['id']}").json()
    fresh=address_port(client,fresh,'10.20.3.8')
    assert client.get('/api/ipam/inventory-links',params={'address':'10.20.3.7'}).json()['total']==0
    assert sync(client,fresh).json()['status']=='created'
    assert sync(client,item).status_code==409


@pytest.mark.parametrize('ip,expected',[('192.0.2.4/24','no_subnet'),('2001:db8::1/64','unsupported'),(None,'no_address')])
def test_missing_network_and_unsupported_addresses_preserve_device(client,ip,expected):
    item=address_port(client,device(client),ip)
    assert sync(client,item).json()['status']==expected
    assert client.get(f"{BASE}/{item['id']}").json()==item
    with repository.devices.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM ipam_addresses').fetchone()[0]==0


def test_conflicts_and_parent_reservations_do_not_get_overwritten(client):
    parent=subnet(client);child=subnet(client,'10.20.3.0/24')
    db.add_address(child['id'],'10.20.3.7','reserved',hostname='Reserved owner',locked=True)
    item=address_port(client,device(client))
    assert sync(client,item).json()['status']=='conflict'
    with repository.devices.connection() as conn:
        row=conn.execute('SELECT * FROM ipam_addresses WHERE address=?',('10.20.3.7',)).fetchone()
        assert row['status']=='reserved' and row['hostname']=='Reserved owner' and row['locked']
    # Parent pools are authoritative even if the most specific subnet is a child.
    db.add_dhcp_pool(parent['id'],'10.20.3.100','10.20.3.110')
    item=address_port(client,item,'10.20.3.105')
    assert sync(client,item).json()['status']=='conflict'
    item=address_port(client,item,'10.20.3.0')
    assert sync(client,item).json()['status']=='conflict'


def test_atomic_audit_failure_and_concurrent_duplicate_registration(client,monkeypatch):
    subnet(client);item=address_port(client,device(client))
    original=repository.devices.audit
    def failed(*args,**kwargs):raise RuntimeError('Audit unavailable')
    monkeypatch.setattr(repository.devices,'audit',failed)
    with pytest.raises(RuntimeError):repository.place_port(item['id'],item['ports'][0]['id'],item['version'])
    with repository.devices.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM ipam_addresses').fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM ipam_audit_log WHERE change_type='create'").fetchone()[0]==0
    monkeypatch.setattr(repository.devices,'audit',original)
    def attempt(_):return repository.place_port(item['id'],item['ports'][0]['id'],item['version'])['status']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,range(2)))==['created','existing']


def test_permissions_and_current_tenant_boundaries(client):
    subnet(client);item=address_port(client,device(client))
    auth_db.create_role('inventory-no-ipam',['device-visualization','dc-inventory'])
    auth_db.create_user('inventory-user',auth.hash_password('Password123'),role='inventory-no-ipam')
    client.post('/api/auth/login',json={'username':'inventory-user','password':'Password123'})
    assert sync(client,item).status_code==403
    assert client.get('/api/ipam/inventory-links',params={'address':'10.20.3.7'}).status_code==403
    client.post('/api/auth/logout')
    auth_db.create_role('ipam-no-inventory',['ipam.read','ipam.write'])
    auth_db.create_user('ipam-user',auth.hash_password('Password123'),role='ipam-no-inventory')
    client.post('/api/auth/login',json={'username':'ipam-user','password':'Password123'})
    assert sync(client,item).status_code==403
    assert client.get('/api/ipam/inventory-links',params={'address':'10.20.3.7'}).status_code==403
    client.post('/api/auth/logout')
    auth_db.create_user('inventory-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'inventory-admin','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Other inventory'}).json()['id']
    headers={'X-Tenant-ID':tenant}
    other=address_port(client,device(client,headers=headers),headers=headers)
    assert sync(client,other,headers=headers).json()['status']=='no_subnet'
    assert client.get('/api/ipam/inventory-links',params={'address':'10.20.3.7'},headers=headers).json()['total']==1
    assert client.get('/api/ipam/inventory-links',params={'address':'not-an-ip'}).status_code==422


def test_existing_used_metadata_shared_ip_and_port_parent_scoping(client):
    network=subnet(client)
    db.add_address(network['id'],'10.20.3.7','used',hostname='Existing hostname',description='Keep me',locked=True)
    first=address_port(client,device(client,'Shared IP A'))
    second=address_port(client,device(client,'Shared IP B'))
    assert sync(client,first).json()['status']=='existing'
    assert sync(client,second).json()['status']=='existing'
    with repository.devices.connection() as conn:
        row=conn.execute('SELECT * FROM ipam_addresses WHERE address=?',('10.20.3.7',)).fetchone()
        assert row['hostname']=='Existing hostname' and row['description']=='Keep me' and row['locked']
    response=client.get('/api/ipam/inventory-links',params={'address':'10.20.3.7','limit':1})
    assert response.json()['total']==2 and len(response.json()['items'])==1
    wrong=client.post(f"{BASE}/{first['id']}/ports/{second['ports'][0]['id']}/ipam-placement",json={'expectedVersion':first['version']})
    assert wrong.status_code==404


def test_free_address_claim_preserves_metadata_and_locked_addresses(client):
    network=subnet(client)
    db.add_address(network['id'],'10.20.3.7','free',description='Existing description')
    item=address_port(client,device(client))
    assert sync(client,item).json()['status']=='existing'
    with repository.devices.connection() as conn:
        row=conn.execute('SELECT * FROM ipam_addresses WHERE address=?',('10.20.3.7',)).fetchone()
        assert row['status']=='used' and row['hostname']==item['name'] and row['description']=='Existing description'
    db.add_address(network['id'],'10.20.3.8','free',locked=True)
    item=address_port(client,item,'10.20.3.8')
    assert sync(client,item).json()['status']=='conflict'
