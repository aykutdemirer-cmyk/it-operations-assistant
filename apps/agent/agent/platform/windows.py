"""Yalnızca Windows'a özgü toplama mantığı. Bu modül Linux'ta hiç
import EDİLMEZ (bkz. `agent/platform/__init__.py::resolve`) — bu yüzden
Windows-only kütüphaneleri (`winreg`) doğrudan üst seviyede import
etmek güvenli."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("agent.platform.windows")

# `quser` sabit genişlikli (fixed-width) kolonlar kullanır — değerler
# (özellikle LOGON TIME, "9/2/2026 8:57 AM" gibi boşluk içerir) basit
# `str.split()` ile güvenilir ayrıştırılamaz. Başlık satırındaki her
# kolon adının BAŞLANGIÇ pozisyonunu bulup veri satırlarını buna göre
# dilimleriz — klasik, sağlam bir `quser` ayrıştırma tekniği.
_QUSER_COLUMNS = ("USERNAME", "SESSIONNAME", "ID", "STATE", "IDLE TIME", "LOGON TIME")
_QUSER_STATUS_MAP = {"active": "active", "disc": "disconnected"}


def machine_id() -> str | None:
    """Registry'deki `MachineGuid` — makineye özgü, hostname değişse
    bile SABİT kalan bir kimlik. Okunamazsa (yetki/registry sorunu)
    `None` döner, agent ÇÖKMEZ."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        logger.debug("MachineGuid okunamadı", exc_info=True)
        return None


def hardware_info() -> dict:
    """Windows'ta üretici/model bilgisi güvenilir şekilde yalnızca WMI
    üzerinden alınabilir — bu, ekstra bir bağımlılık (`wmi`/`pywin32`)
    gerektirir ve bu fazın kapsamı dışında bırakıldı (bkz. README).
    Dürüstçe `None` döner, uydurulmaz."""
    return {"manufacturer": None, "model": None}


def list_services() -> list[dict]:
    """`psutil.win_service_iter()` — Windows Service Control Manager'a
    psutil'in kendi sarmalayıcısı üzerinden erişir, EKSTRA bir
    bağımlılık (`pywin32` vb.) gerektirmez. Tek tek servis okunurken
    başarısız olan (yetki/geçici durum) servisler sessizce atlanır —
    bir servisin hatası tüm listeyi boşaltmaz."""
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil zorunlu bağımlılık
        logger.warning("psutil yüklü değil, Windows servis listesi alınamadı")
        return []

    services: list[dict] = []
    try:
        service_iter = psutil.win_service_iter()
    except Exception:
        logger.warning("Windows servis listesi alınamadı", exc_info=True)
        return []

    for svc in service_iter:
        try:
            info = svc.as_dict()
        except Exception:
            continue
        services.append(
            {
                "name": info.get("name"),
                "display_name": info.get("display_name"),
                "state": info.get("status"),
                "startup_type": info.get("start_type"),
            }
        )
    return services


def list_sessions() -> list[dict]:
    """`quser` (`query user`) çıktısını ayrıştırır. Hiç oturum yoksa ya
    da komut yoksa/zaman aşımına uğrarsa boş liste döner — agent ÇÖKMEZ.
    `>` işareti (şu an bağlı olunan oturumu işaretler) veri hizalamasını
    BOZMAZ — header'daki `USERNAME` ile aynı sütunda durur, ayrıca
    işlenmesi gerekmez (`str.strip()` yeterli)."""
    try:
        result = subprocess.run(
            ["quser"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("quser çalıştırılamadı", exc_info=True)
        return []

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        # Hiç oturum yok (nadir) veya `quser` başarısız oldu (stderr'e
        # yazar, `returncode != 0`) — ikisi de dürüstçe boş liste.
        return []

    header = lines[0]
    positions = []
    for name in _QUSER_COLUMNS:
        idx = header.find(name)
        if idx == -1:
            logger.warning("quser başlık formatı beklenmedik: %r", header)
            return []
        positions.append(idx)
    positions.append(len(header) + 512)  # son kolon (LOGON TIME) için güvenlik payı

    sessions: list[dict] = []
    for line in lines[1:]:
        values = [line[positions[i] : positions[i + 1]].strip() for i in range(len(_QUSER_COLUMNS))]
        username, session_name, _session_id, state, _idle_time, logon_time = values
        if not username:
            continue
        sessions.append(
            {
                "username": username,
                "session_name": session_name or None,
                "status": _QUSER_STATUS_MAP.get(state.lower(), state.lower() or None),
                "logon_time": logon_time or None,
            }
        )
    return sessions
