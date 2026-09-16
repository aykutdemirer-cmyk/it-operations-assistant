"""Faz 49 — `app/services/ldap.py` için gerçek bir AD sunucusu GEREKMEYEN
testler. `_blocking_search` (tek senkron LDAP I/O noktası) mock'lanır —
protokol/parsing mantığı `ldap3`'ün kendisi test edilmeden, yalnızca bu
modülün onun sonucunu nasıl işlediği doğrulanır."""

from unittest.mock import MagicMock, patch

import pytest
from ldap3 import NTLM, SIMPLE
from ldap3.core.exceptions import LDAPBindError

from app.services.ldap import (
    LdapConnectError,
    _bind_candidates,
    _bind_connection,
    _check_tcp_reachable,
    decrypt_bind_password,
    encrypt_bind_password,
    sync_directory,
)
from app.services.ldap import test_connection as ldap_test_connection

pytestmark = pytest.mark.anyio


def _params(**overrides):
    base = {
        "host": "dc01.lab.local",
        "port": 389,
        "use_ssl": False,
        "domain_fqdn": "lab.local",
        "bind_dn": "svc-ldap-sync@lab.local",
        "bind_password": "s3cret",
        "base_dn": "DC=lab,DC=local",
    }
    base.update(overrides)
    return base


def test_bind_candidates_leaves_full_dn_untouched():
    assert _bind_candidates("CN=svc,OU=User,DC=lab,DC=local", "lab.local") == [
        ("CN=svc,OU=User,DC=lab,DC=local", SIMPLE)
    ]


def test_bind_candidates_leaves_upn_untouched():
    assert _bind_candidates("svc_ldap@lab.local", "lab.local") == [("svc_ldap@lab.local", SIMPLE)]


def test_bind_candidates_leaves_ntlm_format_untouched():
    assert _bind_candidates("LAB\\svc_ldap", "lab.local") == [("LAB\\svc_ldap", NTLM)]


def test_bind_candidates_expands_bare_username_to_upn_then_ntlm():
    assert _bind_candidates("svc_ldap", "lab.local") == [
        ("svc_ldap@lab.local", SIMPLE),
        ("LAB\\svc_ldap", NTLM),
    ]


def test_check_tcp_reachable_raises_ldap_connect_error_on_refused_connection():
    with patch("app.services.ldap.socket.create_connection", side_effect=OSError("connection refused")):
        with pytest.raises(LdapConnectError):
            _check_tcp_reachable("10.0.213.240", 389)


def test_check_tcp_reachable_succeeds_when_socket_connects():
    with patch("app.services.ldap.socket.create_connection") as mocked:
        mocked.return_value.__enter__ = MagicMock(return_value=None)
        mocked.return_value.__exit__ = MagicMock(return_value=False)
        _check_tcp_reachable("10.0.213.240", 389)


def test_bind_connection_falls_back_to_ntlm_when_upn_bind_is_rejected():
    upn_connection = MagicMock()
    upn_connection.bind.return_value = False
    upn_connection.result = {"description": "invalidCredentials", "message": "data 52e"}

    ntlm_connection = MagicMock()
    ntlm_connection.bind.return_value = True

    with patch("app.services.ldap.Connection", side_effect=[upn_connection, ntlm_connection]):
        result = _bind_connection(MagicMock(), _params(bind_dn="svc_ldap"))

    assert result is ntlm_connection
    upn_connection.unbind.assert_called_once()


def test_bind_connection_survives_non_ldap_exception_from_one_candidate():
    """Gerçek üretim hatası: `ldap3`'ün NTLM implementasyonu bazı Python/
    OpenSSL derlemelerinde `hashlib`'den `LDAPException` OLMAYAN bir
    `ValueError` ('unsupported hash type MD4') fırlatıyor — bu, tek bir
    bind adayının çökmesi YÜZÜNDEN tüm isteğin 500 ile patlamasına yol
    açmıştı (canlıda gözlemlendi). `_bind_connection` diğer adaylara
    devam edebilmeli."""
    upn_connection = MagicMock()
    upn_connection.bind.side_effect = ValueError("unsupported hash type MD4")

    ntlm_connection = MagicMock()
    ntlm_connection.bind.return_value = True

    with patch("app.services.ldap.Connection", side_effect=[upn_connection, ntlm_connection]):
        result = _bind_connection(MagicMock(), _params(bind_dn="svc_ldap"))

    assert result is ntlm_connection


