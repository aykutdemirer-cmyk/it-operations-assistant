"""`app/snmp/secrets.py::resolve_secret` için birim testleri.

Gerçek bir ortam değişkeni okunur/okunmaz — `monkeypatch.setenv`/
`delenv` ile izole edilir, hiçbir gerçek `.env` dosyasına dokunulmaz."""

from app.snmp.secrets import resolve_secret

_ENV_VAR = "TEST_ITOPS_SNMP_SECRET_REF"
_ENV_VALUE = "gizli-deger-asla-loglanmamali"


def test_none_ref_returns_none():
    assert resolve_secret(None) is None


def test_blank_ref_returns_none():
    assert resolve_secret("") is None


def test_resolves_env_var_when_defined(monkeypatch):
    monkeypatch.setenv(_ENV_VAR, _ENV_VALUE)
    assert resolve_secret(_ENV_VAR) == _ENV_VALUE


def test_undefined_env_var_returns_none_without_fallback(monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    assert resolve_secret(_ENV_VAR) is None


def test_undefined_env_var_falls_back_to_literal_when_allowed(monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    literal = "public"
    assert resolve_secret(literal, allow_literal_fallback=True) == literal


def test_defined_env_var_still_wins_over_literal_fallback(monkeypatch):
    # `ref` HEM geçerli bir env değişken adı HEM de (teorik olarak) bir
    # düz metin community string gibi görünebilir — env'de gerçekten
    # tanımlıysa her zaman ONUN değeri kullanılır, literal fallback
    # yalnızca env'de HİÇ bulunamadığında devreye girer.
    monkeypatch.setenv(_ENV_VAR, _ENV_VALUE)
    assert resolve_secret(_ENV_VAR, allow_literal_fallback=True) == _ENV_VALUE


def test_blank_ref_returns_none_even_with_fallback():
    assert resolve_secret("", allow_literal_fallback=True) is None
