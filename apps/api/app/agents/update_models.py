"""Windows Update Tarama Motoru için Pydantic modelleri (Agent
Lifecycle/Updates increment). `app/agents/command_models.py`'deki
AYNI gerekçeyle `models.py`'den ayrı tutuldu — kendi başına ayrı bir
sorumluluk.

`scan_method` alanı `com`/`installed_hotfixes`/`unavailable` — İKİ
İLKİ FARKLI ANLAM taşır (bkz. `apps/agent/agent/collectors/
windows_updates.py` docstring'i): `com` GERÇEKTEN BEKLEYEN
güncellemeleri, `installed_hotfixes` ZATEN KURULMUŞ hotfix'leri
(COM başarısız olduğunda devreye giren, farklı semantiğe sahip bir
yedek) döner. Frontend bu ikisini AYRI etiketlerle göstermeli, asla
aynıymış gibi birleştirmemeli."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

WindowsUpdateScanMethod = Literal["com", "installed_hotfixes", "unavailable"]


class WindowsUpdateItem(BaseModel):
    kb_number: str | None = None
    title: str
    description: str | None = None
    size_bytes: int | None = None


class AgentWindowsUpdatesRequest(BaseModel):
    """Agent'ın `POST /api/agents/{agent_id}/updates` ile gönderdiği
    tam tarama sonucu — Bearer auth (telemetry/inventory ile AYNI
    desen)."""

    collected_at: datetime
    scan_method: WindowsUpdateScanMethod
    is_admin: bool
    updates: list[WindowsUpdateItem] = []
    error: str | None = None
    # `Microsoft.Update.SystemInfo().RebootRequired` — makinenin GENEL
    # bekleyen yeniden başlatma durumu, HER taramada TAZE sorgulanır
    # (bkz. `apps/agent/agent/collectors/windows_updates.py::
    # _query_reboot_required`). Bir kurulumun HEMEN ardından `true`
    # olabilir; frontend bunu görünce "⚠️ Yeniden başlatma gerekiyor"
    # uyarısı + mevcut `power_control`/`reboot` komutuna tek tıkla
    # kısayol gösterir (bkz. `AgentDetailView.tsx`).
    reboot_required: bool = False


class AgentWindowsUpdatesResponse(AgentWindowsUpdatesRequest):
    """`GET /api/agents/{agent_id}/updates` — kaydedilmiş son tarama
    sonucu, `agent_id` eklenmiş haliyle."""

    agent_id: UUID
