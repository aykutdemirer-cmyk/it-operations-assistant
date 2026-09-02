"""`app/agents/rdp.py` için testler — gerçek bir RDP bağlantısı ASLA
kurulmaz, yalnızca `.rdp` dosya içeriği üretimi test edilir."""

import pytest

from app.agents.rdp import NoConnectableAddressError, build_rdp_file


def test_build_rdp_file_includes_full_address():
    content = build_rdp_file(local_ip="10.0.213.30", username=None)
    assert "full address:s:10.0.213.30" in content


def test_build_rdp_file_includes_username_when_known():
    content = build_rdp_file(local_ip="10.0.213.30", username="Administrator")
    assert "username:s:Administrator" in content


def test_build_rdp_file_omits_username_when_unknown():
    content = build_rdp_file(local_ip="10.0.213.30", username=None)
    assert "username:s:" not in content


def test_build_rdp_file_raises_when_no_local_ip():
    with pytest.raises(NoConnectableAddressError):
        build_rdp_file(local_ip=None, username="Administrator")


def test_build_rdp_file_uses_crlf_line_endings():
    """Windows `.rdp` dosya formatı CRLF bekler — LF ile üretilirse
    bazı istemcilerde satırlar yanlış parse edilebilir."""
    content = build_rdp_file(local_ip="10.0.213.30", username=None)
    assert "\r\n" in content
