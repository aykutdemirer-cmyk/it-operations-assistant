import ipaddress

import pytest

from app.discovery.cidr import InvalidCIDRError, list_host_ips, parse_ipv4_cidr


def test_parse_ipv4_cidr_accepts_valid_cidr():
    network = parse_ipv4_cidr("10.0.5.0/24")

    assert network == ipaddress.ip_network("10.0.5.0/24")


def test_parse_ipv4_cidr_rejects_malformed_string():
    with pytest.raises(InvalidCIDRError):
        parse_ipv4_cidr("not-a-cidr")


def test_parse_ipv4_cidr_rejects_ipv6():
    with pytest.raises(InvalidCIDRError):
        parse_ipv4_cidr("2001:db8::/32")


def test_list_host_ips_excludes_network_and_broadcast_for_slash_24():
    network = parse_ipv4_cidr("10.0.5.0/24")

    hosts = list_host_ips(network)

    assert len(hosts) == 254
    assert "10.0.5.0" not in hosts
    assert "10.0.5.255" not in hosts
    assert hosts[0] == "10.0.5.1"
    assert hosts[-1] == "10.0.5.254"


def test_list_host_ips_for_slash_30_has_two_usable_hosts():
    network = parse_ipv4_cidr("10.0.5.0/30")

    hosts = list_host_ips(network)

    assert hosts == ["10.0.5.1", "10.0.5.2"]
