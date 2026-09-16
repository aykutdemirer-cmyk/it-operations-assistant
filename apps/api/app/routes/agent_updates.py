"""Windows Update Tarama Motoru — Agent Lifecycle/Updates increment.

`POST /api/agents/{agent_id}/updates` — YALNIZCA Agent çağırır (Bearer
auth), `telemetry`/`inventory` ile AYNI `_authenticate`/`_require_
matching_agent` deseni (bkz. `routes/agents.py`/`routes/agent_
commands.py`). `GET /api/agents/{agent_id}/updates` — web UI çağırır,
auth YOK (mevcut `GET /api/agents/{agent_id}` ile AYNI ilke, salt-okunur
bir okuma)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException

from app.agents import service as agent_service
from app.agents.exceptions import AgentAuthenticationError, AgentNotFoundError
from app.agents.update_models import AgentWindowsUpdatesRequest, AgentWindowsUpdatesResponse
from app.db import agent_updates as updates_repo
from app.db.agents import get_agent_by_id, get_connection

router = APIRouter(prefix="/api/agents")

logger = logging.getLogger(__name__)


async def _connect():
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (agent-updates)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc
    # Şema uygulama başlangıcında tek seferlik kurulur (bkz.
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


@router.post("/{agent_id}/updates")
async def report_windows_updates(
    agent_id: UUID,
    request: AgentWindowsUpdatesRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    conn = await _connect()
    try:
        agent = await _authenticate(conn, authorization)
        _require_matching_agent(agent, agent_id)
        await updates_repo.upsert_scan_result(
            conn,
            agent_id=agent_id,
            collected_at=request.collected_at,
            scan_method=request.scan_method,
            is_admin=request.is_admin,
            updates=[u.model_dump() for u in request.updates],
            error=request.error,
            reboot_required=request.reboot_required,
        )
        return {"status": "ok"}
    finally:
        await conn.close()


@router.get("/{agent_id}/updates", response_model=AgentWindowsUpdatesResponse)
async def get_windows_updates(agent_id: UUID) -> AgentWindowsUpdatesResponse:
    """En son kaydedilmiş tarama sonucunu döner. Agent hiç tarama
    göndermemişse dürüst bir `404` (uydurma bir "unavailable" satır
    ASLA üretilmez)."""
    conn = await _connect()
    try:
        agent = await get_agent_by_id(conn, agent_id)
        if agent is None:
            raise AgentNotFoundError(f"Agent bulunamadı: {agent_id}")
        row = await updates_repo.get_scan_result(conn, agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent bulunamadı") from exc
    finally:
        await conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Bu agent için henüz bir Windows Update taraması yok")
    return AgentWindowsUpdatesResponse(**row)
