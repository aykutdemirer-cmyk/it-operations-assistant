"""Faz 49 — LDAP/Active Directory bağlantı testi ve dizin senkronizasyonu.

Bu proje LDAP-tabanlı GİRİŞ (bind auth) UYGULAMAMAKTADIR — kullanıcı
girişi Faz 46'dan beri hâlâ yerel bcrypt (`users.password_hash`).
Buradaki entegrasyon YALNIZCA: (1) AD kullanıcı/grup dizinini
periyodik olarak senkronize edip PAM'in kural ekranında göstermek,
(2) bir yerel `users` satırını (`users.ad_username`) bir AD hesabına
BAĞLAMAK (admin'in ELLE yaptığı bir eşleme — otomatik/örtük DEĞİL,
Faz 29'un Agent↔Asset eşleştirmesindeki temkinlilikle AYNI ilke),
(3) o bağlı kullanıcının AD grup üyeliklerinden gelen `pam_access_
rules` satırlarını da yetkilendirme sırasında dikkate almak (bkz.
`app/pam/service.py::authorize_ssh_session`/`authorize_rdp_session`).

`ldap3` (LGPL-3.0, saf Python) `python-ldap` YERİNE tercih edildi —
o OpenLDAP C başlıklarına karşı DERLENMESİ gerekiyor, bu Windows
Server ortamında ek bir derleme zinciri gerektirirdi.

Yalnızca DOĞRUDAN (`memberOf`) grup üyelikleri çözülür — iç içe
(nested) AD grup üyeliği (bir grubun başka bir grubun üyesi olması)
KASITLI olarak kapsam dışı: doğru çözümlemek "primary group" özel
durumu + döngüsel referans koruması gerektiren, ayrı bir iş; yanlış/
eksik bir nested-group çözümlemesi GERÇEK bir yetkilendirme açığına
yol açabilir, bu yüzden hiç UYDURULMADI — yalnızca gerçekten
`memberOf`'ta görünen doğrudan üyelikler senkronize edilir."""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from typing import TypedDict

import asyncpg
from ldap3 import NTLM, SIMPLE, Connection, Server
from ldap3.core.exceptions import LDAPException

from app.db import ldap as db
from app.pam.vault import decrypt_payload, encrypt_payload

logger = logging.getLogger("app.services.ldap")

_SEARCH_TIMEOUT_SECONDS = 15
_TCP_CHECK_TIMEOUT_SECONDS = 5


class LdapConnectError(Exception):
    """LDAP sunucusuna bağlanılamadı/bind başarısız. Mesajı ldap3'ün
    GERÇEK hata detayını (exception tipi + sunucunun `result` açıklaması)
    taşır — hiçbir zaman düz metin parola İÇERMEZ (ldap3 exception'ları
    zaten parola değerini hiç taşımıyor, yalnızca DN/sonuç kodu), bu
    yüzden bu detayı hem admin'e (test/sync sonucu) hem log'a vermek
    CLAUDE.md'nin "kimlik bilgisi/ham kimlik doğrulama verisi
    loglanmaz" kuralını ihlal etmiyor — DN ve LDAP sonuç açıklaması bir
    "kimlik bilgisi" değil, bir bağlantı teşhis bilgisidir."""


class LdapConnectionParams(TypedDict):
    host: str
    port: int
    use_ssl: bool
    domain_fqdn: str
    bind_dn: str
    bind_password: str
    base_dn: str


@dataclass
class SyncResult:
    groups_synced: int
    users_synced: int
    memberships_synced: int


def encrypt_bind_password(password: str) -> str:
    """LDAP bind parolası `vault_credentials` ile AYNI Fernet anahtarını
    (`PAM_VAULT_SECRET_KEY`) kullanır — YENİ bir şifreleme anahtarı
    EKLENMEDİ, aynı "PAM kasası" güvenlik sınırının doğal bir uzantısı."""
    return encrypt_payload({"password": password})


def decrypt_bind_password(encrypted: str) -> str:
    return decrypt_payload(encrypted)["password"]


