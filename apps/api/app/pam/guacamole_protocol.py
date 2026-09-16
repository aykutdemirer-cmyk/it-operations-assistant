"""Faz 48 — Apache Guacamole metin protokolünün minimal bir
implementasyonu. `PyGuacamole`/`guacamole-lite` gibi üçüncü parti bir
kütüphane EKLENMEDİ (bakım durumu belirsiz, küçük ve tam olarak
belgelenmiş bir protokol için gereksiz bir bağımlılık) — protokol
kendisi çok basit: her "instruction" virgülle ayrılmış, uzunluk-
önekli (length-prefixed) elemanlardan oluşur ve `;` ile biter:

    <len>.<opcode>,<len>.<arg1>,<len>.<arg2>,...;

Uzunluk-öneki sayesinde elemanların İÇİNDE `,`/`;` geçmesi ayrıştırmayı
BOZMAZ — bu yüzden burada naif bir `split(",")` KULLANILMAZ, karakter
karakter okunur (bkz. `read_instruction`).

Referans: https://guacamole.apache.org/doc/gug/guacamole-protocol.html
(resmi belge — bu modül onun birebir, bağımsız bir uygulamasıdır)."""

from __future__ import annotations

import asyncio

_MAX_ELEMENT_LENGTH = 1_000_000  # aşırı büyük/bozuk bir uzunluk önekine karşı sağlamlık


class GuacamoleProtocolError(Exception):
    """guacd'den beklenmeyen/bozuk bir instruction geldiğinde."""


def encode_instruction(*elements: str) -> bytes:
    """`opcode, arg1, arg2, ...` → ham Guacamole instruction baytları."""
    parts = [f"{len(el.encode('utf-8'))}.{el}" for el in elements]
    return (",".join(parts) + ";").encode("utf-8")


async def read_instruction(reader: asyncio.StreamReader) -> list[str]:
    """Stream'den TEK bir instruction okur, `[opcode, arg1, ...]` döner.
    guacd bağlantısı kapanırsa (EOF) boş liste döner — çağıran taraf
    bunu bağlantının bittiği anlamına gelecek şekilde yorumlamalı."""
    elements: list[str] = []
    try:
        while True:
            length_digits = bytearray()
            while True:
                byte = await reader.readexactly(1)
                if byte == b".":
                    break
                if not byte.isdigit():
                    raise GuacamoleProtocolError(f"Beklenmeyen bayt (uzunluk öneki bekleniyordu): {byte!r}")
                length_digits += byte
                if len(length_digits) > 7:  # 9,999,999 karakterden uzun bir eleman gerçekçi değil
                    raise GuacamoleProtocolError("Uzunluk öneki aşırı büyük")
            length = int(length_digits)
            if length > _MAX_ELEMENT_LENGTH:
                raise GuacamoleProtocolError("Eleman uzunluğu izin verilen üst sınırı aşıyor")
            value = (await reader.readexactly(length)).decode("utf-8")
            elements.append(value)
            separator = await reader.readexactly(1)
            if separator == b";":
                return elements
            if separator != b",":
                raise GuacamoleProtocolError(f"Beklenmeyen ayraç: {separator!r}")
    except asyncio.IncompleteReadError:
        if elements:
            raise GuacamoleProtocolError("guacd bağlantısı bir instruction'ın ortasında kapandı")
        return []


def split_complete_instructions(buffer: bytes) -> tuple[bytes, bytes]:
    """`buffer`'ı `(tam_instruction'lar, kalan_yarım_veri)` olarak ikiye
    ayırır — **gerçek, canlı test sırasında bulunan bir üretim hatası**
    için var: `guacamole-common-js`'in tarayıcı tarafındaki `Guacamole.
    WebSocketTunnel` ayrıştırıcısı (kaynakta doğrulandı) HER WebSocket
    mesajının TAM instruction(lar) içerdiğini VARSAYAR — mesajlar arası
    bir tampon TUTMAZ. Bir instruction (ör. bir ekran görüntüsü
    `blob`'u) rastgele bir bayt sınırında İKİ ayrı WS mesajına bölünürse
    tarayıcı ya bağlantıyı KOPARIR ("Incomplete instruction.") ya da
    veriyi SESSİZCE BOZAR ("source image could not be decoded" —
    canlı ortamda GERÇEKTEN gözlemlendi). Bu fonksiyon guacd'den gelen
    ham bayt akışını TAMPONLAYIP yalnızca TAM biten instruction'ları
    döner; yarım kalan son instruction bir SONRAKİ okumada tamamlanmak
    üzere `kalan_yarım_veri` içinde saklanır (bkz. `_pump_guacd_to_
    websocket`'in kullanım şekli)."""
    complete_end = 0
    pos = 0
    n = len(buffer)
    while pos < n:
        dot = buffer.find(b".", pos)
        if dot == -1:
            break  # uzunluk öneki henüz tam gelmedi
        length_str = buffer[pos:dot]
        if not length_str.isdigit():
            break  # bozuk/beklenmedik veri — geri kalanı sonraki okumaya bırak
        length = int(length_str)
        elem_end = dot + 1 + length
        if elem_end >= n:
            break  # eleman (+ ayracı) için yeterli veri henüz yok
        separator = buffer[elem_end : elem_end + 1]
        pos = elem_end + 1
        if separator == b";":
            complete_end = pos  # instruction TAMAMLANDI
        elif separator != b",":
            break  # bozuk ayraç — geri kalanı sonraki okumaya bırak
    return buffer[:complete_end], buffer[complete_end:]
