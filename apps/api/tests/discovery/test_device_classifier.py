from app.discovery.device_classifier import classify_device


def test_fortinet_vendor_classified_as_firewall_high():
    result = classify_device(vendor="Fortinet, Inc.", open_ports=[])

    assert result.device_type == "firewall"
    assert result.confidence == "high"
    assert result.evidence == ["vendor: Fortinet"]


def test_palo_alto_vendor_classified_as_firewall_high():
    result = classify_device(vendor="Palo Alto Networks, Inc.", open_ports=[])

    assert result.device_type == "firewall"
    assert result.confidence == "high"
    assert result.evidence == ["vendor: Palo Alto"]


def test_vendor_match_is_case_insensitive():
    result = classify_device(vendor="FORTINET, INC.", open_ports=[])

    assert result.device_type == "firewall"
    assert result.confidence == "high"


def test_cisco_with_ssh_and_https_classified_as_network_device_medium():
    result = classify_device(vendor="Cisco Systems, Inc", open_ports=[22, 443])

    assert result.device_type == "network_device"
    assert result.confidence == "medium"
    assert result.evidence == ["vendor: Cisco", "port: 22", "port: 443"]


def test_cisco_vendor_alone_without_both_ports_does_not_match_network_device_rule():
    # Yalnızca 22 açık, 443 kapalı -> AND koşulu sağlanmıyor, eşleşme yok.
    result = classify_device(vendor="Cisco Systems, Inc", open_ports=[22])

    assert result.device_type != "network_device"


def test_rdp_and_smb_together_is_ambiguous_returns_unknown_low_not_windows():
    result = classify_device(vendor=None, open_ports=[3389, 445])

    assert result.device_type == "unknown"
    assert result.confidence == "low"
    assert result.evidence == ["port: 3389", "port: 445"]


def test_only_rdp_without_smb_does_not_trigger_ambiguous_rule():
    result = classify_device(vendor=None, open_ports=[3389])

    assert result.evidence == []


def test_insufficient_evidence_returns_unknown_low_empty_evidence():
    result = classify_device(vendor=None, hostname=None, open_ports=[])

    assert result.device_type == "unknown"
    assert result.confidence == "low"
    assert result.evidence == []


def test_unrelated_vendor_and_ports_returns_unknown():
    result = classify_device(vendor="Dell Inc.", open_ports=[80])

    assert result.device_type == "unknown"
    assert result.confidence == "low"


def test_higher_priority_vendor_rule_wins_over_lower_priority_port_rule():
    # Fortinet (tier 1) hem de 3389+445 (tier 2, ambiguous) aynı anda
    # doğru olsa bile en yüksek öncelikli kural (Fortinet) kazanmalı ve
    # onun evidence'ı korunmalı; diğer kuralın evidence'ı karışmamalı.
    result = classify_device(vendor="Fortinet, Inc.", open_ports=[3389, 445])

    assert result.device_type == "firewall"
    assert result.confidence == "high"
    assert result.evidence == ["vendor: Fortinet"]


def test_higher_priority_wins_between_two_tier_two_rules():
    # Cisco+22+443 (tier 2) mevcutken 3389+445 (tier 2, ama Cisco kuralı
    # listede önce tanımlı) de doğruysa Cisco kuralı kazanmalı.
    result = classify_device(
        vendor="Cisco Systems, Inc", open_ports=[22, 443, 3389, 445]
    )

    assert result.device_type == "network_device"
    assert result.evidence == ["vendor: Cisco", "port: 22", "port: 443"]
