from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# Desteklenmesi planlanan sürümler — bkz. Faz 4.16 (v2c) ve Faz 7
# (v3 eklendi; v1 kasıtlı olarak desteklenmiyor, bkz. decisions.md).
SNMPVersion = Literal["v2c", "v3"]

IfStatus = Literal["up", "down", "testing", "unknown", "dormant", "notPresent", "lowerLayerDown"]

PollStatus = Literal[
    "not_configured",
    "unreachable",
    "timeout",
    "authentication_failed",
    "success",
    "partial",
]


class SystemInfo(BaseModel):
    """`SYSTEM_OIDS` sorgusunun sonucu — tüm alanlar opsiyonel: bir ajan
    bazı OID'leri desteklemeyebilir, eksik alan asla uydurulmaz."""

    sys_name: str | None = None
    sys_descr: str | None = None
    sys_object_id: str | None = None
    sys_uptime_ticks: int | None = None  # SNMP TimeTicks (1/100 saniye)


class InterfaceInfo(BaseModel):
    """`INTERFACE_OIDS` sorgusunun tek bir `ifIndex` için sonucu.

    `if_in_octets`/`if_out_octets`: mümkünse 64-bit sayaç
    (`ifHCInOctets`/`ifHCOutOctets`, IF-MIB/ifXTable) kullanılır; ajan
    bunu desteklemiyorsa 32-bit `ifInOctets`/`ifOutOctets`'e düşülür —
    hangisinin kullanıldığı `if_counters_64bit` alanında açıkça
    belirtilir (`None` = hiçbiri okunamadı)."""

    if_index: int
    if_name: str | None = None
    if_descr: str | None = None
    if_admin_status: IfStatus | None = None
    if_oper_status: IfStatus | None = None
    if_speed_bps: int | None = None
    if_in_octets: int | None = None
    if_out_octets: int | None = None
    if_counters_64bit: bool | None = None
    # `bandwidth.calculate_bandwidth_bps` ile, bu asset+ifIndex için bir
    # önceki poll'a göre hesaplanır. İlk poll'da (henüz baseline yok)
    # veya counter rollover/zaman ilerlememe durumunda her zaman `None`
    # — asla 0 veya tahmini bir değer değil (bkz. bandwidth.py).
    if_in_bps: float | None = None
    if_out_bps: float | None = None
    # ifInErrors/ifOutErrors (IF-MIB) — KÜMÜLATİF sayaçlardır (ajan son
    # yeniden başlatıldığından beri), bir ORAN değil. `bandwidth.py`'nin
    # aksine burada bir delta/rate hesabı YAPILMAZ (Faz 26 kapsamında
    # bilinçli bir basitleştirme) — frontend alert kuralı bunu "toplam
    # hata sayısı > 0" olarak yorumlar, "şu an aktif hata oranı" olarak
    # değil. Veri yoksa (ajan desteklemiyorsa) `None` kalır.
    if_in_errors: int | None = None
    if_out_errors: int | None = None


class SNMPPollResult(BaseModel):
    """Bir asset için tek bir SNMP poll denemesinin sonucu.

    `status` her zaman gerçek durumu yansıtır, altı değer birbirine asla
    karıştırılmaz:
    - `not_configured`: bu asset için bir `SNMPProfile` yok.
    - `unreachable`: hedefe hiç ulaşılamadı (host/ağ seviyesinde).
    - `timeout`: `timeout`/`retries` içinde hiç yanıt gelmedi (v2c'de
      yanlış community string de çoğunlukla bu şekilde görünür — bkz.
      `exceptions.SNMPAuthenticationError` docstring'i).
    - `authentication_failed`: ajan açıkça bir kimlik doğrulama
      reddi/hata göstergesiyle yanıt verdi.
    - `success`: system VE (varsa) interface poll'ları tamamen başarılı.
    - `partial`: system başarılı ama en az bir interface/OID
      okunamadı (veya tersi) — `error` alanı hangi kısmın eksik
      olduğunu açıklar.
    Hiçbir durumda `system`/`interfaces` rastgele veya varsayılan
    (uydurma) değerlerle doldurulmaz — veri yoksa `None`/`[]` kalır."""

    asset_id: UUID
    polled_at: datetime
    status: PollStatus
    system: SystemInfo | None = None
    interfaces: list[InterfaceInfo] = []
    error: str | None = None
    duration_ms: float | None = None  # gerçek poll süresi; not_configured'da None
