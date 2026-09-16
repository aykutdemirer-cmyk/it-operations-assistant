"""Faz 72 — `app/vcenter/client.py` için gerçek vCenter olmadan testler.
`httpx.MockTransport` ile GERÇEK ağ isteği hiç yapılmıyor — yalnızca
`VCenterSession`'ın oturum açma/kapatma/istek akışı doğrulanıyor."""

import httpx
import pytest

from app.vcenter.client import VCenterConnectError, VCenterConnectionParams, VCenterSession

pytestmark = pytest.mark.anyio

_PARAMS: VCenterConnectionParams = {
    "host": "vcenter.lab.local",
    "port": 443,
    "username": "admin@vsphere.local",
    "password": "s3cret",
    "verify_ssl": False,
}


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_session_opens_and_sends_session_id_header_on_requests():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session" and request.method == "POST":
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(201, json="fake-session-token")
        if request.url.path == "/api/vcenter/vm" and request.method == "GET":
            seen_headers["session_id"] = request.headers.get("vmware-api-session-id")
            return httpx.Response(200, json=[])
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with VCenterSession(_PARAMS, transport=_transport(handler)) as session:
        result = await session.get("/vcenter/vm")

    assert result == []
    assert seen_headers["session_id"] == "fake-session-token"


async def test_session_calls_delete_session_on_exit():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session" and request.method == "POST":
            return httpx.Response(201, json="tok")
        if request.url.path == "/api/session" and request.method == "DELETE":
            calls.append("logout")
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with VCenterSession(_PARAMS, transport=_transport(handler)):
        pass

    assert calls == ["logout"]


async def test_open_session_raises_connect_error_on_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with pytest.raises(VCenterConnectError, match="Kimlik doğrulama"):
        async with VCenterSession(_PARAMS, transport=_transport(handler)):
            pass


async def test_request_raises_connect_error_on_http_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session":
            return httpx.Response(201, json="tok")
        return httpx.Response(500, text="internal error")

    with pytest.raises(VCenterConnectError, match="HTTP 500"):
        async with VCenterSession(_PARAMS, transport=_transport(handler)) as session:
            await session.get("/vcenter/vm")


async def test_logout_failure_does_not_raise():
    """Oturum kapatma başarısız olsa bile (`DELETE /api/session` HTTP
    hatası) çağıranın asıl işlemi (zaten tamamlanmış) etkilenmemeli."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session" and request.method == "POST":
            return httpx.Response(201, json="tok")
        if request.url.path == "/api/session" and request.method == "DELETE":
            return httpx.Response(500)
        return httpx.Response(200, json=[])

    async with VCenterSession(_PARAMS, transport=_transport(handler)) as session:
        await session.get("/vcenter/vm")
    # __aexit__ hata fırlatmadan tamamlandı.
