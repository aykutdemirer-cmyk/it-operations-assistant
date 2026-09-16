"""Faz 33 — Remote Command Execution (process kill / service control)
için Pydantic modelleri. `app/agents/models.py`'den KASITLI olarak ayrı
tutuldu — o dosya zaten büyük (223 satır) ve bu yeni özellik kendi
başına ayrı bir sorumluluk (bkz. CLAUDE.md: her modül tek sorumluluk
taşır)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

CommandType = Literal[
    "kill_process", "service_control", "refresh_inventory", "power_control", "uninstall_service", "update_self",
    "check_updates", "install_update",
]
CommandAction = Literal[
    "kill", "start", "stop", "restart", "collect", "reboot", "shutdown", "logoff", "uninstall", "update", "scan",
    "install",
]
CommandStatus = Literal["pending", "sent", "succeeded", "failed", "rejected"]

_VALID_ACTIONS_BY_TYPE: dict[str, set[str]] = {
    "kill_process": {"kill"},
    "service_control": {"start", "stop", "restart"},
    # Faz 33.1 — "Yenile" butonu: agent'a envanterini HEMEN göndermesini
    # ister, hedef (`target`) bir süreç/servis DEĞİLDİR (sabit "inventory").
    "refresh_inventory": {"collect"},
    # Faz 37 — Güç ve Oturum Yönetimi. `target`: yalnızca `logoff`
    # (Linux'ta hedef kullanıcı adı) anlamlıdır; `reboot`/`shutdown`
    # için anlamsızdır ama Pydantic validator'ı boş string kabul
    # etmediği için frontend sabit `"system"` gönderir (bkz.
    # `apps/agent/agent/commands.py::control_power`).
    "power_control": {"reboot", "shutdown", "logoff"},
    # Lifecycle Management — Uzaktan Silme/Güncelleme. `target` her
    # ikisi için de anlamsız (tek bir kendi agent süreci) ama validator
    # boş string kabul etmediği için sabit `"self"` gönderilir (bkz.
    # `app/agents/service.py::delete_agent`/`trigger_agent_update`).
    "uninstall_service": {"uninstall"},
    "update_self": {"update"},
    # Windows Update Tarama Motoru — "Güncellemeleri Kontrol Et" butonu.
    # `refresh_inventory` ile AYNI gerekçeyle `target` anlamsız (sabit
    # "self" — agent kendi makinesini tarar, backend hedef seçmez).
    "check_updates": {"scan"},
    # Windows Update Yükleme — `target`: belirli bir KB numarası (ör.
    # `"KB5001234"`) veya bekleyen TÜM güncellemeler için `"all"`.
    # Geri dönüşü OLMAYAN, GERÇEK bir sistem değişikliği — frontend
    # `kill_process`/`service_control`/`power_control` ile AYNI
    # `ConfirmModal` zorunluluğunu uygular.
    "install_update": {"install"},
}


class AgentCommandRequest(BaseModel):
    """Web UI'den gelen komut isteği. `requested_by` şimdilik serbest
    metin (Faz 13 Auth/RBAC'tan önce gerçek bir kullanıcı kimliği yok —
    frontend en fazla bir görünen ad/IP geçebilir, `None` de kabul
    edilir)."""

    command_type: CommandType
    action: CommandAction
    target: str
    requested_by: str | None = None

    @field_validator("target")
    @classmethod
    def _target_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("target boş olamaz")
        return stripped

    def validate_action_matches_type(self) -> None:
        """`kill_process` yalnızca `kill`, `service_control` yalnızca
        `start`/`stop`/`restart` kabul eder — Pydantic `Literal` bunu
        alan bazında zaten kısıtlıyor ama ikisi arasındaki eşleşmeyi
        (ör. `kill_process` + `restart`) ayrıca burada kontrol ederiz."""
        if self.action not in _VALID_ACTIONS_BY_TYPE[self.command_type]:
            raise ValueError(f"'{self.action}' aksiyonu '{self.command_type}' için geçerli değil")


class AgentCommandSummary(BaseModel):
    id: UUID
    agent_id: UUID
    command_type: CommandType
    action: CommandAction
    target: str
    status: CommandStatus
    result_detail: str | None
    requested_by: str | None
    created_at: datetime
    sent_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_row(cls, row: dict) -> "AgentCommandSummary":
        return cls(**row)


class PendingCommand(BaseModel):
    """Agent'ın `GET .../commands/pending` ile aldığı, çalıştırması
    gereken minimal komut şekli — audit alanları (requested_by,
    created_at) agent için gereksiz, gönderilmez."""

    id: UUID
    command_type: CommandType
    action: CommandAction
    target: str


class PendingCommandsResponse(BaseModel):
    commands: list[PendingCommand]


class CommandResultRequest(BaseModel):
    status: Literal["succeeded", "failed"]
    result_detail: str | None = None
