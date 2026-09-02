import socket
from types import SimpleNamespace
from unittest.mock import patch

import psutil

from agent.collectors import network


def _addr(family, address):
    return SimpleNamespace(family=family, address=address, netmask=None, broadcast=None, ptp=None)


def test_classify_interface_type_ethernet():
    assert network.classify_interface_type("Ethernet0") == "ethernet"
    assert network.classify_interface_type("eth0") == "ethernet"
    assert network.classify_interface_type("enp3s0") == "ethernet"


def test_classify_interface_type_wifi():
    assert network.classify_interface_type("Wi-Fi") == "wifi"
    assert network.classify_interface_type("wlan0") == "wifi"


def test_classify_interface_type_loopback():
    assert network.classify_interface_type("lo") == "loopback"
    assert network.classify_interface_type("Loopback Pseudo-Interface 1") == "loopback"


def test_classify_interface_type_docker():
    assert network.classify_interface_type("docker0") == "docker"
    assert network.classify_interface_type("veth1234") == "docker"


def test_classify_interface_type_vpn():
    assert network.classify_interface_type("tun0") == "vpn"
    assert network.classify_interface_type("wg0-wireguard") == "vpn"


def test_classify_interface_type_unknown_defaults_to_other():
    assert network.classify_interface_type("some-random-name") == "other"


def test_collect_interfaces_normalizes_addresses_and_counters():
    addrs = {
        "eth0": [
            _addr(socket.AF_INET, "10.0.213.5"),
            _addr(socket.AF_INET6, "fe80::1"),
            _addr(psutil.AF_LINK, "AA:BB:CC:DD:EE:FF"),
        ]
    }
    stats = {"eth0": SimpleNamespace(isup=True, duplex=0, speed=1000, mtu=1500, flags="up")}
    io_counters = {
        "eth0": SimpleNamespace(bytes_sent=100, bytes_recv=200, packets_sent=1, packets_recv=2, errin=0, errout=0, dropin=0, dropout=0)
    }

    with patch("agent.collectors.network.psutil.net_if_addrs", return_value=addrs):
        with patch("agent.collectors.network.psutil.net_if_stats", return_value=stats):
            with patch("agent.collectors.network.psutil.net_io_counters", return_value=io_counters):
                result = network.collect_interfaces()

    assert len(result) == 1
    iface = result[0]
    assert iface["name"] == "eth0"
    assert iface["interface_type"] == "ethernet"
    assert iface["ip_address"] == "10.0.213.5"
    assert set(iface["addresses"]) == {"10.0.213.5", "fe80::1"}
    assert iface["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert iface["state"] == "up"
    assert iface["speed_bps"] == 1_000_000_000
    assert iface["rx_bytes"] == 200
    assert iface["tx_bytes"] == 100


def test_collect_interfaces_handles_missing_stats_and_counters_gracefully():
    addrs = {"eth0": [_addr(socket.AF_INET, "10.0.0.1")]}

    with patch("agent.collectors.network.psutil.net_if_addrs", return_value=addrs):
        with patch("agent.collectors.network.psutil.net_if_stats", return_value={}):
            with patch("agent.collectors.network.psutil.net_io_counters", return_value={}):
                result = network.collect_interfaces()

    assert result[0]["state"] is None
    assert result[0]["speed_bps"] is None
    assert result[0]["rx_bytes"] is None


def test_collect_interfaces_returns_empty_list_when_unavailable():
    with patch("agent.collectors.network.psutil.net_if_addrs", side_effect=RuntimeError("boom")):
        assert network.collect_interfaces() == []
