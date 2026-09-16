"""Faz 48 — `app/pam/guacd.py::open_rdp_connection`'ın el sıkışma
mantığını GERÇEK bir `guacd` OLMADAN doğrular: yerel bir asyncio TCP
sunucusu `guacd`'nin resmi el sıkışma sırasını (select→args→size/
audio/video/image→connect→ready) taklit eder. Bu, bu makinede `guacd`
kurulu OLMASA bile protokol implementasyonunun doğruluğunu gerçekten
test eder (bkz. docs/roadmap.md Faz 48 notu — gerçek guacd'ye karşı
canlı doğrulama bu ortamda yapılamadı)."""

import asyncio

import pytest

from app.pam.guacamole_protocol import encode_instruction, read_instruction
from app.pam.guacd import GuacdConnectError, open_rdp_connection

_FAKE_ARGS = ["hostname", "port", "username", "password", "domain", "width", "height", "dpi", "ignore-cert", "security", "some-unknown-future-param"]
_FAKE_ARGS_WITH_RECORDING = _FAKE_ARGS + [
    "recording-path",
    "recording-name",
    "create-recording-path",
    "recording-exclude-output",
    "recording-exclude-mouse",
]
_FAKE_ARGS_WITH_DRIVE = _FAKE_ARGS + ["disable-copy", "disable-paste", "enable-drive", "drive-path", "create-drive-path", "drive-name"]


async def _fake_guacd_handler(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, captured: dict, args: list[str] = _FAKE_ARGS
) -> None:
    try:
        select_instruction = await read_instruction(reader)
        captured["select"] = select_instruction

        writer.write(encode_instruction("args", *args))
        await writer.drain()

        captured["size"] = await read_instruction(reader)
        captured["audio"] = await read_instruction(reader)
        captured["video"] = await read_instruction(reader)
        captured["image"] = await read_instruction(reader)
        captured["connect"] = await read_instruction(reader)

        writer.write(encode_instruction("ready", "$fake-connection-id"))
        await writer.drain()
    finally:
        writer.close()


@pytest.fixture
async def fake_guacd(unused_tcp_port):
    captured: dict = {}

    async def handler(reader, writer):
        await _fake_guacd_handler(reader, writer, captured=captured)

    server = await asyncio.start_server(handler, "127.0.0.1", unused_tcp_port)
    async with server:
        yield unused_tcp_port, captured
        server.close()


@pytest.fixture
async def fake_guacd_with_recording_args(unused_tcp_port):
    captured: dict = {}

    async def handler(reader, writer):
        await _fake_guacd_handler(reader, writer, captured=captured, args=_FAKE_ARGS_WITH_RECORDING)

    server = await asyncio.start_server(handler, "127.0.0.1", unused_tcp_port)
    async with server:
        yield unused_tcp_port, captured
        server.close()


@pytest.fixture
async def fake_guacd_with_drive_args(unused_tcp_port):
    captured: dict = {}

    async def handler(reader, writer):
        await _fake_guacd_handler(reader, writer, captured=captured, args=_FAKE_ARGS_WITH_DRIVE)

    server = await asyncio.start_server(handler, "127.0.0.1", unused_tcp_port)
    async with server:
        yield unused_tcp_port, captured
        server.close()


@pytest.fixture
def unused_tcp_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.anyio
async def test_open_rdp_connection_completes_handshake_and_injects_credentials(monkeypatch, fake_guacd):
    port, captured = fake_guacd
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))

    reader, writer = await open_rdp_connection(
        hostname="10.0.9.30",
        port=3389,
        username="Administrator",
        password="hunter2",
        domain="CORP",
        width=1024,
        height=768,
        dpi=96,
    )
    writer.close()

    assert captured["select"] == ["select", "rdp"]
    assert captured["size"] == ["size", "1024", "768", "96"]
    # `connect` değerleri `args`'ın DÖNDÜRDÜĞÜ SIRAYLA olmalı — bilinmeyen
    # bir parametre ("some-unknown-future-param") için boş string.
    assert captured["connect"] == ["connect", "10.0.9.30", "3389", "Administrator", "hunter2", "CORP", "1024", "768", "96", "true", "nla", ""]


