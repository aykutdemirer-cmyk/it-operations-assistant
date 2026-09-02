"""`app/agents/matching.py` için saf mantık testleri — DB/ağ yok. Hiçbir
zaman `agents.asset_id`'yi YAZMAZ; yalnızca değerlendirme döner."""

from uuid import uuid4

from app.agents.matching import evaluate_asset_match


def _agent(**overrides) -> dict:
    defaults = dict(hostname="win-host-01", local_ip="10.0.5.10", mac_address="AA-BB-CC-DD-EE-10")
    defaults.update(overrides)
    return defaults


def _asset(**overrides) -> dict:
    defaults = dict(
        id=uuid4(), hostname="win-host-01", ip_address="10.0.5.10", mac_address="AA-BB-CC-DD-EE-10"
    )
    defaults.update(overrides)
    return defaults


def test_two_matching_signals_yield_confirmed():
    asset = _asset(mac_address="00-00-00-00-00-00")  # yalnızca hostname+ip eşleşir
    result = evaluate_asset_match(_agent(), [asset])

    assert result.confidence == "confirmed"
    assert result.asset_id == str(asset["id"])
    assert set(result.matched_signals) == {"hostname", "ip"}


def test_all_three_signals_matching_is_still_confirmed():
    asset = _asset()
    result = evaluate_asset_match(_agent(), [asset])

    assert result.confidence == "confirmed"
    assert len(result.matched_signals) == 3


def test_single_signal_yields_candidate_not_confirmed():
    asset = _asset(hostname="different-hostname", mac_address="00-00-00-00-00-00")
    result = evaluate_asset_match(_agent(), [asset])

    assert result.confidence == "candidate"
    assert result.matched_signals == ["ip"]
    assert result.asset_id == str(asset["id"])


def test_no_signals_yields_unmatched():
    asset = _asset(hostname="other", ip_address="10.0.5.99", mac_address="11-11-11-11-11-11")
    result = evaluate_asset_match(_agent(), [asset])

    assert result.confidence == "unmatched"
    assert result.asset_id is None
    assert result.matched_signals == []


def test_empty_asset_list_yields_unmatched():
    result = evaluate_asset_match(_agent(), [])

    assert result.confidence == "unmatched"
    assert result.asset_id is None


def test_prefers_confirmed_over_earlier_candidate():
    candidate_only = _asset(hostname="other", mac_address="00-00-00-00-00-00")  # yalnızca ip eşleşir
    confirmed = _asset(hostname="win-host-01")  # hostname + ip eşleşir

    result = evaluate_asset_match(_agent(), [candidate_only, confirmed])

    assert result.confidence == "confirmed"
    assert result.asset_id == str(confirmed["id"])


def test_hostname_and_ip_matching_different_assets_does_not_falsely_confirm():
    """Hostname bir asset'te, IP BAŞKA bir asset'te eşleşiyorsa — bu iki
    AYRI tek-sinyal eşleşmedir, birleştirilip 'confirmed' sayılmamalı."""
    asset_hostname_match = _asset(hostname="win-host-01", ip_address="10.0.5.200", mac_address="ff")
    asset_ip_match = _asset(hostname="unrelated", ip_address="10.0.5.10", mac_address="ff")

    result = evaluate_asset_match(_agent(), [asset_hostname_match, asset_ip_match])

    assert result.confidence == "candidate"


def test_case_insensitive_hostname_and_mac_matching():
    asset = _asset(hostname="WIN-HOST-01", mac_address="aa-bb-cc-dd-ee-10")
    result = evaluate_asset_match(_agent(), [asset])

    assert result.confidence == "confirmed"


def test_missing_agent_fields_never_crash_and_never_false_match():
    agent = _agent(hostname=None, local_ip=None, mac_address=None)
    asset = _asset(hostname=None, ip_address=None, mac_address=None)

    result = evaluate_asset_match(agent, [asset])

    assert result.confidence == "unmatched"
