from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_status_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_snmp_always_returns_not_configured():
    """Gerçek bir SNMP ajanı yokken bu endpoint asla "ok" dönmemeli —
    her zaman dürüstçe not_configured döndüğünü doğrular."""
    response = client.get("/api/health/snmp")

    assert response.status_code == 200
    assert response.json() == {"snmp": "not_configured"}
