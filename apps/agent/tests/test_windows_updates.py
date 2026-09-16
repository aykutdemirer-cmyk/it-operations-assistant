"""`agent/collectors/windows_updates.py` için testler. Gerçek bir COM
çağrısı veya gerçek `powershell.exe` çalıştırması ASLA yapılmaz —
`win32com.client.Dispatch`/`subprocess.run` mock'lanır."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent.collectors import windows_updates as wu


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# --- is_windows_admin ---


def test_is_windows_admin_false_on_non_windows():
    with patch("agent.collectors.windows_updates.current_os", return_value="linux"):
        assert wu.is_windows_admin() is False


def test_is_windows_admin_reflects_ctypes_result():
    fake_ctypes = MagicMock()
    fake_ctypes.windll.shell32.IsUserAnAdmin.return_value = 1
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", {"ctypes": fake_ctypes}),
    ):
        assert wu.is_windows_admin() is True


def test_is_windows_admin_false_when_ctypes_check_fails():
    fake_ctypes = MagicMock()
    fake_ctypes.windll.shell32.IsUserAnAdmin.side_effect = OSError("boom")
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", {"ctypes": fake_ctypes}),
    ):
        assert wu.is_windows_admin() is False


# --- scan_pending_updates: platform gate ---


def test_scan_returns_unavailable_on_non_windows():
    with patch("agent.collectors.windows_updates.current_os", return_value="linux"):
        result = wu.scan_pending_updates()

    assert result.scan_method == "unavailable"
    assert result.updates == []
    assert result.error is not None


# --- scan_pending_updates: COM primary path ---


def _fake_com_update(kb_ids, title, description="", max_size=1234):
    update = MagicMock()
    update.KBArticleIDs.Count = len(kb_ids)
    update.KBArticleIDs.__iter__ = lambda self: iter(kb_ids)
    update.Title = title
    update.Description = description
    update.MaxDownloadSize = max_size
    return update


def _patched_win32com_modules(fake_client):
    """`import win32com.client` içeride bir fonksiyon gövdesinde
    çalıştığından, `sys.modules['win32com.client']`'i tek başına
    override etmek YETMEZ — üst paket (`win32com`) zaten bu süreçte
    yüklenmişse (veya hiç yüklenmemişse), Python'un import mekanizması
    alt modülü üst paketin bir ATTRIBUTE'u olarak çözer; bu attribute
    yalnızca modül GERÇEKTEN ilk kez yüklenirken atanır, sys.modules
    cache'i zaten doluyken ATLANIR. Bu yüzden hem üst paketin `.client`
    attribute'u hem de `sys.modules['win32com.client']` birlikte
    patch'lenir — testlerde dotted-import mock'lamanın standart yolu."""
    fake_win32com_pkg = MagicMock()
    fake_win32com_pkg.client = fake_client
    return {"win32com": fake_win32com_pkg, "win32com.client": fake_client}


def test_scan_uses_com_when_available():
    fake_update = _fake_com_update(["5001234"], "2026-09 Cumulative Update", "desc", 500)
    fake_result = MagicMock()
    fake_result.Updates.Count = 1
    fake_result.Updates.Item.return_value = fake_update

    fake_searcher = MagicMock()
    fake_searcher.Search.return_value = fake_result
    fake_session = MagicMock()
    fake_session.CreateUpdateSearcher.return_value = fake_searcher

    fake_win32com_client = MagicMock()
    fake_win32com_client.Dispatch.return_value = fake_session

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch.dict("sys.modules", _patched_win32com_modules(fake_win32com_client)),
    ):
        result = wu.scan_pending_updates()

    assert result.scan_method == "com"
    assert result.is_admin is True
    assert result.error is None
    assert len(result.updates) == 1
    assert result.updates[0].kb_number == "KB5001234"
    assert result.updates[0].title == "2026-09 Cumulative Update"
    assert result.updates[0].size_bytes == 500
    fake_searcher.Search.assert_called_once_with("IsInstalled=0 and IsHidden=0")


def test_scan_com_result_with_no_kb_number_is_none():
    fake_update = _fake_com_update([], "Driver update")
    fake_result = MagicMock()
    fake_result.Updates.Count = 1
    fake_result.Updates.Item.return_value = fake_update
    fake_searcher = MagicMock()
    fake_searcher.Search.return_value = fake_result
    fake_session = MagicMock()
    fake_session.CreateUpdateSearcher.return_value = fake_searcher
    fake_win32com_client = MagicMock()
    fake_win32com_client.Dispatch.return_value = fake_session

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=False),
        patch.dict("sys.modules", _patched_win32com_modules(fake_win32com_client)),
    ):
        result = wu.scan_pending_updates()

    assert result.updates[0].kb_number is None


# --- scan_pending_updates: PowerShell fallback ---


def test_scan_falls_back_to_installed_hotfixes_when_com_fails():
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch("agent.collectors.windows_updates._scan_via_com", side_effect=RuntimeError("COM not registered")),
        patch(
            "agent.collectors.windows_updates.subprocess.run",
            return_value=_completed(0, stdout='[{"HotFixID": "KB1111111", "Description": "Security Update"}]'),
        ),
    ):
        result = wu.scan_pending_updates()

    assert result.scan_method == "installed_hotfixes"
    assert result.error is not None
    assert "COM taraması başarısız" in result.error
    assert result.updates == [wu.UpdateItem(kb_number="KB1111111", title="Security Update")]


def test_scan_fallback_normalizes_single_dict_result():
    """`ConvertTo-Json` tek satırda liste DEĞİL düz obje döner."""
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch("agent.collectors.windows_updates._scan_via_com", side_effect=RuntimeError("boom")),
        patch(
            "agent.collectors.windows_updates.subprocess.run",
            return_value=_completed(0, stdout='{"HotFixID": "KB2222222", "Description": "Only One"}'),
        ),
    ):
        result = wu.scan_pending_updates()

    assert len(result.updates) == 1
    assert result.updates[0].kb_number == "KB2222222"


def test_scan_returns_unavailable_when_both_methods_fail():
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch("agent.collectors.windows_updates._scan_via_com", side_effect=RuntimeError("COM broken")),
        patch("agent.collectors.windows_updates.subprocess.run", side_effect=OSError("powershell not found")),
    ):
        result = wu.scan_pending_updates()

    assert result.scan_method == "unavailable"
    assert result.updates == []
    assert "Hem COM hem PowerShell" in result.error


def test_scan_never_raises_when_powershell_returns_nonzero():
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch("agent.collectors.windows_updates._scan_via_com", side_effect=RuntimeError("boom")),
        patch(
            "agent.collectors.windows_updates.subprocess.run",
            return_value=_completed(1, stderr="access denied"),
        ),
    ):
        result = wu.scan_pending_updates()

    assert result.scan_method == "unavailable"


def test_scan_falls_back_when_powershell_times_out():
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch("agent.collectors.windows_updates._scan_via_com", side_effect=RuntimeError("boom")),
        patch(
            "agent.collectors.windows_updates.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=30),
        ),
    ):
        result = wu.scan_pending_updates()

    assert result.scan_method == "unavailable"


def test_scan_fallback_handles_empty_hotfix_list():
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch("agent.collectors.windows_updates._scan_via_com", side_effect=RuntimeError("boom")),
        patch("agent.collectors.windows_updates.subprocess.run", return_value=_completed(0, stdout="")),
    ):
        result = wu.scan_pending_updates()

    assert result.scan_method == "installed_hotfixes"


# --- _query_reboot_required ---


def test_query_reboot_required_true_from_com():
    fake_info = MagicMock(RebootRequired=True)
    fake_client = MagicMock()
    fake_client.Dispatch.return_value = fake_info
    with patch.dict("sys.modules", _patched_win32com_modules(fake_client)):
        assert wu._query_reboot_required() is True


def test_query_reboot_required_false_from_com():
    fake_info = MagicMock(RebootRequired=False)
    fake_client = MagicMock()
    fake_client.Dispatch.return_value = fake_info
    with patch.dict("sys.modules", _patched_win32com_modules(fake_client)):
        assert wu._query_reboot_required() is False


def test_query_reboot_required_false_when_com_unavailable():
    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}):
        assert wu._query_reboot_required() is False


def test_scan_includes_reboot_required_flag():
    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch("agent.collectors.windows_updates.is_windows_admin", return_value=True),
        patch("agent.collectors.windows_updates._query_reboot_required", return_value=True),
        patch("agent.collectors.windows_updates._scan_via_com", return_value=[]),
    ):
        result = wu.scan_pending_updates()

    assert result.reboot_required is True


# --- install_updates ---


class _FakeUpdateCollection:
    """Gerçek `IUpdateCollection`'ın test double'ı — `.Add`/`.Count`/
    `.Item(i)` ile basit bir liste gibi davranır (MagicMock'un
    varsayılan davranışı bunu doğal olarak sağlamaz)."""

    def __init__(self):
        self._items: list = []

    def Add(self, item):
        self._items.append(item)

    @property
    def Count(self):
        return len(self._items)

    def Item(self, i):
        return self._items[i]


def _fake_search_updates(items):
    container = MagicMock()
    container.Count = len(items)
    container.Item.side_effect = lambda i: items[i]
    return container


def _fake_win32com_for_install(search_items, *, download_code=2, install_code=2, reboot_required=False):
    fake_session = MagicMock()
    fake_searcher = MagicMock()
    fake_search_result = MagicMock()
    fake_search_result.Updates = _fake_search_updates(search_items)
    fake_searcher.Search.return_value = fake_search_result
    fake_session.CreateUpdateSearcher.return_value = fake_searcher

    fake_downloader = MagicMock()
    fake_downloader.Download.return_value = MagicMock(ResultCode=download_code)
    fake_session.CreateUpdateDownloader.return_value = fake_downloader

    fake_installer = MagicMock()
    fake_installer.Install.return_value = MagicMock(ResultCode=install_code, RebootRequired=reboot_required)
    fake_session.CreateUpdateInstaller.return_value = fake_installer

    fake_client = MagicMock()

    def _dispatch(name):
        if name == "Microsoft.Update.Session":
            return fake_session
        if name == "Microsoft.Update.UpdateColl":
            return _FakeUpdateCollection()
        if name == "Microsoft.Update.SystemInfo":
            return MagicMock(RebootRequired=reboot_required)
        raise ValueError(f"unexpected Dispatch({name!r})")

    fake_client.Dispatch.side_effect = _dispatch
    return fake_client, fake_downloader, fake_installer


def test_install_updates_rejected_on_non_windows():
    with patch("agent.collectors.windows_updates.current_os", return_value="linux"):
        result = wu.install_updates("all")
    assert result.success is False
    assert "Windows" in result.detail


def test_install_updates_installs_all_when_filter_is_all():
    item1 = _fake_com_update(["1111111"], "Update 1")
    item2 = _fake_com_update(["2222222"], "Update 2")
    fake_client, downloader, installer = _fake_win32com_for_install([item1, item2])

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("all")

    assert result.success is True
    assert result.installed_count == 2
    assert downloader.Updates.Count == 2
    assert installer.Updates.Count == 2


def test_install_updates_installs_all_when_filter_is_none():
    item1 = _fake_com_update(["1111111"], "Update 1")
    fake_client, _downloader, _installer = _fake_win32com_for_install([item1])

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates(None)

    assert result.success is True
    assert result.installed_count == 1


def test_install_updates_installs_only_the_matching_kb():
    item1 = _fake_com_update(["1111111"], "Update 1")
    item2 = _fake_com_update(["2222222"], "Update 2")
    fake_client, downloader, _installer = _fake_win32com_for_install([item1, item2])

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("KB2222222")

    assert result.success is True
    assert result.installed_count == 1
    assert downloader.Updates.Item(0) is item2


def test_install_updates_accepts_kb_number_without_prefix():
    item1 = _fake_com_update(["1111111"], "Update 1")
    fake_client, downloader, _installer = _fake_win32com_for_install([item1])

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("1111111")

    assert result.success is True
    assert downloader.Updates.Count == 1


def test_install_updates_fails_when_no_match():
    item1 = _fake_com_update(["1111111"], "Update 1")
    fake_client, _downloader, _installer = _fake_win32com_for_install([item1])

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("KB9999999")

    assert result.success is False
    assert "bulunamadı" in result.detail


def test_install_updates_fails_when_download_fails():
    item1 = _fake_com_update(["1111111"], "Update 1")
    fake_client, _downloader, _installer = _fake_win32com_for_install([item1], download_code=4)

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("all")

    assert result.success is False
    assert "İndirme" in result.detail


def test_install_updates_fails_when_install_fails():
    item1 = _fake_com_update(["1111111"], "Update 1")
    fake_client, _downloader, _installer = _fake_win32com_for_install([item1], install_code=4)

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("all")

    assert result.success is False
    assert "Yükleme" in result.detail


def test_install_updates_reports_reboot_required():
    item1 = _fake_com_update(["1111111"], "Update 1")
    fake_client, _downloader, _installer = _fake_win32com_for_install([item1], reboot_required=True)

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("all")

    assert result.success is True
    assert result.reboot_required is True
    assert "yeniden başlatma" in result.detail


def test_install_updates_calls_accept_eula_when_not_already_accepted():
    item1 = _fake_com_update(["1111111"], "Update 1")
    item1.EulaAccepted = False
    fake_client, _downloader, _installer = _fake_win32com_for_install([item1])

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        wu.install_updates("all")

    item1.AcceptEula.assert_called_once()


def test_install_updates_never_raises_on_unexpected_exception():
    fake_client = MagicMock()
    fake_client.Dispatch.side_effect = RuntimeError("COM boom")

    with (
        patch("agent.collectors.windows_updates.current_os", return_value="windows"),
        patch.dict("sys.modules", _patched_win32com_modules(fake_client)),
    ):
        result = wu.install_updates("all")  # exception fırlatmamalı

    assert result.success is False
    assert "COM boom" in result.detail