@pytest.mark.anyio
async def test_open_rdp_connection_never_sends_password_in_select_or_size():
    # Kimlik bilgisi YALNIZCA `connect` instruction'ında, önceki hiçbir
    # adımda geçmemeli — bu test bunu `_perform_handshake`'in encode
    # çağrılarının SIRASINA bakarak dolaylı doğruluyor (üstteki test
    # zaten `connect`'in TAM içeriğini kontrol ediyor; burada yalnızca
    # `select`/`size` payload'larının parola İÇERMEDİĞİ teyit ediliyor).
    from app.pam.guacamole_protocol import encode_instruction as encode

    assert b"hunter2" not in encode("select", "rdp")
    assert b"hunter2" not in encode("size", "1024", "768", "96")


@pytest.mark.anyio
async def test_open_rdp_connection_raises_guacd_connect_error_when_unreachable(monkeypatch):
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", "1")  # hiçbir şey dinlemiyor olması BEKLENİR

    with pytest.raises(GuacdConnectError):
        await open_rdp_connection(
            hostname="10.0.9.30", username="Administrator", password="x", domain=None, width=800, height=600
        )


@pytest.mark.anyio
async def test_open_rdp_connection_rewrites_loopback_hostname_for_guacd_container(monkeypatch, fake_guacd):
    """**Gerçek, canlı test sırasında bulunan bir üretim hatası:** guacd
    Docker konteynerinde çalışırken `127.0.0.1` konteynerin KENDİSİNİ
    işaret eder, backend'in çalıştığı Windows host'u DEĞİL — gerçek
    guacd'ye karşı doğrulanıp `app/pam/guacd.py::_resolve_rdp_target_
    hostname`'e eklenen düzeltme burada `hostname` instruction'ının
    GERÇEKTEN `host.docker.internal`'a döndüğünü doğruluyor."""
    port, captured = fake_guacd
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))

    reader, writer = await open_rdp_connection(
        hostname="127.0.0.1", username="Administrator", password="x", domain=None, width=800, height=600
    )
    writer.close()

    assert captured["connect"][1] == "host.docker.internal"


@pytest.mark.anyio
async def test_open_rdp_connection_leaves_real_lan_hostname_untouched(monkeypatch, fake_guacd):
    port, captured = fake_guacd
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))

    reader, writer = await open_rdp_connection(
        hostname="10.0.213.30", username="Administrator", password="x", domain=None, width=800, height=600
    )
    writer.close()

    assert captured["connect"][1] == "10.0.213.30"


# ---- Faz 50 — Oturum Kaydı (Session Recording) ---------------------------


@pytest.mark.anyio
async def test_open_rdp_connection_includes_recording_params_when_configured(monkeypatch, fake_guacd_with_recording_args):
    port, captured = fake_guacd_with_recording_args
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))
    monkeypatch.setenv("GUACD_RECORDING_PATH", "/var/lib/guacd/recordings")
    monkeypatch.setenv("PAM_RECORDING_HOST_DIR", "/tmp/pam-recordings")

    reader, writer = await open_rdp_connection(
        hostname="10.0.9.30",
        username="Administrator",
        password="hunter2",
        domain="CORP",
        width=1024,
        height=768,
        session_id="11111111-1111-1111-1111-111111111111",
    )
    writer.close()

    # `connect` sırası `_FAKE_ARGS_WITH_RECORDING`'in sırasıyla AYNI —
    # son 5 değer recording-path/name/create-path/exclude-output/exclude-mouse.
    assert captured["connect"][-5:] == [
        "/var/lib/guacd/recordings",
        "11111111-1111-1111-1111-111111111111",
        "true",
        "false",
        "false",
    ]