def test_bind_connection_raises_with_all_attempt_details_when_every_format_fails():
    failing_connection = MagicMock()
    failing_connection.bind.return_value = False
    failing_connection.result = {"description": "invalidCredentials", "message": "data 52e"}

    with patch("app.services.ldap.Connection", return_value=failing_connection):
        with pytest.raises(LdapConnectError, match="invalidCredentials"):
            _bind_connection(MagicMock(), _params(bind_dn="svc_ldap"))


def test_bind_password_round_trip_encrypts_and_decrypts():
    encrypted = encrypt_bind_password("hunter2")

    assert "hunter2" not in encrypted
    assert decrypt_bind_password(encrypted) == "hunter2"


async def test_ldap_test_connection_succeeds_when_blocking_search_succeeds():
    with patch("app.services.ldap._blocking_search", return_value=([], [])) as mocked:
        await ldap_test_connection(_params())
    mocked.assert_called_once()


async def test_ldap_test_connection_raises_ldap_connect_error_on_bind_failure():
    with patch("app.services.ldap._blocking_search", side_effect=LDAPBindError("invalid credentials")):
        with pytest.raises(LdapConnectError):
            await ldap_test_connection(_params())


async def test_ldap_test_connection_raises_ldap_connect_error_on_network_failure():
    with patch("app.services.ldap._blocking_search", side_effect=OSError("unreachable")):
        with pytest.raises(LdapConnectError):
            await ldap_test_connection(_params())


async def test_sync_directory_persists_groups_users_and_direct_memberships(isolated_db):
    groups = [
        {"dn": "CN=IT-Helpdesk,OU=Groups,DC=lab,DC=local", "name": "IT-Helpdesk"},
        {"dn": "CN=Domain Admins,OU=Groups,DC=lab,DC=local", "name": "Domain Admins"},
    ]
    users = [
        {
            "dn": "CN=Aykut,OU=Users,DC=lab,DC=local",
            "username": "aykut",
            "display_name": "Aykut Demirer",
            "member_of": ["CN=IT-Helpdesk,OU=Groups,DC=lab,DC=local"],
        }
    ]

    with patch("app.services.ldap._blocking_search", return_value=(groups, users)):
        result = await sync_directory(isolated_db, _params())

    assert result.groups_synced == 2
    assert result.users_synced == 1
    assert result.memberships_synced == 1

    group_ids = await isolated_db.fetch("SELECT id, name FROM ad_groups")
    assert {row["name"] for row in group_ids} == {"IT-Helpdesk", "Domain Admins"}

    membership_rows = await isolated_db.fetch(
        """
        SELECT g.name FROM ad_group_memberships m
        JOIN ad_users u ON u.id = m.ad_user_id
        JOIN ad_groups g ON g.id = m.ad_group_id
        WHERE u.username = $1
        """,
        "aykut",
    )
    assert [row["name"] for row in membership_rows] == ["IT-Helpdesk"]


async def test_sync_directory_removes_stale_groups_not_seen_in_latest_sync(isolated_db):
    with patch("app.services.ldap._blocking_search", return_value=([{"dn": "CN=Old,DC=lab,DC=local", "name": "Old"}], [])):
        await sync_directory(isolated_db, _params())

    with patch("app.services.ldap._blocking_search", return_value=([{"dn": "CN=New,DC=lab,DC=local", "name": "New"}], [])):
        await sync_directory(isolated_db, _params())

    names = {row["name"] for row in await isolated_db.fetch("SELECT name FROM ad_groups")}
    assert names == {"New"}


async def test_sync_directory_raises_ldap_connect_error_without_writing_anything(isolated_db):
    """`ad_groups`'un GERÇEKTEN boş başladığı VARSAYILAMAZ — kullanıcının
    kendi gerçek AD'sine karşı GERÇEK bir senkronizasyon zaten çalıştı bu
    oturumda (canlı `ad_groups`'ta gerçek gruplar var). Bunun yerine bu
    testin KENDİ transaction'ı içinde (rollback ile geri alınır, kalıcı
    veriye etkisi yok) önceden bir satır sayısı alıp senkronizasyon
    denemesinden SONRA hiç DEĞİŞMEDİĞİNİ doğruluyoruz."""
    before = await isolated_db.fetchval("SELECT count(*) FROM ad_groups")

    with patch("app.services.ldap._blocking_search", side_effect=LDAPBindError("invalid credentials")):
        with pytest.raises(LdapConnectError):
            await sync_directory(isolated_db, _params())

    after = await isolated_db.fetchval("SELECT count(*) FROM ad_groups")
    assert after == before
