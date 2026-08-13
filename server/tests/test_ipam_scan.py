import ipaddress

import pytest

import ipam_scan


def test_enumerate_scan_targets_excludes_network_broadcast_and_excludes():
    cidr = "10.0.0.0/29"
    excludes = {"10.0.0.2", "10.0.0.5"}

    targets = ipam_scan.enumerate_scan_targets(cidr, excludes)

    assert "10.0.0.0" not in targets  # network address
    assert "10.0.0.7" not in targets  # broadcast address
    assert "10.0.0.2" not in targets  # excluded
    assert "10.0.0.5" not in targets  # excluded

    for host in ("10.0.0.1", "10.0.0.3", "10.0.0.4", "10.0.0.6"):
        assert host in targets


def test_enumerate_scan_targets_raises_over_cap():
    cidr = "10.0.0.0/16"
    cap = ipam_scan.MAX_SCAN_ADDRESSES
    actual_count = ipaddress.ip_network(cidr).num_addresses

    with pytest.raises(ValueError) as exc_info:
        ipam_scan.enumerate_scan_targets(cidr, set())

    message = str(exc_info.value)
    assert str(actual_count) in message
    assert str(cap) in message