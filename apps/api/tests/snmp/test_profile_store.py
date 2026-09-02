"""`app/snmp/profile_store.py` için testler — gerçek ağ/DB yok, yalnızca
`.env`-tabanlı tek-hedef çözümleme mantığı (Faz 22.2 v2c + Faz 22.4 v3)."""

from uuid import uuid4

from app.snmp.profile_store import get_profile_for_asset


def test_returns_none_when_no_target_configured():
    assert get_profile_for_asset(uuid4()) is None


def test_returns_none_when_asset_id_does_not_match(monkeypatch):
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(uuid4()))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")
    assert get_profile_for_asset(uuid4()) is None


def test_resolves_v2c_profile_when_asset_id_matches(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_VERSION", "v2c")
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")

    profile = get_profile_for_asset(asset_id)

    assert profile is not None
    assert profile.version == "v2c"
    assert profile.community_ref == "SNMP_V2C_COMMUNITY"
    assert profile.port == 161


def test_v2c_asset_id_match_is_case_insensitive(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id).upper())
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")

    assert get_profile_for_asset(asset_id) is not None


def test_returns_none_when_v2c_community_ref_missing(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_VERSION", "v2c")
    monkeypatch.delenv("SNMP_TARGET_COMMUNITY_REF", raising=False)

    assert get_profile_for_asset(asset_id) is None


def test_resolves_v3_noauthnopriv_profile(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_VERSION", "v3")
    monkeypatch.setenv("SNMP_TARGET_USERNAME", "readonly")

    profile = get_profile_for_asset(asset_id)

    assert profile is not None
    assert profile.version == "v3"
    assert profile.security_level == "noAuthNoPriv"


def test_resolves_v3_authpriv_profile(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_VERSION", "v3")
    monkeypatch.setenv("SNMP_TARGET_USERNAME", "monitoring")
    monkeypatch.setenv("SNMP_TARGET_AUTH_PROTOCOL", "SHA256")
    monkeypatch.setenv("SNMP_TARGET_AUTH_CREDENTIAL_REF", "SNMP_V3_AUTH")
    monkeypatch.setenv("SNMP_TARGET_PRIV_PROTOCOL", "AES256")
    monkeypatch.setenv("SNMP_TARGET_PRIV_CREDENTIAL_REF", "SNMP_V3_PRIV")

    profile = get_profile_for_asset(asset_id)

    assert profile is not None
    assert profile.security_level == "authPriv"
    assert profile.auth_credential_ref == "SNMP_V3_AUTH"
    assert profile.priv_credential_ref == "SNMP_V3_PRIV"


def test_returns_none_when_v3_username_missing(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_VERSION", "v3")
    monkeypatch.delenv("SNMP_TARGET_USERNAME", raising=False)

    assert get_profile_for_asset(asset_id) is None


def test_returns_none_when_v3_config_is_invalid_combination(monkeypatch):
    # priv verilmiş ama auth verilmemiş — SNMPProfile'ın kendi
    # validasyonu tarafından reddedilir, sessizce None döner.
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_VERSION", "v3")
    monkeypatch.setenv("SNMP_TARGET_USERNAME", "monitoring")
    monkeypatch.setenv("SNMP_TARGET_PRIV_PROTOCOL", "AES")
    monkeypatch.setenv("SNMP_TARGET_PRIV_CREDENTIAL_REF", "SNMP_V3_PRIV")
    monkeypatch.delenv("SNMP_TARGET_AUTH_PROTOCOL", raising=False)

    assert get_profile_for_asset(asset_id) is None


def test_returns_none_for_unsupported_version(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_VERSION", "v1")

    assert get_profile_for_asset(asset_id) is None


def test_returns_none_when_numeric_fields_are_malformed(monkeypatch):
    asset_id = uuid4()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset_id))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")
    monkeypatch.setenv("SNMP_TARGET_PORT", "not-a-port")

    assert get_profile_for_asset(asset_id) is None
