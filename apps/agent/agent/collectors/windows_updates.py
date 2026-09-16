"""Windows Update taraması — Windows-ONLY (Linux'ta hiç çağrılmaz,
`main.py::AgentRuntime.start` yalnızca `current_os() == "windows"` ise
bu döngüyü başlatır).

İki aşamalı, dürüst bir strateji:

1. **Birincil — COM (`Microsoft.Update.Session`):** Windows'a YERLEŞİK
   Windows Update Agent API'sinin COM arayüzü (`pywin32` gerektirir,
   ekstra bir servis/modül kurulumu YOK). `Search("IsInstalled=0 and
   IsHidden=0")` GERÇEKTEN BEKLEYEN (henüz kurulmamış) güncellemeleri
   döner — bu, kullanıcının istediği asıl anlam ("hangi güncellemeler
   var").
2. **Yedek — `Get-CimInstance Win32_QuickFixEngineering`:** COM
   kullanılamıyorsa (`pywin32` build'e dahil değilse, Windows Update
   servisi kapalıysa, COM exception'ı vb.) devreye girer. **DÜRÜSTLÜK
   NOTU:** bu, kullanıcının önerdiği `Search-WindowsUpdate` DEĞİLDİR —
   o cmdlet üçüncü parti `PSWindowsUpdate` modülünü gerektirir
   (varsayılan Windows kurulumunda YOK, otomatik `Install-Module`
   internet + ek yetki ister, bir arka plan ajanının sessizce modül
   kurması riskli/kırılgan). `Win32_QuickFixEngineering` her Windows
   makinesinde YERLEŞİK ama FARKLI bir anlam taşır: BEKLEYEN değil,
   ZATEN KURULMUŞ hotfix'leri listeler (bir denetim/uyumluluk
   görünümü). Bu fark `scan_method` alanında AÇIKÇA taşınır — asla
   `com` sonucuymuş gibi GÖSTERİLMEZ (bkz. `UpdateScanResult.
   scan_method`, `apps/api/app/agents/update_models.py`'deki AYNI
   `Literal`)."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

from agent.platform import current_os

logger = logging.getLogger("agent.collectors.windows_updates")

_COM_TIMEOUT_HINT_SECONDS = 120  # COM çağrısının kendisi timeout PARAMETRESİ almaz (bkz. not aşağıda)
_POWERSHELL_TIMEOUT_SECONDS = 30


@dataclass
class UpdateItem:
    kb_number: str | None
    title: str
    description: str | None = None
    size_bytes: int | None = None


@dataclass
class UpdateScanResult:
    scan_method: str  # "com" | "installed_hotfixes" | "unavailable"
    is_admin: bool
    updates: list[UpdateItem] = field(default_factory=list)
    error: str | None = None
    # `Microsoft.Update.SystemInfo().RebootRequired` — makinenin GENEL
    # (herhangi bir spesifik güncellemeye bağlı olmayan) bekleyen yeniden
    # başlatma durumu. Her taramada TAZE sorgulanır (kendi başımıza
    # elle bir bayrak tutup güncel/bayat olma riski almak yerine).
    reboot_required: bool = False


@dataclass
class InstallResult:
    success: bool
    reboot_required: bool
    detail: str
    installed_count: int = 0


def is_windows_admin() -> bool:
    """Yönetici (Admin/SYSTEM) yetkisi kontrolü. Windows Update
    taraması (özellikle COM `Search()`) yönetici yetkisi OLMADAN da
    genelde çalışır ama kurulum/indirme işlemleri gerektirmez — burada
    yalnızca RAPORLAMA amaçlı (backend'e `is_admin` alanı olarak
    gönderilir, kullanıcı arayüzünde "bu tarama kısıtlı yetkiyle mi
    yapıldı" bilgisini dürüstçe göstermek için). Yetki kontrolünün
    kendisi başarısız olursa (ör. `ctypes` erişilemez) dürüstçe
    `False`."""
    if current_os() != "windows":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        logger.debug("Yönetici yetkisi kontrol edilemedi", exc_info=True)
        return False


def _query_reboot_required() -> bool:
    """`Microsoft.Update.SystemInfo` — Windows Update Agent API'sinin
    KENDİ, resmi "bu makine yeniden başlatma bekliyor mu" sorgusu
    (belirli bir kuruluma bağlı DEĞİL, sistem genelinde). COM
    kullanılamıyorsa/hata verirse dürüstçe `False` — asla tahmini bir
    değer UYDURULMAZ."""
    try:
        import win32com.client

        return bool(win32com.client.Dispatch("Microsoft.Update.SystemInfo").RebootRequired)
    except Exception:
        logger.debug("Reboot-required durumu sorgulanamadı", exc_info=True)
        return False


def _scan_via_com() -> list[UpdateItem]:
    """`win32com.client` içe aktarımı GECİKTİRİLİR — bu modül yanlışlıkla
    Linux'ta import edilirse (ör. testlerde) `ImportError` yerine modülün
    KENDİSİ hâlâ import edilebilsin diye (bkz. `agent/winservice.py::
    _import_pywin32` ile AYNI desen). NOT: `Search()` çağrısının kendisi
    bir zaman aşımı PARAMETRESİ almaz — Windows Update sunucularına
    gerçek bir ağ isteği yapabilir, bu yüzden bu tarama arka planda,
    uzun bir aralıkla (`WINDOWS_UPDATES_INTERVAL`, varsayılan 6 saat)
    ayrı bir thread'de çalıştırılır (bkz. `main.py`), ana heartbeat/
    telemetry döngülerini ASLA bloklamaz."""
    import win32com.client

    session = win32com.client.Dispatch("Microsoft.Update.Session")
    searcher = session.CreateUpdateSearcher()
    result = searcher.Search("IsInstalled=0 and IsHidden=0")

    items: list[UpdateItem] = []
    for i in range(result.Updates.Count):
        update = result.Updates.Item(i)
        kb_numbers = [str(kb) for kb in update.KBArticleIDs] if update.KBArticleIDs.Count else []
        size_bytes = None
        try:
            size_bytes = int(update.MaxDownloadSize) if update.MaxDownloadSize else None
        except (TypeError, ValueError, AttributeError):
            pass
        items.append(
            UpdateItem(
                kb_number=", ".join(f"KB{kb}" for kb in kb_numbers) or None,
                title=str(update.Title),
                description=str(update.Description) if update.Description else None,
                size_bytes=size_bytes,
            )
        )
    return items


def _scan_via_installed_hotfixes() -> list[UpdateItem]:
    """Yedek yol — bkz. modül docstring'indeki DÜRÜSTLÜK NOTU (bu,
    BEKLEYEN değil ZATEN KURULMUŞ hotfix'leri döner)."""
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance -ClassName Win32_QuickFixEngineering | "
            "Select-Object HotFixID, Description, InstalledOn | ConvertTo-Json -Compress",
        ],
        capture_output=True, text=True, timeout=_POWERSHELL_TIMEOUT_SECONDS, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or f"exit code {result.returncode}").strip())

    raw = (result.stdout or "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    # `ConvertTo-Json` tek bir sonuçta LİSTE değil, DÜZ bir obje döner —
    # `Win32_QuickFixEngineering`'de tipik olarak onlarca kayıt olduğu
    # için bu nadir bir durum ama testlerde/az hotfix'li bir makinede
    # gerçekleşebilir; normalize edilir.
    rows = parsed if isinstance(parsed, list) else [parsed]

    items: list[UpdateItem] = []
    for row in rows:
        hotfix_id = row.get("HotFixID")
        if not hotfix_id:
            continue
        items.append(UpdateItem(kb_number=str(hotfix_id), title=str(row.get("Description") or hotfix_id)))
    return items


# Windows Update Agent API'nin `OperationResultCode` enum'u
# (orcNotStarted=0, orcInProgress=1, orcSucceeded=2,
# orcSucceededWithErrors=3, orcFailed=4, orcAborted=5).
_RESULT_SUCCEEDED = (2, 3)


def _matches_kb(item_kb_field: str, kb_filter: str) -> bool:
    """`update.KBArticleIDs`'ten üretilen `"KB1, KB2"` biçimindeki
    alanın, kullanıcının seçtiği TEK bir KB numarasıyla eşleşip
    eşleşmediğini kontrol eder (bir güncelleme birden fazla KB
    numarası taşıyabilir, bkz. `_scan_via_com`)."""
    normalized_filter = kb_filter.strip().upper()
    if not normalized_filter.startswith("KB"):
        normalized_filter = f"KB{normalized_filter}"
    return normalized_filter in [kb.strip().upper() for kb in item_kb_field.split(",")]


def install_updates(kb_filter: str | None) -> InstallResult:
    """Seçilen (veya `kb_filter` `None`/`"all"` ise TÜM bekleyen)
    güncellemeleri GERÇEKTEN indirir ve yükler — yalnızca COM
    (`Microsoft.Update.Session`) üzerinden; yedek PowerShell yolu
    (`Win32_QuickFixEngineering`) yalnızca OKUMA amaçlıdır, yükleme
    YAPAMAZ (`Search-WindowsUpdate`/`PSWindowsUpdate` modülü
    varsayılan Windows kurulumunda yok — bkz. modül docstring'i).
    COM kullanılamıyorsa dürüstçe başarısız döner, hiçbir sahte
    başarı ÜRETİLMEZ."""
    if current_os() != "windows":
        return InstallResult(False, False, "Yükleme yalnızca Windows'ta destekleniyor")

    try:
        import win32com.client

        session = win32com.client.Dispatch("Microsoft.Update.Session")
        searcher = session.CreateUpdateSearcher()
        search_result = searcher.Search("IsInstalled=0 and IsHidden=0")

        selected = win32com.client.Dispatch("Microsoft.Update.UpdateColl")
        want_all = kb_filter is None or kb_filter.strip().lower() == "all"
        for i in range(search_result.Updates.Count):
            update = search_result.Updates.Item(i)
            if want_all:
                selected.Add(update)
                continue
            kb_numbers = [str(kb) for kb in update.KBArticleIDs] if update.KBArticleIDs.Count else []
            kb_field = ", ".join(f"KB{kb}" for kb in kb_numbers)
            if kb_field and _matches_kb(kb_field, kb_filter):
                selected.Add(update)

        if selected.Count == 0:
            return InstallResult(False, _query_reboot_required(), "Eşleşen bekleyen güncelleme bulunamadı")

        for i in range(selected.Count):
            update = selected.Item(i)
            if not update.EulaAccepted:
                update.AcceptEula()

        downloader = session.CreateUpdateDownloader()
        downloader.Updates = selected
        download_result = downloader.Download()
        if download_result.ResultCode not in _RESULT_SUCCEEDED:
            return InstallResult(
                False, _query_reboot_required(),
                f"İndirme başarısız oldu (ResultCode={download_result.ResultCode})",
            )

        installer = session.CreateUpdateInstaller()
        installer.Updates = selected
        install_result = installer.Install()

        reboot_required = bool(install_result.RebootRequired)
        if install_result.ResultCode not in _RESULT_SUCCEEDED:
            return InstallResult(
                False, reboot_required,
                f"Yükleme başarısız oldu (ResultCode={install_result.ResultCode})",
            )

        return InstallResult(
            True, reboot_required,
            f"{selected.Count} güncelleme başarıyla yüklendi" + (" — yeniden başlatma gerekiyor" if reboot_required else ""),
            installed_count=selected.Count,
        )
    except Exception as exc:  # noqa: BLE001 - COM'un kendi geniş exception yüzeyi
        logger.exception("Windows Update yüklemesi başarısız oldu")
        return InstallResult(False, False, f"Yükleme sırasında beklenmeyen hata: {exc}")


def scan_pending_updates() -> UpdateScanResult:
    """Backend'e gönderilecek tam tarama sonucunu üretir. Hiçbir
    aşama başarısız olursa agent ÇÖKMEZ — dürüstçe `scan_method=
    "unavailable"` + `error` alanıyla döner (uydurma bir liste ASLA
    üretilmez)."""
    if current_os() != "windows":
        return UpdateScanResult("unavailable", False, [], "Yalnızca Windows'ta destekleniyor")

    admin = is_windows_admin()
    reboot_required = _query_reboot_required()

    try:
        updates = _scan_via_com()
        return UpdateScanResult("com", admin, updates, None, reboot_required)
    except Exception as exc:  # noqa: BLE001 - COM'un kendi geniş exception yüzeyi
        logger.warning("COM ile Windows Update taraması başarısız (%s) — yedek yönteme geçiliyor", exc)
        com_error = str(exc)

    try:
        updates = _scan_via_installed_hotfixes()
        return UpdateScanResult(
            "installed_hotfixes", admin, updates,
            f"COM taraması başarısız oldu (bekleyen güncellemeler yerine kurulu hotfix'ler gösteriliyor): {com_error}",
            reboot_required,
        )
    except Exception as exc:  # noqa: BLE001 - subprocess/JSON hatalarının geniş yüzeyi
        logger.warning("Yedek Windows Update taraması da başarısız oldu (%s)", exc)
        return UpdateScanResult(
            "unavailable", admin, [], f"Hem COM hem PowerShell taraması başarısız oldu: {exc}", reboot_required
        )
