"""Asset ↔ SNMP Profile ilişki API'si için gerçek PostgreSQL'e bağlı
testler (Faz 29.5). `isolated_db`/`client` sayesinde gerçek/kalıcı
veriye hiçbir etkisi yok. Gerçek bir SNMP ağ trafiği yok — bu dosyadaki
testler yalnızca ilişki CRUD'ını doğrular, poll denemez."""

from datetime import datetime, timezone

import pytest

from app.db.assets import upsert_asset


@pytest.fixture(autouse=True)
async def _clean_tables(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE snmp_profiles, assets CASCADE")


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.213.5",
        hostname="switch01",
        mac_address=None,
        vendor=None,
        device_type="switch",
        confidence="medium",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


def _profile_payload(**overrides) -> dict:
    payload = dict(
        name="Core Switch SNMP",
        target_host="10.0.200.1",
        port=161,
        version="v2c",
        timeout_seconds=3.0,
        retries=2,
        enabled=True,
        community_ref="SNMP_CORE_COMMUNITY",
    )
    payload.update(overrides)
    return payload


async def _seed_profile(client, **overrides) -> dict:
    response = await client.post("/api/snmp/profiles", json=_profile_payload(**overrides))
    assert response.status_code == 201
    return response.json()


@pytest.mark.anyio
async def test_get_asset_profile_returns_unconfigured_when_no_assignment(isolated_db, client):
    asset = await _seed_asset(isolated_db)

    response = await client.get(f"/api/assets/{asset['id']}/snmp-profile")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["profile"] is None


@pytest.mark.anyio
async def test_get_asset_profile_returns_404_for_unknown_asset(client):
    response = await client.get("/api/assets/00000000-0000-0000-0000-000000000000/snmp-profile")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_assign_profile_to_asset(isolated_db, client, monkeypatch):
    monkeypatch.setenv("SNMP_CORE_COMMUNITY", "gizli-deger")
    asset = await _seed_asset(isolated_db)
    profile = await _seed_profile(client)

    assign_response = await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile['id']}")
    assert assign_response.status_code == 200
    assert assign_response.json() == {"status": "assigned"}

    get_response = await client.get(f"/api/assets/{asset['id']}/snmp-profile")
    body = get_response.json()
    assert body["configured"] is True
    assert body["profile"]["id"] == profile["id"]
    assert body["profile"]["name"] == "Core Switch SNMP"
    assert body["profile"]["credential_configured"] is True
    assert "gizli-deger" not in get_response.text


@pytest.mark.anyio
async def test_assign_profile_to_unknown_asset_returns_404(client):
    profile = await _seed_profile(client)
    response = await client.put(
        f"/api/assets/00000000-0000-0000-0000-000000000000/snmp-profile/{profile['id']}"
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_assign_unknown_profile_to_asset_returns_404(isolated_db, client):
    asset = await _seed_asset(isolated_db)
    response = await client.put(
        f"/api/assets/{asset['id']}/snmp-profile/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_reassign_replaces_the_previous_profile(isolated_db, client):
    asset = await _seed_asset(isolated_db)
    profile_a = await _seed_profile(client, name="Profile A")
    profile_b = await _seed_profile(client, name="Profile B")

    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile_a['id']}")
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile_b['id']}")

    body = (await client.get(f"/api/assets/{asset['id']}/snmp-profile")).json()
    assert body["profile"]["id"] == profile_b["id"]


@pytest.mark.anyio
async def test_unassign_profile_from_asset(isolated_db, client):
    asset = await _seed_asset(isolated_db)
    profile = await _seed_profile(client)
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile['id']}")

    unassign_response = await client.delete(f"/api/assets/{asset['id']}/snmp-profile")
    assert unassign_response.status_code == 200
    assert unassign_response.json() == {"status": "unassigned"}

    body = (await client.get(f"/api/assets/{asset['id']}/snmp-profile")).json()
    assert body["configured"] is False


@pytest.mark.anyio
async def test_unassign_unknown_asset_returns_404(client):
    response = await client.delete("/api/assets/00000000-0000-0000-0000-000000000000/snmp-profile")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_unassign_when_nothing_assigned_is_idempotent(isolated_db, client):
    asset = await _seed_asset(isolated_db)

    response = await client.delete(f"/api/assets/{asset['id']}/snmp-profile")

    assert response.status_code == 200
    assert response.json() == {"status": "unassigned"}