def _check_tcp_reachable(host: str, port: int) -> None:
    """LDAP/TLS protokolünden ÖNCE ham bir TCP `connect()` dener —
    sertifika/TLS doğrulaması OLMADAN, salt "bu host:port'a hiç
    ulaşılabiliyor mu" sorusuna dürüst bir cevap verir. IP ile girilen
    (DNS'siz) Domain Controller'larda "sunucuya hiç ulaşılamıyor" ile
    "sunucuya ulaşıldı ama bind reddedildi" hatalarını ayırt etmenin
    tek güvenilir yolu bu — ldap3'ün kendi hata mesajları ikisini de
    aynı genel istisnaya sarabiliyor."""
    try:
        with socket.create_connection((host, port), timeout=_TCP_CHECK_TIMEOUT_SECONDS):
            return
    except OSError as exc:
        raise LdapConnectError(f"{host}:{port} adresine TCP ile ulaşılamadı ({exc})") from exc


def _bind_candidates(bind_dn: str, domain_fqdn: str) -> list[tuple[str, str]]:
    """Kullanıcının girdiği Bind DN zaten tam bir DN (`CN=...`), UPN
    (`user@domain`) ya da NTLM (`DOMAIN\\user`) formatındaysa AYNEN
    (tek adayla) kullanılır. Yalın bir sAMAccountName (`svc_ldap` gibi)
    girildiyse — Active Directory'nin simple bind'i bunu KABUL ETMEZ,
    DN veya UPN ister — otomatik olarak UPN (`svc_ldap@domain.fqdn`,
    SIMPLE) ve NTLM (`DOMAIN\\svc_ldap`, NTLM) formatlarıyla SIRAYLA
    dener."""
    stripped = bind_dn.strip()
    if "=" in stripped or "@" in stripped or "\\" in stripped:
        return [(stripped, NTLM if "\\" in stripped else SIMPLE)]

    domain_prefix = domain_fqdn.split(".")[0].upper() if domain_fqdn else ""
    candidates: list[tuple[str, str]] = []
    if domain_fqdn:
        candidates.append((f"{stripped}@{domain_fqdn}", SIMPLE))
    if domain_prefix:
        candidates.append((f"{domain_prefix}\\{stripped}", NTLM))
    if not candidates:
        candidates.append((stripped, SIMPLE))
    return candidates


def _bind_connection(server: Server, params: LdapConnectionParams) -> Connection:
    """`_bind_candidates`'in ürettiği formatları SIRAYLA dener, ilk
    başarılı bind'i döner. Hepsi başarısız olursa, DENENEN HER formatın
    gerçek ldap3 sonucunu (`connection.result` — DN + LDAP sonuç kodu/
    açıklaması, PAROLA DEĞİL) tek bir `LdapConnectError` mesajında
    birleştirir; genel/anlamsız bir "bağlanılamadı" mesajı YERİNE bu,
    kullanıcının gerçekten hangi formatın neden reddedildiğini görmesini
    sağlar."""
    attempt_errors: list[str] = []
    for user, authentication in _bind_candidates(params["bind_dn"], params.get("domain_fqdn", "")):
        connection = Connection(
            server,
            user=user,
            password=params["bind_password"],
            authentication=authentication,
            receive_timeout=_SEARCH_TIMEOUT_SECONDS,
        )
        try:
            if connection.bind():
                return connection
            result = connection.result or {}
            attempt_errors.append(f"{user}: {result.get('description')} — {result.get('message')}")
            connection.unbind()
        except LDAPException as exc:
            attempt_errors.append(f"{user}: {type(exc).__name__}: {exc}")
        except Exception as exc:
            # `ldap3`'ün NTLM implementasyonu MD4 hash kullanıyor —
            # bazı Python/OpenSSL derlemelerinde (OpenSSL 3.x varsayılan
            # sağlayıcısı MD4'ü güvensiz kabul edip devre dışı bırakıyor)
            # bu `hashlib`'den `LDAPException` OLMAYAN bir `ValueError`
            # olarak geliyor (gerçek bu ortamda GÖZLEMLENDİ) — burada
            # yakalanmazsa TÜM istek 500 ile çöküyordu. Diğer formatların
            # denenmeye devam edebilmesi için genel `Exception` da
            # yakalanıp bir sonraki adaya geçiliyor.
            attempt_errors.append(f"{user}: {type(exc).__name__}: {exc}")
    raise LdapConnectError("Bind başarısız — denenen format(lar): " + "; ".join(attempt_errors))


