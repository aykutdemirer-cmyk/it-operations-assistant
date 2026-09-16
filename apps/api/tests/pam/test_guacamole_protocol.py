"""Faz 48 — `app/pam/guacamole_protocol.py` için saf birim testleri.
Gerçek `guacd`/ağ/DB kullanılmaz — yalnızca protokol kodlama/
ayrıştırma mantığı doğrulanır."""

import asyncio

import pytest

from app.pam.guacamole_protocol import (
    GuacamoleProtocolError,
    encode_instruction,
    read_instruction,
    split_complete_instructions,
)


def test_encode_instruction_uses_length_prefixed_elements():
    assert encode_instruction("select", "rdp") == b"6.select,3.rdp;"


def test_encode_instruction_handles_empty_elements():
    assert encode_instruction("audio") == b"5.audio;"


def test_encode_instruction_length_is_byte_length_not_char_length():
    # "ü"/"ç" ikisi de UTF-8'de 2 bayt (6 ASCII karakter + 2*2 = 8 bayt,
    # 6 KARAKTER değil) — uzunluk önekinin BAYT sayısı olduğunu doğrular
    # (guacd'nin kendisi de UTF-8 bayt sayısı bekler).
    encoded = encode_instruction("türkçe")
    assert len("türkçe") == 6
    assert encoded.startswith(b"8.")


@pytest.mark.anyio
async def test_read_instruction_parses_opcode_and_args():
    reader = asyncio.StreamReader()
    reader.feed_data(b"4.args,8.hostname,4.port;")
    reader.feed_eof()

    result = await read_instruction(reader)

    assert result == ["args", "hostname", "port"]


@pytest.mark.anyio
async def test_read_instruction_roundtrips_with_encode_instruction():
    reader = asyncio.StreamReader()
    reader.feed_data(encode_instruction("connect", "10.0.9.30", "3389", "Administrator"))
    reader.feed_eof()

    result = await read_instruction(reader)

    assert result == ["connect", "10.0.9.30", "3389", "Administrator"]


@pytest.mark.anyio
async def test_read_instruction_returns_empty_list_on_clean_eof():
    reader = asyncio.StreamReader()
    reader.feed_eof()

    result = await read_instruction(reader)

    assert result == []


@pytest.mark.anyio
async def test_read_instruction_rejects_bad_separator():
    reader = asyncio.StreamReader()
    reader.feed_data(b"4.args:bad;")
    reader.feed_eof()

    with pytest.raises(GuacamoleProtocolError):
        await read_instruction(reader)


@pytest.mark.anyio
async def test_read_instruction_raises_on_truncated_stream_mid_instruction():
    reader = asyncio.StreamReader()
    reader.feed_data(b"10.incomplete")
    reader.feed_eof()

    with pytest.raises(GuacamoleProtocolError):
        await read_instruction(reader)


# ---- split_complete_instructions ------------------------------------------
# Gerçek, canlı test sırasında bulunan bir üretim hatası için (bkz.
# `app/pam/guacd.py::_pump_guacd_to_websocket` docstring'i) — tarayıcı
# tarafındaki ayrıştırıcı her WS mesajının TAM instruction(lar) içerdiğini
# varsayıyor, bu fonksiyon bunu garanti eder.


def test_split_complete_instructions_returns_whole_buffer_when_all_complete():
    buf = encode_instruction("mouse", "0", "0") + encode_instruction("sync", "123")
    complete, remainder = split_complete_instructions(buf)
    assert complete == buf
    assert remainder == b""


def test_split_complete_instructions_holds_back_incomplete_trailing_instruction():
    complete_part = encode_instruction("mouse", "0", "0")
    incomplete_part = b"4.blob,3.abc"  # "abc" yalnızca 3 karakter ama daha fazlası bekleniyor
    complete, remainder = split_complete_instructions(complete_part + incomplete_part)
    assert complete == complete_part
    assert remainder == incomplete_part


def test_split_complete_instructions_holds_back_split_mid_element():
    # Bir elemanın DEĞER kısmı ortadan bölünmüş — ör. bir blob'un
    # base64 verisi iki ayrı TCP read()'e denk gelmiş.
    full = encode_instruction("blob", "3", "aGVsbG8=")
    split_point = len(full) - 5
    part_one, part_two = full[:split_point], full[split_point:]

    complete, remainder = split_complete_instructions(part_one)
    assert complete == b""
    assert remainder == part_one

    # Kalan veri bir SONRAKİ okumada tamamlanınca doğru şekilde bitiyor.
    complete, remainder = split_complete_instructions(remainder + part_two)
    assert complete == full
    assert remainder == b""


def test_split_complete_instructions_empty_buffer():
    assert split_complete_instructions(b"") == (b"", b"")


def test_split_complete_instructions_never_reassembles_a_broken_instruction_as_valid():
    """Regresyon testi: eski (hatalı) davranış rastgele bir bayt
    sınırında bölünmüş bir instruction'ı OLDUĞU GİBİ WebSocket'e
    gönderiyordu — bu da tarayıcıda "source image could not be
    decoded" hatasına yol açıyordu (bkz. docs/roadmap.md Faz 48 notu,
    gerçek kullanıcı testinde bulundu). Bu test, YARIM bir instruction'ın
    HİÇBİR ZAMAN `complete` kısmına sızmadığını doğrular."""
    full = encode_instruction("img", "3", "12", "-1", "9", "image/png", "0", "0")
    for cut in range(1, len(full)):
        complete, remainder = split_complete_instructions(full[:cut])
        # `complete` ya boş ya da `full`'un GERÇEK, TAM bir öneki olmalı
        # — asla `full`'un ortasında rastgele bir yerde KESİLMİŞ bir hal
        # DEĞİL (bu, tarayıcının ayrıştırıcısını bozan tam senaryo).
        assert full[:cut].startswith(complete)
        assert complete == b"" or complete.endswith(b";")
