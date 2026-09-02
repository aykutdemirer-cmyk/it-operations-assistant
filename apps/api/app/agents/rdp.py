"""Faz 34 — Hızlı Bağlantı: RDP `.rdp` dosyası üretimi.

Backend hiçbir zaman bir RDP bağlantısı BAŞLATMAZ — yalnızca
istemcinin kendi Uzak Masaüstü Bağlantısı uygulamasının (`mstsc.exe`)
açacağı standart bir `.rdp` metin dosyası üretir. Gerçek bağlantıyı
kullanıcının kendi makinesi, kendi kimlik bilgileriyle kurar."""

from __future__ import annotations


class NoConnectableAddressError(Exception):
    """Agent'ın bilinen bir `local_ip`'si yok — sahte/uydurma bir IP
    ile `.rdp` dosyası ÜRETİLMEZ."""


def build_rdp_file(*, local_ip: str | None, username: str | None) -> str:
    """`full address:s:<ip>` zorunlu; `username:s:<user>` yalnızca
    biliniyorsa (ör. `last_logged_in_user`) eklenir — bilinmiyorsa
    RDP istemcisi kullanıcıdan kendisi sorar, uydurma bir kullanıcı
    adı ASLA yazılmaz."""
    if not local_ip:
        raise NoConnectableAddressError("Agent'ın bilinen bir yerel IP adresi yok")

    lines = [
        f"full address:s:{local_ip}",
        "prompt for credentials:i:1",
    ]
    if username:
        lines.append(f"username:s:{username}")
    return "\r\n".join(lines) + "\r\n"
