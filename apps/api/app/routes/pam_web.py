"""Faz 76 — PAM Web Konsolu: `POST /api/pam/web/{asset_id}/session`
GERÇEK bir HTTP oturumu kurar (giriş formuna kimlik bilgisini sunucu
tarafında enjekte eder, bkz. `app/pam/web_console.py`), dönen opak
`session_id` `ANY /api/pam/web/proxy/{session_id}/{path}` üzerinden
hedefe ters-proxy'lenir — tarayıcı kimlik bilgisi DEĞERİNİ hiçbir zaman
görmez. Admin profil CRUD'u (`/api/pam/web/profiles/{asset_id}`) AYNI
dosyada, `PAM_ADMIN`."""

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth.dependencies import CurrentUser, require_permission
from app.db.assets import get_connection as get_assets_connection
from app.db.pam import (
    close_session_log,
    delete_web_console_profile,
    get_connection as get_pam_connection,
    get_web_console_profile,
    insert_session_log,
    upsert_web_console_profile,
)
from app.pam.models import WebConsoleProfileRequest, WebConsoleProfileResponse, WebConsoleSessionResponse
from app.pam.service import SshNotAuthorizedError, WebConsoleNotConfiguredError, authorize_web_session
from app.pam.web_console import WebConsoleConnectError, WebConsoleTarget, establish_session, proxy_request, rewrite_html_links, rewrite_location_header
from app.pam import web_console_sessions

router = APIRouter(prefix="/api/pam/web", tags=["pam"])

logger = logging.getLogger(__name__)

# Bir proxy isteğinin gerçek hedefe forward EDİLMEYECEK, tarayıcı↔bizim
# aramızda kalması gereken "hop-by-hop" header'ları (HTTP/1.1 RFC 7230
# §6.1) + hedefin kendi çerez/karışıklık başlıkları (biz kendi
# çerezlerimizi `proxy_request`'in KENDİSİ enjekte ediyor).
_STRIP_REQUEST_HEADERS = {"host", "cookie", "authorization", "content-length", "connection"}
_STRIP_RESPONSE_HEADERS = {
    "content-length", "content-encoding", "transfer-encoding", "connection",
    # Hedefin KENDİ X-Frame-Options/CSP'si bizim iframe'imizi ENGELLER —
    # içerik artık BİZİM origin'imizden servis edildiği için bunlar
    # anlamsız, kaldırılmazsa tarayıcı proxy'lenen sayfayı gösteremez.
    "x-frame-options", "content-security-policy",
}


def _profile_to_response(row) -> WebConsoleProfileResponse:
    return WebConsoleProfileResponse(
        asset_id=row["asset_id"],
        port=row["port"],
        verify_ssl=row["verify_ssl"],
        login_path=row["login_path"],
        username_field=row["username_field"],
        password_field=row["password_field"],
        updated_at=row["updated_at"],
    )


@router.get("/profiles/{asset_id}", response_model=WebConsoleProfileResponse | None, dependencies=[Depends(require_permission("PAM_ADMIN"))])
async def get_web_console_profile_route(asset_id: UUID) -> WebConsoleProfileResponse | None:
    conn = await get_pam_connection()
    try:
        row = await get_web_console_profile(conn, asset_id)
    finally:
        await conn.close()
    return _profile_to_response(row) if row is not None else None


@router.put("/profiles/{asset_id}", response_model=WebConsoleProfileResponse)
async def upsert_web_console_profile_route(
    asset_id: UUID, payload: WebConsoleProfileRequest, current_user: CurrentUser = Depends(require_permission("PAM_ADMIN"))
) -> WebConsoleProfileResponse:
    conn = await get_pam_connection()
    try:
        row = await upsert_web_console_profile(
            conn,
            asset_id=asset_id,
            port=payload.port,
            verify_ssl=payload.verify_ssl,
            login_path=payload.login_path,
            username_field=payload.username_field,
            password_field=payload.password_field,
            created_by=current_user.id,
        )
    finally:
        await conn.close()
    return _profile_to_response(row)


@router.delete("/profiles/{asset_id}", status_code=204, dependencies=[Depends(require_permission("PAM_ADMIN"))])
async def delete_web_console_profile_route(asset_id: UUID) -> None:
    conn = await get_pam_connection()
    try:
        await delete_web_console_profile(conn, asset_id)
    finally:
        await conn.close()


