"""Faz 48 — `guacd` (Guacamole Daemon) ile TCP üzerinden GERÇEK RDP
bağlantısı kuran istemci tarafı. `guacd` kendisi bu projeye dahil
DEĞİL — ayrı, Linux-native bir servis (bkz. `infra/docker-compose.yml`,
Docker Desktop/WSL2 üzerinde container olarak GERÇEKTEN çalıştırılıp
canlı doğrulandı — bkz. docs/roadmap.md Faz 48 notu). Bu modül guacd'ye
bağlanıp el sıkışmayı (handshake) yapar; el sıkışma bittikten SONRA
çağıran taraf (`app/routes/pam_rdp.py`) ham baytları WebSocket ↔ guacd
arasında olduğu gibi köprüler.

**Zero-Knowledge enjeksiyon burada gerçekleşir:** `connect`
instruction'ındaki `password` değeri kasadan ÇÖZÜLMÜŞ gerçek parola —
tarayıcıya (WebSocket'in KARŞI ucu) hiçbir zaman gönderilmez, yalnızca
guacd'ye, sunucu-sunucu TCP bağlantısı üzerinden."""

from __future__ import annotations

import asyncio
import logging
import os
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from app.pam import session_registry
from app.pam.guacamole_protocol import (
    GuacamoleProtocolError,
    encode_instruction,
    read_instruction,
    split_complete_instructions,
)

logger = logging.getLogger("app.pam.guacd")

_READ_CHUNK_SIZE = 8192

# guacd varsayılan portu resmi Guacamole dokümantasyonunda SABİT 4822 —
# `GUACD_PORT` yalnızca ileri düzey/alışılmadık kurulumlar için
# override edilebilir.
_DEFAULT_GUACD_HOST = "127.0.0.1"
_DEFAULT_GUACD_PORT = 4822
_HANDSHAKE_TIMEOUT_SECONDS = 10

# guacd'nin `image`/`audio`/`video` el sıkışma adımlarında beklediği
# desteklenen mimetype listeleri — bu artırımda yalnızca statik
# görüntü/klavye/fare desteklenir, ses/video KASITLI olarak boş
# bırakıldı (bkz. docs/roadmap.md Faz 48 — kapsam dışı).
_SUPPORTED_IMAGE_MIMETYPES = ["image/jpeg", "image/png"]


def guacd_address() -> tuple[str, int]:
    host = os.environ.get("GUACD_HOST", _DEFAULT_GUACD_HOST)
    port = int(os.environ.get("GUACD_PORT", str(_DEFAULT_GUACD_PORT)))
    return host, port


def _resolve_rdp_target_hostname(hostname: str) -> str:
    """**Gerçek, canlı test sırasında bulunan bir üretim hatası:**
    `assets.ip_address` bu backend sürecinin KENDİ makinesini işaret
    ediyorsa (`127.0.0.1`/`localhost` — ör. Agent'ın kendi `local_ip`'si)
    guacd'ye OLDUĞU GİBİ geçilirse guacd bunu KENDİ konteynerinin loopback
    adresi sanır (Docker ağ izolasyonu — konteyner içindeki `127.0.0.1`
    HOST makineyi DEĞİL, konteynerin kendisini işaret eder), RDP sunucusu
    orada YOK, guacd `"Server refused connection (wrong security type?)"`
    gibi YANILTICI bir hata veriyordu. Docker Desktop (bu ortam) host
    makineye özel bir DNS adı sağlıyor — `host.docker.internal` — gerçek
    guacd konteynerine karşı BUNUNLA test edilip doğrulandı (bkz.
    docs/roadmap.md Faz 48 notu). Yalnızca loopback adresler için
    devreye girer; gerçek bir LAN IP'si (ör. `10.0.213.x`) HİÇ
    DOKUNULMADAN geçer — o zaten guacd konteynerinden erişilebilir."""
    if hostname in ("127.0.0.1", "localhost", "::1"):
        return os.environ.get("GUACD_HOST_LOOPBACK_TARGET", "host.docker.internal")
    return hostname


class GuacdConnectError(Exception):
    """guacd'ye bağlanılamadı VEYA el sıkışma tamamlanamadı — ham
    exception detayı çağıran tarafa (WebSocket) hiçbir zaman
    sızdırılmaz, yalnızca bu mesaj kullanıcıya döner."""


