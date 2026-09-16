"""Windows Agent EXE download testleri (Faz 32). Gerçek bir PyInstaller
build'i ÇALIŞTIRILMAZ — `app.agents.download` modülünün dist dizini/
build-info.json yolu sabitleri `unittest.mock.patch` ile geçici bir
`tmp_path`'e yönlendirilir. Bu route'lar DB'ye hiç dokunmaz, bu yüzden
`isolated_db` gerekmez — düz `client` fixture'ı yeterli."""

import json
import zipfile
from io import BytesIO
from unittest.mock import patch

import pytest

from app.agents.download import (
    ArtifactNotAvailableError,
    build_windows_service_bundle_zip,
    resolve_windows_agent_artifact,
    resolve_windows_service_artifact,
)


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


# --- Windows Servisi paketi (başka bir bilgisayara kurmak için ZIP) ---


def _write_service_build_info(dist_dir, *, filename="itops-agent.exe", version="1.0.0", exe_content=b"fake-service-exe", **overrides):
    dist_dir.mkdir(parents=True, exist_ok=True)
    exe_path = dist_dir / filename
    exe_path.write_bytes(exe_content)
    info = {"version": version, "filename": filename, "size_bytes": len(exe_content), "built_at": "2026-01-01T00:00:00Z"}
    info.update(overrides)
    (dist_dir / "service-build-info.json").write_text(json.dumps(info), encoding="utf-8")
    return exe_path


def _write_fake_scripts(scripts_dir):
    scripts_dir.mkdir(parents=True, exist_ok=True)
    install_path = scripts_dir / "install_windows_service.ps1"
    uninstall_path = scripts_dir / "uninstall_windows_service.ps1"
    install_path.write_text("# fake install script\n", encoding="utf-8")
    uninstall_path.write_text("# fake uninstall script\n", encoding="utf-8")
    return install_path, uninstall_path


def _patched_service(dist_dir, scripts_dir=None):
    targets = {
        "_DIST_DIR": dist_dir,
        "_SERVICE_BUILD_INFO_PATH": dist_dir / "service-build-info.json",
    }
    if scripts_dir is not None:
        targets["_INSTALL_SCRIPT_PATH"] = scripts_dir / "install_windows_service.ps1"
        targets["_UNINSTALL_SCRIPT_PATH"] = scripts_dir / "uninstall_windows_service.ps1"
    return patch.multiple("app.agents.download", **targets)


def test_resolve_service_artifact_raises_when_build_info_missing(tmp_path):
    with _patched_service(tmp_path):
        with pytest.raises(ArtifactNotAvailableError):
            resolve_windows_service_artifact()


def test_resolve_service_artifact_returns_real_metadata_when_present(tmp_path):
    _write_service_build_info(tmp_path)
    with _patched_service(tmp_path):
        artifact = resolve_windows_service_artifact()

    assert artifact.version == "1.0.0"
    assert artifact.filename == "itops-agent.exe"
    assert artifact.size_bytes == len(b"fake-service-exe")


def test_resolve_service_artifact_rejects_path_traversal_filename(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    info = {"version": "1.0.0", "filename": "../../etc/passwd", "size_bytes": 1, "built_at": "x"}
    (tmp_path / "service-build-info.json").write_text(json.dumps(info), encoding="utf-8")
    with _patched_service(tmp_path):
        with pytest.raises(ArtifactNotAvailableError):
            resolve_windows_service_artifact()


def test_build_service_bundle_zip_contains_exe_scripts_and_readme(tmp_path):
    exe_path = _write_service_build_info(tmp_path / "dist", exe_content=b"real-exe-bytes-here")
    install_path, uninstall_path = _write_fake_scripts(tmp_path / "scripts")

    with _patched_service(tmp_path / "dist", tmp_path / "scripts"):
        artifact = resolve_windows_service_artifact()
        zip_bytes = build_windows_service_bundle_zip(artifact)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert names == {
            "itops-agent.exe",
            "install_windows_service.ps1",
            "uninstall_windows_service.ps1",
            "README.txt",
        }
        assert zf.read("itops-agent.exe") == exe_path.read_bytes()
        assert zf.read("install_windows_service.ps1") == install_path.read_bytes()
        assert zf.read("uninstall_windows_service.ps1") == uninstall_path.read_bytes()
        readme = zf.read("README.txt").decode("utf-8")
        assert "install_windows_service.ps1" in readme
        assert "ITOpsAgent" in readme


def test_build_service_bundle_zip_raises_when_scripts_missing(tmp_path):
    _write_service_build_info(tmp_path / "dist")
    # scripts dizini KASITLI oluşturulmadı.
    with _patched_service(tmp_path / "dist", tmp_path / "scripts"):
        artifact = resolve_windows_service_artifact()
        with pytest.raises(ArtifactNotAvailableError):
            build_windows_service_bundle_zip(artifact)


@pytest.mark.anyio
async def test_service_download_info_reports_unavailable_when_not_built(client, tmp_path):
    with _patched_service(tmp_path):
        response = await client.get("/api/agents/download/windows-service/info")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False


@pytest.mark.anyio
async def test_service_download_info_reports_real_metadata_when_built(client, tmp_path):
    _write_service_build_info(tmp_path, version="1.0.0", exe_content=b"x" * 300)

    with _patched_service(tmp_path):
        response = await client.get("/api/agents/download/windows-service/info")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "available": True,
        "version": "1.0.0",
        "filename": "itops-agent.exe",
        "size_bytes": 300,
        "built_at": "2026-01-01T00:00:00Z",
    }


@pytest.mark.anyio
async def test_download_windows_service_returns_404_when_not_built(client, tmp_path):
    with _patched_service(tmp_path):
        response = await client.get("/api/agents/download/windows-service")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_download_windows_service_returns_real_zip_with_correct_headers(client, tmp_path):
    _write_service_build_info(tmp_path / "dist", exe_content=b"real-service-exe")
    _write_fake_scripts(tmp_path / "scripts")

    with _patched_service(tmp_path / "dist", tmp_path / "scripts"):
        response = await client.get("/api/agents/download/windows-service")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'attachment; filename="itops-agent-windows-service.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        assert zf.read("itops-agent.exe") == b"real-service-exe"


@pytest.mark.anyio
async def test_download_windows_service_uses_the_real_repo_scripts_end_to_end(client, tmp_path):
    """Gerçek `apps/agent/scripts/*.ps1` dosyalarını (mock'lanmamış)
    kullanarak — bu testin geçmesi, gerçek kurulum script'lerinin
    ZIP'e doğru şekilde paketlendiğini kanıtlar."""
    _write_service_build_info(tmp_path, exe_content=b"real-exe")

    with patch.multiple(
        "app.agents.download",
        _DIST_DIR=tmp_path,
        _SERVICE_BUILD_INFO_PATH=tmp_path / "service-build-info.json",
    ):
        response = await client.get("/api/agents/download/windows-service")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        install_content = zf.read("install_windows_service.ps1").decode("utf-8")
        assert "ITOpsAgent" in install_content
        assert "sc.exe create" in install_content
