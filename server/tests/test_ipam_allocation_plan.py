import concurrent.futures


def create_subnet(client, cidr, **extra):
    response = client.post("/api/ipam/subnets", json={"cidr": cidr, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def allocation_plan(client, parent, prefix):
    response = client.post("/api/ipam/allocation-plan", json={"parent": parent, "prefix": prefix})
    assert response.status_code == 200, response.text
    return response.json()


def test_allocation_plan_supports_arbitrary_prefixes_and_multiple_recommendations(client):
    create_subnet(client, "10.40.0.0/22")
    for prefix in (23, 27, 31):
        plan = allocation_plan(client, "10.40.0.0/22", prefix)
        assert plan["requestedPrefix"] == prefix
        assert len(plan["recommendations"]) >= min(3, 1 << (prefix - 22))
        assert plan["freshnessToken"]


def test_allocation_plan_previews_occupied_subnets_addresses_and_pools(client):
    parent = create_subnet(client, "10.41.0.0/24")
    create_subnet(client, "10.41.0.64/26")
    client.post(f"/api/ipam/subnets/{parent['id']}/addresses", json={"address": "10.41.0.10"})
    client.post(f"/api/ipam/subnets/{parent['id']}/dhcp-pools", json={"start_ip": "10.41.0.20", "end_ip": "10.41.0.30", "name": "dynamic"})
    plan = allocation_plan(client, "10.41.0.0/24", 28)
    assert {item["source"] for item in plan["occupiedRanges"]} >= {"subnet", "address", "dhcp_pool"}
    assert all(not cidr.startswith("10.41.0.64/") for cidr in plan["recommendations"])


def test_atomic_allocation_creates_metadata_tags_and_rejects_stale_token(client):
    create_subnet(client, "10.42.0.0/24")
    tag = client.post("/api/ipam/tags", json={"name": "edge", "color": "#112233"}).json()
    plan = allocation_plan(client, "10.42.0.0/24", 27)
    payload = {"parent": plan["parent"], "cidr": plan["recommendations"][0], "freshnessToken": plan["freshnessToken"], "vlan": 220, "description": "Allocated edge", "tagIds": [tag["id"]]}
    created = client.post("/api/ipam/allocation-plan/create", json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["vlan"] == 220
    assert client.get(f"/api/ipam/subnets/{created.json()['id']}/tags").json()[0]["id"] == tag["id"]
    stale = client.post("/api/ipam/allocation-plan/create", json=payload)
    assert stale.status_code == 409
    assert "stale" in stale.json()["detail"].lower()


def test_atomic_allocation_prevents_concurrent_overlap(client):
    create_subnet(client, "10.43.0.0/24")
    plan = allocation_plan(client, "10.43.0.0/24", 27)
    payload = {"parent": plan["parent"], "cidr": plan["recommendations"][0], "freshnessToken": plan["freshnessToken"], "vlan": None, "description": None, "tagIds": []}
    def submit():
        return client.post("/api/ipam/allocation-plan/create", json=payload).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(statuses) == [200, 409]
