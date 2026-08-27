"""Tests for the Custom Tags System (Phase C)."""

import pytest


def test_create_and_list_tags(client):
    """Test creating tags and listing them."""
    resp = client.post(
        "/api/ipam/tags",
        json={"name": "production", "color": "#ff0000", "description": "Prod servers"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "production"
    assert data["color"] == "#ff0000"
    assert data["description"] == "Prod servers"
    assert data["id"] is not None

    list_resp = client.get("/api/ipam/tags")
    assert list_resp.status_code == 200
    tags_data = list_resp.json()
    assert tags_data["count"] >= 1
    assert len(tags_data["tags"]) >= 1


def test_create_tag_validation(client):
    """Test tag name validation rules."""
    # Too short - Pydantic validator returns 422
    resp = client.post("/api/ipam/tags", json={"name": "a"})
    assert resp.status_code in (400, 422)

    # Invalid characters
    resp = client.post("/api/ipam/tags", json={"name": "prod server"})
    assert resp.status_code in (400, 422)

    # Invalid color
    resp = client.post(
        "/api/ipam/tags", json={"name": "test-tag", "color": "red"}
    )
    assert resp.status_code in (400, 422)

    # Description too long
    resp = client.post(
        "/api/ipam/tags",
        json={"name": "test-tag", "description": "x" * 201},
    )
    assert resp.status_code in (400, 422)

    # Valid creation
    resp = client.post("/api/ipam/tags", json={"name": "valid-tag"})
    assert resp.status_code == 200


def test_delete_tag(client):
    """Test deleting a tag."""
    create_resp = client.post(
        "/api/ipam/tags", json={"name": "delete-me", "color": "#00ff00"}
    )
    assert create_resp.status_code == 200
    tag_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/api/ipam/tags/{tag_id}")
    assert delete_resp.status_code == 200

    # Should no longer exist
    get_resp = client.get("/api/ipam/tags")
    tags = get_resp.json()["tags"]
    assert all(t["id"] != tag_id for t in tags)


def test_delete_nonexistent_tag(client):
    """Test deleting a tag that doesn't exist."""
    resp = client.delete("/api/ipam/tags/99999")
    assert resp.status_code == 404


def test_add_subnet_tag(client):
    """Test adding a tag to a subnet."""
    # Create a subnet
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert subnet_resp.status_code == 200
    subnet_id = subnet_resp.json()["id"]

    # Create a tag
    tag_resp = client.post("/api/ipam/tags", json={"name": "network-tag"})
    assert tag_resp.status_code == 200
    tag_id = tag_resp.json()["id"]

    # Add tag to subnet
    add_resp = client.post(f"/api/ipam/subnets/{subnet_id}/tags/{tag_id}")
    assert add_resp.status_code == 200

    # Verify tags are attached
    get_resp = client.get(f"/api/ipam/subnets/{subnet_id}/tags")
    assert get_resp.status_code == 200
    tags = get_resp.json()
    assert any(t["id"] == tag_id for t in tags)


def test_remove_subnet_tag(client):
    """Test removing a tag from a subnet."""
    # Create a subnet and tag
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.1.0/29"})
    subnet_id = subnet_resp.json()["id"]

    tag_resp = client.post("/api/ipam/tags", json={"name": "remove-me"})
    tag_id = tag_resp.json()["id"]

    # Add and then remove
    client.post(f"/api/ipam/subnets/{subnet_id}/tags/{tag_id}")
    del_resp = client.delete(f"/api/ipam/subnets/{subnet_id}/tags/{tag_id}")
    assert del_resp.status_code == 200

    get_resp = client.get(f"/api/ipam/subnets/{subnet_id}/tags")
    tags = get_resp.json()
    assert all(t["id"] != tag_id for t in tags)


def test_add_address_tag(client):
    """Test adding a tag to an address."""
    # Create a subnet and address
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.2.0/29"})
    subnet_id = subnet_resp.json()["id"]

    addr_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.2.1", "status": "used"},
    )
    assert addr_resp.status_code == 200
    address_id = addr_resp.json()["addresses"][0]["id"]

    # Create a tag
    tag_resp = client.post("/api/ipam/tags", json={"name": "addr-tag"})
    tag_id = tag_resp.json()["id"]

    # Add tag to address
    add_resp = client.post(f"/api/ipam/addresses/{address_id}/tags/{tag_id}")
    assert add_resp.status_code == 200

    # Verify tags are attached
    get_resp = client.get(f"/api/ipam/addresses/{address_id}/tags")
    assert get_resp.status_code == 200
    tags = get_resp.json()
    assert any(t["id"] == tag_id for t in tags)


def test_remove_address_tag(client):
    """Test removing a tag from an address."""
    # Create a subnet, address, and tag
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.3.0/29"})
    subnet_id = subnet_resp.json()["id"]

    addr_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.3.1", "status": "used"},
    )
    address_id = addr_resp.json()["addresses"][0]["id"]

    tag_resp = client.post("/api/ipam/tags", json={"name": "addr-remove"})
    tag_id = tag_resp.json()["id"]

    client.post(f"/api/ipam/addresses/{address_id}/tags/{tag_id}")
    del_resp = client.delete(f"/api/ipam/addresses/{address_id}/tags/{tag_id}")
    assert del_resp.status_code == 200

    get_resp = client.get(f"/api/ipam/addresses/{address_id}/tags")
    tags = get_resp.json()
    assert all(t["id"] != tag_id for t in tags)


