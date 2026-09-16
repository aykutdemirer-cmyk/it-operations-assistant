"""Faz 76 — PAM Web Konsolu (zero-knowledge HTTPS kimlik enjeksiyonu).
Firewalla gibi yalnızca bir HTTPS web yönetim arayüzü olan cihazlara,
RDP (`guacd.py`)/SSH (`asyncssh`) ile AYNI ilkeyle erişim: kimlik
bilgisi YALNIZCA burada, sunucu-sunucu bir HTTP isteğinde çözülür,
tarayıcıya asla ulaşmaz.

RDP'nin `guacd`'si gibi HAZIR bir protokol motoru YOK — bu modül kendi,
BİLİNÇLİ olarak dar kapsamlı ters proxy'sini yazıyor (bkz. docs/
roadmap.md Faz 76 "Kapsam dışı" — tam SPA/WebSocket uyumluluğu YOK,
yalnızca düz HTML form-login + kök-göreli link yeniden yazma)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

_INPUT_TAG_RE = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""(\w[\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

# Yanıt gövdesindeki kök-göreli linkler — `href="/..."`/`src="/..."`/
# `action="/..."` — proxy önekine yeniden yazılır. Yalnızca TEK bir
# `/` ile başlayanlar eşleşir (`//cdn.example.com` gibi protokol-göreli
# mutlak URL'ler KASITLI olarak dokunulmaz — üçüncü parti CDN, proxy
# ÜZERİNDEN değil doğrudan gider, dürüst bir sınır).
_ROOT_RELATIVE_LINK_RE = re.compile(r"""(href|src|action)=(["'])/(?!/)""", re.IGNORECASE)


class WebConsoleConnectError(Exception):
    """Hedefe bağlanılamadı VEYA giriş reddedildi — ham exception detayı
    çağıran tarafa (frontend) hiçbir zaman sızdırılmaz, yalnızca bu
    mesaj döner (SNMP/LDAP/vCenter "test connection" ile AYNI ilke)."""


@dataclass
class WebConsoleTarget:
    host: str
    port: int
    verify_ssl: bool
    login_path: str
    username_field: str
    password_field: str

    @property
    def base_url(self) -> str:
        return f"https://{self.host}:{self.port}"


def _parse_input_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(tag):
        name = match.group(1).lower()
        value = match.group(2) if match.group(2) is not None else match.group(3)
        attrs[name] = value
    return attrs


def extract_hidden_fields(html: str) -> dict[str, str]:
    """Giriş sayfasındaki `<input type="hidden" name="..." value="...">`
    alanlarını (ör. CSRF token) toplar — sıra/öznitelik dizilimi
    ÖNEMSENMEZ. Hiç yoksa boş sözlük döner (çoğu basit cihaz konsolunda
    beklenen durum)."""
    fields: dict[str, str] = {}
    for tag in _INPUT_TAG_RE.findall(html):
        attrs = _parse_input_attrs(tag)
        if attrs.get("type", "").lower() == "hidden" and "name" in attrs:
            fields[attrs["name"]] = attrs.get("value", "")
    return fields


def rewrite_html_links(html: str, proxy_prefix: str) -> str:
    """Kök-göreli linkleri (`/foo` → `{proxy_prefix}/foo`) yeniden
    yazar — GERÇEK bir HTML/JS parser DEĞİL, best-effort bir regex
    (bkz. modül docstring'i — bilinçli sınır)."""
    prefix = proxy_prefix.rstrip("/")
    return _ROOT_RELATIVE_LINK_RE.sub(lambda m: f"{m.group(1)}={m.group(2)}{prefix}/", html)


def rewrite_location_header(location: str, target: WebConsoleTarget, proxy_prefix: str) -> str:
    """Bir `Location` yönlendirme header'ını proxy önekine çevirir —
    hedefin KENDİ host'una işaret eden mutlak URL'ler de (kök-göreli
    gibi) proxy'ye yönlendirilir; DIŞARIDAKİ bir host'a giderse
    OLDUĞU GİBİ bırakılır (proxy'nin bilerek dışında kalan bir akış)."""
    prefix = proxy_prefix.rstrip("/")
    if location.startswith("/") and not location.startswith("//"):
        return f"{prefix}{location}"
    if location.startswith(target.base_url):
        return f"{prefix}{location[len(target.base_url):]}"
    return location


async def establish_session(
    target: WebConsoleTarget, *, username: str, password: str, transport: httpx.BaseTransport | None = None
) -> dict[str, str]:
    """Giriş sayfasını GET edip olası gizli alanları toplar, kullanıcı
    adı/parolayla POST eder, dönen oturum çerezlerini (düz bir sözlük
    olarak — `httpx.AsyncClient` kapandıktan SONRA da kullanılabilsin
    diye) döner. Başarısızlıkta `WebConsoleConnectError`. `transport`
    yalnızca testler için (`httpx.MockTransport` — gerçek bir cihaza
    bağlanmadan giriş akışını doğrulamak için, bkz. `app/vcenter/
    client.py`'deki AYNI desen); üretim kodu HİÇBİR ZAMAN geçirmez."""
    async with httpx.AsyncClient(
        base_url=target.base_url, verify=target.verify_ssl, timeout=15, follow_redirects=False, transport=transport
    ) as client:
        try:
            login_page = await client.get(target.login_path)
        except httpx.HTTPError as exc:
            raise WebConsoleConnectError(f"Giriş sayfasına ulaşılamadı: {exc}") from exc

        hidden_fields = extract_hidden_fields(login_page.text) if login_page.status_code < 400 else {}
        form_data = {**hidden_fields, target.username_field: username, target.password_field: password}

        try:
            login_response = await client.post(target.login_path, data=form_data)
        except httpx.HTTPError as exc:
            raise WebConsoleConnectError(f"Giriş isteği başarısız: {exc}") from exc

        if login_response.status_code >= 500:
            raise WebConsoleConnectError(f"Hedef cihaz hata döndürdü: HTTP {login_response.status_code}")

        return dict(client.cookies)


async def proxy_request(
    target: WebConsoleTarget,
    cookies: dict[str, str],
    *,
    method: str,
    path: str,
    proxy_prefix: str,
    request_headers: dict[str, str] | None = None,
    content: bytes | None = None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Response:
    """Saklı oturum çerezleriyle hedefe TEK bir isteği yönlendirir —
    çağıran taraf (`app/routes/pam_web.py`) yanıt gövdesini (HTML ise
    `rewrite_html_links`, yönlendirmeyse `rewrite_location_header` ile)
    işleyip tarayıcıya döner. `transport` — bkz. `establish_session`."""
    async with httpx.AsyncClient(
        base_url=target.base_url, verify=target.verify_ssl, timeout=15, cookies=cookies, follow_redirects=False,
        transport=transport,
    ) as client:
        try:
            return await client.request(
                method, f"/{path.lstrip('/')}", headers=request_headers, content=content
            )
        except httpx.HTTPError as exc:
            raise WebConsoleConnectError(f"Hedefe istek başarısız: {exc}") from exc
