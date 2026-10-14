import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
import auth
import auth_db
import db

BASE = '/api/dhcp-generator/configurations'
FIXTURES = Path(__file__).parent / 'fixtures' / 'dhcp_generator'


def configuration(name='fw-example'):
    data = json.loads((FIXTURES / 'mvp.json').read_text())
    data['firewall'] = name
    return data


def create(client, name='fw-example', headers=None):
    response = client.post(BASE, json={'configuration': configuration(name)}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def publish(client, item, description='Initial release', headers=None):
    return client.post(f"{BASE}/{item['id']}/versions", json={'expectedRevision': item['revision'], 'description': description}, headers=headers)


def test_preview_publish_download_diff_restore(client):
    item = create(client)
    preview = client.post(f"{BASE}/{item['id']}/preview", json={'expectedRevision': 1})
    assert preview.status_code == 200, preview.text
    assert preview.json()['report']['gaia_compatibility'] == 'unverified'
    assert 'range 192.0.2.10 192.0.2.120;' in preview.json()['content']
    first = publish(client, item).json()
    assert first['number'] == 1
    artifact = client.get(f"{BASE}/{item['id']}/versions/{first['id']}/artifact")
    assert artifact.status_code == 200
    assert artifact.headers['content-disposition'].endswith('.conf"')
    assert artifact.content.startswith(b'# Published version:')
    changed = item['configuration']
    changed['subnets'][0]['pools'][0]['end'] = '192.0.2.130'
    saved = client.put(f"{BASE}/{item['id']}", json={'expectedRevision': 1, 'configuration': changed}).json()
    second = publish(client, saved, 'Expand pool').json()
    diff = client.get(f"{BASE}/{item['id']}/diff", params={'before': first['id'], 'after': second['id']})
    assert diff.status_code == 200 and '+  range 192.0.2.10 192.0.2.130;' in diff.json()['text']
    restored = client.post(f"{BASE}/{item['id']}/restore", json={'expectedRevision': saved['revision'], 'versionId': first['id']})
    assert restored.status_code == 200
    assert restored.json()['revision'] == 3
    assert restored.json()['configuration']['subnets'][0]['pools'][0]['end'] == '192.0.2.120'
    assert client.get(f"{BASE}/{item['id']}/versions/{first['id']}/artifact").content == artifact.content
    assert client.get(f"{BASE}/{item['id']}/audit").json()['total'] == 5


def test_validation_and_stale_write_preserve_history(client):
    item = create(client)
    first = publish(client, item)
    assert first.status_code == 201
    assert publish(client, item).status_code == 409
    bad = configuration()
    bad['subnets'][0]['reservations'][0]['ip'] = '192.0.2.11'
    assert client.put(f"{BASE}/{item['id']}", json={'expectedRevision': 1, 'configuration': bad}).status_code == 422
    stale = client.put(f"{BASE}/{item['id']}", json={'expectedRevision': 42, 'configuration': configuration()})
    assert stale.status_code == 409
    conn = db.get_connection()
    with pytest.raises(Exception):
        conn.execute("UPDATE dhcp_versions SET description='overwritten'")
    conn.rollback()
    with pytest.raises(Exception):
        conn.execute('DELETE FROM dhcp_versions')
    conn.close()
    assert client.get(f"{BASE}/{item['id']}/versions").json()['total'] == 1


def test_draft_can_be_incomplete_but_publication_requires_pool(client):
    data = configuration()
    data['subnets'][0]['pools'] = []
    item = client.post(BASE, json={'configuration': data})
    assert item.status_code == 201
    assert publish(client, item.json()).status_code == 422
    assert client.get(f"{BASE}/{item.json()['id']}/versions").json()['total'] == 0


def test_concurrent_draft_edits_and_publication(client):
    item = create(client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: publish(client, item).status_code, range(2)))
    assert sorted(results) == [201, 409]
    edits = [configuration(), configuration()]
    edits[0]['domain'] = 'a.example.org'
    edits[1]['domain'] = 'b.example.org'
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda data: client.put(f"{BASE}/{item['id']}", json={'expectedRevision': 1, 'configuration': data}).status_code, edits))
    assert sorted(results) == [200, 409]


