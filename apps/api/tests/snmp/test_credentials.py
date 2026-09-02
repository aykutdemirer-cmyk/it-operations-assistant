from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.snmp.credentials import SNMPProfile


def test_v2c_profile_requires_community_ref():
    with pytest.raises(ValidationError):
        SNMPProfile(asset_id=uuid4(), version="v2c")


def test_v2c_profile_valid_with_community_ref():
    profile = SNMPProfile(
        asset_id=uuid4(), version="v2c", community_ref="SNMP_COMMUNITY_CORE_SW_01"
    )
    assert profile.community_ref == "SNMP_COMMUNITY_CORE_SW_01"
    assert profile.port == 161
    assert profile.timeout_seconds == 2.0
    assert profile.retries == 1


def test_v3_profile_requires_username_auth_protocol_and_auth_ref():
    with pytest.raises(ValidationError):
        SNMPProfile(asset_id=uuid4(), version="v3")


def test_v3_profile_valid_with_auth_no_priv():
    profile = SNMPProfile(
        asset_id=uuid4(),
        version="v3",
        username="monitoring",
        auth_protocol="SHA",
        auth_credential_ref="SNMP_V3_AUTH_CORE_SW_01",
    )
    assert profile.priv_protocol is None
    assert profile.priv_credential_ref is None


def test_v3_profile_priv_protocol_requires_priv_credential_ref():
    with pytest.raises(ValidationError):
        SNMPProfile(
            asset_id=uuid4(),
            version="v3",
            username="monitoring",
            auth_protocol="SHA",
            auth_credential_ref="SNMP_V3_AUTH_CORE_SW_01",
            priv_protocol="AES",
        )


def test_v3_profile_valid_with_auth_priv():
    profile = SNMPProfile(
        asset_id=uuid4(),
        version="v3",
        username="monitoring",
        auth_protocol="SHA",
        auth_credential_ref="SNMP_V3_AUTH_CORE_SW_01",
        priv_protocol="AES",
        priv_credential_ref="SNMP_V3_PRIV_CORE_SW_01",
    )
    assert profile.priv_protocol == "AES"


def test_v3_profile_valid_with_no_auth_no_priv():
    # Faz 22.4 — yalnızca username ile noAuthNoPriv geçerli bir SNMPv3
    # güvenlik seviyesidir (RFC 3414).
    profile = SNMPProfile(asset_id=uuid4(), version="v3", username="readonly")
    assert profile.auth_protocol is None
    assert profile.priv_protocol is None
    assert profile.security_level == "noAuthNoPriv"


def test_v3_profile_auth_protocol_requires_auth_credential_ref():
    with pytest.raises(ValidationError):
        SNMPProfile(asset_id=uuid4(), version="v3", username="monitoring", auth_protocol="SHA")


def test_v3_profile_priv_requires_auth_first():
    # authPriv, authNoPriv olmadan var olamaz.
    with pytest.raises(ValidationError):
        SNMPProfile(
            asset_id=uuid4(),
            version="v3",
            username="monitoring",
            priv_protocol="AES",
            priv_credential_ref="SNMP_V3_PRIV_CORE_SW_01",
        )


def test_security_level_reflects_configured_fields():
    v2c = SNMPProfile(asset_id=uuid4(), version="v2c", community_ref="SNMP_COMMUNITY_X")
    no_auth = SNMPProfile(asset_id=uuid4(), version="v3", username="readonly")
    auth_only = SNMPProfile(
        asset_id=uuid4(),
        version="v3",
        username="monitoring",
        auth_protocol="SHA256",
        auth_credential_ref="SNMP_V3_AUTH_X",
    )
    auth_priv = SNMPProfile(
        asset_id=uuid4(),
        version="v3",
        username="monitoring",
        auth_protocol="SHA256",
        auth_credential_ref="SNMP_V3_AUTH_X",
        priv_protocol="AES256",
        priv_credential_ref="SNMP_V3_PRIV_X",
    )

    assert v2c.security_level is None
    assert no_auth.security_level == "noAuthNoPriv"
    assert auth_only.security_level == "authNoPriv"
    assert auth_priv.security_level == "authPriv"


def test_profile_never_carries_a_plaintext_secret_field():
    # Model şemasında "password"/"secret"/"community" (referans değil,
    # ham değer) adında bir alan olmadığını doğrular — yalnızca *_ref
    # alanları var.
    field_names = set(SNMPProfile.model_fields.keys())
    for name in field_names:
        assert not name.endswith(("_password", "_secret"))
        if name in ("community_ref", "auth_credential_ref", "priv_credential_ref"):
            continue
        assert "community" not in name or name == "community_ref"