def drive_config() -> str | None:
    """Faz 74 — Sürücü Yönlendirme (Dosya Transferi). `GUACD_DRIVE_PATH`
    guacd'nin KENDİ dosya sisteminden gördüğü, paylaşılan sürücülerin
    kök dizini (bkz. `infra/docker-compose.yml`'e eklenen bind mount) —
    `recording_config()`'ten farklı olarak backend'in bu dizini kendi
    tarafından AYRICA görmesine gerek YOK (yalnızca guacd/RDP oturumu
    içine erişiyor, backend bir dosyayı kendi sunmuyor), bu yüzden tek
    bir env yeterli. Set edilmemişse sürücü yönlendirme SESSİZCE devre
    dışı (opt-in — var olmayan/yazılamayan bir yol verilirse guacd
    bağlantısının kendisi başarısız olurdu)."""
    return os.environ.get("GUACD_DRIVE_PATH")


def recording_config() -> tuple[str | None, str | None]:
    """Faz 50 — Oturum Kaydı. `GUACD_RECORDING_PATH` guacd'nin KENDİ
    dosya sisteminden gördüğü kayıt dizini (guacd genelde ayrı bir
    Docker konteynerinde çalışır — bkz. `infra/docker-compose.yml`'e
    eklenen bind mount); `PAM_RECORDING_HOST_DIR` bu backend'in AYNI
    dizini kendi dosya sisteminden gördüğü yol (playback/stream
    endpoint'i buradan okur). İkisi de set edilmemişse kayıt SESSİZCE
    devre dışı kalır — guacd'ye var olmayan/yazılamayan bir yol
    verilirse bağlantının kendisi başarısız olurdu, bu yüzden
    varsayılan KAPALI (opt-in, `ENABLE_REMOTE_COMMANDS`/`AGENT_
    MAINTENANCE_ENABLED` ile AYNI iki-anahtarlı ilke)."""
    guacd_path = os.environ.get("GUACD_RECORDING_PATH")
    host_dir = os.environ.get("PAM_RECORDING_HOST_DIR")
    if not guacd_path or not host_dir:
        return None, None
    return guacd_path, host_dir


async def open_rdp_connection(
    *,
    hostname: str,
    port: int = 3389,
    username: str,
    password: str | None,
    domain: str | None,
    width: int,
    height: int,
    dpi: int = 96,
    session_id: str | None = None,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """guacd'ye bağlanır, RDP el sıkışmasını TAMAMLAR, `ready`
    instruction'ından sonraki ham stream'i döner (çağıran taraf bunu
    doğrudan WebSocket'e köprüler). Başarısızlıkta `GuacdConnectError`.

    `session_id` verilirse VE `recording_config()` bir kayıt dizini
    döndürüyorsa, guacd bu oturumu `{recording-path}/{session_id}`
    dosyasına (Guacamole'ün kendi `.guac` protokol formatında) kaydeder
    — çağıran taraf (`app/routes/pam_rdp.py`) bu dosya yolunu (host
    tarafından görüldüğü haliyle) `pam_session_logs.recording_file_path`'e
    yazar."""
    hostname = _resolve_rdp_target_hostname(hostname)
    host, guacd_port = guacd_address()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, guacd_port), timeout=_HANDSHAKE_TIMEOUT_SECONDS
        )
    except (OSError, TimeoutError) as exc:
        raise GuacdConnectError(f"guacd'ye bağlanılamadı ({host}:{guacd_port})") from exc

    guacd_recording_path, _ = recording_config()
    guacd_drive_path = drive_config()

    try:
        await asyncio.wait_for(
            _perform_handshake(
                reader,
                writer,
                hostname=hostname,
                port=port,
                username=username,
                password=password,
                domain=domain,
                width=width,
                height=height,
                dpi=dpi,
                recording_path=guacd_recording_path,
                recording_name=session_id,
                drive_root_path=guacd_drive_path,
                session_id=session_id,
            ),
            timeout=_HANDSHAKE_TIMEOUT_SECONDS,
        )
    except (GuacamoleProtocolError, TimeoutError, OSError) as exc:
        writer.close()
        raise GuacdConnectError("guacd el sıkışması başarısız") from exc

    return reader, writer