def test_tenant_permissions_and_parent_scoping(client):
    user = auth_db.create_user('dhcp-admin', auth.hash_password('Password123'), role='admin')
    assert client.post('/api/auth/login', json={'username': 'dhcp-admin', 'password': 'Password123'}).status_code == 200
    tenant_id = client.post('/api/tenants', json={'name': 'DHCP tenant'}).json()['id']
    headers = {'X-Tenant-ID': tenant_id}
    first = create(client)
    other = create(client, headers=headers)
    version = publish(client, first).json()
    assert client.get(f"{BASE}/{other['id']}/versions/{version['id']}", headers=headers).status_code == 404
    sibling = create(client, name='fw-other')
    assert client.get(f"{BASE}/{sibling['id']}/versions/{version['id']}").status_code == 404
    assert client.post(f"{BASE}/{sibling['id']}/restore", json={'expectedRevision': 1, 'versionId': version['id']}).status_code == 404
    assert client.get(f"{BASE}/{first['id']}/audit").json()['items'][0]['actorId'] == user['id']
    auth_db.create_role('no-dhcp', ['ipam.read'])
    auth_db.create_user('no-dhcp', auth.hash_password('Password123'), role='no-dhcp')
    client.post('/api/auth/logout')
    client.post('/api/auth/login', json={'username': 'no-dhcp', 'password': 'Password123'})
    assert client.get(BASE).status_code == 403
    assert client.get(f"{BASE}/{first['id']}/versions/{version['id']}/artifact").status_code == 403


def test_publish_audit_rollback(client):
    item = create(client)
    conn = db.get_connection()
    conn.execute("CREATE TRIGGER reject_dhcp_audit BEFORE INSERT ON dhcp_audit BEGIN SELECT RAISE(ABORT,'audit failure'); END")
    conn.commit()
    conn.close()
    assert publish(client, item).status_code == 400
    assert client.get(f"{BASE}/{item['id']}/versions").json()['total'] == 0


@pytest.mark.parametrize('profile', ['R81.10', 'R82.10'])
def test_ported_engine_matches_source_golden(profile):
    from dhcp_generator.vendor.generator import render_mvp
    data = configuration()
    data['profile'] = profile
    assert render_mvp(data) == (FIXTURES / f'mvp-{profile}.conf').read_bytes()


def test_parser_failure_blocks_publication_and_keeps_draft(client, monkeypatch):
    from dhcp_generator import service
    item = create(client)
    def failed_check(*args, **kwargs):
        return b'example', {'syntax_status': 'syntax_error', 'data_validated': True}
    monkeypatch.setattr(service, 'prepare_artifact', failed_check)
    response = publish(client, item)
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'syntax_error'
    assert client.get(f"{BASE}/{item['id']}/versions").json()['total'] == 0
    assert client.get(f"{BASE}/{item['id']}").json()['revision'] == 1


def test_strict_schema_noop_and_literal_search(client):
    item = create(client, 'fw_underscore')
    create(client, 'fw-other')
    assert client.get(BASE, params={'query': '_'}).json()['total'] == 1
    first_page = client.get(BASE, params={'limit': 1, 'offset': 0}).json()
    second_page = client.get(BASE, params={'limit': 1, 'offset': 1}).json()
    assert first_page['total'] == second_page['total'] == 2
    assert first_page['items'][0]['id'] != second_page['items'][0]['id']
    current = client.put(f"{BASE}/{item['id']}", json={'expectedRevision': 1, 'configuration': item['configuration']})
    assert current.status_code == 200 and current.json()['revision'] == 1
    assert client.get(f"{BASE}/{item['id']}/audit").json()['total'] == 1
    invalid = configuration('fw-extra')
    invalid['parser_path'] = '/bin/sh'
    assert client.post(BASE, json={'configuration': invalid}).status_code == 422
    assert client.post(BASE, json={'configuration': configuration('fw-other')}).status_code == 400
    assert client.get(BASE).json()['total'] == 2
