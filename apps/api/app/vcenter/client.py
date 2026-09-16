"""Faz 72 — vCenter REST API (vSphere Automation API) düşük seviyeli
istemcisi. `httpx` (proje zaten bağımlı — YENİ kütüphane EKLENMEDİ,
kullanıcının `AskUserQuestion` ile seçtiği pyVmomi/SOAP DEĞİL, REST).
Her çağrı kendi oturumunu açıp (`POST /api/session`) işini bitirince
kapatır (`DELETE /api/session`) — kalıcı bir bağlantı havuzu/arka plan
worker'ı YOK (bu fazın kapsamı yalnızca istek-anlık sorgular ve güç
işlemleri, bkz. docs/roadmap.md Faz 72 kapsam dışı)."""

from typing import Literal, TypedDict

import httpx


class VCenterConnectionParams(TypedDict):
    host: str
    port: int
    username: str
    password: str
    verify_ssl: bool


class VCenterConnectError(Exception):
    """Oturum açma, bir isteğin başarısız olması veya vCenter'ın hata
    döndürmesi — GERÇEK ayrıntı `str(exc)`'te, hiçbir yerde uydurulmuş
    bir başarı mesajına DÖNÜŞTÜRÜLMEZ (SNMP/LDAP test-connection ile
    aynı dürüstlük ilkesi)."""


def _base_url(params: VCenterConnectionParams) -> str:
    return f"https://{params['host']}:{params['port']}/api"


async def _open_session(client: httpx.AsyncClient, params: VCenterConnectionParams) -> str:
    try:
        response = await client.post(
            f"{_base_url(params)}/session",
            auth=(params["username"], params["password"]),
        )
    except httpx.HTTPError as exc:
        raise VCenterConnectError(f"vCenter'a bağlanılamadı: {exc}") from exc
    if response.status_code == 401:
        raise VCenterConnectError("Kimlik doğrulama reddedildi (kullanıcı adı/parola hatalı)")
    if response.status_code != 201 and response.status_code != 200:
        raise VCenterConnectError(f"Oturum açılamadı: HTTP {response.status_code} — {response.text[:200]}")
    token = response.json()
    if not isinstance(token, str) or not token:
        raise VCenterConnectError("vCenter beklenmeyen bir oturum yanıtı döndürdü")
    return token


async def _close_session(client: httpx.AsyncClient, params: VCenterConnectionParams, token: str) -> None:
    try:
        await client.delete(f"{_base_url(params)}/session", headers={"vmware-api-session-id": token})
    except httpx.HTTPError:
        # Oturum kapatma başarısızlığı çağıranın asıl işlemini (zaten
        # tamamlanmış) ASLA başarısız kılmamalı — vCenter'ın kendi
        # oturum zaman aşımı zaten er ya da geç temizler.
        pass


class VCenterSession:
    """`async with VCenterSession(params) as session:` — tek bir
    vCenter oturumu boyunca birden fazla istek yapmak için (ör.
    `list_vms` + her VM için `guest/identity`)."""

    def __init__(self, params: VCenterConnectionParams, *, transport: httpx.BaseTransport | None = None):
        # `transport` yalnızca testler için — gerçek bir vCenter'a
        # bağlanmadan (`httpx.MockTransport`) `_open_session`/istek
        # akışını doğrulamak amacıyla eklendi, üretim kodu HİÇBİR ZAMAN
        # geçirmiyor (varsayılan `None` → gerçek TLS bağlantısı).
        self._params = params
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None

    async def __aenter__(self) -> "VCenterSession":
        self._client = httpx.AsyncClient(verify=self._params["verify_ssl"], timeout=15, transport=self._transport)
        try:
            self._token = await _open_session(self._client, self._params)
        except VCenterConnectError:
            await self._client.aclose()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        assert self._client is not None
        if self._token is not None:
            await _close_session(self._client, self._params, self._token)
        await self._client.aclose()

    async def get(self, path: str, *, params: dict | None = None) -> object:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, *, json: dict | None = None) -> object:
        return await self._request("POST", path, json=json)

    async def _request(self, method: Literal["GET", "POST"], path: str, **kwargs: object) -> object:
        assert self._client is not None and self._token is not None
        try:
            response = await self._client.request(
                method,
                f"{_base_url(self._params)}{path}",
                headers={"vmware-api-session-id": self._token},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise VCenterConnectError(f"vCenter isteği başarısız: {exc}") from exc
        if response.status_code >= 400:
            raise VCenterConnectError(f"vCenter hatası: HTTP {response.status_code} — {response.text[:300]}")
        if not response.content:
            return None
        return response.json()
