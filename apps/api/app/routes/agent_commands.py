"""Faz 33 — Remote Command Execution: process kill / service control.

İki AYRI erişim yolu var:
- `POST/GET .../commands` — web UI çağırır, auth YOK (bkz. docs/
  decisions.md §17 — bilinen, kullanıcıya açıkça bildirilmiş risk;
  Faz 13 Auth/RBAC'tan önce bu API'ye erişen herkes komut oluşturabilir).
- `GET .../commands/pending` + `POST .../commands/{id}/result` —
  YALNIZCA Agent çağırır, Bearer auth ZORUNLU (mevcut heartbeat/
  telemetry/inventory endpoint'leriyle AYNI `_authenticate`/
  `_require_matching_agent` deseni, bkz. `routes/agents.py`)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException

from app.agents import command_service as service
from app.agents import service as agent_service
from app.agents.command_models import (
    AgentCommandRequest,
    AgentCommandSummary,
    CommandResultRequest,
    PendingCommand,
    PendingCommandsResponse,
)
from app.agents.exceptions import AgentAuthenticationError, AgentNotFoundError
from app.db import agent_commands as commands_repo
from app.db.agents import get_connection

router = APIRouter(prefix="/api/agents")

logger = logging.getLogger(__name__)


async def _connect():
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (agent-commands)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc
    # Şema artık uygulama başlangıcında tek seferlik kurulur (bkz.
    # `app/main.py::_ensure_schema_once`).
    return conn


async def _authenticate(conn, authorization: str | None) -> dict:
    try:
        return await agent_service.authenticate(conn, authorization)
    except AgentAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Kimlik doğrulama başarısız") from exc


def _require_matching_agent(agent: dict, agent_id: UUID) -> None:
    if agent["id"] != agent_id:
        raise HTTPException(status_code=403, detail="Token bu agent'a ait değil")


@router.post("/{agent_id}/commands", response_model=AgentCommandSummary, status_code=201)
async def create_command(agent_id: UUID, request: AgentCommandRequest) -> AgentCommandSummary:
    """Web UI'den tetiklenir. Backend yalnızca KABA bir ön-kontrol
    yapar (ör. PID<=4) — otoriter blacklist Agent'ta (bkz. `apps/agent/
    agent/commands.py`). Komut hemen çalışmaz; `status=pending` olarak
    kaydedilir, Agent'ın bir sonraki command-poll turunda çekilir."""
    conn = await _connect()
    try:
        try:
            return await service.submit_command(conn, agent_id, request)
        except AgentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Agent bulunamadı") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await conn.close()


@router.get("/{agent_id}/commands", response_model=list[AgentCommandSummary])
async def list_commands(agent_id: UUID) -> list[AgentCommandSummary]:
    """Son 100 komut — en yeni önce. Minimal audit görünümü (kim/ne
    zaman/hangi hedefe/ne sonuçla)."""
    conn = await _connect()
    try:
        return await service.list_commands(conn, agent_id)
    finally:
        await conn.close()


@router.get("/{agent_id}/commands/pending", response_model=PendingCommandsResponse)
async def get_pending_commands(
    agent_id: UUID, authorization: str | None = Header(default=None)
) -> PendingCommandsResponse:
    """YALNIZCA Agent çağırır (Bearer auth). Dönen komutlar aynı anda
    `sent`e işaretlenir — aynı komut iki kere çekilip iki kere
    çalıştırılmasın diye (bkz. `list_pending_and_mark_sent`)."""
    conn = await _connect()
    try:
        agent = await _authenticate(conn, authorization)
        _require_matching_agent(agent, agent_id)
        rows = await commands_repo.list_pending_and_mark_sent(conn, agent_id)
        return PendingCommandsResponse(commands=[PendingCommand(**row) for row in rows])
    finally:
        await conn.close()


@router.post("/{agent_id}/commands/{command_id}/result")
async def report_command_result(
    agent_id: UUID,
    command_id: UUID,
    request: CommandResultRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    """YALNIZCA Agent çağırır (Bearer auth) — komutu çalıştırdıktan
    sonra gerçek sonucu bildirir. `extract_bearer_token`/token eşleşmesi
    zaten `_require_matching_agent`'la garanti edildiği için buradaki
    `command_id`'nin GERÇEKTEN bu agent'a ait olup olmadığını da ayrıca
    doğrulamamız gerekir — aksi halde bir agent BAŞKA bir agent'ın
    komut sonucunu üzerine yazabilir."""
    conn = await _connect()
    try:
        agent = await _authenticate(conn, authorization)
        _require_matching_agent(agent, agent_id)

        command = await commands_repo.get_command(conn, command_id)
        if command is None or command["agent_id"] != agent_id:
            raise HTTPException(status_code=404, detail="Komut bulunamadı")

        await commands_repo.complete_command(
            conn, command_id=command_id, status=request.status, result_detail=request.result_detail
        )
        return {"status": "ok"}
    finally:
        await conn.close()
