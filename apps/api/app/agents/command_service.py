"""Faz 33 — komut oluşturma/işleme iş mantığı. Backend burada yalnızca
KABA (coarse) bir ön-kontrol yapar (ör. PID <= 4) — OTORİTER blacklist
kontrolü Agent tarafındadır (`apps/agent/agent/commands.py`), çünkü
backend hedef makinenin gerçek süreç/servis isimlerini BİLEMEZ (bkz.
docs/decisions.md §17)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.agents.command_models import AgentCommandRequest, AgentCommandSummary
from app.agents.exceptions import AgentNotFoundError
from app.db import agent_commands as commands_repo
from app.db.agents import get_agent_by_id

# Backend'in bilebileceği, platform-bağımsız BARİZ sistem PID'leri —
# gerçek süreç adı listesi (svchost.exe, System, vb.) yalnızca Agent
# tarafında biliniyor, burada tekrarlanmıyor.
_OBVIOUS_SYSTEM_PIDS = {"0", "1", "4"}


def _coarse_rejection_reason(request: AgentCommandRequest) -> str | None:
    if request.command_type == "kill_process" and request.target in _OBVIOUS_SYSTEM_PIDS:
        return f"PID {request.target} sistem süreci olarak biliniyor — reddedildi"
    if request.command_type == "kill_process":
        try:
            pid = int(request.target)
        except ValueError:
            return "PID sayısal olmalı"
        if pid < 0:
            return "PID negatif olamaz"
    return None


async def submit_command(
    conn: asyncpg.Connection, agent_id: UUID, request: AgentCommandRequest
) -> AgentCommandSummary:
    request.validate_action_matches_type()

    agent = await get_agent_by_id(conn, agent_id)
    if agent is None:
        raise AgentNotFoundError(f"Agent bulunamadı: {agent_id}")

    reason = _coarse_rejection_reason(request)
    if reason is not None:
        row = await commands_repo.create_rejected_command(
            conn,
            agent_id=agent_id,
            command_type=request.command_type,
            action=request.action,
            target=request.target,
            requested_by=request.requested_by,
            reason=reason,
        )
        return AgentCommandSummary.from_row(row)

    row = await commands_repo.create_command(
        conn,
        agent_id=agent_id,
        command_type=request.command_type,
        action=request.action,
        target=request.target,
        requested_by=request.requested_by,
    )
    return AgentCommandSummary.from_row(row)


async def list_commands(conn: asyncpg.Connection, agent_id: UUID) -> list[AgentCommandSummary]:
    rows = await commands_repo.list_commands_for_agent(conn, agent_id)
    return [AgentCommandSummary.from_row(row) for row in rows]
