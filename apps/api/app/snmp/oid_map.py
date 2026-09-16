# Standart MIB-II (RFC 1213) ve IF-MIB (RFC 2863) OID'leri — SNMP ajanı
# devreye girdiğinde `client.py` bu isimlerle sorgu yapacak. Şu an gerçek
# bir SNMP kütüphanesi (örn. pysnmp) bağımlılığı eklenmedi (bkz.
# docs/decisions.md) — bu dosya yalnızca isim <-> OID eşlemesini, kodun
# başka hiçbir yerinde ham OID string'i hardcode edilmeyecek şekilde tek
# yerde toplar.

# system grubu (1.3.6.1.2.1.1) — cihaz başına tek değer (scalar)
SYSTEM_OIDS: dict[str, str] = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
}

# ifTable / ifXTable (1.3.6.1.2.1.2.2.1, 1.3.6.1.2.1.31.1.1.1) — arayüz
# başına tekrarlanan (table) değerler. Gerçek sorguda her OID'nin sonuna
# `.<ifIndex>` eklenir; burada yalnızca taban OID tutulur.
#
# ifHCInOctets/ifHCOutOctets (ifXTable, RFC 2863) 64-bit sayaçlardır ve
# yüksek hızlı arayüzlerde 32-bit ifInOctets/ifOutOctets'in çok hızlı
# taşmasını (rollover) önlemek için tercih edilir; `client.py` önce bu
# ikisini dener, ajan desteklemiyorsa (yanıt yoksa) 32-bit muadiline
# düşer — hangisinin kullanıldığı `InterfaceInfo.if_counters_64bit`
# alanında açıkça işaretlenir.
INTERFACE_OIDS: dict[str, str] = {
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
    "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
    "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
    "ifName": "1.3.6.1.2.1.31.1.1.1.1",
    "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
    "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
    "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
    "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
}

# `ifNumber` (1.3.6.1.2.1.2.1.0) — cihazdaki interface sayısı; walk
# yerine `ifIndex`'leri doğrudan bulmak için ifTable üzerinde bulk-walk
# yapılır, bu OID yalnızca referans amaçlıdır.
IF_NUMBER_OID = "1.3.6.1.2.1.2.1.0"

# ifTable/ifXTable bulk-walk için taban (subtree) OID'leri — `client.py`
# bu iki subtree'yi GETBULK ile dolaşıp ifIndex'leri keşfeder.
IF_TABLE_BASE_OID = "1.3.6.1.2.1.2.2.1"
IF_X_TABLE_BASE_OID = "1.3.6.1.2.1.31.1.1.1"

# HOST-RESOURCES-MIB (RFC 2790) — CPU/Bellek. KASITLI olarak
# SYSTEM_OIDS/INTERFACE_OIDS'ten AYRI: bu MIB standart MIB-II/IF-MIB'in
# aksine yalnızca "host" niteliğindeki cihazlarda (sunucu, Windows/Linux
# host) yaygın desteklenir — çoğu switch/router/firewall/AP bunu hiç
# implemente ETMEZ. `client.py` bu OID'leri desteklenmiyor olarak
# BULURSA (SNMPError) `SystemInfo.cpu_percent`/`memory_*` dürüstçe
# `None` kalır — asla varsayılan/tahmini bir değere düşülmez, ve poll'un
# genel `status`'unu (`partial`e bile) ETKİLEMEZ (bkz. client.py
# `_get_cpu_memory_info` docstring'i).
#
# hrProcessorTable (1.3.6.1.2.1.25.3.3.1) — her CPU çekirdeği/işlemci
# için ayrı bir satır; `hrProcessorLoad` son 1 dakikadaki ortalama
# yüzde kullanım (0-100). Birden fazla çekirdek varsa `client.py`
# hepsinin ortalamasını alır.
HR_PROCESSOR_LOAD_BASE_OID = "1.3.6.1.2.1.25.3.3.1.2"

# hrStorageTable (1.3.6.1.2.1.25.2.3.1) — diskler/bellek dahil tüm
# depolama birimlerini tek bir tabloda listeler; `hrStorageType`
# değeri `HR_STORAGE_RAM_TYPE_OID`'e eşit olan satır fiziksel RAM'dir
# (diğerleri disk/swap/vb. — hiçbiri bellek olarak yorumlanmaz).
HR_STORAGE_TYPE_BASE_OID = "1.3.6.1.2.1.25.2.3.1.2"
HR_STORAGE_SIZE_BASE_OID = "1.3.6.1.2.1.25.2.3.1.5"
HR_STORAGE_USED_BASE_OID = "1.3.6.1.2.1.25.2.3.1.6"
HR_STORAGE_ALLOC_UNITS_BASE_OID = "1.3.6.1.2.1.25.2.3.1.4"
# hrStorageTypes::hrStorageRam (RFC 2790) — `hrStorageType` sütununun
# "bu satır fiziksel RAM'dir" anlamına gelen sabit değeri.
HR_STORAGE_RAM_TYPE_OID = "1.3.6.1.2.1.25.2.1.2"
