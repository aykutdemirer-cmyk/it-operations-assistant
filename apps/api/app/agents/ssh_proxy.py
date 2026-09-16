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
from typing import Awaitable, Callable

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


async def _pump_terminal_io(
    websocket: WebSocket,
    process: asyncssh.SSHClientProcess,
    *,
    on_keystroke: Callable[[str], Awaitable[None]] | None = None,
) -> None:
    """`connected` sonrası ortak G/Ç döngüsü — hem manuel-kimlik-bilgili
    (Faz 35) hem PAM zero-knowledge (Faz 46) oturumları bunu paylaşır.

    Faz 50 — `on_keystroke` verilirse, tarayıcıdan gelen HER "input"
    mesajının `data`'sı (xterm.js'in ürettiği ham klavye girdisi —
    pratikte neredeyse her tuş vuruşu kendi mesajı) bu callback'e
    iletilir (bkz. `app/pam/service.py`/`app/db/pam.py::
    insert_keystroke_chunk` — yalnızca PAM zero-knowledge SSH oturumları
    bunu geçer, Faz 35'in manuel-kimlik-bilgili akışı GEÇMEZ)."""
    reader_task = asyncio.create_task(_relay_ssh_output(process, websocket))
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            msg_type = message.get("type")
            if msg_type == "input":
                data = message.get("data", "")
                process.stdin.write(data)
                if on_keystroke is not None and data:
                    await on_keystroke(data)
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


async def run_pam_ssh_websocket_session(
    websocket: WebSocket,
    *,
    host: str,
    port: int = 22,
    username: str,
    password: str | None = None,
    private_key: str | None = None,
    passphrase: str | None = None,
    max_session_duration_mins: int,
    on_keystroke: Callable[[str], Awaitable[None]] | None = None,
    kill_event: asyncio.Event | None = None,
) -> str:
    """Faz 46 — Zero-Knowledge PAM SSH oturumu. `run_ssh_websocket_
    session`'ın AKSİNE, kimlik bilgisi istemciden HİÇ ALINMAZ — çağıran
    taraf (`app/routes/agent_ssh.py::pam_ssh_terminal`) `app/pam/
    service.py::authorize_ssh_session`'dan ÇÖZÜLMÜŞ kimlik bilgisini
    geçirir; tarayıcıya parola/anahtar DEĞERİ hiçbir zaman gönderilmez.
    `max_session_duration_mins` doldığunda oturum sunucu tarafından
    kapatılır (kullanıcı isterse daha erken de kapatabilir).

    Faz 50 — `on_keystroke` bkz. `_pump_terminal_io`. `kill_event`
    verilirse (bkz. `app/pam/session_registry.py`) admin'in "Oturumu
    Kapat" eylemi bu oturumu da `asyncio.wait(FIRST_COMPLETED)`'a
    üçüncü bir bekleyici olarak eklenerek ANINDA sonlandırabilir.

    Dönüş değeri `end_reason` (`"user_closed"`/`"timeout"`/`"error"`/
    `"terminated_by_admin"`) — çağıran taraf bunu `pam_session_logs`'a
    yazar."""
    await websocket.accept()

    try:
        init_message = await asyncio.wait_for(
            websocket.receive_json(), timeout=_INIT_MESSAGE_TIMEOUT_SECONDS
        )
    except (TimeoutError, WebSocketDisconnect):
        await _safe_close(websocket)
        return "error"
    except Exception:
        await _safe_send_json(websocket, {"type": "error", "message": "Geçersiz ilk mesaj"})
        await _safe_close(websocket)
        return "error"

    if not isinstance(init_message, dict) or init_message.get("type") != "connect":
        await _safe_send_json(websocket, {"type": "error", "message": "İlk mesaj 'connect' tipinde olmalı"})
        await _safe_close(websocket)
        return "error"

    cols = int(init_message.get("cols") or 80)
    rows = int(init_message.get("rows") or 24)

    client_keys = []
    if private_key:
        try:
            client_keys = [asyncssh.import_private_key(private_key, passphrase=passphrase)]
        except asyncssh.KeyImportError:
            await _safe_send_json(websocket, {"type": "error", "message": "Kasadaki SSH anahtarı okunamadı"})
            await _safe_close(websocket)
            return "error"

    try:
        conn = await asyncio.wait_for(
            asyncssh.connect(
                host,
                port=port,
                username=username,
                password=password if not client_keys else None,
                client_keys=client_keys or None,
                known_hosts=None,  # bkz. modül docstring'i — TOFU/host key pinleme kapsam dışı
            ),
            timeout=_CONNECT_TIMEOUT_SECONDS,
        )
    except asyncssh.PermissionDenied:
        await _safe_send_json(websocket, {"type": "error", "message": "Kimlik doğrulama başarısız"})
        await _safe_close(websocket)
        return "error"
    except (asyncssh.Error, OSError, TimeoutError) as exc:
        await _safe_send_json(websocket, {"type": "error", "message": f"Bağlanılamadı: {exc}"})
        await _safe_close(websocket)
        return "error"

    try:
        process = await conn.create_process(term_type="xterm-256color", term_size=(cols, rows))
    except asyncssh.Error as exc:
        await _safe_send_json(websocket, {"type": "error", "message": f"Oturum açılamadı: {exc}"})
        conn.close()
        await _safe_close(websocket)
        return "error"

    await _safe_send_json(websocket, {"type": "connected"})

    io_task = asyncio.create_task(_pump_terminal_io(websocket, process, on_keystroke=on_keystroke))
    kill_task = asyncio.create_task(kill_event.wait()) if kill_event is not None else None
    waiters = {io_task} | ({kill_task} if kill_task is not None else set())
    end_reason = "user_closed"
    try:
        done, pending = await asyncio.wait(
            waiters, timeout=max_session_duration_mins * 60, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            end_reason = "timeout"
            await _safe_send_json(websocket, {"type": "error", "message": "Oturum süresi doldu — bağlantı kapatıldı"})
        elif kill_task is not None and kill_task in done:
            end_reason = "terminated_by_admin"
        io_task.cancel()
        if kill_task is not None:
            kill_task.cancel()
    finally:
        conn.close()
        await _safe_close(websocket)

    return end_reason