async def _perform_handshake(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    hostname: str,
    port: int,
    username: str,
    password: str | None,
    domain: str | None,
    width: int,
    height: int,
    dpi: int,
    recording_path: str | None = None,
    recording_name: str | None = None,
    drive_root_path: str | None = None,
    session_id: str | None = None,
) -> None:
    """Resmi Guacamole protokolü el sıkışma sırası: `select` → (guacd)
    `args` → `size`/`audio`/`video`/`image` → `connect` → (guacd)
    `ready`. `connect`'in değerleri `args`'ın DÖNDÜRDÜĞÜ SIRAYLA
    gönderilir (parametre adı bizim BİLDİĞİMİZ bir alana denk geliyorsa
    değer, gelmiyorsa boş string) — guacd sürümleri arasında `args`
    listesi FARKLILIK gösterebildiği için sabit bir sıra VARSAYILMAZ."""
    writer.write(encode_instruction("select", "rdp"))
    await writer.drain()

    args_instruction = await read_instruction(reader)
    if not args_instruction or args_instruction[0] != "args":
        raise GuacamoleProtocolError(f"'args' bekleniyordu, gelen: {args_instruction!r}")
    param_names = args_instruction[1:]

    writer.write(encode_instruction("size", str(width), str(height), str(dpi)))
    writer.write(encode_instruction("audio"))
    writer.write(encode_instruction("video"))
    writer.write(encode_instruction("image", *_SUPPORTED_IMAGE_MIMETYPES))
    await writer.drain()

    known_values = {
        "hostname": hostname,
        "port": str(port),
        "username": username,
        "password": password or "",
        "domain": domain or "",
        "width": str(width),
        "height": str(height),
        "dpi": str(dpi),
        # Bu makinede henüz kimse host key/sertifika PİNLEMEDİ (Faz 35'in
        # SSH tarafındaki `known_hosts=None` kararıyla AYNI bilinçli
        # sınırlama) — guacd'nin kendi kendine imzalı RDP sertifikasını
        # reddetmemesi için.
        "ignore-cert": "true",
        # GERÇEK guacd 1.5.5'e karşı canlı test edildi (bkz. docs/
        # roadmap.md Faz 48 notu): "any" ile de "nla" ile de bağlantı
        # guacd'ye kadar ulaşıyor, ama modern Windows Server (bu makine
        # dahil) varsayılan olarak NLA ZORUNLU tutuyor — "nla" gerçek
        # bir Windows RDP hedefiyle en uyumlu/doğru varsayılan.
        "security": "nla",
        # Faz 74 — güvenlik/güç modu ile ilgisi olmayan, guacd sürüm
        # varsayımına BIRAKILMAYAN açık bir tercih (kullanıcının çift
        # yönlü pano isteği): `security: nla` kararıyla AYNI ilke.
        "disable-copy": "false",
        "disable-paste": "false",
    }
    # Faz 50 — Oturum Kaydı. `recording_path` yalnızca `recording_
    # config()` gerçek bir kayıt dizini döndürdüğünde dolu; boşsa bu üç
    # anahtar `known_values`'a HİÇ eklenmiyor, guacd'nin `args`'ında
    # zaten karşılığı olmadığı için `connect_values`'ta boş string
    # olarak kalıyor — kayıt SESSİZCE devre dışı (guacd bunu normal bir
    # kayıtsız oturum olarak başlatır).
    if recording_path and recording_name:
        known_values["recording-path"] = recording_path
        known_values["recording-name"] = recording_name
        known_values["create-recording-path"] = "true"
        known_values["recording-exclude-output"] = "false"
        known_values["recording-exclude-mouse"] = "false"
    # Faz 74 — Sürücü Yönlendirme. `drive_root_path` yalnızca `drive_
    # config()` bir kök dizin döndürdüğünde dolu; AYNI opt-in ilkesi —
    # boşsa sürücü alanları HİÇ eklenmiyor, guacd normal (sürücüsüz) bir
    # oturum başlatır. Her oturumun kendi `{root}/{session_id}` alt
    # dizini var — çakışma yapısal olarak imkansız (`session_id` zaten
    # bir UUID).
    if drive_root_path and session_id:
        known_values["enable-drive"] = "true"
        known_values["drive-path"] = f"{drive_root_path.rstrip('/')}/{session_id}"
        known_values["create-drive-path"] = "true"
        known_values["drive-name"] = "PAM Paylaşılan Sürücü"
    connect_values = [known_values.get(name, "") for name in param_names]
    writer.write(encode_instruction("connect", *connect_values))
    await writer.drain()

    ready_instruction = await read_instruction(reader)
    if not ready_instruction or ready_instruction[0] != "ready":
        raise GuacamoleProtocolError(f"'ready' bekleniyordu, gelen: {ready_instruction!r}")


