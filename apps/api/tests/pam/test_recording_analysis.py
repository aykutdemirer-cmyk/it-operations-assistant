"""Faz 53 — `app/pam/recording_analysis.py::extract_activity_markers`
için gerçek `.guac` protokol formatında SENTETİK (ama protokol olarak
geçerli) kayıt dosyalarıyla testler. Gerçek bir guacd/RDP bağlantısı
kullanılmaz — bkz. `encode_instruction` (aynı modül Faz 48'in guacd
el sıkışma testlerinde de kullanılıyor)."""

import pytest

from app.pam.guacamole_protocol import encode_instruction
from app.pam.recording_analysis import extract_activity_markers, extract_idle_gaps

pytestmark = pytest.mark.anyio


def _recording(*instructions: bytes) -> bytes:
    return b"".join(instructions)


async def test_returns_empty_list_for_empty_file(tmp_path):
    path = tmp_path / "empty.guac"
    path.write_bytes(b"")

    assert await extract_activity_markers(str(path)) == []


async def test_ignores_key_release_events(tmp_path):
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("sync", "1000"),
        encode_instruction("key", "97", "0"),  # bırakma (pressed=0) — yok sayılır
    )
    path.write_bytes(data)

    assert await extract_activity_markers(str(path)) == []


async def test_extracts_key_press_offsets_relative_to_first_sync(tmp_path):
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("sync", "1000"),
        encode_instruction("key", "97", "1"),  # offset 0
        encode_instruction("sync", "6000"),
        encode_instruction("key", "98", "1"),  # offset 5000
    )
    path.write_bytes(data)

    assert await extract_activity_markers(str(path)) == [0, 5000]


async def test_collapses_bursts_within_min_gap_into_one_marker(tmp_path):
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("sync", "1000"),
        encode_instruction("key", "97", "1"),  # offset 0 — tutulur
        encode_instruction("sync", "1500"),
        encode_instruction("key", "98", "1"),  # offset 500 — 2000ms'den YAKIN, atlanır
        encode_instruction("sync", "4000"),
        encode_instruction("key", "99", "1"),  # offset 3000 — YETERİNCE uzak, tutulur
    )
    path.write_bytes(data)

    assert await extract_activity_markers(str(path)) == [0, 3000]


async def test_ignores_key_events_before_any_sync(tmp_path):
    """Gerçek bir `.guac` dosyası her zaman erken bir `sync` ile başlar
    (bkz. Faz 50 guacd handshake) ama bu fonksiyon bunu VARSAYMAZ —
    bir `sync` görülmeden gelen `key` olayları için henüz bir zaman
    referansı yoktur, sessizce atlanır."""
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("key", "97", "1"),
        encode_instruction("sync", "2000"),
        encode_instruction("key", "98", "1"),  # offset 0
    )
    path.write_bytes(data)

    assert await extract_activity_markers(str(path)) == [0]


# ---- Faz 75 — extract_idle_gaps -------------------------------------------


async def test_idle_gaps_returns_empty_for_empty_file(tmp_path):
    path = tmp_path / "empty.guac"
    path.write_bytes(b"")

    assert await extract_idle_gaps(str(path)) == []


async def test_idle_gaps_ignores_short_pauses_below_threshold(tmp_path):
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("sync", "1000"),
        encode_instruction("key", "97", "1"),  # offset 0
        encode_instruction("sync", "2500"),
        encode_instruction("key", "98", "1"),  # offset 1500 — 3000ms eşiğinin ALTINDA
    )
    path.write_bytes(data)

    assert await extract_idle_gaps(str(path), min_gap_ms=3000) == []


async def test_idle_gaps_detects_real_long_pause_between_activity(tmp_path):
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("sync", "1000"),
        encode_instruction("key", "97", "1"),  # aktivite, offset 0
        encode_instruction("sync", "6000"),  # offset 5000 — 5sn boşluk, sadece sync (heartbeat)
        encode_instruction("mouse", "10", "20", "0"),  # aktivite tekrar başlıyor, offset 5000
    )
    path.write_bytes(data)

    assert await extract_idle_gaps(str(path), min_gap_ms=3000) == [{"start_ms": 0, "end_ms": 5000}]


async def test_idle_gaps_includes_trailing_gap_to_end_of_recording(tmp_path):
    """Kullanıcı son bir aktiviteden sonra klavye/fareyi bırakıp
    oturumu kapatmadan ayrılırsa — kaydın SONUNA kadar süren boşluk da
    (yalnızca `sync` heartbeat'i varken) bir "idle gap" olarak
    işaretlenir."""
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("sync", "1000"),
        encode_instruction("key", "97", "1"),  # offset 0
        encode_instruction("sync", "9000"),  # offset 8000 — sondaki boşluk
    )
    path.write_bytes(data)

    assert await extract_idle_gaps(str(path), min_gap_ms=3000) == [{"start_ms": 0, "end_ms": 8000}]


async def test_idle_gaps_detects_multiple_separate_gaps(tmp_path):
    path = tmp_path / "session.guac"
    data = _recording(
        encode_instruction("sync", "0"),
        encode_instruction("key", "97", "1"),  # offset 0
        encode_instruction("sync", "4000"),  # boşluk 1: 0-4000
        encode_instruction("key", "98", "1"),  # offset 4000, aktivite
        encode_instruction("sync", "4500"),
        encode_instruction("mouse", "5", "5", "0"),  # offset 4500 — kısa, boşluk sayılmaz
        encode_instruction("sync", "9000"),  # boşluk 2: 4500-9000
        encode_instruction("key", "99", "1"),  # offset 9000
    )
    path.write_bytes(data)

    assert await extract_idle_gaps(str(path), min_gap_ms=3000) == [
        {"start_ms": 0, "end_ms": 4000},
        {"start_ms": 4500, "end_ms": 9000},
    ]
