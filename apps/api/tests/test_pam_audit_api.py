"""Faz 50 — `/api/pam/audit/*` canlı oturum sonlandırma, tuş logu ve
oturum kaydı stream endpoint'leri için gerçek PostgreSQL'e bağlı
testler (bkz. kök `conftest.py::isolated_db`). Gerçek bir WebSocket/
guacd/SSH bağlantısı hiçbir testte açılmaz — `app.pam.session_registry`
elle (WebSocket handler'ın kendisinin yaptığı gibi) register/unregister
edilir."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.assets import upsert_asset
from app.db.pam import insert_session_log, set_session_recording_path
from app.pam.guacamole_protocol import encode_instruction
from app.db.users import insert_user, set_permissions
from app.pam import session_registry

pytestmark = pytest.mark.anyio


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_user(isolated_db, *, username, role, password="s3cret-pw!"):
    row = await insert_user(isolated_db, username=username, password_hash=hash_password(password), role=role, full_name=None)
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    return row


async def _login(client, *, username, password="s3cret-pw!") -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _admin_headers(isolated_db, client, username="audit-admin") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.9.50",
        hostname="audit-target.example.local",
        mac_address="AA-BB-CC-DD-EE-50",
        vendor="Dell Inc.",
        device_type="server",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


async def _seed_session(isolated_db, *, user_id, asset_id, protocol="ssh") -> dict:
    return await insert_session_log(
        isolated_db, user_id=user_id, asset_id=asset_id, credential_id=None, protocol=protocol, client_ip="10.0.0.5"
    )


async def test_terminate_session_returns_404_for_unknown_session(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    response = await client.post("/api/pam/audit/11111111-1111-1111-1111-111111111111/terminate", headers=headers)

    assert response.status_code == 404


async def test_list_active_excludes_db_row_not_registered_in_process(isolated_db, client):
    """Faz 51 — gerçek bir durum senkronizasyon bug'ının düzeltmesi:
    `ended_at IS NULL` TEK BAŞINA "Canlı Oturumlar" listesinde
    görünmek için yeterli değil, bu SÜREÇTEKİ `session_registry`'de de
    kayıtlı olmalı — aksi halde `close_session_log` yazımı başarısız
    olduğunda kalıcı bir hayalet "canlı" satır görünürdü."""
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op7", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.57")
    ghost_session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])
    real_session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])
    session_registry.register(real_session["id"])
    try:
        response = await client.get("/api/pam/audit?active=true", headers=headers)

        assert response.status_code == 200
        ids = {row["id"] for row in response.json()}
        assert str(real_session["id"]) in ids
        assert str(ghost_session["id"]) not in ids
    finally:
        session_registry.unregister(real_session["id"])


async def test_terminate_session_returns_409_when_not_registered_active(isolated_db, client):
    """DB'de `ended_at IS NULL` bir satır olsa bile bu backend SÜRECİNDE
    (`session_registry`) kayıtlı değilse — ör. backend yeniden
    başlatıldı — sonlandırılamaz."""
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op1", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.51")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])

    response = await client.post(f"/api/pam/audit/{session['id']}/terminate", headers=headers)

    assert response.status_code == 409


async def test_terminate_session_returns_409_when_already_ended(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op2", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.52")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])
    await isolated_db.execute(
        "UPDATE pam_session_logs SET ended_at = clock_timestamp(), end_reason = 'user_closed' WHERE id = $1",
        session["id"],
    )
    session_registry.register(session["id"])
    try:
        response = await client.post(f"/api/pam/audit/{session['id']}/terminate", headers=headers)
        assert response.status_code == 409
    finally:
        session_registry.unregister(session["id"])


async def test_terminate_session_signals_kill_event_and_records_terminated_by(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op3", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.53")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])
    event = session_registry.register(session["id"])
    try:
        response = await client.post(f"/api/pam/audit/{session['id']}/terminate", headers=headers)

        assert response.status_code == 200
        assert event.is_set()
        row = await isolated_db.fetchrow("SELECT terminated_by, ended_at FROM pam_session_logs WHERE id = $1", session["id"])
        assert row["terminated_by"] is not None
        # `terminate_session` yalnızca sinyal gönderir/`terminated_by`yı
        # yazar — asıl `ended_at`/`end_reason` WebSocket köprüsü kill
        # event'i GÖRÜP kendisi kapandığında yazılır (burada simüle
        # edilmedi), bu yüzden hâlâ aktif görünmesi BEKLENİR.
        assert row["ended_at"] is None
    finally:
        session_registry.unregister(session["id"])


async def test_terminate_session_requires_pam_admin(isolated_db, client):
    await _seed_user(isolated_db, username="audit-viewer", role="VIEWER")
    token = await _login(client, username="audit-viewer")

    response = await client.post(
        "/api/pam/audit/11111111-1111-1111-1111-111111111111/terminate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


async def test_list_keystrokes_returns_404_for_unknown_session(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    response = await client.get("/api/pam/audit/11111111-1111-1111-1111-111111111111/keystrokes", headers=headers)

    assert response.status_code == 404


async def test_list_keystrokes_returns_chunks_in_order(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op4", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.54")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])
    for chunk in ("l", "s", " ", "-", "l", "a", "\r"):
        await isolated_db.execute(
            "INSERT INTO pam_keystrokes (session_id, data) VALUES ($1, $2)", session["id"], chunk
        )

    response = await client.get(f"/api/pam/audit/{session['id']}/keystrokes", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [row["data"] for row in body] == ["l", "s", " ", "-", "l", "a", "\r"]


async def test_stream_recording_returns_404_when_no_recording_path(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op5", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.55")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"], protocol="ssh")

    response = await client.get(f"/api/pam/audit/{session['id']}/recording", headers=headers)

    assert response.status_code == 404


async def test_stream_recording_returns_file_bytes_when_present(isolated_db, client, tmp_path: Path):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op6", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.56")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"], protocol="rdp")

    recording_file = tmp_path / f"{session['id']}.guac"
    recording_file.write_bytes(b"4.sync,13.1700000000000;")
    await set_session_recording_path(isolated_db, session["id"], str(recording_file))

    response = await client.get(f"/api/pam/audit/{session['id']}/recording", headers=headers)

    assert response.status_code == 200
    assert response.content == b"4.sync,13.1700000000000;"


async def test_stream_recording_returns_400_when_file_is_empty(isolated_db, client, tmp_path: Path):
    """Faz 53 sonrası bugfix — boş bir kayıt dosyası (ör. bağlantı
    guacd'ye ulaşır ulaşmaz kesildi) 404 (\"kayıt hiç yok\") DEĞİL,
    ayrı/anlamlı bir 400 ile ayırt edilir."""
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op10", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.60")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"], protocol="rdp")

    recording_file = tmp_path / f"{session['id']}.guac"
    recording_file.write_bytes(b"")
    await set_session_recording_path(isolated_db, session["id"], str(recording_file))

    response = await client.get(f"/api/pam/audit/{session['id']}/recording", headers=headers)

    assert response.status_code == 400


async def test_activity_markers_returns_404_for_unknown_session(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    response = await client.get(
        "/api/pam/audit/11111111-1111-1111-1111-111111111111/activity-markers", headers=headers
    )

    assert response.status_code == 404


async def test_activity_markers_returns_empty_list_when_no_recording(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op8", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.58")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"], protocol="ssh")

    response = await client.get(f"/api/pam/audit/{session['id']}/activity-markers", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_activity_markers_extracts_real_key_press_offsets(isolated_db, client, tmp_path: Path):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op9", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.59")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"], protocol="rdp")

    recording_file = tmp_path / f"{session['id']}.guac"
    recording_file.write_bytes(
        encode_instruction("sync", "1000")
        + encode_instruction("key", "97", "1")
        + encode_instruction("sync", "6000")
        + encode_instruction("key", "98", "1")
    )
    await set_session_recording_path(isolated_db, session["id"], str(recording_file))

    response = await client.get(f"/api/pam/audit/{session['id']}/activity-markers", headers=headers)

    assert response.status_code == 200
    assert response.json() == [0, 5000]


# ---- Faz 75 — İnaktif Süre Atlama (idle-gaps) ------------------------------


async def test_idle_gaps_returns_404_for_unknown_session(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    response = await client.get("/api/pam/audit/11111111-1111-1111-1111-111111111111/idle-gaps", headers=headers)

    assert response.status_code == 404


async def test_idle_gaps_returns_empty_list_when_no_recording(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op10", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.60")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"], protocol="ssh")

    response = await client.get(f"/api/pam/audit/{session['id']}/idle-gaps", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_idle_gaps_extracts_real_long_pause(isolated_db, client, tmp_path: Path):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="audit-op11", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.61")
    session = await _seed_session(isolated_db, user_id=operator["id"], asset_id=asset["id"], protocol="rdp")

    recording_file = tmp_path / f"{session['id']}.guac"
    recording_file.write_bytes(
        encode_instruction("sync", "1000")
        + encode_instruction("key", "97", "1")
        + encode_instruction("sync", "9000")
        + encode_instruction("mouse", "10", "20", "0")
    )
    await set_session_recording_path(isolated_db, session["id"], str(recording_file))

    response = await client.get(f"/api/pam/audit/{session['id']}/idle-gaps", headers=headers)

    assert response.status_code == 200
    assert response.json() == [{"start_ms": 0, "end_ms": 8000}]
