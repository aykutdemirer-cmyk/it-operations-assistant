"""Agent kimliğinin (agent_id + token) yerel olarak saklanması.

Backend Faz 28'de token'ı yalnızca `POST /api/agents/register`
yanıtında BİR KEZ döner — bir daha asla görünmez (bkz. `apps/api/app/
agents/authentication.py`). Bu modül, `.env`'de `AGENT_ID`/`AGENT_TOKEN`
açıkça verilmemişse, agent'ın kendi kendine kaydolduğunda aldığı
kimliği yerel bir dosyaya kalıcı olarak yazar — böylece agent her
başlatıldığında YENİDEN kayıt olmaz (her yeniden başlatmada yeni bir
agent_id üretmek, backend'de aynı makine için sonsuz "ghost" agent
kaydı biriktirirdi).

Dosya izinleri mümkün olan en dar haliyle ayarlanır (yalnızca sahip
okuyabilir/yazabilir, Linux'ta `chmod 600`; Windows'ta ACL API'leri
gerektirmeden dosya sistemi varsayılanına bırakılır — Windows'ta kullanıcı
profili zaten diğer kullanıcılardan izole).

Token hiçbir zaman loglanmaz — `redact_token()` yalnızca son 4 karakteri
gösterir (debug/log çıktısında "bu token doğru mu" diye teyit etmek
için yeterli, tam değeri sızdırmaz)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path


def redact_token(token: str | None) -> str:
    if not token:
        return "(yok)"
    if len(token) <= 4:
        return "****"
    return f"****{token[-4:]}"


def load_local_state(path: Path) -> dict | None:
    """Daha önce kaydedilmiş `{agent_id, token}`'ı okur — dosya yoksa
    veya bozuksa `None` döner (hata fırlatmaz, çağıran taraf yeniden
    kayıt akışına düşer)."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or "agent_id" not in data or "token" not in data:
        return None
    return data


def save_local_state(path: Path, *, agent_id: str, token: str) -> None:
    """`{agent_id, token}`'ı yerel dosyaya yazar, mümkün olduğunca dar
    izinlerle (bkz. modül docstring'i)."""
    payload = json.dumps({"agent_id": agent_id, "token": token})
    path.write_text(payload, encoding="utf-8")
    if os.name != "nt":
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # dosya sistemi izin değişikliğini desteklemiyor olabilir


def build_auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
