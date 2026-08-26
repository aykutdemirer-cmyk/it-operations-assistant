import time

from app.discovery.vendor import extract_oui, lookup_vendor


def test_extract_oui_from_hyphenated_mac():
    assert extract_oui("00-09-0F-09-00-08") == "00-09-0F"


def test_extract_oui_from_colon_separated_mac():
    assert extract_oui("00:09:0F:09:00:08") == "00-09-0F"


def test_extract_oui_from_space_separated_mac():
    assert extract_oui("00 09 0F 09 00 08") == "00-09-0F"


def test_extract_oui_is_case_insensitive_and_uppercases_result():
    assert extract_oui("aa-bb-cc-dd-ee-ff") == "AA-BB-CC"


def test_extract_oui_returns_none_for_invalid_mac():
    assert extract_oui("not-a-mac") is None
    assert extract_oui("12-34") is None
    assert extract_oui("") is None


def test_lookup_vendor_returns_known_vendor_for_known_oui():
    # 00-09-0F IEEE OUI kaydında gerçekten "Fortinet, Inc." olarak
    # tahsislidir (bkz. app/discovery/data/oui.json).
    vendor = lookup_vendor("00-09-0F-09-00-08")

    assert vendor == "Fortinet, Inc."


def test_lookup_vendor_is_case_insensitive():
    assert lookup_vendor("00-09-0f-09-00-08") == "Fortinet, Inc."
    assert lookup_vendor("00:09:0f:09:00:08") == "Fortinet, Inc."


def test_lookup_vendor_returns_none_for_unknown_oui():
    # FF-FF-FF IEEE registry'de tahsisli değildir.
    assert lookup_vendor("FF-FF-FF-00-00-00") is None


def test_lookup_vendor_returns_none_for_invalid_mac():
    assert lookup_vendor("garbage") is None
    assert lookup_vendor("") is None


def test_lookup_vendor_is_fast_for_repeated_calls():
    # İlk çağrı dataset'i diskten yükler (lru_cache); sonraki 10.000
    # çağrı yalnızca bellek içi dict lookup olmalı — dış servise veya
    # tekrar tekrar disk okumaya gitmemeli.
    lookup_vendor("00-09-0F-09-00-08")

    start = time.perf_counter()
    for _ in range(10_000):
        lookup_vendor("00-09-0F-09-00-08")
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0
