"""`POST /api/snmp/poll/{asset_id}` için gerçek PostgreSQL'e bağlı testler.

`isolated_db` (bkz. kök `conftest.py`) sayesinde `TRUNCATE TABLE assets`
çalışsa bile gerçek/kalıcı veriye hiçbir etkisi yok — test transaction'ı
rollback ile bitiyor. Gerçek bir SNMP ajanına hiçbir istek gönderilmez;
profil-bağımlı testlerde `SNMPClient.poll_asset` mock'lanır."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.db.assets import upsert_asset


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
async def _clean_assets_table(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE assets CASCADE")


async def _seed(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.9.10",
        hostname="switch.example.local",
        mac_address="AA-BB-CC-DD-EE-01",
        vendor="Cisco Systems, Inc.",
        device_type="switch",
        confidence="medium",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


@pytest.mark.anyio
async def test_poll_existing_asset_returns_not_configured_without_fabricated_data(isolated_db, client):
    asset = await _seed(isolated_db)

    response = await client.post(f"/api/snmp/poll/{asset['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == str(asset["id"])
    assert body["status"] == "not_configured"
    assert body["system"] is None
    assert body["interfaces"] == []
    assert body["error"] is not None


@pytest.mark.anyio
async def test_poll_missing_asset_returns_404(client):
    response = await client.post(f"/api/snmp/poll/{uuid4()}")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_poll_invalid_uuid_returns_422(client):
    response = await client.post("/api/snmp/poll/not-a-uuid")

    assert response.status_code == 422


@pytest.mark.anyio
async def test_poll_returns_503_when_database_unreachable(client):
    with patch(
        "app.routes.snmp.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.post(f"/api/snmp/poll/{uuid4()}")

    assert response.status_code == 503
    assert response.json()["detail"] == {"database": "unreachable"}


@pytest.mark.anyio
async def test_poll_uses_real_client_when_profile_resolves(isolated_db, client):
    """Bir `SNMPProfile` çözülürse gerçek `SNMPClient.poll_asset`
    çağrılır — hiçbir gerçek ağ isteği gönderilmez, `SNMPClient` mock'lanır
    (bkz. Faz 22.2: gerçek cihaz olmadan sadece unit/integration testleri)."""
    asset = await _seed(isolated_db)
    from app.snmp.models import SNMPPollResult

    fake_result = SNMPPollResult(
        asset_id=asset["id"],
        polled_at=_now(),
        status="success",
        error=None,
    )
    with (
        patch(
            "app.routes.snmp.resolve_profile_for_asset",
            AsyncMock(return_value=object()),  # None olmayan herhangi bir profil
        ),
        patch(
            "app.routes.snmp.SNMPClient.poll_asset",
            AsyncMock(return_value=fake_result),
        ) as mock_poll,
    ):
        response = await client.post(f"/api/snmp/poll/{asset['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    mock_poll.assert_called_once()
    # Gerçek kullanıcı bildirimiyle bulunan bir hata: `assets.ip_address`
    # (INET) asyncpg'den bir `ipaddress.IPv4Address` NESNESİ olarak
    # gelir, düz bir `str` DEĞİL — `str()` dönüşümü OLMADAN pysnmp'nin
    # `slim.get()`'i `TypeError` ile çöküyordu (bkz. `app/routes/
    # snmp.py::poll_asset_snmp`'deki düzeltme). Poll edilen host'un
    # GERÇEK bir string olduğu burada AÇIKÇA doğrulanır.
    called_host = mock_poll.call_args.args[1]
    assert called_host == str(asset["ip_address"])
    assert isinstance(called_host, str)


@pytest.mark.anyio
async def test_poll_response_never_contains_community_secret(isolated_db, client, monkeypatch):
    """Profil çözülmese bile (yani `not_configured` yolunda) — ve
    çözülse de — response body'sinde hiçbir community/secret DEĞERİ
    bulunmaz; yalnızca `community_ref` gibi bir İSİM env'de var olsa
    bile response'a hiç yazılmaz (model bu alanı hiç taşımaz)."""
    monkeypatch.setenv("SNMP_TEST_LEAK_CHECK_COMMUNITY", "gizli-deger-hicbir-yerde-gorunmemeli")
    asset = await _seed(isolated_db)

    response = await client.post(f"/api/snmp/poll/{asset['id']}")

    assert response.status_code == 200
    assert "gizli-deger-hicbir-yerde-gorunmemeli" not in response.text
