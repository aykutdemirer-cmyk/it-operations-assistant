"""Backend ile HTTP iletişimi. Bilinçli olarak `requests`/`httpx`
bağımlılığı EKLENMEDİ — stdlib `urllib.request` bu agent'ın ihtiyaç
duyduğu basit JSON POST/GET isteklerini fazladan bir bağımlılık
olmadan karşılıyor (tek dış bağımlılık `psutil` olarak kalsın diye,
bkz. `requirements.txt`).

Hiçbir yerde token/credential DEĞERİ loglanmaz (bkz. `authentication.py
::redact_token`)."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from agent.authentication import build_auth_header

logger = logging.getLogger("agent.client")

_DEFAULT_TIMEOUT_SECONDS = 10


class BackendError(Exception):
    """Tüm client hatalarının ortak üst sınıfı."""


class BackendUnavailableError(BackendError):
    """Bağlantı kurulamadı (DNS/timeout/connection refused/TLS)."""


class BackendAuthenticationError(BackendError):
    """401/403 — token geçersiz veya bu agent'a ait değil."""


class BackendValidationError(BackendError):
    """422 — gönderilen payload backend'in beklediği şemaya uymuyor."""


class BackendServerError(BackendError):
    """5xx — backend tarafında beklenmeyen bir hata."""


@dataclass
class HttpResponse:
    status: int
    body: dict[str, Any]


class BackendClient:
    """`config.AgentConfig`'ten `backend_url`/`verify_tls` alır. Her
    metod GERÇEK bir HTTP isteği yapar — hiçbir sahte/varsayılan yanıt
    üretmez; backend erişilemezse `BackendUnavailableError` fırlatır,
    çağıran taraf (bkz. `main.py`) retry/backoff uygular."""

    def __init__(self, backend_url: str, verify_tls: bool = True, timeout: int = _DEFAULT_TIMEOUT_SECONDS):
        self._backend_url = backend_url.rstrip("/")
        self._timeout = timeout
        self._ssl_context = None
        if not verify_tls:
            # Yalnızca kullanıcı AÇIKÇA `VERIFY_TLS=false` verdiğinde —
            # geliştirme/self-signed sertifika senaryosu için. Global bir
            # `ssl._create_default_https_context` değişikliği YAPILMAZ,
            # yalnızca bu client'ın kendi isteklerine özgü bir context.
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._ssl_context = ctx
            logger.warning("VERIFY_TLS=false — sertifika doğrulaması devre dışı (yalnızca geliştirme için kullanın)")

    def _request(self, method: str, path: str, *, json_body: dict | None = None, headers: dict | None = None) -> HttpResponse:
        url = f"{self._backend_url}{path}"
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url, data=data, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=self._timeout, context=self._ssl_context) as resp:
                body = _parse_json(resp.read())
                return HttpResponse(status=resp.status, body=body)
        except urllib.error.HTTPError as exc:
            body = _parse_json(exc.read())
            if exc.code in (401, 403):
                raise BackendAuthenticationError(body.get("detail", "Kimlik doğrulama başarısız")) from exc
            if exc.code == 422:
                raise BackendValidationError(body.get("detail", "Geçersiz payload")) from exc
            if exc.code >= 500:
                raise BackendServerError(f"Backend sunucu hatası: {exc.code}") from exc
            return HttpResponse(status=exc.code, body=body)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise BackendUnavailableError(f"Backend'e ulaşılamadı: {exc}") from exc

    def register(self, payload: dict) -> dict:
        response = self._request("POST", "/api/agents/register", json_body=payload)
        if "agent_id" not in response.body or "token" not in response.body:
            # Beklenmeyen şekilde bir yanıt geldi (ör. BACKEND_URL yanlışlıkla
            # backend yerine frontend'i [Next.js, genelde :3000] gösteriyor —
            # o zaman JSON değil bir HTML sayfası döner, gövde boş kalır).
            # Çıplak KeyError yerine kullanıcının anlayabileceği bir hata.
            raise BackendError(
                f"Backend'den beklenmeyen bir yanıt geldi (agent_id/token yok). "
                f"BACKEND_URL'in FastAPI backend'ine işaret ettiğinden emin olun "
                f"(genelde :8000, Next.js frontend'in :3000 portu DEĞİL)."
            )
        return response.body

    def heartbeat(self, token: str, payload: dict) -> dict:
        response = self._request(
            "POST", "/api/agents/heartbeat", json_body=payload, headers=build_auth_header(token)
        )
        return response.body

    def send_telemetry(self, token: str, agent_id: str, payload: dict) -> None:
        self._request(
            "POST", f"/api/agents/{agent_id}/telemetry", json_body=payload, headers=build_auth_header(token)
        )

    def send_inventory(self, token: str, agent_id: str, payload: dict) -> None:
        self._request(
            "POST", f"/api/agents/{agent_id}/inventory", json_body=payload, headers=build_auth_header(token)
        )

    def get_pending_commands(self, token: str, agent_id: str) -> list[dict]:
        """Faz 33 — çalıştırılmamış komutları çeker. Backend bunları
        AYNI ANDA `sent`e işaretler (bkz. `list_pending_and_mark_sent`)
        — bu çağrı idempotent DEĞİLDİR, iki kez çağrılırsa ikinci
        seferde boş liste döner."""
        response = self._request(
            "GET", f"/api/agents/{agent_id}/commands/pending", headers=build_auth_header(token)
        )
        return response.body.get("commands", [])

    def report_command_result(
        self, token: str, agent_id: str, command_id: str, status: str, result_detail: str | None
    ) -> None:
        self._request(
            "POST",
            f"/api/agents/{agent_id}/commands/{command_id}/result",
            json_body={"status": status, "result_detail": result_detail},
            headers=build_auth_header(token),
        )

    def test_connection(self) -> HttpResponse:
        """Yalnızca backend'in ayakta olup olmadığını kontrol eder —
        kimlik doğrulama gerektirmez (bkz. `main.py::cmd_test_connection`,
        asıl "authentication valid" kontrolü ayrı bir heartbeat denemesiyle
        yapılır)."""
        return self._request("GET", "/api/health")


def _parse_json(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
