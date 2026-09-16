"""Faz 52 — LDAP Bind-Auth Girişi (opt-in) + Otomatik AD Kullanıcı
Provisioning.

Faz 49'un kendi dokümantasyonu bunu KASITLI kapsam dışı bırakmıştı
("gerçek LDAP SSO/bind-auth login ayrı, çok daha büyük bir güvenlik
yüzeyi") — kullanıcının açık isteğiyle burada BİLİNÇLİ olarak
genişletiliyor. Gerçek risk aynen geçerli: bu yol açıldığında, AD'de
GEÇERLİ bir hesabı olan HERKES (senkronize edilmiş olmak kaydıyla) bu
sisteme otomatik bir hesapla girebilir. Bu yüzden İKİ ayrı korumayla
opt-in: `LDAP_AUTH_ENABLED` (varsayılan `false`, `.env`) VE otomatik
provizyon edilen hesaplara kullanıcının önerdiği `OPERATOR` YERİNE
`VIEWER` varsayılan rolü (üç rolün en düşük yetkilisi — admin gerekirse
sonradan elle yükseltir; `LDAP_AUTH_DEFAULT_ROLE` ile override
edilebilir)."""

from __future__ import annotations

import asyncio
import logging
import os

import asyncpg
from ldap3 import SIMPLE, Connection, Server
from ldap3.core.exceptions import LDAPException

from app.auth.permissions import default_permissions_for_role
from app.db.ldap import get_ad_user_by_username, get_config
from app.db.users import get_user_by_ad_username, get_user_by_username, insert_ad_user, set_permissions, update_ad_profile

logger = logging.getLogger("app.services.ldap_auth")

_BIND_TIMEOUT_SECONDS = 8
_VALID_ROLES = ("ADMIN", "OPERATOR", "VIEWER")


def is_ldap_auth_enabled() -> bool:
    raw = os.environ.get("LDAP_AUTH_ENABLED", "false")
    return raw.strip().lower() in ("1", "true", "yes")


def default_ldap_role() -> str:
    role = os.environ.get("LDAP_AUTH_DEFAULT_ROLE", "VIEWER").strip().upper()
    return role if role in _VALID_ROLES else "VIEWER"


def _blocking_bind(*, host: str, port: int, use_ssl: bool, domain_fqdn: str, username: str, password: str) -> bool:
    """SENKRON — `asyncio.to_thread` ile çağrılmalı (bkz. `app/services/
    ldap.py::_blocking_search`'teki AYNI gerekçe, `ldap3` asyncio
    desteklemiyor). Kasıtlı olarak `app/services/ldap.py::_bind_
    candidates`'in çok-formatlı deneme mantığını TEKRARLAMAZ — gerçek
    kullanıcı girişinde tek, bilinen-doğru format (UPN) yeterli; servis
    hesabı bağlantısının aksine burada NTLM/tam-DN fallback'i
    GEREKMEZ (bu domain'de UPN formatının çalıştığı canlı olarak
    doğrulandı, bkz. docs/roadmap.md Faz 49 sonrası notu)."""
    server = Server(host, port=port, use_ssl=use_ssl, connect_timeout=_BIND_TIMEOUT_SECONDS)
    connection = Connection(
        server,
        user=f"{username}@{domain_fqdn}",
        password=password,
        authentication=SIMPLE,
        receive_timeout=_BIND_TIMEOUT_SECONDS,
    )
    try:
        return connection.bind()
    finally:
        connection.unbind()


