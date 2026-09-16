"""Faz 53 — Oturum Kaydı Zaman Çubuğu İşaretleri (Timeline Activity
Markers). `.guac` kayıt dosyası ZATEN oturumun kendi ham Guacamole
protokol akışı (bkz. Faz 50 — `app/pam/guacd.py::recording_config`) —
bu, gerçek tuş basma/bırakma olaylarını taşıyan `key` instruction'ının
VE periyodik `sync` instruction'larının (o ana kadar geçen GERÇEK
zamanı taşıyan) dosyada ZATEN bulunduğu anlamına gelir. Bu modül YENİ
bir veri UYDURMAZ — yalnızca zaten kaydedilmiş GERÇEK tuş basma
olaylarının zaman damgalarını ayrıştırıp `SessionReplayModal`'ın zaman
çubuğunda işaretleyebileceği bir listeye çevirir.

Yalnızca RDP oturumları için anlamlıdır — SSH tuş loglaması (Faz 50
`pam_keystrokes`) ayrı, video kaydı OLMAYAN bir mekanizma; bu ikisi
aynı oturumda hiç bir arada bulunmaz (bkz. `pam_audit.py` modül
docstring'i)."""

from __future__ import annotations

import asyncio

from app.pam.guacamole_protocol import read_instruction

# Art arda gelen tuş vuruşlarını (ör. bir kelime yazarken) TEK bir
# işarete indirger — UI netliği için, veri kaybı DEĞİL: her işaret
# civarındaki GERÇEK bir aktivite patlamasını temsil eder.
MARKER_MIN_GAP_MS = 2000

# Faz 75 — İnaktif Süre Atlama. Bu eşikten KISA boşluklar (ör. iki tuş
# vuruşu arası doğal bir duraklama) "inaktif" sayılmaz — yalnızca
# GERÇEKTEN uzun, hareketsiz aralıklar atlanabilir olarak işaretlenir.
IDLE_GAP_MIN_MS = 3000

# `.guac` kaydında GERÇEK kullanıcı/ekran aktivitesini taşıyan
# instruction'lar — `sync` (periyodik saat sinyali, aktivite DEĞİL)
# bunun DIŞINDA tutulur. `key`/`mouse` GİRDİ, geri kalanı guacd'nin
# ekranda GERÇEKTEN bir şey değiştiğinde gönderdiği ÇIKTI
# instruction'ları (bkz. Guacamole protokol referansı).
_ACTIVITY_OPCODES = {"key", "mouse", "img", "png", "jpeg", "webp", "blob", "copy", "rect", "cursor", "clipboard"}


async def extract_activity_markers(file_path: str) -> list[int]:
    """`.guac` kayıt dosyasındaki gerçek tuş-basma (`key`, pressed=1)
    olaylarının, kaydın başlangıcına (ilk `sync` instruction'ına) göre
    milisaniye ofsetlerini artan sırada döner."""
    with open(file_path, "rb") as f:
        data = f.read()

    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    markers: list[int] = []
    origin: int | None = None
    current_sync: int | None = None
    last_marker: int | None = None

    while True:
        instruction = await read_instruction(reader)
        if not instruction:
            break
        opcode = instruction[0]
        if opcode == "sync" and len(instruction) >= 2:
            try:
                current_sync = int(instruction[1])
            except ValueError:
                continue
            if origin is None:
                origin = current_sync
        elif opcode == "key" and len(instruction) >= 3 and instruction[2] == "1":
            if current_sync is None or origin is None:
                continue
            offset = current_sync - origin
            if last_marker is None or offset - last_marker >= MARKER_MIN_GAP_MS:
                markers.append(offset)
                last_marker = offset

    return markers


async def extract_idle_gaps(file_path: str, min_gap_ms: int = IDLE_GAP_MIN_MS) -> list[dict]:
    """Faz 75 — kayıttaki GERÇEK `sync` zaman damgalarından, aralarında
    hiçbir kullanıcı/ekran aktivitesi (`_ACTIVITY_OPCODES`) OLMAYAN
    uzun boşlukları çıkarır. **Uydurulmuş bir veri DEĞİL** — Guacamole
    protokolü zaten olay-güdümlü olduğu için (ekranda gerçek bir
    değişiklik yoksa guacd hiçbir şey göndermez/kaydetmez), bu
    fonksiyon yalnızca kayıtta ZATEN var olan boşlukları ölçüp bir
    liste haline getiriyor — guacd'de bunun için bir config anahtarı
    YOK (bkz. docs/roadmap.md Faz 75 — kullanıcının varsaydığı
    "inaktivite suppression parametresi" gerçekte mevcut değil).

    Dönüş: `[{"start_ms": int, "end_ms": int}, ...]` — kaydın
    başlangıcına göre, artan sırada, örtüşmeyen aralıklar."""
    with open(file_path, "rb") as f:
        data = f.read()

    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()

    gaps: list[dict] = []
    origin: int | None = None
    current_offset = 0
    last_activity_offset = 0

    while True:
        instruction = await read_instruction(reader)
        if not instruction:
            break
        opcode = instruction[0]
        if opcode == "sync" and len(instruction) >= 2:
            try:
                sync_time = int(instruction[1])
            except ValueError:
                continue
            if origin is None:
                origin = sync_time
            current_offset = sync_time - origin
        elif opcode in _ACTIVITY_OPCODES:
            if current_offset - last_activity_offset >= min_gap_ms:
                gaps.append({"start_ms": last_activity_offset, "end_ms": current_offset})
            last_activity_offset = current_offset

    # Kaydın sonuna kadar süren, son bir aktiviteden sonraki boşluk da
    # (ör. kullanıcı klavye/fareyi bırakıp oturumu kapatmadan ayrıldı).
    if current_offset - last_activity_offset >= min_gap_ms:
        gaps.append({"start_ms": last_activity_offset, "end_ms": current_offset})

    return gaps
