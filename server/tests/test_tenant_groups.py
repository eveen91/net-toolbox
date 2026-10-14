import auth
import auth_db
import main
import pytest
from tenancy import access

BASE='/api/admin/access-groups'


def signin(client,name):
    assert client.post('/api/auth/login',json={'username':name,'password':'Password123'}).status_code==200


def setup(client):
    admin=auth_db.create_user('platform',auth.hash_password('Password123'),role='admin')
    signin(client,'platform')
    tenant=client.post('/api/tenants',json={'name':'Tenant A'}).json()['id']
    other=client.post('/api/tenants',json={'name':'Tenant B'}).json()['id']
    user=auth_db.create_user('member',auth.hash_password('Password123'))
    auth_db.create_role('reader',['ipam.read'])
    auth_db.create_role('routing',['routing-map'])
    return admin,tenant,other,user


def group(client,name='Network',source='local',dn=None):
    result=client.post(BASE,json={'name':name,'source':source,'groupDn':dn})
    assert result.status_code==201,result.text
    return result.json()['id']


def grant(client,tenant,gid,role='reader'):
    return client.put(f'/api/tenants/{tenant}/group-access/{gid}',json={'role':role})


def test_local_group_union_overrides_live_revocation_and_isolation(client):
    admin,tenant,other,user=setup(client)
    first,second=group(client),group(client,'Routing')
    for gid,role in [(first,'reader'),(second,'routing')]:
        assert client.put(f'{BASE}/{gid}/members/{user["id"]}').status_code==200
        assert grant(client,tenant,gid,role).status_code==200
    signin(client,'member')
    headers={'X-Tenant-ID':tenant}
    assert client.get('/api/ipam/subnets',headers=headers).status_code==200
    assert client.get('/api/routing/hosts',headers=headers).status_code==200
    assert client.post('/api/ipam/subnets',headers=headers,json={'cidr':'192.0.2.0/24'}).status_code==403
    assert client.get('/api/ipam/subnets',headers={'X-Tenant-ID':other}).status_code==403
    info=client.get('/api/auth/session',headers=headers).json()
    assert set(info['user']['permissions'])=={'ipam.read','routing-map'}
    assert tenant in [item['id'] for item in info['tenants']]
    assert other not in [item['id'] for item in info['tenants']]
    auth_db.set_tenant_membership(tenant,user['id'],'reader',admin['id'])
    assert client.get('/api/routing/hosts',headers=headers).status_code==403
    auth_db.remove_tenant_membership(tenant,user['id'],admin['id'])
    assert client.get('/api/routing/hosts',headers=headers).status_code==200
    access.member_change(first,user['id'],admin['id'],remove=True)
    assert client.get('/api/ipam/subnets',headers=headers).status_code==403
    access.delete_group(second,admin['id'])
    assert client.get('/api/routing/hosts',headers=headers).status_code==403
    assert tenant not in [item['id'] for item in client.get('/api/tenants').json()]


def test_group_tenant_admin_cannot_manage_platform_groups_or_grant_initial_access(client):
    admin,tenant,other,user=setup(client)
    gid=group(client)
    client.put(f'{BASE}/{gid}/members/{user["id"]}')
    assert grant(client,tenant,gid,'admin').status_code==400
    assert grant(client,tenant,gid,'tenant-admin').status_code==200
    signin(client,'member')
    assert client.get(f'/api/tenants/{tenant}/members').status_code==200
    assert client.get(f'/api/tenants/{tenant}/group-access').status_code==200
    assert client.get(f'/api/tenants/{other}/group-access').status_code==403
    assert client.get(BASE).status_code==403
    assert grant(client,tenant,gid).status_code==403
    stranger=auth_db.create_user('stranger',auth.hash_password('Password123'))
    assert client.put(f'/api/tenants/{tenant}/members/{stranger["id"]}',json={'role':'reader'}).status_code==403
    assert client.delete(f'/api/tenants/{tenant}/group-access/{gid}').status_code==403


