from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.discovery.schemas import PingResult, PortResult, ScanResult
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_persistence():
    """Bu dosyadaki testler saf HTTP/discovery-mock testleridir; gerçek
    PostgreSQL'e bağımlı olmamaları için `persist_scan_result` ve scan
    history fonksiyonları mock'lanır. Discovery -> DB entegrasyonunun
    kendisi için bkz. `tests/db/test_discovery_persistence.py`; scan
    history entegrasyonu için bkz. `tests/test_scan_history_integration.py`."""
    with (
        patch("app.routes.discovery.persist_scan_result", AsyncMock(return_value=None)),
        patch("app.routes.discovery.start_scan_record", AsyncMock(return_value=None)),
        patch("app.routes.discovery.complete_scan_record", AsyncMock(return_value=None)),
        patch("app.routes.discovery.fail_scan_record", AsyncMock(return_value=None)),
    ):
        yield


def test_icmp_scan_returns_valid_schema_for_valid_cidr():
    fake_result = ScanResult(
        cidr="10.0.5.0/24",
        total_hosts=254,
        alive_hosts=1,
        hosts=[
            PingResult(
                ip="10.0.5.1",
                status="up",
                latency_ms=2.1,
                mac_address="AA-BB-CC-DD-EE-FF",
                vendor="Fortinet, Inc.",
                hostname="firewall.example.local",
                open_ports=[PortResult(port=443, status="open", latency_ms=2.4)],
                device_type="firewall",
                confidence="high",
                evidence=["vendor: Fortinet"],
            )
        ],
    )

    with patch(
        "app.routes.discovery.scan_network", AsyncMock(return_value=fake_result)
    ):
        response = client.post("/api/discovery/icmp", json={"cidr": "10.0.5.0/24"})

    assert response.status_code == 200
    body = response.json()
    assert body["cidr"] == "10.0.5.0/24"
    assert body["total_hosts"] == 254
    assert body["alive_hosts"] == 1
    assert body["hosts"] == [
        {
            "ip": "10.0.5.1",
            "status": "up",
            "latency_ms": 2.1,
            "mac_address": "AA-BB-CC-DD-EE-FF",
            "vendor": "Fortinet, Inc.",
            "hostname": "firewall.example.local",
            "open_ports": [{"port": 443, "status": "open", "latency_ms": 2.4}],
            "device_type": "firewall",
            "confidence": "high",
            "evidence": ["vendor: Fortinet"],
        }
    ]


def test_icmp_scan_returns_unknown_low_empty_evidence_by_default():
    fake_result = ScanResult(
        cidr="10.0.5.0/24",
        total_hosts=254,
        alive_hosts=1,
        hosts=[PingResult(ip="10.0.5.1", status="up", latency_ms=2.1)],
    )

    with patch(
        "app.routes.discovery.scan_network", AsyncMock(return_value=fake_result)
    ):
        response = client.post("/api/discovery/icmp", json={"cidr": "10.0.5.0/24"})

    host = response.json()["hosts"][0]
    assert host["device_type"] == "unknown"
    assert host["confidence"] == "low"
    assert host["evidence"] == []


def test_icmp_scan_returns_empty_open_ports_when_none_open():
    fake_result = ScanResult(
        cidr="10.0.5.0/24",
        total_hosts=254,
        alive_hosts=1,
        hosts=[PingResult(ip="10.0.5.1", status="up", latency_ms=2.1)],
    )

    with patch(
        "app.routes.discovery.scan_network", AsyncMock(return_value=fake_result)
    ):
        response = client.post("/api/discovery/icmp", json={"cidr": "10.0.5.0/24"})

    assert response.json()["hosts"][0]["open_ports"] == []


def test_icmp_scan_returns_null_hostname_when_not_found():
    fake_result = ScanResult(
        cidr="10.0.5.0/24",
        total_hosts=254,
        alive_hosts=1,
        hosts=[PingResult(ip="10.0.5.1", status="up", latency_ms=2.1)],
    )

    with patch(
        "app.routes.discovery.scan_network", AsyncMock(return_value=fake_result)
    ):
        response = client.post("/api/discovery/icmp", json={"cidr": "10.0.5.0/24"})

    assert response.json()["hosts"][0]["hostname"] is None


def test_icmp_scan_returns_null_vendor_when_not_found():
    fake_result = ScanResult(
        cidr="10.0.5.0/24",
        total_hosts=254,
        alive_hosts=1,
        hosts=[
            PingResult(
                ip="10.0.5.1",
                status="up",
                latency_ms=2.1,
                mac_address="FF-FF-FF-00-00-00",
            )
        ],
    )

    with patch(
        "app.routes.discovery.scan_network", AsyncMock(return_value=fake_result)
    ):
        response = client.post("/api/discovery/icmp", json={"cidr": "10.0.5.0/24"})

    assert response.json()["hosts"][0]["vendor"] is None


def test_icmp_scan_returns_null_mac_when_not_found():
    fake_result = ScanResult(
        cidr="10.0.5.0/24",
        total_hosts=254,
        alive_hosts=1,
        hosts=[PingResult(ip="10.0.5.1", status="up", latency_ms=2.1)],
    )

    with patch(
        "app.routes.discovery.scan_network", AsyncMock(return_value=fake_result)
    ):
        response = client.post("/api/discovery/icmp", json={"cidr": "10.0.5.0/24"})

    assert response.json()["hosts"][0]["mac_address"] is None


def test_icmp_scan_rejects_invalid_cidr():
    response = client.post("/api/discovery/icmp", json={"cidr": "not-a-cidr"})

    assert response.status_code == 400


def test_icmp_scan_rejects_missing_cidr_field():
    response = client.post("/api/discovery/icmp", json={})

    assert response.status_code == 422