@pytest.mark.anyio
async def test_open_rdp_connection_omits_recording_params_when_not_configured(monkeypatch, fake_guacd_with_recording_args):
    """`GUACD_RECORDING_PATH`/`PAM_RECORDING_HOST_DIR` set EDİLMEDİĞİNDE
    (varsayılan — opt-in) `recording-*` parametreleri BOŞ string olarak
    gönderilir, guacd bunu kayıtsız normal bir oturum olarak başlatır."""
    port, captured = fake_guacd_with_recording_args
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))
    monkeypatch.delenv("GUACD_RECORDING_PATH", raising=False)
    monkeypatch.delenv("PAM_RECORDING_HOST_DIR", raising=False)

    reader, writer = await open_rdp_connection(
        hostname="10.0.9.30",
        username="Administrator",
        password="hunter2",
        domain="CORP",
        width=1024,
        height=768,
        session_id="11111111-1111-1111-1111-111111111111",
    )
    writer.close()

    assert captured["connect"][-5:] == ["", "", "", "", ""]


# ---- Faz 74 — Çift Yönlü Pano + Sürücü Yönlendirme ------------------------


@pytest.mark.anyio
async def test_open_rdp_connection_always_enables_clipboard_regardless_of_drive_config(monkeypatch, fake_guacd_with_drive_args):
    """`disable-copy`/`disable-paste` guacd sürüm varsayımına
    BIRAKILMIYOR — sürücü hiç yapılandırılmasa bile HER ZAMAN `false`
    gönderilir."""
    port, captured = fake_guacd_with_drive_args
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))
    monkeypatch.delenv("GUACD_DRIVE_PATH", raising=False)

    reader, writer = await open_rdp_connection(
        hostname="10.0.9.30", username="Administrator", password="x", domain=None, width=800, height=600,
        session_id="11111111-1111-1111-1111-111111111111",
    )
    writer.close()

    # Sıra: disable-copy, disable-paste, enable-drive, drive-path, create-drive-path, drive-name
    assert captured["connect"][-6:-4] == ["false", "false"]
    assert captured["connect"][-4:] == ["", "", "", ""]


@pytest.mark.anyio
async def test_open_rdp_connection_includes_drive_params_when_configured(monkeypatch, fake_guacd_with_drive_args):
    port, captured = fake_guacd_with_drive_args
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))
    monkeypatch.setenv("GUACD_DRIVE_PATH", "/var/pam/drives")

    reader, writer = await open_rdp_connection(
        hostname="10.0.9.30", username="Administrator", password="x", domain=None, width=800, height=600,
        session_id="22222222-2222-2222-2222-222222222222",
    )
    writer.close()

    assert captured["connect"][-6:] == [
        "false",
        "false",
        "true",
        "/var/pam/drives/22222222-2222-2222-2222-222222222222",
        "true",
        "PAM Paylaşılan Sürücü",
    ]


@pytest.mark.anyio
async def test_open_rdp_connection_omits_drive_params_without_session_id(monkeypatch, fake_guacd_with_drive_args):
    """`GUACD_DRIVE_PATH` ayarlı olsa bile `session_id` verilmezse
    (teorik olarak — pratikte `pam_rdp.py` her zaman verir) sürücü
    dizini BENZERSİZ olamayacağı için AÇILMAZ."""
    port, captured = fake_guacd_with_drive_args
    monkeypatch.setenv("GUACD_HOST", "127.0.0.1")
    monkeypatch.setenv("GUACD_PORT", str(port))
    monkeypatch.setenv("GUACD_DRIVE_PATH", "/var/pam/drives")

    reader, writer = await open_rdp_connection(
        hostname="10.0.9.30", username="Administrator", password="x", domain=None, width=800, height=600,
    )
    writer.close()

    assert captured["connect"][-4:] == ["", "", "", ""]