@router.post("/{asset_id}/session", response_model=WebConsoleSessionResponse)
async def start_web_console_session_route(
    asset_id: UUID, current_user: CurrentUser = Depends(require_permission("PAM_ACCESS"))
) -> WebConsoleSessionResponse:
    pam_conn = await get_pam_connection()
    try:
        try:
            authorization = await authorize_web_session(pam_conn, user_id=current_user.id, asset_id=asset_id)
        except SshNotAuthorizedError:
            raise HTTPException(status_code=403, detail="Bu cihaza web konsolu erişim yetkiniz yok")
        except WebConsoleNotConfiguredError:
            raise HTTPException(status_code=409, detail="Bu cihaz için web konsolu henüz yapılandırılmadı")

        assets_conn = await get_assets_connection()
        try:
            asset = await assets_conn.fetchrow("SELECT ip_address FROM assets WHERE id = $1", asset_id)
        finally:
            await assets_conn.close()
        if asset is None or asset["ip_address"] is None:
            raise HTTPException(status_code=409, detail="Cihazın bilinen bir IP adresi yok")

        target = WebConsoleTarget(
            host=str(asset["ip_address"]),
            port=authorization.profile["port"],
            verify_ssl=authorization.profile["verify_ssl"],
            login_path=authorization.profile["login_path"],
            username_field=authorization.profile["username_field"],
            password_field=authorization.profile["password_field"],
        )

        try:
            cookies = await establish_session(target, username=authorization.username, password=authorization.password)
        except WebConsoleConnectError as exc:
            logger.warning("PAM web konsolu girişi başarısız: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc))

        session_log = await insert_session_log(
            pam_conn,
            user_id=current_user.id,
            asset_id=asset_id,
            credential_id=authorization.credential_id,
            protocol="web",
            client_ip=None,
        )
        session_id = session_log["id"]

        web_console_sessions.register(
            session_id,
            user_id=current_user.id,
            target=target,
            cookies=cookies,
            ttl_seconds=authorization.max_session_duration_mins * 60,
        )
    finally:
        await pam_conn.close()

    return WebConsoleSessionResponse(
        session_id=session_id,
        proxy_url=f"/api/pam/web/proxy/{session_id}/",
        max_session_duration_mins=authorization.max_session_duration_mins,
    )


@router.post("/{session_id}/close", status_code=204)
async def close_web_console_session_route(session_id: UUID) -> None:
    web_console_sessions.unregister(session_id)
    conn = await get_pam_connection()
    try:
        await close_session_log(conn, session_id, end_reason="user_closed")
    finally:
        await conn.close()


@router.api_route(
    "/proxy/{session_id}/{path:path}",
    methods=["GET"],
    operation_id="proxy_web_console_route_get",
)
@router.api_route(
    "/proxy/{session_id}/{path:path}",
    methods=["POST"],
    operation_id="proxy_web_console_route_post",
)
@router.api_route(
    "/proxy/{session_id}/{path:path}",
    methods=["PUT"],
    operation_id="proxy_web_console_route_put",
)
@router.api_route(
    "/proxy/{session_id}/{path:path}",
    methods=["DELETE"],
    operation_id="proxy_web_console_route_delete",
)
@router.api_route(
    "/proxy/{session_id}/{path:path}",
    methods=["PATCH"],
    operation_id="proxy_web_console_route_patch",
)
async def proxy_web_console_route(session_id: UUID, path: str, request: Request) -> Response:
    """Kimlik doğrulaması BURADA `Authorization` header'ıyla DEĞİL —
    `session_id`'nin kendisiyle yapılır (bkz. `web_console_sessions.py`
    docstring'i, RDP/SSH'ın JWT-query-string ödünleşimiyle AYNI
    gerekçe: `<iframe src>` özel header taşıyamaz)."""
    session = web_console_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı veya süresi doldu")

    body = await request.body()
    forward_headers = {k: v for k, v in request.headers.items() if k.lower() not in _STRIP_REQUEST_HEADERS}
    proxy_prefix = f"/api/pam/web/proxy/{session_id}"

    try:
        target_response = await proxy_request(
            session.target,
            session.cookies,
            method=request.method,
            path=path,
            proxy_prefix=proxy_prefix,
            request_headers=forward_headers,
            content=body or None,
        )
    except WebConsoleConnectError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    response_headers = {k: v for k, v in target_response.headers.items() if k.lower() not in _STRIP_RESPONSE_HEADERS}
    if "location" in target_response.headers:
        response_headers["location"] = rewrite_location_header(
            target_response.headers["location"], session.target, proxy_prefix
        )

    content_type = target_response.headers.get("content-type", "")
    if "text/html" in content_type:
        body_text = rewrite_html_links(target_response.text, proxy_prefix)
        return Response(content=body_text, status_code=target_response.status_code, headers=response_headers, media_type=content_type)

    return Response(content=target_response.content, status_code=target_response.status_code, headers=response_headers, media_type=content_type or None)