async def authenticate_and_provision(conn: asyncpg.Connection, *, username: str, password: str) -> asyncpg.Record | None:
    """LDAP bind ile kimlik doğrular; başarılıysa bu AD kullanıcısına
    bağlı bir yerel `users` satırı (var olan ya da YENİ provizyon
    edilen) döner. `None` — LDAP yapılandırılmamış, bind başarısız, VEYA
    kullanıcı henüz senkronize edilmemiş (bkz. aşağıdaki not) demektir;
    `app/auth/service.py::login` bunu diğer başarısızlıklarla AYNI genel
    401'e çevirir (enumeration önleme — Faz 46'nın kendi ilkesiyle
    tutarlı).

    **Bilinçli tasarım kararı:** provizyon SADECE bu kullanıcı zaten
    `ad_users`'ta (bkz. Faz 49'un periyodik senkronizasyonu) varsa
    çalışır — bind BAŞARILI olsa bile `ad_users`'ta yoksa reddedilir.
    Giriş sırasında AD'ye ANLIK bir "bu kullanıcının displayName/mail'i
    ne" sorgusu ATILMIYOR — tek doğruluk kaynağı hâlâ periyodik/manuel
    senkronizasyon (Faz 49'un "ad_groups/ad_users yalnızca sync job'ta
    yazılır" değişmezini bozmuyor)."""
    if not is_ldap_auth_enabled():
        return None

    config = await get_config(conn)
    if config is None:
        return None

    try:
        bound = await _run_bind(config, username, password)
    except LDAPException as exc:
        logger.info("LDAP girişi başarısız (bind): %s — %s", username, type(exc).__name__)
        return None
    except OSError as exc:
        logger.warning("LDAP girişi başarısız (ağ): %s — %s", username, exc)
        return None

    if not bound:
        return None

    ad_user = await get_ad_user_by_username(conn, username)
    if ad_user is None:
        logger.info("LDAP bind başarılı ama '%s' henüz senkronize edilmemiş (ad_users'ta yok)", username)
        return None

    existing = await get_user_by_ad_username(conn, username)
    if existing is not None:
        await update_ad_profile(conn, existing["id"], full_name=ad_user["display_name"], email=ad_user["email"])
        return await get_user_by_ad_username(conn, username)

    # `users.username` UNIQUE — bu AD kullanıcı adıyla BAĞLANTISIZ bir
    # yerel hesap ZATEN varsa (ör. `ad_username` hiç set edilmemiş bir
    # yerel kullanıcı, aynı isimde), otomatik provizyon buraya
    # KÖRLEMESİNE bir INSERT ile çakışırdı (`UniqueViolationError`) —
    # ya da daha kötüsü, o hesabı SESSİZCE AD kimliğine bağlardı. İkisi
    # de admin'in ELLE onaylaması gereken bir karar (bkz. `PUT /api/
    # pam/users/{id}` — `ad_username` alanı), burada OTOMATİK
    # yapılmaz — reddedilir.
    username_collision = await get_user_by_username(conn, username)
    if username_collision is not None:
        logger.warning(
            "LDAP bind başarılı ama '%s' zaten bağlantısız bir yerel hesapla çakışıyor — otomatik provizyon reddedildi",
            username,
        )
        return None

    role = default_ldap_role()
    row = await insert_ad_user(
        conn,
        username=username,
        ad_username=username,
        role=role,
        full_name=ad_user["display_name"],
        email=ad_user["email"],
    )
    await set_permissions(conn, row["id"], default_permissions_for_role(role))
    logger.info("Yeni AD kullanıcısı otomatik provizyon edildi: %s (rol=%s)", username, role)
    return row


class AdUserNotFoundError(Exception):
    """`create_user_from_ad` — verilen `ad_username` senkronize edilmiş
    `ad_users`'ta yok (bkz. Ayarlar > Active Directory / LDAP'ta "Şimdi
    Senkronize Et")."""


class AdUserAlreadyLinkedError(Exception):
    """Bu AD hesabı zaten BAŞKA bir yerel kullanıcıya bağlı — aynı AD
    hesabından iki yerel hesap türetilemez (`users.ad_username`'ın
    doğası gereği zaten tekil, ama net bir hata mesajı için erken
    kontrol edilir)."""


async def create_user_from_ad(conn: asyncpg.Connection, *, ad_username: str, role: str) -> asyncpg.Record:
    """Admin'in `/pam/users` ekranındaki "Active Directory'den İçe
    Aktar" eylemi — `authenticate_and_provision`'ın AKSİNE canlı bir
    LDAP bind GEREKMEZ (admin zaten kendi PAM_ADMIN yetkisiyle bu
    kararı VERİYOR), yalnızca `ad_username`'in senkronize dizinde
    (`ad_users`) var olması yeterli."""
    ad_user = await get_ad_user_by_username(conn, ad_username)
    if ad_user is None:
        raise AdUserNotFoundError()
    if await get_user_by_ad_username(conn, ad_username) is not None:
        raise AdUserAlreadyLinkedError()
    if await get_user_by_username(conn, ad_username) is not None:
        raise AdUserAlreadyLinkedError()

    row = await insert_ad_user(
        conn,
        username=ad_username,
        ad_username=ad_username,
        role=role,
        full_name=ad_user["display_name"],
        email=ad_user["email"],
    )
    await set_permissions(conn, row["id"], default_permissions_for_role(role))
    return row


async def _run_bind(config: asyncpg.Record, username: str, password: str) -> bool:
    return await asyncio.to_thread(
        _blocking_bind,
        host=config["host"],
        port=config["port"],
        use_ssl=config["use_ssl"],
        domain_fqdn=config["domain_fqdn"],
        username=username,
        password=password,
    )
