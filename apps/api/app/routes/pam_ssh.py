"""Faz 46/47 — Zero-Knowledge PAM SSH: `WS /api/pam/ssh/{asset_id}`.
`app/routes/agent_ssh.py`'nin (Faz 35, agent `local_ip`'sine manuel
kimlik bilgisiyle bağlanan) YERİNE değil, YANINA eklendi — o akış
PAM kuralı OLMAYAN kullanıcılar için fallback olarak aynen kalıyor.

Tarayıcının native `WebSocket` API'si özel HEADER göndermeyi
DESTEKLEMEZ — bu yüzden JWT burada (yalnızca bu endpoint'te) query
string'de (`?token=...`) taşınır. Bu, `Authorization: Bearer` header'ı
kadar güçlü değildir (URL'ler sunucu access log'larına düşebilir) ama
- token kısa ömürlü (bkz. `JWT_TOKEN_TTL_MINUTES`),
- yalnızca kimlik doğrular, kimlik bilgisi DEĞERİ hiç taşımaz,
web tarayıcı WebSocket kısıtlaması altında bilinen, kabul edilmiş bir
uzlaşımdır (aynı desen Grafana/Kibana gibi ürünlerde de kullanılır)."""

import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket

from app.agents.ssh_proxy import run_pam_ssh_websocket_session
from app.auth.exceptions import InvalidTokenError
from app.auth.security import decode_access_token
from app.db.assets import get_connection as get_assets_connection
from app.db.pam import close_session_log, get_connection as get_pam_connection, insert_keystroke_chunk, insert_session_log
from app.db.users import get_permissions as get_user_permissions
from app.pam import session_registry
from app.pam.service import SshNotAuthorizedError, authorize_ssh_session

router = APIRouter(prefix="/api/pam")

logger = logging.getLogger(__name__)


@router.websocket("/ssh/{asset_id}")
async def pam_ssh_terminal(websocket: WebSocket, asset_id: UUID, token: str | None = None) -> None:
    if not token:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Oturum token'ı gerekli"})
        await websocket.close()
        return
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Oturum token'ı geçersiz veya süresi dolmuş"})
        await websocket.close()
        return
    user_id = UUID(payload["sub"])

    try:
        pam_conn = await get_pam_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi (pam ssh)")
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Backend veritabanına erişilemedi"})
        await websocket.close()
        return

    try:
        # Faz 47 — `PAM_ACCESS` genel izni ÖNCE kontrol edilir: admin bu
        # izni geri alırsa, kullanıcının eski `pam_access_rules` satırları
        # hâlâ dursa bile bağlantı hemen reddedilir (izin=kapalı, PAM'in
        # tamamı kapalı demektir — asset bazlı kural bunun YERİNE geçmez,
        # İKİSİ birden gerekir).
        if "PAM_ACCESS" not in await get_user_permissions(pam_conn, user_id):
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "PAM erişim yetkiniz yok"})
            await websocket.close()
            return

        try:
            ssh_username, secret_payload, max_duration_mins, credential_id = await authorize_ssh_session(
                pam_conn, user_id=user_id, asset_id=asset_id
            )
        except SshNotAuthorizedError:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "Bu sunucuya SSH erişim yetkiniz yok"})
            await websocket.close()
            return

        try:
            assets_conn = await get_assets_connection()
        except OSError:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "Backend veritabanına erişilemedi"})
            await websocket.close()
            return
        try:
            asset = await assets_conn.fetchrow("SELECT ip_address FROM assets WHERE id = $1", asset_id)
        finally:
            await assets_conn.close()

        if asset is None or asset["ip_address"] is None:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "Cihazın bilinen bir IP adresi yok"})
            await websocket.close()
            return

        # `assets.ip_address` (INET) asyncpg'den bir `ipaddress.IPv4Address`
        # NESNESİ olarak gelir — Faz 45'in dersi burada da geçerli, str()
        # dönüşümü OLMADAN asyncssh'e geçmek çöker.
        host = str(asset["ip_address"])

        client_ip = websocket.client.host if websocket.client else None
        session_log = await insert_session_log(
            pam_conn,
            user_id=user_id,
            asset_id=asset_id,
            credential_id=credential_id,
            protocol="ssh",
            client_ip=client_ip,
        )
        session_id = session_log["id"]

        # Faz 50 — her tuş vuruşu (`data`) ayrı bir satır olarak
        # `pam_keystrokes`'a yazılır. `pam_conn` bu WebSocket'in tüm
        # ömrü boyunca AÇIK tutulan tek bağlantı (Faz 46'dan beri aynı
        # desen) — ek bir connection açmaya gerek yok.
        async def _record_keystroke(data: str) -> None:
            try:
                await insert_keystroke_chunk(pam_conn, session_id, data)
            except Exception:
                logger.warning("Tuş logu yazılamadı (session_id=%s)", session_id, exc_info=True)

        kill_event = session_registry.register(session_id)
        try:
            end_reason = await run_pam_ssh_websocket_session(
                websocket,
                host=host,
                username=ssh_username,
                password=secret_payload.get("password"),
                private_key=secret_payload.get("private_key"),
                passphrase=secret_payload.get("passphrase"),
                max_session_duration_mins=max_duration_mins,
                on_keystroke=_record_keystroke,
                kill_event=kill_event,
            )
        finally:
            session_registry.unregister(session_id)

        # `terminated_by` — bkz. `app/routes/pam_rdp.py`'deki AYNI not:
        # bu WebSocket handler'ı kimin sonlandırdığını bilmez, o kolon
        # `app/pam/service.py::terminate_session` tarafından AYRI ve
        # ÖNCEDEN yazılır; `close_session_log` ona dokunmaz.
        await close_session_log(pam_conn, session_id, end_reason=end_reason)
    finally:
        await pam_conn.close()
