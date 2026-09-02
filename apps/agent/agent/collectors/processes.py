"""Temel process envanteri — Faz 30 master prompt §11.

BİLİNÇLİ KISITLAMA: `cmdline` (komut satırı argümanları) BURADA HİÇ
toplanmaz. Birçok uygulama secret/token/parola'yı komut satırı
argümanı olarak geçirir (ör. `--password=...`, connection string'ler);
bunu toplamak, agent'ı istemeden bir credential-harvesting aracına
çevirir. Yalnızca PID/isim/CPU%/memory%/kullanıcı/durum toplanır.

Süreç listesi büyük olabileceğinden `limit` ile en yoğun (CPU sonra
memory'e göre sıralı) N süreçle sınırlanır — sınırsız bir liste hem
payload boyutunu hem DB'yi gereksiz şişirir."""

from __future__ import annotations

import logging

import psutil

logger = logging.getLogger("agent.collectors.processes")

_ATTRS = ("pid", "name", "cpu_percent", "memory_percent", "username", "status")


def _normalize_cpu_percent(raw: float | None, cpu_count: int) -> float | None:
    """`psutil.Process.cpu_percent()` NORMALİZE EDİLMEMİŞ döner — çok
    çekirdekli bir makinede boşta duran bir süreç bile ("System Idle
    Process" gibi) %100'ün çok üzerinde görünebilir (ör. 12 mantıksal
    çekirdekli, çoğunlukla boşta bir makinede ~1100%). Gerçek bir
    kullanıcı bildirimiyle bulunan hata — Windows Görev Yöneticisi'nin
    gösterdiği 0-100% ölçeğine normalize ederiz (çekirdek sayısına
    böleriz, üst sınır 100.0 — zamanlama kaynaklı ölçüm gürültüsüne
    karşı bir güvenlik payı)."""
    if raw is None:
        return None
    return min(raw / cpu_count, 100.0)


def collect_processes(limit: int = 50) -> list[dict]:
    processes: list[dict] = []
    try:
        cpu_count = psutil.cpu_count() or 1
    except Exception:
        cpu_count = 1

    try:
        iterator = psutil.process_iter(attrs=_ATTRS)
    except Exception:
        logger.warning("Process listesi alınamadı", exc_info=True)
        return processes

    for proc in iterator:
        try:
            info = proc.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        processes.append(
            {
                "pid": info.get("pid"),
                "name": info.get("name") or "unknown",
                "cpu_percent": _normalize_cpu_percent(info.get("cpu_percent"), cpu_count),
                "memory_percent": info.get("memory_percent"),
                "username": info.get("username"),
                "status": info.get("status"),
            }
        )

    processes.sort(key=lambda p: (p["cpu_percent"] or 0.0, p["memory_percent"] or 0.0), reverse=True)
    return processes[:limit]
