"""Faz 76 — `app/pam/web_console.py` için gerçek bir hedef cihaz
OLMADAN testler: `httpx.MockTransport` (vCenter client'ındaki AYNI
desen, bkz. `app/vcenter/client.py`) gerçek bir HTML giriş formunu
taklit eder."""

import httpx
import pytest

from app.pam.web_console import (
    WebConsoleConnectError,
    WebConsoleTarget,
    establish_session,
    extract_hidden_fields,
    proxy_request,
    rewrite_html_links,
    rewrite_location_header,
)

pytestmark = pytest.mark.anyio

_TARGET = WebConsoleTarget(
    host="10.0.213.1", port=443, verify_ssl=False, login_path="/login", username_field="username", password_field="password"
)


def _transport(handler):
    return httpx.MockTransport(handler)


def test_extract_hidden_fields_finds_csrf_token_regardless_of_attribute_order():
    html = """
    <form method="post">
      <input value="abc123" name="csrf_token" type="hidden">
      <input type="hidden" name="next" value="/dashboard">
      <input type="text" name="username">
    </form>
    """
    assert extract_hidden_fields(html) == {"csrf_token": "abc123", "next": "/dashboard"}


def test_extract_hidden_fields_returns_empty_dict_when_none_present():
    assert extract_hidden_fields("<form><input type='text' name='username'></form>") == {}


def test_rewrite_html_links_rewrites_root_relative_links_only():
    html = '<a href="/dashboard">x</a><img src="/static/logo.png"><a href="//external.cdn.com/a.js">y</a><a href="https://other.example.com/z">z</a>'
    rewritten = rewrite_html_links(html, "/api/pam/web/proxy/abc")

    assert 'href="/api/pam/web/proxy/abc/dashboard"' in rewritten
    assert 'src="/api/pam/web/proxy/abc/static/logo.png"' in rewritten
    # Protokol-göreli ve tam mutlak URL'ler KASITLI dokunulmadı.
    assert "//external.cdn.com/a.js" in rewritten
    assert "https://other.example.com/z" in rewritten


def test_rewrite_location_header_rewrites_root_relative_and_same_host_absolute():
    assert rewrite_location_header("/dashboard", _TARGET, "/api/pam/web/proxy/abc") == "/api/pam/web/proxy/abc/dashboard"
    assert (
        rewrite_location_header("https://10.0.213.1:443/dashboard", _TARGET, "/api/pam/web/proxy/abc")
        == "/api/pam/web/proxy/abc/dashboard"
    )


def test_rewrite_location_header_leaves_external_host_untouched():
    assert rewrite_location_header("https://sso.example.com/auth", _TARGET, "/api/pam/web/proxy/abc") == "https://sso.example.com/auth"


async def test_establish_session_submits_hidden_fields_and_credentials():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/login":
            return httpx.Response(200, text='<input type="hidden" name="csrf_token" value="tok-1">')
        if request.method == "POST" and request.url.path == "/login":
            captured["body"] = request.read().decode()
            return httpx.Response(302, headers={"location": "/dashboard", "set-cookie": "session=xyz; Path=/"})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    cookies = await establish_session(_TARGET, username="admin", password="hunter2", transport=_transport(handler))

    assert "csrf_token=tok-1" in captured["body"]
    assert "username=admin" in captured["body"]
    assert "password=hunter2" in captured["body"]
    assert cookies["session"] == "xyz"


async def test_establish_session_works_without_hidden_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html>no hidden fields</html>")
        return httpx.Response(200, headers={"set-cookie": "session=ok; Path=/"})

    cookies = await establish_session(_TARGET, username="admin", password="x", transport=_transport(handler))

    assert cookies["session"] == "ok"


async def test_establish_session_raises_on_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(WebConsoleConnectError):
        await establish_session(_TARGET, username="admin", password="x", transport=_transport(handler))


async def test_establish_session_raises_on_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(500)

    with pytest.raises(WebConsoleConnectError):
        await establish_session(_TARGET, username="admin", password="x", transport=_transport(handler))


async def test_proxy_request_sends_stored_cookies_to_target():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    response = await proxy_request(
        _TARGET, {"session": "xyz"}, method="GET", path="/dashboard", proxy_prefix="/api/pam/web/proxy/abc",
        transport=_transport(handler),
    )

    assert response.status_code == 200
    assert "session=xyz" in captured["cookie"]


async def test_proxy_request_raises_connect_error_on_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(WebConsoleConnectError):
        await proxy_request(
            _TARGET, {}, method="GET", path="/", proxy_prefix="/api/pam/web/proxy/abc", transport=_transport(handler)
        )
