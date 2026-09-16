"""Faz 52 — `app/services/ldap_auth.py` için gerçek bir AD sunucusu
GEREKMEYEN testler. Gerçek bind çağrısı (`_blocking_bind`) mock'lanır —
protokol katmanı zaten `tests/services/test_ldap_service.py`'de test
edildi, burada yalnızca provizyon/güvenlik mantığı doğrulanıyor."""

from unittest.mock import patch

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.ldap import upsert_config
from app.db.users import insert_user
from app.services.ldap_auth import (
    AdUserAlreadyLinkedError,
    AdUserNotFoundError,
    authenticate_and_provision,
    create_user_from_ad,
    default_ldap_role,
    is_ldap_auth_enabled,
)

pytestmark = pytest.mark.anyio


def test_is_ldap_auth_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("LDAP_AUTH_ENABLED", raising=False)
    assert is_ldap_auth_enabled() is False


def test_is_ldap_auth_enabled_true_values(monkeypatch):
    for value in ("true", "1", "yes", "TRUE"):
        monkeypatch.setenv("LDAP_AUTH_ENABLED", value)
        assert is_ldap_auth_enabled() is True


def test_default_ldap_role_defaults_to_viewer_not_operator(monkeypatch):
    """Kullanıcının önerdiği `OPERATOR` YERİNE bilinçli olarak `VIEWER`
    varsayılanı — bkz. modül docstring'i."""
    monkeypatch.delenv("LDAP_AUTH_DEFAULT_ROLE", raising=False)
    assert default_ldap_role() == "VIEWER"


def test_default_ldap_role_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("LDAP_AUTH_DEFAULT_ROLE", "SUPERADMIN")
    assert default_ldap_role() == "VIEWER"


def test_default_ldap_role_accepts_admin(monkeypatch):
    monkeypatch.setenv("LDAP_AUTH_DEFAULT_ROLE", "ADMIN")
    assert default_ldap_role() == "ADMIN"


async def _seed_ldap_config(isolated_db):
    await upsert_config(
        isolated_db,
        host="dc01.lab.local",
        port=636,
        use_ssl=True,
        domain_fqdn="lab.local",
        base_dn="DC=lab,DC=local",
        bind_dn="svc_ldap@lab.local",
        encrypted_bind_password="unused-in-these-tests",
    )


async def _seed_ad_user(isolated_db, *, username, display_name="Test User", email="test@lab.local"):
    await isolated_db.execute(
        "INSERT INTO ad_users (distinguished_name, username, display_name, email) VALUES ($1, $2, $3, $4)",
        f"CN={display_name},DC=lab,DC=local",
        username,
        display_name,
        email,
    )


async def test_authenticate_and_provision_returns_none_when_disabled(isolated_db, monkeypatch):
    monkeypatch.delenv("LDAP_AUTH_ENABLED", raising=False)
    await _seed_ldap_config(isolated_db)

    result = await authenticate_and_provision(isolated_db, username="jdoe", password="x")

    assert result is None


async def test_authenticate_and_provision_returns_none_when_no_ldap_config(isolated_db, monkeypatch):
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")

    result = await authenticate_and_provision(isolated_db, username="jdoe", password="x")

    assert result is None


async def test_authenticate_and_provision_returns_none_when_bind_fails(isolated_db, monkeypatch):
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")
    await _seed_ldap_config(isolated_db)

    with patch("app.services.ldap_auth._run_bind", return_value=False):
        result = await authenticate_and_provision(isolated_db, username="jdoe", password="wrong")

    assert result is None


async def test_authenticate_and_provision_returns_none_when_user_not_synced(isolated_db, monkeypatch):
    """Bind BAŞARILI olsa bile `ad_users`'ta yoksa (hiç senkronize
    edilmemiş) provizyon REDDEDİLİR — bkz. fonksiyonun docstring'i."""
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")
    await _seed_ldap_config(isolated_db)

    with patch("app.services.ldap_auth._run_bind", return_value=True):
        result = await authenticate_and_provision(isolated_db, username="not-synced-user", password="x")

    assert result is None


async def test_authenticate_and_provision_creates_new_user_with_default_role(isolated_db, monkeypatch):
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")
    monkeypatch.setenv("LDAP_AUTH_DEFAULT_ROLE", "VIEWER")
    await _seed_ldap_config(isolated_db)
    await _seed_ad_user(isolated_db, username="jdoe", display_name="John Doe", email="jdoe@lab.local")

    with patch("app.services.ldap_auth._run_bind", return_value=True):
        result = await authenticate_and_provision(isolated_db, username="jdoe", password="correct-password")

    assert result is not None
    assert result["ad_username"] == "jdoe"
    assert result["role"] == "VIEWER"
    assert result["full_name"] == "John Doe"
    assert result["email"] == "jdoe@lab.local"
    assert result["password_hash"] is None
    assert result["is_ad_user"] is True


async def test_authenticate_and_provision_reuses_existing_linked_account(isolated_db, monkeypatch):
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")
    await _seed_ldap_config(isolated_db)
    await _seed_ad_user(isolated_db, username="jdoe", display_name="John Doe Updated")

    with patch("app.services.ldap_auth._run_bind", return_value=True):
        first = await authenticate_and_provision(isolated_db, username="jdoe", password="x")
        second = await authenticate_and_provision(isolated_db, username="jdoe", password="x")

    assert first is not None and second is not None
    assert first["id"] == second["id"]
    # İkinci girişte profil TAZELENİR (displayName değişmiş olsa bile).
    assert second["full_name"] == "John Doe Updated"


async def test_authenticate_and_provision_rejects_unrelated_local_username_collision(isolated_db, monkeypatch):
    """Aynı kullanıcı adında, `ad_username` BAĞLANTISIZ bir yerel hesap
    zaten varsa — otomatik provizyon o hesabı SESSİZCE ele geçirmez,
    reddeder (gerçek bir güvenlik/veri bütünlüğü koruması)."""
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")
    await _seed_ldap_config(isolated_db)
    await _seed_ad_user(isolated_db, username="jdoe")
    await insert_user(isolated_db, username="jdoe", password_hash=hash_password("localpass123"), role="ADMIN", full_name=None)

    with patch("app.services.ldap_auth._run_bind", return_value=True):
        result = await authenticate_and_provision(isolated_db, username="jdoe", password="x")

    assert result is None


async def test_create_user_from_ad_raises_when_not_synced(isolated_db):
    with pytest.raises(AdUserNotFoundError):
        await create_user_from_ad(isolated_db, ad_username="ghost", role="VIEWER")


async def test_create_user_from_ad_creates_user_without_live_bind(isolated_db):
    await _seed_ad_user(isolated_db, username="asmith", display_name="Alice Smith")

    row = await create_user_from_ad(isolated_db, ad_username="asmith", role="OPERATOR")

    assert row["ad_username"] == "asmith"
    assert row["role"] == "OPERATOR"
    assert row["full_name"] == "Alice Smith"
    assert row["password_hash"] is None


async def test_create_user_from_ad_rejects_double_import(isolated_db):
    await _seed_ad_user(isolated_db, username="asmith")
    await create_user_from_ad(isolated_db, ad_username="asmith", role="VIEWER")

    with pytest.raises(AdUserAlreadyLinkedError):
        await create_user_from_ad(isolated_db, ad_username="asmith", role="VIEWER")
