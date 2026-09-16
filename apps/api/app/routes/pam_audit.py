"""Faz 46 — `/api/pam/audit`: Session Audit Log, ADMIN-only. `?active=
true` yalnızca hâlâ açık (`ended_at IS NULL`) oturumları, `?active=
false`/parametresiz TÜM geçmişi döner (bkz. `app/pam/service.py::
list_session_logs`).

Faz 50 — bu router'a canlı oturum sonlandırma, tuş logu görüntüleme ve
oturum kaydı (video) stream'i eklendi. `/sessions/active` gibi AYRI bir
namespace/router AÇILMADI — mevcut `/api/pam/audit` zaten ADMIN-only
denetim ekranının tek doğruluk kaynağı, kullanıcının önerdiği `/api/
v1/pam/sessions/*` bu projenin versiyonsuz URL şemasıyla (bkz. Faz 42
notu) uyuşmuyordu."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import FileResponse

from app.auth.dependencies import CurrentUser, get_current_user, require_permission
from app.auth.exceptions import InvalidTokenError
from app.auth.security import decode_access_token
from app.db.pam import get_connection, get_session_log
from app.db.users import get_permissions as get_user_permissions
from app.pam import session_registry
from app.pam.models import PamKeystrokeResponse, PamSessionLogResponse
from app.pam.recording_analysis import extract_activity_markers, extract_idle_gaps
from app.pam.service import SessionNotActiveError, SessionNotFoundError, list_keystrokes, list_session_logs, terminate_session

router = APIRouter(prefix="/api/pam/audit", tags=["pam"], dependencies=[Depends(require_permission("PAM_ADMIN"))])

# Faz 51 — Canlı Oturum İzleme (Shadowing) WebSocket'i. `router`'ın
# ÜZERİNDEKİ router-seviyesi `require_permission` bağımlılığı `Header`
# tabanlıdır (`Authorization: Bearer ...`) — tarayıcının native
# `WebSocket` API'si özel header GÖNDEREMEZ (bkz. `app/routes/pam_rdp.
# py`/`pam_ssh.py`'deki AYNI kısıt), bu yüzden bu route o router-
# seviyesi bağımlılığı MİRAS ALAMAZ; kendi ayrı (bağımlılıksız) router'ı
# üzerinde tanımlanıp `app/main.py`'de AYRICA include edilir, kimlik
# doğrulamayı `pam_rdp.py`/`pam_ssh.py` ile AYNI query-string JWT
# desenini elle uygulayarak yapar.
ws_router = APIRouter(prefix="/api/pam/audit", tags=["pam"])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (pam audit)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


@router.get("", response_model=list[PamSessionLogResponse])
async def list_audit_route(
    active: bool = False,
    search: str | None = None,
    protocol: str | None = None,
    reason: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[PamSessionLogResponse]:
    """Faz 54 — `search` (kullanıcı adı/cihaz/istemci IP'de serbest
    metin arama), `protocol` ('rdp'/'ssh'), `reason` (`end_reason`'ın
    kendisi), `limit`/`offset` hepsi opsiyonel — hiçbiri verilmezse
    Faz 46'daki davranışla birebir aynı."""
    conn = await _connect()
    try:
        return await list_session_logs(
            conn, active_only=active, search=search, protocol=protocol, reason=reason, limit=limit, offset=offset
        )
    finally:
        await conn.close()