async def _pump_guacd_to_websocket(
    reader: asyncio.StreamReader, websocket: WebSocket, *, session_id: UUID | None = None
) -> None:
    """El sıkışma bittikten sonra guacd'den gelen ham protokol
    baytlarını WebSocket text frame'leri olarak iletir.

    **Gerçek, canlı test sırasında bulunan bir üretim hatası:** ham
    baytları OLDUĞU GİBİ (rastgele bayt sınırlarında) iletmek
    `guacamole-common-js`'in tarayıcı tarafındaki ayrıştırıcısını
    (kaynakta doğrulandı, bkz. `Guacamole.WebSocketTunnel`) BOZUYORDU —
    o ayrıştırıcı HER WebSocket mesajının TAM instruction(lar) içerdiğini
    VARSAYAR, mesajlar arası bir tampon TUTMAZ. Bir ekran görüntüsü
    `blob`'u iki mesaja bölününce tarayıcı "source image could not be
    decoded" hatası verip görüntüyü hiç işlemiyordu, sonunda guacd de
    "User is not responding" diyerek bağlantıyı kesiyordu. Düzeltme:
    `split_complete_instructions` ile yalnızca TAM biten instruction'lar
    gönderilir, yarım kalan son instruction bir SONRAKİ okumaya kadar
    tamponda bekletilir.

    Faz 51 — `session_id` verilirse, birincil tarayıcıya gönderilen AYNI
    tam instruction grubu `session_registry.publish_to_shadows`'a da
    yayınlanır (bkz. `app/routes/pam_audit.py::shadow_session_route` —
    "Canlı İzle" salt-okunur izleyicileri bunu tüketir). Hiçbir izleyici
    yoksa bu no-op'tur, birincil akışa maliyeti yoktur."""
    buffer = b""
    try:
        while True:
            chunk = await reader.read(_READ_CHUNK_SIZE)
            if not chunk:
                break
            buffer += chunk
            complete, buffer = split_complete_instructions(buffer)
            if complete:
                await websocket.send_text(complete.decode("utf-8"))
                if session_id is not None:
                    session_registry.publish_to_shadows(session_id, complete)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("guacd→WebSocket akışı sona erdi", exc_info=True)


async def bridge_websocket_to_guacd(
    websocket: WebSocket,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    max_session_duration_mins: int,
    kill_event: asyncio.Event | None = None,
    session_id: UUID | None = None,
) -> str:
    """El sıkışma TAMAMLANMIŞ bir guacd bağlantısını WebSocket'e
    köprüler — Faz 46'nın `run_pam_ssh_websocket_session`'ıyla AYNI
    "sunucu tarafında süre sınırı" ilkesi. Dönüş değeri `end_reason`
    (`"user_closed"`/`"timeout"`/`"error"`/`"terminated_by_admin"`).

    Faz 50 — `kill_event` verilirse (bkz. `app/pam/session_registry.py`)
    ÜÇÜNCÜ bir bekleyici olarak `asyncio.wait(FIRST_COMPLETED)`'a
    eklenir: bir admin "Oturumu Kapat" dediğinde bu event set edilir,
    köprü ANINDA (guacd/tarayıcının kendisi bir şey göndermesini
    beklemeden) kapanır.

    **Gerçek, canlı test sırasında bulunan bir üretim hatası:** eskiden
    yalnızca WebSocket→guacd yönü `asyncio.wait_for` ile beklenip guacd→
    WebSocket yönü (`pump_task`) tamamen BAĞIMSIZ çalışıyordu — guacd
    kimlik doğrulama hatası verip KENDİSİ bağlantıyı kapattığında
    (`pump_task` sessizce biterdi) köprü bunu HİÇ fark etmiyor, tarayıcı
    hiçbir şey göndermediği için `_relay_websocket_to_guacd` tam süre
    sınırına kadar (`max_session_duration_mins` dakika!) askıda
    kalıyordu. Artık İKİ yön de `asyncio.wait(..., FIRST_COMPLETED)` ile
    izleniyor — HANGİSİ önce biterse köprü hemen kapanıyor."""
    pump_task = asyncio.create_task(_pump_guacd_to_websocket(reader, websocket, session_id=session_id))
    end_reason = "user_closed"

    async def _relay_websocket_to_guacd() -> None:
        while True:
            message = await websocket.receive_text()
            writer.write(message.encode("utf-8"))
            await writer.drain()

    relay_task = asyncio.create_task(_relay_websocket_to_guacd())
    kill_task = asyncio.create_task(kill_event.wait()) if kill_event is not None else None
    waiters = {pump_task, relay_task} | ({kill_task} if kill_task is not None else set())

    try:
        done, pending = await asyncio.wait(
            waiters, timeout=max_session_duration_mins * 60, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            end_reason = "timeout"
        elif kill_task is not None and kill_task in done:
            end_reason = "terminated_by_admin"
        else:
            finished = next(iter(done))
            exc = finished.exception()
            if isinstance(exc, WebSocketDisconnect):
                end_reason = "user_closed"
            elif exc is not None:
                logger.error("PAM RDP WebSocket köprüsünde beklenmeyen hata", exc_info=exc)
                end_reason = "error"
            # `pump_task` guacd'nin kendisi bağlantıyı kapattığı için
            # (ör. kimlik doğrulama hatası) sessizce bitmişse de bu
            # oturumun sonu demektir — "error" değil "user_closed"
            # varsayılanı yeterli, gerçek sebep zaten guacd'nin
            # tarayıcıya gönderdiği "error" instruction'ında.
    finally:
        pump_task.cancel()
        relay_task.cancel()
        if kill_task is not None:
            kill_task.cancel()
        writer.close()
        try:
            await websocket.close()
        except Exception:
            pass

    return end_reason
