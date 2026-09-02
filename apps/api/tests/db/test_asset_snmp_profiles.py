"""`app/db/asset_snmp_profiles.py` repository katmanı için gerçek
PostgreSQL'e bağlı testler (Faz 29.5). `db_conn` (bkz. `tests/db/
conftest.py`) transaction+rollback ile izole ediyor — gerçek veriye
etki yok. Gerçek SNMP ağ trafiği yok, yalnızca ilişki tablosu CRUD'ı."""

from datetime import datetime, timezone

import asyncpg
import pytest

from app.db.asset_snmp_profiles import (
    assign_profile_to_asset,
    count_assets_by_profile,
    count_assets_for_profile,
    get_profile_for_asset,
    list_assets_for_profile,
    unassign_profile_from_asset,
)
from app.db.assets import upsert_asset
from app.db.snmp_profiles import insert_profile


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_asset(conn, **overrides) -> dict:
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
        last_seen=_now(),
    )
    defaults.update(overrides)
    return await upsert_asset(conn, **defaults)


async def _seed_profile(conn, **overrides) -> dict:
    defaults = dict(
        name="Core Switch SNMP",
        target_host="",
        port=161,
        version="v2c",
        timeout_seconds=2.0,
        retries=2,
        enabled=True,
        community_ref="SNMP_CORE_COMMUNITY",
        username=None,
        auth_protocol=None,
        auth_credential_ref=None,
        priv_protocol=None,
        priv_credential_ref=None,
    )
    defaults.update(overrides)
    return await insert_profile(conn, **defaults)


@pytest.mark.anyio
async def test_get_profile_for_asset_returns_none_without_assignment(db_conn):
    asset = await _seed_asset(db_conn)
    assert await get_profile_for_asset(db_conn, asset["id"]) is None


@pytest.mark.anyio
async def test_assign_then_get_profile_for_asset(db_conn):
    asset = await _seed_asset(db_conn)
    profile = await _seed_profile(db_conn)

    await assign_profile_to_asset(db_conn, asset_id=asset["id"], profile_id=profile["id"])
    row = await get_profile_for_asset(db_conn, asset["id"])

    assert row is not None
    assert row["id"] == profile["id"]
    assert row["name"] == "Core Switch SNMP"


@pytest.mark.anyio
async def test_reassigning_replaces_the_previous_profile(db_conn):
    asset = await _seed_asset(db_conn)
    profile_a = await _seed_profile(db_conn, name="Profile A")
    profile_b = await _seed_profile(db_conn, name="Profile B")

    await assign_profile_to_asset(db_conn, asset_id=asset["id"], profile_id=profile_a["id"])
    await assign_profile_to_asset(db_conn, asset_id=asset["id"], profile_id=profile_b["id"])

    row = await get_profile_for_asset(db_conn, asset["id"])
    assert row["id"] == profile_b["id"]

    # asset başına en fazla bir satır olduğunu (üzerine yazıldığını, yeni
    # bir satır eklenmediğini) doğrula.
    count = await db_conn.fetchval(
        "SELECT count(*) FROM asset_snmp_profiles WHERE asset_id = $1", asset["id"]
    )
    assert count == 1


@pytest.mark.anyio
async def test_assign_unknown_asset_raises_foreign_key_violation(db_conn):
    profile = await _seed_profile(db_conn)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await assign_profile_to_asset(
            db_conn, asset_id="00000000-0000-0000-0000-000000000000", profile_id=profile["id"]
        )


@pytest.mark.anyio
async def test_assign_unknown_profile_raises_foreign_key_violation(db_conn):
    asset = await _seed_asset(db_conn)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await assign_profile_to_asset(
            db_conn, asset_id=asset["id"], profile_id="00000000-0000-0000-0000-000000000000"
        )


@pytest.mark.anyio
async def test_unassign_removes_the_relationship(db_conn):
    asset = await _seed_asset(db_conn)
    profile = await _seed_profile(db_conn)
    await assign_profile_to_asset(db_conn, asset_id=asset["id"], profile_id=profile["id"])

    removed = await unassign_profile_from_asset(db_conn, asset["id"])

    assert removed is True
    assert await get_profile_for_asset(db_conn, asset["id"]) is None


@pytest.mark.anyio
async def test_unassign_when_nothing_assigned_returns_false(db_conn):
    asset = await _seed_asset(db_conn)
    assert await unassign_profile_from_asset(db_conn, asset["id"]) is False


@pytest.mark.anyio
async def test_list_assets_for_profile_returns_all_assigned_assets(db_conn):
    asset_a = await _seed_asset(db_conn, ip_address="10.0.213.5")
    asset_b = await _seed_asset(db_conn, ip_address="10.0.213.6")
    unrelated = await _seed_asset(db_conn, ip_address="10.0.213.7")
    profile = await _seed_profile(db_conn)

    await assign_profile_to_asset(db_conn, asset_id=asset_a["id"], profile_id=profile["id"])
    await assign_profile_to_asset(db_conn, asset_id=asset_b["id"], profile_id=profile["id"])

    assets = await list_assets_for_profile(db_conn, profile["id"])

    ids = {a["id"] for a in assets}
    assert ids == {asset_a["id"], asset_b["id"]}
    assert unrelated["id"] not in ids


@pytest.mark.anyio
async def test_count_assets_for_profile(db_conn):
    asset_a = await _seed_asset(db_conn, ip_address="10.0.213.5")
    asset_b = await _seed_asset(db_conn, ip_address="10.0.213.6")
    profile = await _seed_profile(db_conn)

    assert await count_assets_for_profile(db_conn, profile["id"]) == 0

    await assign_profile_to_asset(db_conn, asset_id=asset_a["id"], profile_id=profile["id"])
    await assign_profile_to_asset(db_conn, asset_id=asset_b["id"], profile_id=profile["id"])

    assert await count_assets_for_profile(db_conn, profile["id"]) == 2


@pytest.mark.anyio
async def test_count_assets_by_profile_groups_correctly(db_conn):
    asset_a = await _seed_asset(db_conn, ip_address="10.0.213.5")
    asset_b = await _seed_asset(db_conn, ip_address="10.0.213.6")
    profile_a = await _seed_profile(db_conn, name="Profile A")
    profile_b = await _seed_profile(db_conn, name="Profile B")

    await assign_profile_to_asset(db_conn, asset_id=asset_a["id"], profile_id=profile_a["id"])
    await assign_profile_to_asset(db_conn, asset_id=asset_b["id"], profile_id=profile_a["id"])

    counts = await count_assets_by_profile(db_conn)

    assert counts[profile_a["id"]] == 2
    assert profile_b["id"] not in counts


@pytest.mark.anyio
async def test_deleting_asset_cascades_the_relationship_row(db_conn):
    asset = await _seed_asset(db_conn)
    profile = await _seed_profile(db_conn)
    await assign_profile_to_asset(db_conn, asset_id=asset["id"], profile_id=profile["id"])

    await db_conn.execute("DELETE FROM assets WHERE id = $1", asset["id"])

    assert await count_assets_for_profile(db_conn, profile["id"]) == 0


@pytest.mark.anyio
async def test_deleting_profile_cascades_the_relationship_row(db_conn):
    asset = await _seed_asset(db_conn)
    profile = await _seed_profile(db_conn)
    await assign_profile_to_asset(db_conn, asset_id=asset["id"], profile_id=profile["id"])

    await db_conn.execute("DELETE FROM snmp_profiles WHERE id = $1", profile["id"])

    assert await get_profile_for_asset(db_conn, asset["id"]) is None
