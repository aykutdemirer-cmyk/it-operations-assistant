from app.discovery.arp import normalize_mac, parse_arp_output

ENGLISH_ARP_OUTPUT = """
Interface: 10.0.199.13 --- 0xe
  Internet Address      Physical Address      Type
  10.0.199.1             aa-bb-cc-dd-ee-ff     dynamic
  10.0.199.14            11-22-33-44-55-66     dynamic
  10.0.199.255           ff-ff-ff-ff-ff-ff     static
  224.0.0.22             01-00-5e-00-00-16     static
"""

TURKISH_ARP_OUTPUT = """
Arabirim: 10.0.199.13 --- 0xe
  İnternet Adresi        Fiziksel Adres        Tür
  10.0.199.1             aa-bb-cc-dd-ee-ff     dynamic
  10.0.199.14            11-22-33-44-55-66     dynamic
"""


def test_parse_arp_output_extracts_multiple_entries():
    entries = parse_arp_output(ENGLISH_ARP_OUTPUT)

    assert entries["10.0.199.1"] == "AA-BB-CC-DD-EE-FF"
    assert entries["10.0.199.14"] == "11-22-33-44-55-66"
    assert len(entries) == 4


def test_parse_arp_output_matches_correct_ip_to_mac():
    entries = parse_arp_output(ENGLISH_ARP_OUTPUT)

    assert entries["10.0.199.1"] != entries["10.0.199.14"]


def test_parse_arp_output_is_locale_independent():
    entries = parse_arp_output(TURKISH_ARP_OUTPUT)

    assert entries["10.0.199.1"] == "AA-BB-CC-DD-EE-FF"
    assert entries["10.0.199.14"] == "11-22-33-44-55-66"


def test_parse_arp_output_returns_empty_dict_for_garbage_input():
    entries = parse_arp_output("bu bir arp çıktısı değil\n???\n")

    assert entries == {}


def test_parse_arp_output_handles_empty_string():
    assert parse_arp_output("") == {}


def test_normalize_mac_uppercases_and_uses_hyphens():
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA-BB-CC-DD-EE-FF"


def test_normalize_mac_converts_colon_separated_input():
    assert normalize_mac("aa:bb:cc:dd:ee:ff") == "AA-BB-CC-DD-EE-FF"