def test_ad_verification_candidate_groups_refresh_and_no_spoofing(client,monkeypatch):
    admin,tenant,other,user=setup(client)
    dn='CN=Network,OU=Groups,DC=example,DC=com'
    gid=group(client,'Directory network','ad',dn)
    assert dn not in access.ad_candidates()
    assert grant(client,tenant,gid).status_code==200
    ad=auth_db.create_user('directory','',auth_source='ad')
    assert client.put(f'{BASE}/{gid}/members/{ad["id"]}').status_code==400
    # An ordinary local account cannot be made into an AD group member.
    with pytest.raises(ValueError):
        access.observe_ad(user['id'],[dn])
    monkeypatch.setattr(auth_db,'get_ad_config',lambda:{'enabled':True,'host':'mock','port':636,'useTls':True,'domainSuffix':'example.com','requiredGroupDn':None,'adminGroupDn':None})
    state={'dns':[dn.upper()]}
    def authenticate(*args,**kwargs):
        assert dn in kwargs['candidate_group_dns']
        return {'isRequiredMember':state.get('required',True),'isAdminMember':False,'matchedGroupDns':state['dns']}
    monkeypatch.setattr(main.ldap_auth,'authenticate_ad_user',authenticate)
    assert client.post('/api/auth/login',json={'username':'directory','password':'Password123','authMethod':'ad'}).status_code==200
    headers={'X-Tenant-ID':tenant}
    assert client.get('/api/ipam/subnets',headers=headers).status_code==200
    assert access.members(gid)['items'][0]['id']==ad['id']
    state['dns']=[]
    assert client.post('/api/auth/login',json={'username':'directory','password':'Password123','authMethod':'ad'}).status_code==200
    assert client.get('/api/ipam/subnets',headers=headers).status_code==403
    assert access.members(gid)['total']==0
    state['dns']=[dn]
    assert client.post('/api/auth/login',json={'username':'directory','password':'Password123','authMethod':'ad'}).status_code==200
    state.update(dns=['CN=Unconfigured'],required=False)
    assert client.post('/api/auth/login',json={'username':'directory','password':'Password123','authMethod':'ad'}).status_code==401
    assert client.get('/api/ipam/subnets',headers=headers).status_code==403
    assert access.members(gid)['total']==0
    state.update(dns=[dn],required=True)
    assert client.post('/api/auth/login',json={'username':'first-directory','password':'Password123','authMethod':'ad'}).status_code==200
    assert client.get('/api/ipam/subnets',headers=headers).status_code==200
    assert client.get('/api/ipam/subnets').status_code==403
    assert [t['id'] for t in client.get('/api/tenants').json()]==[tenant]


def test_atomic_audit_and_role_deletion_guards(client):
    admin,tenant,other,user=setup(client)
    gid=group(client)
    assert grant(client,tenant,gid).status_code==200
    with pytest.raises(ValueError):
        auth_db.delete_role(next(role['id'] for role in auth_db.list_roles() if role['name']=='reader'))
    conn=auth_db.get_connection()
    conn.execute("CREATE TRIGGER fail_group_audit BEFORE INSERT ON tenant_audit BEGIN SELECT RAISE(ABORT,'audit rejected'); END")
    conn.commit();conn.close()
    assert client.delete(f'{BASE}/{gid}').status_code==400
    assert access.groups()['total']==1
    assert access.bindings(tenant)[0]['id']==gid
    assert client.put(f'{BASE}/{gid}/members/{user["id"]}').status_code==400
    assert access.members(gid)['total']==0
    assert grant(client,tenant,gid,'routing').status_code==400
    assert access.bindings(tenant)[0]['role']=='reader'


def test_group_migration_constraints_paging_and_anonymous_denial(client):
    admin,tenant,other,user=setup(client)
    first=group(client,'Group_A')
    group(client,'Group B')
    assert client.post(BASE,json={'name':'group_a','source':'local'}).status_code==400
    assert client.get(BASE,params={'query':'_'}).json()['total']==1
    assert client.get(BASE,params={'limit':1,'offset':1}).json()['total']==2
    assert grant(client,tenant,first).status_code==200
    auth_db.init_auth_db()
    assert access.groups()['total']==2
    assert access.bindings(tenant)[0]['role']=='reader'
    assert auth_db.tenant_role('default',user['id'])=='user'
    client.post('/api/auth/logout')
    assert client.get(BASE).status_code==401
    assert client.post(BASE,json={'name':'forbidden','source':'local'}).status_code==401
    assert grant(client,tenant,first).status_code==401