@router.post("/{session_id}/terminate", response_model=PamSessionLogResponse)
async def terminate_session_route(session_id: UUID, current_user: CurrentUser = Depends(get_current_user)) -> PamSessionLogResponse:
    """Faz 50 — "Oturumu Anında Kapat". Yalnızca bu backend SÜRECİNDE
    hâlâ aktif olan (bkz. `app/pam/session_registry.py`) bir oturumu
    sonlandırabilir — bulunamazsa 409 (zaten kapanmış olabilir)."""
    conn = await _connect()
    try:
        try:
            return await terminate_session(conn, session_id, terminated_by=current_user.id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Oturum bulunamadı") from exc
        except SessionNotActiveError as exc:
            raise HTTPException(status_code=409, detail="Oturum artık aktif değil") from exc
    finally:
        await conn.close()


@router.get("/{session_id}/keystrokes", response_model=list[PamKeystrokeResponse])
async def list_session_keystrokes_route(session_id: UUID) -> list[PamKeystrokeResponse]:
    """Yalnızca SSH oturumları için satır döner — RDP oturumlarında
    boş liste (RDP'nin denetim izi `recording_file_path`'teki video
    kaydı, bkz. modül docstring'i)."""
    conn = await _connect()
    try:
        try:
            return await list_keystrokes(conn, session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Oturum bulunamadı") from exc
    finally:
        await conn.close()


@router.get("/{session_id}/recording")
async def stream_session_recording_route(session_id: UUID) -> FileResponse:
    """Kaydedilen `.guac` dosyasını (bkz. `app/pam/guacd.py::
    recording_config`) HTTP Range destekli bir dosya yanıtı olarak
    sunar — `Guacamole.SessionRecording` (frontend, `guacamole-common-
    js`) bunu bir Blob olarak indirip TARAYICIDA replay eder; sunucu
    tarafında bir video dönüştürme (ffmpeg/`guacenc`) YOK — bkz. `docs/
    roadmap.md` Faz 50 notu (kasıtlı sapma). `FileResponse` (Starlette)
    Range isteklerini KENDİLİĞİNDEN destekler, elle bir Range parser
    yazılmadı."""
    conn = await _connect()
    try:
        row = await get_session_log(conn, session_id)
    finally:
        await conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı")
    path = row["recording_file_path"]
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Bu oturum için bir video kaydı yok")
    if Path(path).stat().st_size == 0:
        # Ayrı, anlamlı bir 400 — 404 ("kayıt hiç yok") ile KARIŞTIRILMASIN:
        # dosya VAR ama boş (ör. oturum guacd bağlantısı kurulur kurulmaz
        # kesildi) — `Guacamole.SessionRecording` boş bir kayıtla
        # anlamlı bir şey yapamaz, frontend bunu ayırt edip farklı bir
        # mesaj gösterebilsin diye 404 DEĞİL 400 dönüyoruz.
        raise HTTPException(status_code=400, detail="Oturum kaydı dosyası boş")
    return FileResponse(path, media_type="application/octet-stream", filename=f"{session_id}.guac")


@router.get("/{session_id}/activity-markers", response_model=list[int])
async def list_session_activity_markers_route(session_id: UUID) -> list[int]:
    """Faz 53 — `SessionReplayModal`'ın zaman çubuğu işaretleri. Video
    kaydı yoksa (SSH oturumu veya hiç kayıt yapılmamış) boş liste döner
    — 404 DEĞİL, replay ekranı zaten aynı durumda kaydı da bulamıyor."""
    conn = await _connect()
    try:
        row = await get_session_log(conn, session_id)
    finally:
        await conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı")
    path = row["recording_file_path"]
    if not path or not Path(path).is_file():
        return []
    return await extract_activity_markers(path)


@router.get("/{session_id}/idle-gaps", response_model=list[dict])
async def list_session_idle_gaps_route(session_id: UUID) -> list[dict]:
    """Faz 75 — `SessionReplayModal`'ın "İnaktif Süreleri Atla" özelliği.
    `activity-markers` route'uyla AYNI desen — kayıt yoksa boş liste,
    404 DEĞİL."""
    conn = await _connect()
    try:
        row = await get_session_log(conn, session_id)
    finally:
        await conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı")
    path = row["recording_file_path"]
    if not path or not Path(path).is_file():
        return []
    return await extract_idle_gaps(path)


def _recording_ends_with_teardown(text: str) -> bool:
    """Faz 51 sonrası bulunan GERÇEK bir bug: guacd bir RDP oturumu
    KAPANIRKEN (ör. hedef makine RDP bağlantısını kesti, ekran kilit
    zaman aşımı, vb.) kayda TAM bir "her şeyi imha et" dizisi yazıyor —
    `dispose` instruction'larının ardışık bir dizisi, EN SONUNDA kök/
    varsayılan görüntü katmanının (`dispose,1.0` — katman indeksi `0`)
    imha edilmesiyle biter. Bu, guacd'nin STANDART bağlantı kapatma
    protokolü — birincil oturum kaydı/DB durumu HÂLÂ "aktif" görünse
    bile (bkz. bu route'un WS heartbeat/durum senkronizasyonu henüz
    bunu fark etmemiş olabilir), kaydın kendisi zaten SONA ERMİŞ bir
    oturumu temsil ediyorsa, bunu OLDUĞU GİBİ bir izleyiciye "mevcut
    ekran durumu" olarak göndermek GARANTİLİ bir siyah ekrana yol açar
    — son instruction, izleyicinin daha yeni oluşturduğu görüntüyü de
    dahil TÜM görüntüyü imha eder. Bu fonksiyon bu durumu tespit edip
    çağıran tarafın catch-up'ı ATLAMASINI (yalnızca canlı güncellemelere
    geçmesini) sağlar."""
    segments = [s for s in text.split(";") if s]
    if not segments:
        return False
    last = segments[-1]
    # Ham Guacamole tel formatı: "<uzunluk>.dispose,<uzunluk>.<değer>"
    # — kök katman "0" ise (ör. "7.dispose,1.0").
    parts = last.split(",")
    return len(parts) == 2 and parts[0].endswith(".dispose") and parts[1] == "1.0"


@ws_router.websocket("/{session_id}/shadow")
async def shadow_session_route(websocket: WebSocket, session_id: UUID, token: str | None = None) -> None:
    """Faz 51 — "Canlı İzle" (Live Session Shadowing): admin'in
    birincil RDP oturumunu ANINDA, girdi göndermeden (salt-okunur)
    izlemesi. Yalnızca RDP desteklenir (kullanıcının isteği bir
    "Guacamole izleme modalı" tanımlıyordu, SSH kapsam dışı).

    **Dürüst, belgelenmiş bir sınır:** bu proje guacd'ye DOĞRUDAN
    konuşuyor (Faz 48 — resmi `guacamole-client` web uygulaması/veritabanı
    şeması KASITLI olarak yok), guacd'nin GERÇEK "join" paylaşım
    protokolü (`guacamole-auth-jdbc`'nin paylaşım anahtarları) o Java
    web uygulamasının bir özelliği, ham guacd protokolünde YOK. Bu
    yüzden "katılma anındaki doğru ekran durumu" guacd'den DEĞİL, bu
    oturumun Faz 50 kaydından (etkinse) elde ediliyor — Oturum Kaydı
    (`GUACD_RECORDING_PATH`) etkin DEĞİLSE izleyici yalnızca katıldığı
    andan itibaren gelen güncellemeleri görür, ekran katılma anına
    kadar boş/eksik kalabilir."""
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
        conn = await get_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi (pam audit shadow)")
        await websocket.accept(subprotocol="guacamole")
        await websocket.send_text("error: Backend veritabanına erişilemedi")
        await websocket.close()
        return

    try:
        if "PAM_ADMIN" not in await get_user_permissions(conn, user_id):
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text("error: Bu işlem için yeterli yetkiniz yok")
            await websocket.close()
            return

        row = await get_session_log(conn, session_id)
        if row is None or row["protocol"] != "rdp":
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text("error: Oturum bulunamadı")
            await websocket.close()
            return
        if not session_registry.is_active(session_id):
            await websocket.accept(subprotocol="guacamole")
            await websocket.send_text("error: Bu oturum artık canlı değil")
            await websocket.close()
            return

        recording_path = row["recording_file_path"]
    finally:
        await conn.close()

    await websocket.accept(subprotocol="guacamole")
    logger.info("[SHADOW] Admin joined session %s", session_id)

    recording_found = bool(recording_path) and Path(recording_path).is_file()
    logger.info("[SHADOW] Reading catch-up from file: %s (Found: %s)", recording_path, recording_found)

    if recording_found:
        try:
            catch_up = await asyncio.to_thread(Path(recording_path).read_bytes)
            text = catch_up.decode("utf-8", errors="ignore") if catch_up else ""
            if text and _recording_ends_with_teardown(text):
                # Bkz. `_recording_ends_with_teardown` docstring'i —
                # kayıt ZATEN SONA ERMİŞ bir oturumu temsil ediyor,
                # OLDUĞU GİBİ göndermek garantili siyah ekrana yol
                # açardı. Catch-up ATLANIR, izleyici yalnızca BUNDAN
                # SONRAKİ canlı güncellemeleri görür (dürüst fallback,
                # bkz. modül docstring'i).
                logger.warning(
                    "[SHADOW] Catch-up dosyası bir oturum kapanış dizisiyle bitiyor (session=%s) — atlanıyor",
                    session_id,
                )
            elif text:
                await websocket.send_text(text)
        except OSError as exc:
            logger.warning("[SHADOW] Error reading stream: %s", exc)

    queue = session_registry.subscribe_shadow(session_id)
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            await websocket.send_text(item.decode("utf-8"))
    except Exception as exc:
        logger.info("[SHADOW] Error reading stream: %s", exc, exc_info=True)
    finally:
        logger.info("[SHADOW] Admin left session %s", session_id)
        session_registry.unsubscribe_shadow(session_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass
