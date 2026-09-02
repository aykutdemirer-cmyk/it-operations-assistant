"""SNMP client'ının fırlattığı hata hiyerarşisi.

`app/snmp/client.py`, pysnmp'nin kendi iç exception/`ErrorIndication`
tiplerini asla üst katmana (route, log) sızdırmaz — her zaman bu
modüldeki tiplerden birine çevirir. Bu sayede:

- HTTP katmanı pysnmp'ye bağımlı kalmaz (bkz. CLAUDE.md — katmanlar
  birbirinin implementasyon detayına sızmamalı),
- hata mesajları asla credential DEĞERİ içermez (yalnızca host/port/OID
  gibi credential OLMAYAN bağlam bilgisi taşıyabilir)."""


class SNMPError(Exception):
    """Tüm SNMP hatalarının base sınıfı."""


class SNMPTimeoutError(SNMPError):
    """Ajan `timeout`/`retries` içinde hiç yanıt vermedi."""


class SNMPUnavailableError(SNMPError):
    """Hedefe ulaşılamadı (ör. host çözümlenemedi, ağ erişilemez,
    bağlantı seviyesinde reddedildi) — timeout'tan ayrı: burada ajanın
    var olup olmadığı bile bilinmiyor."""


class SNMPAuthenticationError(SNMPError):
    """Community string (v2c) veya kullanıcı/auth/priv (v3) reddedildi.

    v2c için not: yanlış community string'e çoğu ajan hiç yanıt vermez
    (sessizce drop eder) — bu durum ayırt edilemediği için `timeout`
    olarak sınıflanır. Bu hata yalnızca ajanın gerçekten bir
    `authenticationFailure`/`unknownCommunityName`/`usmStats*` hata
    göstergesiyle YANIT VERDİĞİ durumlarda fırlatılır."""


class SNMPProtocolError(SNMPError):
    """Ajan yanıt verdi ama yanıt SNMP protokol seviyesinde bozuk/
    beklenmeyen (ör. `errorStatus` != 0, beklenmeyen varbind tipi,
    parse edilemeyen OID/değer)."""
