"""Faz 35 — Web SSH Terminal. Tek bir WebSocket endpoint: `WS /api/
agents/{agent_id}/ssh`. Kimlik doğrulama HTTP Bearer DEĞİL — bu
endpoint'i web UI'nin kendisi (tarayıcı sekmesi) açıyor, agent'ın
kendisi değil; mevcut Faz 28 Bearer-auth deseninin bir parçası değildir
(bkz. `docs/decisions.md` §18, bilinen risk — Auth/RBAC yok)."""

import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket

from app.agents import service
from app.agents.ssh_proxy import run_ssh_websocket_session
from app.db.agents import ensure_schema, get_connection

router = APIRouter(prefix="/api/agents")

logger = logging.getLogger(__name__)


@router.websocket("/{agent_id}/ssh")
async def agent_ssh_terminal(websocket: WebSocket, agent_id: UUID) -> None:
    """Hedef host İSTEMCİDEN ALINMAZ — yalnızca DB'de bilinen agent
    `local_ip`'si kullanılır (bkz. `app/agents/ssh_proxy.py` docstring'i
    — bu endpoint keyfi bir "SSH-anywhere" relay'ine dönüştürülemez).
    Agent'ın bilinen bir `local_ip`'si yoksa bağlantı dürüstçe reddedilir."""
    try:
        conn = await get_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi (agent-ssh)")
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Backend veritabanına erişilemedi"})
        await websocket.close()
        return
    await ensure_schema(conn)
    try:
        detail = await service.get_agent_detail(conn, agent_id)
    finally:
        await conn.close()

    if detail is None or not detail.local_ip:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "message": "Agent bulunamadı" if detail is None else "Agent'ın bilinen bir yerel IP adresi yok",
            }
        )
        await websocket.close()
        return

    await run_ssh_websocket_session(websocket, host=detail.local_ip)
