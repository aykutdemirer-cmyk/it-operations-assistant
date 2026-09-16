"""Faz 48 — Gerçek Zero-Knowledge PAM RDP: `WS /api/pam/rdp/{asset_id}`.
Faz 47'nin `.rdp` DOSYA İNDİRME akışının YERİNE geçti (kullanıcının açık
isteğiyle KALDIRILDI) — artık tarayıcıda `guacamole-common-js` ile
render edilen, istemcisiz (clientless) canlı bir HTML5 oturumu.

Mimari (bkz. `app/pam/guacd.py` docstring'i): bu endpoint `guacd`'ye
(Guacamole Daemon, AYRI bir servis — bkz. `infra/docker-compose.yml`)
sunucu-sunucu bir TCP bağlantısı açar, kasadaki kimlik bilgisini ORADA
enjekte eder, sonra ham protokolü WebSocket'e köprüler. Parola/kimlik
bilgisi DEĞERİ tarayıcıya HİÇBİR ZAMAN gönderilmez.

Tarayıcının native `WebSocket` API'si özel header GÖNDEREMEDİĞİ için
JWT burada da (Faz 46'nın SSH tüneliyle AYNI, belgelenmiş ödünleşim)
query string'de (`?token=...`) taşınır.

**Gerçek, canlı test sırasında bulunan bir üretim hatası:**
`guacamole-common-js`'in `Guacamole.WebSocketTunnel`'ı WebSocket'i
`new WebSocket(url, "guacamole")` ile AÇAR — yani "guacamole" alt
protokolünü (subprotocol) İSTER. WebSocket standardı gereği istemci bir
alt protokol istediğinde SUNUCU bunu el sıkışma yanıtında (`Sec-
WebSocket-Protocol`) AÇIKÇA kabul etmezse tarayıcı bağlantıyı KENDİSİ
iptal eder — `websocket.accept()` bunu (varsayılan olarak) yapmıyordu,
bu yüzden gerçek tarayıcılarda (hem Chrome hem Claude'un önizleme
tarayıcısı) bağlantı HİÇ kurulamıyordu (ham bir Python WebSocket
istemcisiyle test edildiğinde ise, alt protokol hiç İSTENMEDİĞİ için
sorun GİZLİ kalıyordu). Her `websocket.accept()` çağrısı bu yüzden
`subprotocol="guacamole"` ile."""

import logging
import os
from uuid import UUID

from fastapi import APIRouter, WebSocket

from app.auth.exceptions import InvalidTokenError
from app.auth.security import decode_access_token
from app.db.assets import get_connection as get_assets_connection
from app.db.pam import (
    close_session_log,
    get_connection as get_pam_connection,
    insert_session_log,
    set_session_recording_path,
)
from app.db.users import get_permissions as get_user_permissions
from app.pam import session_registry
from app.pam.guacd import GuacdConnectError, bridge_websocket_to_guacd, open_rdp_connection, recording_config
from app.pam.service import SshNotAuthorizedError, authorize_rdp_session

router = APIRouter(prefix="/api/pam")

logger = logging.getLogger(__name__)

_DEFAULT_WIDTH = 1280
_DEFAULT_HEIGHT = 800
_DEFAULT_DPI = 96


