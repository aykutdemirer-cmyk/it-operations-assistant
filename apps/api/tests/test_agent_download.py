"""Windows Agent EXE download testleri (Faz 32). Gerçek bir PyInstaller
build'i ÇALIŞTIRILMAZ — `app.agents.download` modülünün dist dizini/
build-info.json yolu sabitleri `unittest.mock.patch` ile geçici bir
`tmp_path`'e yönlendirilir. Bu route'lar DB'ye hiç dokunmaz, bu yüzden
`isolated_db` gerekmez — düz `client` fixture'ı yeterli."""

import json
from unittest.mock import patch

import pytest

from app.agents.download import ArtifactNotAvailableError, resolve_windows_agent_artifact


def _write_build_info(dist_dir, *, filename="IT-Operations-Agent-1.0.0.exe", version="1.0.0", exe_content=b"fake-exe-bytes", **overrides):
    dist_dir.mkdir(parents=True, exist_ok=True)
    exe_path = dist_dir / filename
    exe_path.write_bytes(exe_content)
    info = {"version": version, "filename": filename, "size_bytes": len(exe_content), "built_at": "2026-01-01T00:00:00Z"}
    info.update(overrides)
    (dist_dir / "build-info.json").write_text(json.dumps(info), encoding="utf-8")
    return exe_path


def _patched(dist_dir):
    return patch.multiple(
        "app.agents.download",
        _DIST_DIR=dist_dir,
        _BUILD_INFO_PATH=dist_dir / "build-info.json",
    )


# --- app.agents.download birim testleri (HTTP katmanı olmadan) ---


def test_resolve_artifact_raises_when_build_info_missing(tmp_path):
    with _patched(tmp_path):
        with pytest.raises(ArtifactNotAvailableError):
            resolve_windows_agent_artifact()


def test_resolve_artifact_returns_real_metadata_when_present(tmp_path):
    _write_build_info(tmp_path)
    with _patched(tmp_path):
        artifact = resolve_windows_agent_artifact()

    assert artifact.version == "1.0.0"
    assert artifact.filename == "IT-Operations-Agent-1.0.0.exe"
    assert artifact.size_bytes == len(b"fake-exe-bytes")


def test_resolve_artifact_handles_utf8_bom_from_powershell(tmp_path):
    """Windows PowerShell 5.1'in `Set-Content -Encoding utf8`'i bir BOM
    (byte order mark) EKLER — bu, build.ps1'in gerçek kullanımında
    tekrar tekrar karşılaşılan, gerçek bir hata olarak bulundu (bkz.
    docs/decisions.md). `resolve_windows_agent_artifact` BOM'lu bir
    dosyayı da doğru okuyabilmeli."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    exe_path = tmp_path / "IT-Operations-Agent-1.0.0.exe"
    exe_path.write_bytes(b"fake-exe")
    info = {"version": "1.0.0", "filename": exe_path.name, "size_bytes": 8, "built_at": "2026-01-01T00:00:00Z"}
    # `utf-8-sig` ile yazmak Python tarafında BOM eklemenin en kolay yolu.
    (tmp_path / "build-info.json").write_text(json.dumps(info), encoding="utf-8-sig")

    with _patched(tmp_path):
        artifact = resolve_windows_agent_artifact()

    assert artifact.version == "1.0.0"


def test_resolve_artifact_raises_when_build_info_corrupted(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "build-info.json").write_text("not valid json{{{", encoding="utf-8")
    with _patched(tmp_path):
        with pytest.raises(ArtifactNotAvailableError):
            resolve_windows_agent_artifact()


def test_resolve_artifact_raises_when_exe_file_missing_despite_manifest(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    info = {"version": "1.0.0", "filename": "ghost.exe", "size_bytes": 100, "built_at": "2026-01-01T00:00:00Z"}
    (tmp_path / "build-info.json").write_text(json.dumps(info), encoding="utf-8")
    with _patched(tmp_path):
        with pytest.raises(ArtifactNotAvailableError):
            resolve_windows_agent_artifact()


def test_resolve_artifact_rejects_path_traversal_filename(tmp_path):
    """`build-info.json` sunucu tarafında üretilse de (kullanıcıdan
    DEĞİL) savunma amaçlı — `..` içeren bir dosya adı asla kabul
    edilmez."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    info = {"version": "1.0.0", "filename": "../../etc/passwd", "size_bytes": 1, "built_at": "x"}
    (tmp_path / "build-info.json").write_text(json.dumps(info), encoding="utf-8")
    with _patched(tmp_path):
        with pytest.raises(ArtifactNotAvailableError):
            resolve_windows_agent_artifact()


def test_resolve_artifact_rejects_non_exe_filename(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    info = {"version": "1.0.0", "filename": "malicious.sh", "size_bytes": 1, "built_at": "x"}
    (tmp_path / "build-info.json").write_text(json.dumps(info), encoding="utf-8")
    with _patched(tmp_path):
        with pytest.raises(ArtifactNotAvailableError):
            resolve_windows_agent_artifact()


# --- HTTP route testleri ---


@pytest.mark.anyio
async def test_download_info_reports_unavailable_when_not_built(client, tmp_path):
    with _patched(tmp_path):
        response = await client.get("/api/agents/download/windows/info")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["version"] is None
    assert body["size_bytes"] is None


@pytest.mark.anyio
async def test_download_info_reports_real_metadata_when_built(client, tmp_path):
    _write_build_info(tmp_path, version="1.2.3", filename="IT-Operations-Agent-1.2.3.exe", exe_content=b"x" * 500)

    with _patched(tmp_path):
        response = await client.get("/api/agents/download/windows/info")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "available": True,
        "version": "1.2.3",
        "filename": "IT-Operations-Agent-1.2.3.exe",
        "size_bytes": 500,
        "built_at": "2026-01-01T00:00:00Z",
    }


@pytest.mark.anyio
async def test_download_windows_returns_404_when_not_built(client, tmp_path):
    with _patched(tmp_path):
        response = await client.get("/api/agents/download/windows")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_download_windows_returns_real_file_with_correct_headers(client, tmp_path):
    content = b"fake-real-exe-bytes-for-test"
    _write_build_info(tmp_path, version="1.0.0", filename="IT-Operations-Agent-1.0.0.exe", exe_content=content)

    with _patched(tmp_path):
        response = await client.get("/api/agents/download/windows")

    assert response.status_code == 200
    assert response.content == content
    assert 'attachment; filename="IT-Operations-Agent-1.0.0.exe"' in response.headers["content-disposition"]


@pytest.mark.anyio
async def test_download_windows_never_leaks_server_filesystem_paths_in_error(client, tmp_path):
    with _patched(tmp_path):
        response = await client.get("/api/agents/download/windows")

    assert str(tmp_path) not in response.text