@pytest.mark.anyio
async def test_one_profile_can_be_assigned_to_multiple_assets(isolated_db, client):
    asset_a = await _seed_asset(isolated_db, ip_address="10.0.213.5", hostname="switch01")
    asset_b = await _seed_asset(isolated_db, ip_address="10.0.213.6", hostname="switch02")
    profile = await _seed_profile(client)

    await client.put(f"/api/assets/{asset_a['id']}/snmp-profile/{profile['id']}")
    await client.put(f"/api/assets/{asset_b['id']}/snmp-profile/{profile['id']}")

    assets_response = await client.get(f"/api/snmp/profiles/{profile['id']}/assets")
    assert assets_response.status_code == 200
    ips = {a["ip_address"] for a in assets_response.json()}
    assert ips == {"10.0.213.5", "10.0.213.6"}


@pytest.mark.anyio
async def test_list_profile_assets_returns_404_for_unknown_profile(client):
    response = await client.get("/api/snmp/profiles/00000000-0000-0000-0000-000000000000/assets")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_profile_list_shows_assigned_asset_count(isolated_db, client):
    asset_a = await _seed_asset(isolated_db, ip_address="10.0.213.5")
    asset_b = await _seed_asset(isolated_db, ip_address="10.0.213.6")
    profile = await _seed_profile(client)

    await client.put(f"/api/assets/{asset_a['id']}/snmp-profile/{profile['id']}")
    await client.put(f"/api/assets/{asset_b['id']}/snmp-profile/{profile['id']}")

    list_response = await client.get("/api/snmp/profiles")
    matching = next(p for p in list_response.json() if p["id"] == profile["id"])
    assert matching["assigned_asset_count"] == 2

    detail_response = await client.get(f"/api/snmp/profiles/{profile['id']}")
    assert detail_response.json()["assigned_asset_count"] == 2


@pytest.mark.anyio
async def test_deleting_a_profile_with_assignments_returns_409(isolated_db, client):
    asset = await _seed_asset(isolated_db)
    profile = await _seed_profile(client)
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile['id']}")

    response = await client.delete(f"/api/snmp/profiles/{profile['id']}")

    assert response.status_code == 409
    still_there = await client.get(f"/api/snmp/profiles/{profile['id']}")
    assert still_there.status_code == 200


@pytest.mark.anyio
async def test_deleting_an_unassigned_profile_still_succeeds(client):
    profile = await _seed_profile(client)

    response = await client.delete(f"/api/snmp/profiles/{profile['id']}")

    assert response.status_code == 204


@pytest.mark.anyio
async def test_deleting_asset_cascades_the_assignment_not_the_profile(isolated_db, client):
    asset = await _seed_asset(isolated_db)
    profile = await _seed_profile(client)
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile['id']}")

    await isolated_db.execute("DELETE FROM assets WHERE id = $1", asset["id"])

    profile_response = await client.get(f"/api/snmp/profiles/{profile['id']}")
    assert profile_response.status_code == 200
    assert profile_response.json()["assigned_asset_count"] == 0


@pytest.mark.anyio
async def test_target_host_match_flag_is_none_when_profile_target_host_blank(isolated_db, client):
    """`target_host` yazma API'sinde zorunlu (boş olamaz) — ama DB
    satırında (ör. eski/elle düzenlenmiş bir kayıt) yine de boş olabilir;
    bu durumda karşılaştırma anlamsız olur, `None` döner (hata değil)."""
    from app.db.snmp_profiles import insert_profile

    asset = await _seed_asset(isolated_db, ip_address="10.0.213.5")
    profile = await insert_profile(
        isolated_db,
        name="Legacy Profile",
        target_host="",
        port=161,
        version="v2c",
        timeout_seconds=2.0,
        retries=1,
        enabled=True,
        community_ref="SNMP_LEGACY_COMMUNITY",
        username=None,
        auth_protocol=None,
        auth_credential_ref=None,
        priv_protocol=None,
        priv_credential_ref=None,
    )
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile['id']}")

    body = (await client.get(f"/api/assets/{asset['id']}/snmp-profile")).json()
    assert body["target_host_matches_asset"] is None


@pytest.mark.anyio
async def test_target_host_match_flag_is_false_when_profile_targets_a_different_host(isolated_db, client):
    asset = await _seed_asset(isolated_db, ip_address="10.0.213.5")
    profile = await _seed_profile(client, target_host="10.0.213.1")
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile['id']}")

    body = (await client.get(f"/api/assets/{asset['id']}/snmp-profile")).json()
    assert body["target_host_matches_asset"] is False


@pytest.mark.anyio
async def test_asset_snmp_profile_never_leaks_secret_value(isolated_db, client, monkeypatch):
    monkeypatch.setenv("SNMP_CORE_COMMUNITY", "cok-gizli-deger-hicbir-yerde-gorunmemeli")
    asset = await _seed_asset(isolated_db)
    profile = await _seed_profile(client)
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{profile['id']}")

    response = await client.get(f"/api/assets/{asset['id']}/snmp-profile")

    assert "cok-gizli-deger-hicbir-yerde-gorunmemeli" not in response.text
