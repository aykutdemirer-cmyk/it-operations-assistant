"""`app/snmp/profile_service.py::_guess_device_type_from_sys_descr` için
birim testleri — gerçek bir DB/SNMP bağlantısı gerektirmeyen saf mantık
(bkz. `tests/test_snmp_profiles_api.py` — asset otomatik oluşturma
akışının uçtan uca testleri orada, gerçek `isolated_db`'ye bağlı)."""

from app.snmp.profile_service import _guess_device_type_from_sys_descr


def test_returns_network_device_when_sys_descr_is_none():
    assert _guess_device_type_from_sys_descr(None) == "network_device"


def test_returns_network_device_when_sys_descr_is_empty():
    assert _guess_device_type_from_sys_descr("") == "network_device"


def test_returns_network_device_when_no_keyword_matches():
    assert _guess_device_type_from_sys_descr("Some Custom Firmware 1.0") == "network_device"


def test_detects_fortigate_as_firewall():
    assert _guess_device_type_from_sys_descr("FortiGate-70G v7.0.5,build0304") == "firewall"


def test_detects_pfsense_as_firewall():
    assert _guess_device_type_from_sys_descr("pfSense 2.7.0-RELEASE") == "firewall"


def test_detects_cisco_asa_as_firewall():
    assert _guess_device_type_from_sys_descr("Cisco Adaptive Security Appliance Software (ASA)") == "firewall"


def test_detects_cisco_catalyst_as_switch():
    assert _guess_device_type_from_sys_descr("Cisco IOS Software, Catalyst 9300") == "switch"


def test_detects_cisco_ios_xe_as_router():
    assert _guess_device_type_from_sys_descr("Cisco IOS-XE Software, ISR4331") == "router"


def test_detects_junos_as_router():
    assert _guess_device_type_from_sys_descr("Juniper Networks, Inc. junos 21.4R1") == "router"


def test_is_case_insensitive():
    assert _guess_device_type_from_sys_descr("FORTIGATE-100F") == "firewall"


def test_prefers_more_specific_firewall_hint_over_generic_router_text():
    # Bazı firewall sysDescr'leri "router" kelimesini de içerebilir —
    # daha spesifik "firewall" ipucu listede ÖNCE kontrol edilir.
    assert _guess_device_type_from_sys_descr("pfSense router/firewall appliance") == "firewall"


# --- profil adı yedek sinyal (sysDescr hiçbir ipucu vermediğinde) ---


def test_falls_back_to_profile_name_when_sys_descr_gives_no_hint():
    """Gerçek bir örnek: bir FortiGate'in sysDescr'i yalnızca kurum-içi
    bir adlandırma ("PSL_HQ_FGT") döndürebilir — hiçbir üretici/cihaz
    anahtar kelimesi içermez. Kullanıcının profile verdiği GERÇEK ad
    ("FW") ikinci, dürüst bir sinyal olarak kullanılır."""
    assert _guess_device_type_from_sys_descr("PSL_HQ_FGT", profile_name="FW") == "firewall"


def test_sys_descr_hint_takes_priority_over_profile_name():
    assert _guess_device_type_from_sys_descr("Cisco IOS Software, Catalyst", profile_name="FW") == "switch"


def test_profile_name_word_boundary_does_not_match_substring():
    # "Software" içinde "fw" alt dizesi YOK ama "Firmware" gibi bir
    # kelime de yanlışlıkla eşleşmemeli — yalnızca TAM kelime "fw".
    assert _guess_device_type_from_sys_descr(None, profile_name="Firmware Update Profile") == "network_device"


def test_profile_name_plural_does_not_false_positive_on_switch():
    # "Switches" (çoğul), tam kelime "switch" İLE eşleşmemeli.
    assert _guess_device_type_from_sys_descr(None, profile_name="Core Switches") == "network_device"


def test_profile_name_none_and_no_sys_descr_defaults_to_network_device():
    assert _guess_device_type_from_sys_descr(None, profile_name=None) == "network_device"
