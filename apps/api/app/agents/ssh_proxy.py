"""Faz 35 — Web SSH Terminal. `WS /api/agents/{id}/ssh` üzerinden gelen
bir tarayıcı bağlantısını GERÇEK bir SSH oturumuna (asyncssh) köprüler
— `xterm.js`'in ürettiği ham terminal girdisini/çıktısını olduğu gibi
aktarır, hiçbir komut/klavye girdisi burada YORUMLANMAZ.

GÜVENLİK SINIRLARI (bkz. docs/decisions.md §18):
- Kimlik bilgisi (username/password) HİÇBİR ZAMAN loglanmaz veya
  diske/DB'ye yazılmaz — yalnızca bu bağlantının ömrü boyunca bellekte
  durur, asyncssh'e geçilir, sonra referans bırakılmaz.
- Hedef HOST istemciden ALINMAZ — çağıran taraf (`routes/agent_ssh.py`)
  yalnızca DB'de bilinen agent `local_ip`'sini geçer; bu fonksiyon
  keyfi bir "SSH-anywhere" relay'i OLARAK KULLANILAMAZ.
- `known_hosts=None` BİLİNÇLİ bir tercih — hedef makinelerin SSH host
  key'lerini önceden bilme/pinleme (TOFU) mekanizması bu fazın
  kapsamı dışında bırakıldı, kullanıcıya açıkça bildirildi."""

from __future__ import annotations

import asyncio
import logging

import asyncssh
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("app.agents.ssh_proxy")

_CONNECT_TIMEOUT_SECONDS = 10
_INIT_MESSAGE_TIMEOUT_SECONDS = 30
_READ_CHUNK_SIZE = 4096


async def _safe_send_json(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_json(payload)
    except Exception:
        pass


async def _safe_close(websocket: WebSocket) -> None:
    try:
        await websocket.close()
    except Exception:
        pass


async def _relay_ssh_output(process: asyncssh.SSHClientProcess, websocket: WebSocket) -> None:
    """SSH sürecinin stdout'unu okuyup WebSocket'e ham metin olarak
    aktarır — bağlantı düşene/süreç bitene kadar sürer."""
    try:
        while True:
            chunk = await process.stdout.read(_READ_CHUNK_SIZE)
            if not chunk:
                break
            await _safe_send_json(websocket, {"type": "data", "data": chunk})
    except asyncio.CancelledError:
        raise
    except (asyncssh.Error, OSError):
        logger.debug("SSH stdout okuma sona erdi", exc_info=True)


async def run_ssh_websocket_session(websocket: WebSocket, *, host: str, port: int = 22) -> None:
    """Tek bir web SSH oturumunun tüm yaşam döngüsü. `host`/`port`
    ÇAĞIRAN TARAF tarafından (agent'ın bilinen `local_ip`'sinden)
    çözülmüş olmalı — bu fonksiyon istemciden gelen hiçbir host bilgisine
    güvenmez."""
    await websocket.accept()

    try:
        init_message = await asyncio.wait_for(
            websocket.receive_json(), timeout=_INIT_MESSAGE_TIMEOUT_SECONDS
        )
    except (TimeoutError, WebSocketDisconnect):
        await _safe_close(websocket)
        return
    except Exception:
        await _safe_send_json(websocket, {"type": "error", "message": "Geçersiz ilk mesaj"})
        await _safe_close(websocket)
        return

    if not isinstance(init_message, dict) or init_message.get("type") != "connect":
        await _safe_send_json(websocket, {"type": "error", "message": "İlk mesaj 'connect' tipinde olmalı"})
        await _safe_close(websocket)
        return

    username = init_message.get("username")
    password = init_message.get("password")
    cols = int(init_message.get("cols") or 80)
    rows = int(init_message.get("rows") or 24)

    if not username:
        await _safe_send_json(websocket, {"type": "error", "message": "Kullanıcı adı gerekli"})
        await _safe_close(websocket)
        return

    try:
        conn = await asyncio.wait_for(
            asyncssh.connect(
                host,
                port=port,
                username=username,
                password=password,
                known_hosts=None,  # bkz. modül docstring'i — TOFU/host key pinleme kapsam dışı
            ),
            timeout=_CONNECT_TIMEOUT_SECONDS,
        )
    except asyncssh.PermissionDenied:
        await _safe_send_json(websocket, {"type": "error", "message": "Kimlik doğrulama başarısız"})
        await _safe_close(websocket)
        return
    except (asyncssh.Error, OSError, TimeoutError) as exc:
        await _safe_send_json(websocket, {"type": "error", "message": f"Bağlanılamadı: {exc}"})
        await _safe_close(websocket)
        return

    try:
        process = await conn.create_process(term_type="xterm-256color", term_size=(cols, rows))
    except asyncssh.Error as exc:
        await _safe_send_json(websocket, {"type": "error", "message": f"Oturum açılamadı: {exc}"})
        conn.close()
        await _safe_close(websocket)
        return

    await _safe_send_json(websocket, {"type": "connected"})
    reader_task = asyncio.create_task(_relay_ssh_output(process, websocket))

    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            msg_type = message.get("type")
            if msg_type == "input":
                process.stdin.write(message.get("data", ""))
            elif msg_type == "resize":
                try:
                    process.change_terminal_size(int(message["cols"]), int(message["rows"]))
                except Exception:
                    logger.debug("Terminal boyutu değiştirilemedi", exc_info=True)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("SSH WebSocket oturumunda beklenmeyen hata")
    finally:
        reader_task.cancel()
        try:
            process.stdin.write_eof()
        except Exception:
            pass
        conn.close()
        await _safe_close(websocket)
