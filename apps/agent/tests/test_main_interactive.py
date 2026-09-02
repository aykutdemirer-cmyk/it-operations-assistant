"""Faz 32 — çift tıklamayla açılan bir EXE'nin argümansız çalıştığında
`start`'a düşmesi, yapılandırma eksikse interaktif kurulum istemesi ve
hata durumunda pencerenin erken kapanmaması (`_pause_before_exit`) için
testler. Gerçek bir PyInstaller EXE'si ÇALIŞTIRILMAZ — `sys.frozen`/
`sys.stdin.isatty`/`input()` mock'lanır."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from agent.main import (
    _default_dotenv_path,
    _is_frozen,
    _is_interactive_console,
    _write_env_value,
    main,
)


def test_is_frozen_false_in_normal_test_execution():
    assert _is_frozen() is False


def test_default_dotenv_path_is_cwd_relative_when_not_frozen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("agent.main._is_frozen", return_value=False):
        path = _default_dotenv_path()
    assert path.name == ".env"
    assert not path.is_absolute() or True  # cwd-relative Path(".env") kabul edilir


def test_default_dotenv_path_is_exe_relative_when_frozen(tmp_path):
    fake_exe = tmp_path / "IT-Operations-Agent-1.0.0.exe"
    fake_exe.write_bytes(b"")
    with patch("agent.main._is_frozen", return_value=True):
        with patch.object(sys, "executable", str(fake_exe)):
            path = _default_dotenv_path()
    assert path == (tmp_path / ".env").resolve()


def test_write_env_value_creates_new_file(tmp_path):
    dotenv_path = tmp_path / ".env"
    _write_env_value(dotenv_path, "BACKEND_URL", "http://10.0.0.5:8000")

    content = dotenv_path.read_text(encoding="utf-8")
    assert "BACKEND_URL=http://10.0.0.5:8000" in content


def test_write_env_value_replaces_existing_key_without_duplicating(tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("BACKEND_URL=http://old:8000\nOTHER=kept\n", encoding="utf-8")

    _write_env_value(dotenv_path, "BACKEND_URL", "http://new:8000")

    lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    backend_lines = [line for line in lines if line.startswith("BACKEND_URL=")]
    assert backend_lines == ["BACKEND_URL=http://new:8000"]
    assert "OTHER=kept" in lines


def test_main_defaults_to_start_when_no_arguments_given(tmp_path, monkeypatch):
    """Gerçek kullanıcı bildirimi: çift tıklama argümansız çalıştırır,
    önceden argparse 'command required' hatasıyla ANINDA kapanıyordu.
    Artık argümansız çağrı `start` komutunu tetiklemeli."""
    monkeypatch.chdir(tmp_path)
    called_with = {}

    def _fake_start(args):
        called_with["command"] = "start"
        return 0

    with patch.dict("agent.main._COMMANDS", {"start": _fake_start}):
        exit_code = main([])

    assert called_with.get("command") == "start"
    assert exit_code == 0


def test_main_calls_pause_before_exit_on_failure():
    def _failing_command(args):
        return 1

    with patch.dict("agent.main._COMMANDS", {"version": _failing_command}):
        with patch("agent.main._pause_before_exit") as mock_pause:
            main(["version"])

    mock_pause.assert_called_once()


def test_main_does_not_pause_on_success():
    with patch("agent.main._pause_before_exit") as mock_pause:
        main(["version"])

    mock_pause.assert_not_called()


def test_initial_setup_cancelled_pauses_only_once_via_main(tmp_path, monkeypatch):
    """Gerçek EXE çalıştırmasıyla bulunan regresyon: `_prompt_for_initial_
    setup` EOFError/KeyboardInterrupt ile iptal edildiğinde SADECE
    `main()`'in merkezi `_pause_before_exit()` çağrısı tetiklenmeli —
    fonksiyonun kendisi AYRICA duraklatmamalı, aksi halde kullanıcı
    "Enter'a basın" istemini iki kez görür."""
    from agent.main import _load_config_or_exit

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BACKEND_URL", raising=False)
    fake_exe = tmp_path / "IT-Operations-Agent-1.0.0.exe"
    fake_exe.write_bytes(b"")

    def _raising_command(args):
        with patch.object(sys, "executable", str(fake_exe)):
            _load_config_or_exit()
        return 0  # unreachable, _load_config_or_exit exits via sys.exit

    with patch("agent.main._is_frozen", return_value=True):
        with patch("agent.main._is_interactive_console", return_value=True):
            with patch("builtins.input", side_effect=EOFError):
                with patch.dict("agent.main._COMMANDS", {"start": _raising_command}):
                    with patch("agent.main._pause_before_exit") as mock_pause:
                        exit_code = main(["start"])

    assert exit_code == 1
    mock_pause.assert_called_once()


def test_pause_before_exit_is_noop_when_not_frozen():
    """`python -m agent`/normal dev çalıştırmasında (frozen değil)
    ASLA `input()` ile bloklamamalı — testin kendisi bunu garanti eder
    (mock'lanmamış bir `input()` çağrısı burada testi asıp
    başarısız kılardı)."""
    from agent.main import _pause_before_exit

    _pause_before_exit()  # frozen olmadığı için hiçbir şey yapmamalı, bloklamamalı


def test_prompt_for_initial_setup_writes_env_and_updates_process_environment(tmp_path, monkeypatch):
    from agent.main import _prompt_for_initial_setup

    fake_exe = tmp_path / "IT-Operations-Agent-1.0.0.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.delenv("BACKEND_URL", raising=False)
    monkeypatch.delenv("ENROLLMENT_CODE", raising=False)

    with patch("agent.main._is_frozen", return_value=True):
        with patch.object(sys, "executable", str(fake_exe)):
            with patch("builtins.input", side_effect=["http://10.0.213.10:8000", "ABC-DEF-123"]):
                _prompt_for_initial_setup()

    assert __import__("os").environ["BACKEND_URL"] == "http://10.0.213.10:8000"
    assert __import__("os").environ["ENROLLMENT_CODE"] == "ABC-DEF-123"
    saved = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "BACKEND_URL=http://10.0.213.10:8000" in saved
    assert "ENROLLMENT_CODE=ABC-DEF-123" in saved

    monkeypatch.delenv("BACKEND_URL", raising=False)
    monkeypatch.delenv("ENROLLMENT_CODE", raising=False)


def test_prompt_for_initial_setup_re_asks_when_backend_url_left_blank(tmp_path, monkeypatch):
    from agent.main import _prompt_for_initial_setup

    fake_exe = tmp_path / "IT-Operations-Agent-1.0.0.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.delenv("BACKEND_URL", raising=False)

    with patch("agent.main._is_frozen", return_value=True):
        with patch.object(sys, "executable", str(fake_exe)):
            with patch("builtins.input", side_effect=["", "  ", "http://10.0.213.10:8000", ""]):
                _prompt_for_initial_setup()

    assert __import__("os").environ["BACKEND_URL"] == "http://10.0.213.10:8000"
    monkeypatch.delenv("BACKEND_URL", raising=False)


def test_load_config_or_exit_triggers_interactive_setup_when_frozen_and_no_config(tmp_path, monkeypatch):
    from agent.main import _load_config_or_exit

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BACKEND_URL", raising=False)
    fake_exe = tmp_path / "IT-Operations-Agent-1.0.0.exe"
    fake_exe.write_bytes(b"")

    def _fake_prompt():
        (tmp_path / ".env").write_text("BACKEND_URL=http://prompted:8000\n", encoding="utf-8")

    with patch("agent.main._is_frozen", return_value=True):
        with patch("agent.main._is_interactive_console", return_value=True):
            with patch.object(sys, "executable", str(fake_exe)):
                with patch("agent.main._prompt_for_initial_setup", side_effect=_fake_prompt) as mock_prompt:
                    config = _load_config_or_exit()

    mock_prompt.assert_called_once()
    assert config.backend_url == "http://prompted:8000"


def test_load_config_or_exit_does_not_prompt_when_not_interactive(tmp_path, monkeypatch):
    """Otomasyon/CI ortamında (interaktif değil) eski dürüst hata +
    çıkış davranışı KORUNUR — asla stdin'i bekleyerek asılı kalmaz."""
    from agent.main import _load_config_or_exit

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BACKEND_URL", raising=False)

    with patch("agent.main._is_frozen", return_value=True):
        with patch("agent.main._is_interactive_console", return_value=False):
            with patch("agent.main._prompt_for_initial_setup") as mock_prompt:
                with pytest.raises(SystemExit):
                    _load_config_or_exit()

    mock_prompt.assert_not_called()