@router.websocket("/rdp/{asset_id}")
async def pam_rdp_terminal(
    websocket: WebSocket,
    asset_id: UUID,
    token: str | None = None,
    width: int = _DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
    dpi: int = _DEFAULT_DPI,
) -> None:
    if not token:
        await websocket.accept(subprotocol="guacamole")
        await websocket.send_text("error: Oturum token'ı gerekli")
        await websocket.close()
        return
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        await websocket.accept(subprotocol="guacamole")
        await websocket.send_text("error: Oturum token'ı geçersiz veya süresi dolmuş")
        await websocket.close()
        return
    user_id = UUID(payload["sub"])

    try:
        pam_conn = await get_pam_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi (pam rdp)")
        await websocket.accept(subprotocol="guacamole")
        await websocket.send_text("error: Backend veritabanına erişilemedi")
        await websocket.close()
        return

    try:
        if "PAM_ACCESS" not in await get_user_permissions(pam_conn, user_id):
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text("error: PAM erişim yetkiniz yok")
            await websocket.close()
            return

        try:
            authorization = await authorize_rdp_session(pam_conn, user_id=user_id, asset_id=asset_id)
        except SshNotAuthorizedError:
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text("error: Bu sunucuya RDP erişim yetkiniz yok")
            await websocket.close()
            return

        try:
            assets_conn = await get_assets_connection()
        except OSError:
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text("error: Backend veritabanına erişilemedi")
            await websocket.close()
            return
        try:
            asset = await assets_conn.fetchrow("SELECT ip_address FROM assets WHERE id = $1", asset_id)
        finally:
            await assets_conn.close()

        if asset is None or asset["ip_address"] is None:
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text("error: Cihazın bilinen bir IP adresi yok")
            await websocket.close()
            return

        # `assets.ip_address` (INET) → str() — bkz. Faz 45'in dersi.
        host = str(asset["ip_address"])

        # Faz 50 — Oturum Kaydı: `session_id` guacd'nin `recording-name`
        # değeri olarak kullanılacağı için `insert_session_log` guacd'ye
        # bağlanmadan ÖNCE çağrılır (Faz 46/48'in eski sırasının TERSİ) —
        # bu şekilde oturum log satırının `id`'si ile kayıt dosyasının
        # adı BİREBİR eşleşir, ayrı bir eşleme tablosu gerekmez.
        client_ip = websocket.client.host if websocket.client else None
        session_log = await insert_session_log(
            pam_conn,
            user_id=user_id,
            asset_id=asset_id,
            credential_id=authorization.credential_id,
            protocol="rdp",
            client_ip=client_ip,
        )
        session_id = session_log["id"]

        try:
            reader, writer = await open_rdp_connection(
                hostname=host,
                username=authorization.username,
                password=authorization.password,
                domain=authorization.domain,
                width=width,
                height=height,
                dpi=dpi,
                session_id=str(session_id),
            )
        except GuacdConnectError as exc:
            logger.warning("guacd bağlantısı kurulamadı: %s", exc)
            await close_session_log(pam_conn, session_id, end_reason="error")
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text(
                "error: RDP ağ geçidine (guacd) bağlanılamadı — altyapı henüz kurulmamış olabilir"
            )
            await websocket.close()
            return

        # Faz 51 — gerçek bir bug bulunup düzeltildi: `recording_file_
        # path` önceden yalnızca oturum KAPANDIKTAN SONRA yazılıyordu —
        # bu da "Canlı İzle"nin katılma-anı yakalaması (`app/routes/
        # pam_audit.py::shadow_session_route`) için HİÇBİR ZAMAN dolu
        # olmadığı anlamına geliyordu (guacd dosyayı GERÇEKTEN o an
        # yazıyor olsa bile). Artık bağlantı kurulur kurulmaz, oturum
        # HÂLÂ CANLIYKEN yazılıyor — dosya yolu zaten deterministik
        # (`{recording_host_dir}/{session_id}`), oturumun bitmesini
        # beklemeye hiç gerek yoktu.
        _, recording_host_dir = recording_config()
        if recording_host_dir:
            recording_file_path = os.path.join(recording_host_dir, str(session_id))
            await set_session_recording_path(pam_conn, session_id, recording_file_path)

        await websocket.accept(subprotocol="guacamole")

        kill_event = session_registry.register(session_id)
        try:
            end_reason = await bridge_websocket_to_guacd(
                websocket,
                reader,
                writer,
                max_session_duration_mins=authorization.max_session_duration_mins,
                kill_event=kill_event,
                session_id=session_id,
            )
        finally:
            session_registry.unregister(session_id)

        # `terminated_by` (ADMIN'in kimliği) burada BİLİNMİYOR — bu
        # WebSocket handler'ı yalnızca bir kill EVENT'i görür, kimin
        # gönderdiğini taşımaz. Gerçek admin kimliği `app/pam/
        # service.py::terminate_session` tarafından, kill event set
        # EDİLMEDEN ÖNCE, ayrı bir yazımla kaydedilir (bkz. `app/db/
        # pam.py::close_session_log`'un `COALESCE` deseni — buradan
        # `terminated_by=None` geçmek o değeri SİLMEZ).
        await close_session_log(pam_conn, session_id, end_reason=end_reason)
    finally:
        await pam_conn.close()
