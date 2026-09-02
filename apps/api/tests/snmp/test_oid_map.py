from app.snmp.oid_map import INTERFACE_OIDS, SYSTEM_OIDS


def test_system_oids_cover_required_names():
    assert set(SYSTEM_OIDS) == {"sysDescr", "sysObjectID", "sysUpTime", "sysName"}


def test_interface_oids_cover_required_names():
    # ifHCInOctets/ifHCOutOctets (64-bit, ifXTable) Faz 22.2'de, ifInErrors/
    # ifOutErrors Faz 26'da (interface_error alert kuralı için) eklendi.
    assert set(INTERFACE_OIDS) == {
        "ifDescr",
        "ifAdminStatus",
        "ifOperStatus",
        "ifSpeed",
        "ifInOctets",
        "ifOutOctets",
        "ifName",
        "ifHCInOctets",
        "ifHCOutOctets",
        "ifInErrors",
        "ifOutErrors",
    }


def test_all_oids_are_well_formed_dotted_strings():
    for oid in {**SYSTEM_OIDS, **INTERFACE_OIDS}.values():
        parts = oid.split(".")
        assert len(parts) >= 6
        assert all(part.isdigit() for part in parts)


def test_sys_name_oid_matches_known_mib2_value():
    # RFC 1213 system grubu sabit değerdir — regresyonu yakalamak için.
    assert SYSTEM_OIDS["sysName"] == "1.3.6.1.2.1.1.5.0"