def _blocking_search(params: LdapConnectionParams) -> tuple[list[dict], list[dict]]:
    """SENKRON (bloklayan) LDAP taraması — `asyncio.to_thread` ile
    çağrılmalı, `ldap3` asyncio DESTEKLEMEZ, event loop'u BLOKLAMAMAK
    için ayrı bir thread'e alınır. Yalnızca bu fonksiyonun İÇİNDE
    kimlik bilgisi (plaintext bind parolası) belleğe gelir — dönüş
    değerinde HİÇBİR kimlik bilgisi yok."""
    _check_tcp_reachable(params["host"], params["port"])
    server = Server(params["host"], port=params["port"], use_ssl=params["use_ssl"], connect_timeout=_SEARCH_TIMEOUT_SECONDS)
    connection = _bind_connection(server, params)
    try:
        connection.search(
            params["base_dn"],
            "(objectClass=group)",
            attributes=["cn"],
        )
        groups = [
            {"dn": entry.entry_dn, "name": str(entry.cn) if entry.cn else entry.entry_dn}
            for entry in connection.entries
        ]

        connection.search(
            params["base_dn"],
            "(&(objectClass=user)(objectCategory=person))",
            attributes=["sAMAccountName", "displayName", "memberOf", "mail"],
        )
        users = [
            {
                "dn": entry.entry_dn,
                "username": str(entry.sAMAccountName) if entry.sAMAccountName else None,
                "display_name": str(entry.displayName) if entry.displayName else None,
                # Faz 52 — `POST /api/auth/login`'in LDAP provisioning
                # yolu için (`users.email`'e kopyalanır).
                "email": str(entry.mail) if entry.mail else None,
                "member_of": [str(dn) for dn in entry.memberOf] if entry.memberOf else [],
            }
            for entry in connection.entries
            if entry.sAMAccountName
        ]
        return groups, users
    finally:
        connection.unbind()


async def test_connection(params: LdapConnectionParams) -> None:
    """Yalnızca bağlanıp bind olur, hiçbir şey senkronize ETMEZ —
    `POST /api/settings/ldap/test`'in karşılığı, kaydedilmemiş form
    parametreleriyle de çağrılabilir. Başarısızlıkta `LdapConnectError`
    (`_check_tcp_reachable`/`_bind_connection`'dan gelen DETAYLI mesajla,
    bkz. o fonksiyonların docstring'i) — burada genel bir mesajla
    ÜZERİNE YAZILMAZ."""
    try:
        await asyncio.to_thread(_blocking_search, params)
    except LdapConnectError as exc:
        logger.warning("LDAP bağlantı testi başarısız: %s", exc)
        raise
    except LDAPException as exc:
        logger.warning("LDAP bağlantı testi başarısız (arama adımı): %s", type(exc).__name__)
        raise LdapConnectError(f"LDAP arama hatası: {type(exc).__name__}: {exc}") from exc
    except OSError as exc:
        raise LdapConnectError(f"LDAP sunucusuna ağ üzerinden ulaşılamadı: {exc}") from exc


async def sync_directory(conn: asyncpg.Connection, params: LdapConnectionParams) -> SyncResult:
    """Gerçek bir senkronizasyon turu — AD'deki grupları/kullanıcıları/
    doğrudan üyelikleri okuyup `ad_groups`/`ad_users`/`ad_group_
    memberships`'i TAM olarak (idempotent — mevcut kayıtlar güncellenir,
    AD'de artık bulunmayanlar SİLİNİR) bu veriyle eşitler. `LDAPException`
    kasıtlı olarak burada YAKALANMAZ — çağıran taraf (route katmanı)
    `LdapConnectError`'a çevirip `ldap_config.last_sync_status`'u
    günceller."""
    try:
        groups, users = await asyncio.to_thread(_blocking_search, params)
    except LdapConnectError:
        raise
    except LDAPException as exc:
        raise LdapConnectError(f"LDAP arama hatası: {type(exc).__name__}: {exc}") from exc
    except OSError as exc:
        raise LdapConnectError(f"LDAP sunucusuna ağ üzerinden ulaşılamadı: {exc}") from exc

    async with conn.transaction():
        group_id_by_dn = await db.replace_groups(conn, groups)
        user_id_by_dn = await db.replace_users(conn, users)

        memberships: list[tuple[str, str]] = []
        for user in users:
            user_id = user_id_by_dn.get(user["dn"])
            if user_id is None:
                continue
            for group_dn in user["member_of"]:
                group_id = group_id_by_dn.get(group_dn)
                if group_id is not None:
                    memberships.append((user_id, group_id))
        await db.replace_memberships(conn, memberships)

    return SyncResult(groups_synced=len(groups), users_synced=len(users), memberships_synced=len(memberships))