def test_get_subnets_by_tag(client):
    """Test finding subnets by tag."""
    # Create two subnets and a tag
    s1 = client.post("/api/ipam/subnets", json={"cidr": "10.0.4.0/29"}).json()
    s2 = client.post("/api/ipam/subnets", json={"cidr": "10.0.5.0/29"}).json()
    tag = client.post("/api/ipam/tags", json={"name": "filtered"}).json()

    # Add tag to first subnet only
    client.post(f"/api/ipam/subnets/{s1['id']}/tags/{tag['id']}")

    # Query by tag
    resp = client.get(f"/api/ipam/tags/{tag['id']}/subnets")
    assert resp.status_code == 200
    subnets = resp.json()
    assert len(subnets) == 1
    assert subnets[0]["id"] == s1["id"]


def test_get_addresses_by_tag(client):
    """Test finding addresses by tag."""
    # Create subnet with two addresses and a tag
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.0.6.0/29"}).json()
    a1 = client.post(
        f"/api/ipam/subnets/{subnet['id']}/addresses",
        json={"address": "10.0.6.1", "status": "used"},
    ).json()
    a2 = client.post(
        f"/api/ipam/subnets/{subnet['id']}/addresses",
        json={"address": "10.0.6.2", "status": "used"},
    ).json()
    tag = client.post("/api/ipam/tags", json={"name": "addr-filter"}).json()

    # Add tag to first address only
    client.post(f"/api/ipam/addresses/{a1['addresses'][0]['id']}/tags/{tag['id']}")

    # Query by tag
    resp = client.get(f"/api/ipam/tags/{tag['id']}/addresses")
    assert resp.status_code == 200
    addresses = resp.json()
    assert len(addresses) == 1
    assert addresses[0]["id"] == a1["addresses"][0]["id"]


def test_search_tags(client):
    """Test searching tags by name."""
    client.post("/api/ipam/tags", json={"name": "web-server", "description": "Web servers"})
    client.post("/api/ipam/tags", json={"name": "db-server", "description": "Database servers"})

    resp = client.get("/api/ipam/tags/search?q=web")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["name"] == "web-server"


def test_tag_cascade_delete(client):
    """Test that deleting a tag removes associations."""
    # Create subnet, address, and tag
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.0.7.0/29"}).json()
    addr = client.post(
        f"/api/ipam/subnets/{subnet['id']}/addresses",
        json={"address": "10.0.7.1", "status": "used"},
    ).json()
    tag = client.post("/api/ipam/tags", json={"name": "cascade-test"}).json()
    tag_id = tag["id"]

    # Add tag to both subnet and address
    client.post(f"/api/ipam/subnets/{subnet['id']}/tags/{tag_id}")
    client.post(f"/api/ipam/addresses/{addr['addresses'][0]['id']}/tags/{tag_id}")

    # Delete tag
    client.delete(f"/api/ipam/tags/{tag_id}")

    # Associations should be gone
    subnet_tags = client.get(f"/api/ipam/subnets/{subnet['id']}/tags").json()
    addr_tags = client.get(f"/api/ipam/addresses/{addr['addresses'][0]['id']}/tags").json()
    assert len(subnet_tags) == 0
    assert len(addr_tags) == 0


def test_duplicate_tag_name_rejected(client):
    """Test that duplicate tag names are rejected."""
    client.post("/api/ipam/tags", json={"name": "unique-tag"})
    resp = client.post("/api/ipam/tags", json={"name": "unique-tag"})
    assert resp.status_code in (400, 409)  # SQLite returns 500, caught as 409
