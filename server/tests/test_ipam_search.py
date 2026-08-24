def test_search_ipam_addresses_by_hostname(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "192.168.1.0/24", "vlan": 100})
    assert subnet_resp.status_code == 200
    subnet_id = subnet_resp.json()["id"]

    client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "192.168.1.10", "status": "used", "hostname": "web-prod-01", "description": "Webserver"},
    )
    client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "192.168.1.20", "status": "used", "hostname": "db-prod-01", "description": "Database"},
    )

    # Empty search query returns empty list
    res_empty = client.get("/api/ipam/addresses/search?q=")
    assert res_empty.status_code == 200
    assert res_empty.json() == []

    # Partial match for "web"
    res_web = client.get("/api/ipam/addresses/search?q=web")
    assert res_web.status_code == 200
    web_hits = res_web.json()
    assert len(web_hits) == 1
    assert web_hits[0]["hostname"] == "web-prod-01"
    assert web_hits[0]["subnetId"] == subnet_id
    assert web_hits[0]["subnetCidr"] == "192.168.1.0/24"
    assert web_hits[0]["subnetVlan"] == 100

    # Partial match for "prod"
    res_prod = client.get("/api/ipam/addresses/search?q=prod")
    assert res_prod.status_code == 200
    prod_hits = res_prod.json()
    assert len(prod_hits) == 2

    # Partial match for IP address
    res_ip = client.get("/api/ipam/addresses/search?q=192.168.1.20")
    assert res_ip.status_code == 200
    ip_hits = res_ip.json()
    assert len(ip_hits) == 1
    assert ip_hits[0]["hostname"] == "db-prod-01"
