"""Deterministic scale regressions: bounded queries/pages, not machine speed."""
import ipaddress

import pytest

import db


@pytest.mark.parametrize("subnet_count", [10, 100, 1000])
def test_aggregate_queries_remain_constant_with_large_inventory(client, monkeypatch, subnet_count):
    conn = db.get_connection()
    now = db._now()
    conn.executemany("INSERT INTO ipam_subnets (id, cidr, updated_at) VALUES (?, ?, ?)",
                     [(i + 1, f"{ipaddress.IPv4Address(int(ipaddress.IPv4Address('10.0.0.0')) + i * 256)}/24", now) for i in range(subnet_count)])
    conn.executemany("INSERT INTO ipam_addresses (subnet_id, address, status, updated_at) VALUES (?, ?, ?, ?)",
                     [(i + 1, str(ipaddress.IPv4Address(int(ipaddress.IPv4Address('10.0.0.0')) + i * 256 + n)), 'used' if n <= 50 else 'reserved', now) for i in range(subnet_count) for n in range(1, 101)])
    conn.commit()
    conn.close()
    queries = []
    connect = db.get_connection

    def traced_connection():
        conn = connect()
        conn.set_trace_callback(lambda sql: queries.append(sql) if sql.lstrip().upper().startswith(('SELECT', 'WITH')) else None)
        return conn

    monkeypatch.setattr(db, 'get_connection', traced_connection)
    summaries = db.list_subnets()
    assert len(summaries) == subnet_count
    assert len(queries) == 1
    assert all(row['usedCount'] == 50 and row['reservedCount'] == 50 for row in summaries)
    queries.clear()
    dashboard = db.get_ipam_dashboard()
    assert len(dashboard) == subnet_count
    assert len(queries) == 1
    assert sum(row['recordedCount'] for row in dashboard) == subnet_count * 100
    queries.clear()
    page = db.list_subnet_addresses(1, limit=20, offset=80)
    assert page['total'] == 100
    assert len(page['addresses']) == 20
    assert page['addresses'][0]['address'] == '10.0.0.81'
    assert len(queries) <= 3


def test_large_address_inventory_returns_only_requested_window(client):
    subnet = db.create_subnet('172.16.0.0/16')
    conn = db.get_connection()
    base = int(ipaddress.IPv4Address('172.16.0.0'))
    conn.executemany("INSERT INTO ipam_addresses (subnet_id, address, status, updated_at) VALUES (?, ?, 'used', ?)",
                     [(subnet['id'], str(ipaddress.IPv4Address(base + n)), db._now()) for n in range(1, 20001)])
    conn.commit()
    conn.close()
    response = client.get(f"/api/ipam/subnets/{subnet['id']}/addresses", params={'limit': 500, 'offset': 19500})
    assert response.status_code == 200
    page = response.json()
    assert page['total'] == 20000
    assert len(page['addresses']) == 500
    assert page['addresses'][0]['address'] == str(ipaddress.IPv4Address(base + 19501))
    assert 'addresses' not in client.get(f"/api/ipam/subnets/{subnet['id']}").json()
