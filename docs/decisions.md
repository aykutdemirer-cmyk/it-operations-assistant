# Mimari Kararlar (ADR Özeti)

Her karar kısa gerekçe ile birlikte listelenmiştir. Kararı değiştirmek
isteyen biri önce buradaki gerekçeyi okumalı ve geçersizse burayı
güncellemelidir.

## 1. Frontend: Next.js + React + TypeScript

Dashboard ağırlıklı bir UI; SSR/route yapısı ve geniş ekosistem için
Next.js seçildi. TypeScript strict mod, cihaz/tarama veri modellerinde
tip güvenliği sağlar.

## 2. Backend: Python + FastAPI

Discovery Engine zaten Python gerektiriyor (ICMP/ARP/port tarama için
olgun kütüphaneler). Aynı dilde backend yazmak, discovery katmanı ile API
katmanı arasında ayrı bir süreç/serileştirme katmanı ihtiyacını ortadan
kaldırır. FastAPI, async I/O (çok sayıda host'u paralel taramak için
uygun) ve otomatik OpenAPI şeması sağlar.

## 3. Database: PostgreSQL, ORM yok

İlişkisel veri (devices ↔ ports, scans ↔ devices) için PostgreSQL uygun.
ORM kullanılmaması BarkodSaglik projesindeki disiplinin devamıdır: az
sayıda, iyi tanımlı tablo için ham SQL/`asyncpg` (veya benzeri) yeterli,
ekstra soyutlama katmanı gerekmez. Şema migration ihtiyacı ilgili fazda
ayrıca değerlendirilecektir.

## 4. Discovery: Python standart kütüphane + hedefli 3. parti kütüphaneler

ICMP/ARP/TCP/DNS için Python'da (`socket`, `scapy` vb.) olgun araçlar
mevcut. SNMP ileri fazda eklenecek; MVP'nin akışını etkilememesi için
discovery adımları ayrı, birbirinden bağımsız fonksiyonlar olarak
tasarlanacak (bkz. `architecture.md` §5).

## 5. Monorepo yapısı (`apps/web`, `apps/api`)

Frontend ve backend aynı repo altında, `apps/` altında ayrı paketler
olarak tutulacak. Tek repo, dokümantasyon ve versiyon senkronizasyonunu
kolaylaştırır; `apps/` ayrımı iki tarafın bağımsız geliştirilip
paketlenmesine (Docker, CI) izin verir.

## 6. Containerization: Docker (ileri faz)

Discovery Engine'in ham socket (ICMP/ARP) yetkisi gerektirmesi,
container'ın ağ moduna (`--network host` veya `NET_RAW` capability)
dikkat edilmesini gerektirir. Bu, Docker fazında netleştirilecek açık bir
kısıttır; MVP dokümantasyon fazında sadece not düşülmüştür.

## 7. AI: Claude API (ileri faz), aggregator'dan ayrı katman

BarkodSaglik projesindeki desenle tutarlı olarak: AI katmanı, discovery/
storage katmanının ürettiği veriyi salt-okunur tüketir; ham discovery
çıktısını değiştirmez. Bu ayrım, AI çıktısının yanlışlıkla kaynak veriyi
bozmasını engeller.

## 8. Faz bazlı geliştirme, küçük context

Proje, her biri bağımsız test edilebilir küçük fazlara bölünecek (bkz.
`roadmap.md`). Gerekçe: hem insan hem AI destekli geliştirmede küçük,
net kapsamlı fazlar daha az hata ve daha az token/context maliyeti
üretir. Detaylar `CLAUDE.md` içinde çalışma kuralı olarak yazılıdır.

## 9. Dashboard veri getirme: ölçüldü (Faz 4.21), sonra optimize edildi (Faz 5)

Faz 4.21'de ölçüldü: her dashboard component'i (`DashboardSummary`,
`InfrastructureHealth`, `AlertsPanel`, `DeviceDistribution`,
`OpenPortsOverview`, `AssetInventory`, `RecentActivity`) kendi
`useEffect`'inde bağımsız `fetchAssets()` çağırıyordu;
`RecentScans`/`RecentActivity` de aynı şekilde bağımsız `fetchScans()`
çağırıyordu. Gerçek tarayıcıda ölçüldü: tek bir dashboard sayfa
yüklemesi `GET /api/assets`'e 7, `GET /api/scans`'e 2 ayrı istek
anlamına geliyordu. O noktada karar "şimdilik dokunulmuyor"du (küçük
veri seti, gözle görülür bir sorun yok, erken optimizasyondan kaçınma).

Faz 5'te, kullanıcı açıkça bu katmanın iyileştirilmesini istediği için
ele alındı: `apps/web/lib/DashboardDataProvider.tsx` — React `Context` +
`useState`/`useEffect` tabanlı, **yeni bir dependency eklenmeden**
(SWR/React Query kullanılmadı) paylaşımlı bir veri katmanı. Kök
`app/layout.tsx`'e bağlandı (tüm sayfalarda, `/topology` dahil,
tek instance). Sağladıkları: `assets`/`scans`, `assetsStatus`/
`scansStatus`, `assetsError`/`scansError`, `refetchAssets`/
`refetchScans`. `network-scan-completed` event dinleyicisi de tek
noktaya (`DashboardDataProvider`) taşındı — önceden `RecentScans` kendi
başına dinliyordu.

Sonuç (gerçek tarayıcıda `read_network_requests` ile doğrulandı): tek
dashboard yüklemesinde `GET /api/assets` 7'den 1'e düştü (dev modunda
React StrictMode ikiye katlıyor — production'da katlanmıyor); `/` →
`/topology` arası client-side navigasyonda (aynı layout/provider
instance'ı korunduğu için) **hiç** ek istek atılmıyor.

Bilinçli olarak yapılmayan: component'lerin bağımsız test edilebilirliği
korundu — her component hâlâ kendi render/loading/empty/error/success
testine sahip, yalnızca artık `DashboardDataProvider` ile sarmalanarak
render ediliyor (bkz. `apps/web/tests/testUtils.tsx`).

## 10. SNMP credential/profile mimarisi — yalnızca tasarım, henüz persistence yok (Faz 7)

Kullanıcıya soruldu: gerçek bir SNMP kütüphanesi (`pysnmp` vb.) eklensin
mi, yoksa yalnızca mimari mi tasarlansın? Cevap: **yalnızca mimari** —
gerçek bir SNMP ajanı/cihaz henüz verilmediği için (bkz. master prompt
§25) yeni bir production dependency eklemek veya bir credential-storage
şemasını erken commit etmek riskli/erken olur.

**Yapılan (kod):** `apps/api/app/snmp/credentials.py` — `SNMPProfile`
Pydantic modeli. v2c ve v3 destekleniyor (v1 kasıtlı olarak yok —
SNMPv1'in kendi güvenlik zaafları nedeniyle modern bir NOC platformunda
desteklenmemesi tercih edildi). Model **hiçbir gerçek secret değeri
taşımaz** — yalnızca `community_ref`/`auth_credential_ref`/
`priv_credential_ref` gibi *referans* alanları var (örn. bir `.env`
değişken adı). `model_validator` ile v2c/v3'e göre zorunlu alanlar
doğrulanıyor (örn. v3 + `priv_protocol` varsa `priv_credential_ref` da
zorunlu).

**Yapılmayan (bilinçli, kullanıcı onayı bekliyor):**
- `pysnmp` (veya başka bir SNMP kütüphanesi) dependency'si eklenmedi —
  gerçek bir ajan/cihaz olmadan bir kütüphaneyi "doğru" seçtiğimizi
  doğrulayamayız; gereksiz/yanlış bağımlılık riski var.
- Kalıcı bir `snmp_profiles` DB tablosu **oluşturulmadı**. Aşağıdaki
  şema yalnızca bir PLAN'dır, henüz `infra/postgres/init.sql`'e
  eklenmedi:

  ```sql
  -- PLAN — henüz uygulanmadı, gerçek ajan geldiğinde gözden geçirilecek
  CREATE TABLE snmp_profiles (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
      version TEXT NOT NULL,              -- 'v2c' | 'v3'
      port INTEGER NOT NULL DEFAULT 161,
      timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 2.0,
      retries INTEGER NOT NULL DEFAULT 1,
      community_ref TEXT,                 -- yalnızca referans
      username TEXT,
      auth_protocol TEXT,
      auth_credential_ref TEXT,           -- yalnızca referans
      priv_protocol TEXT,
      priv_credential_ref TEXT,           -- yalnızca referans
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT snmp_profiles_asset_id_key UNIQUE (asset_id)
  );
  ```

- **`*_ref` alanlarının gerçek değere nasıl çözüleceği henüz
  kararlaştırılmadı** (örn. `.env`'de sabit bir değişken mi, yoksa bir
  secrets manager mi). Bu, gerçek bir SNMP ajanı devreye girmeden
  netleştirilmesi gereken ayrı bir güvenlik kararıdır; burada tek
  taraflı seçilmedi.

**Sonraki adım:** kullanıcı gerçek bir SNMP ajanı/cihaz bilgisi
verdiğinde (IP, versiyon, port, credential) — önce hangi kütüphanenin
kullanılacağı sorulacak, sonra `snmp_profiles` tablosu ve
`*_ref` çözümleme mekanizması birlikte tasarlanıp uygulanacak.

### 10.1 Güncelleme (Faz 22.2) — kütüphane seçildi, `*_ref` çözümlendi, tablo hâlâ YOK

Kullanıcı "FAZ 22.2 — GERÇEK SNMP ENTEGRASYONU BAŞLAT" talimatıyla
`pysnmp` kütüphanesini adlandırarak onay verdi (uyumluluk kontrolü
geçmesi şartıyla). Uyumluluk `pip install --dry-run` + PyPI JSON API +
GitHub `LICENSE.rst` ile doğrulandı: `pysnmp==7.1.29` (LeXtudio fork,
aktif geliştiriliyor, Python 3.14 sınıflandırıcısı var, tek runtime
bağımlılığı `pyasn1`, BSD-2-Clause benzeri lisans) eklendi.

**`*_ref` çözümleme mekanizması kararlaştırıldı:** `apps/api/app/snmp/
secrets.py::resolve_secret(ref)` — `ref` bir ortam değişkeni ADI'dır,
fonksiyon `os.environ.get(ref)` ile gerçek değeri döner. Tek, merkezi
çözümleme noktası; hiçbir çağıran taraf `os.environ`'a doğrudan
erişmez.

**Kalıcı `snmp_profiles` tablosu HÂLÂ oluşturulmadı** — yukarıdaki plan
geçerliliğini koruyor, henüz uygulanmadı. Bunun yerine, çoklu-asset
persistence tasarımını erken commit etmeden ilerleyebilmek için bilinçli
bir ARA ADIM eklendi: `apps/api/app/snmp/profile_store.py::
get_profile_for_asset(asset_id)` yalnızca `.env`'deki `SNMP_TARGET_*`
değişkenleriyle tanımlı **tek bir** hedefi çözer (`SNMP_TARGET_ASSET_ID`
eşleşmezse `None` — yani varsayılan davranış `not_configured` olarak
kalır). Bu, "kullanıcı bana IP/VERSION/PORT/CREDENTIAL REF versin, ben
sadece onu kullanayım" kısıtına `.env` üzerinden bir karşılık verir;
kalıcı çoklu-asset profil yönetimi (yukarıdaki `snmp_profiles` planı)
YERİNE geçmez — birden fazla gerçek cihaz izlenmeye başlandığında hâlâ
ayrıca tasarlanıp onaylanması gerekir.

`apps/api/app/snmp/client.py` yalnızca **SNMPv2c** implemente eder;
SNMPv3 mimarisi (`SNMPProfile`) korunuyor ama bilinçli olarak yarım
bırakılmadı — hiç yazılmadı (bkz. `docs/roadmap.md` Faz 22.2).

### 10.2 Güncelleme (Faz 22.4) — SNMPv3 gerçek implementasyon

SNMPv3 için `pysnmp.hlapi.v3arch.asyncio` kullanıldı (v1arch'taki
`Slim` sarmalayıcısının v3 karşılığı yok — `SnmpEngine`/`UsmUserData`/
`get_cmd`/`bulk_cmd` doğrudan kullanılıyor). Ortak system/interface
parsing kodu, `client.py` içinde küçük bir `_Transport` protokolü
(`_V2cTransport`/`_V3Transport`) ile v2c'den tamamen ayrıştırıldı —
MIB parsing mantığı iki versiyon arasında tekrarlanmıyor.

**Desteklenen güvenlik seviyeleri:** `noAuthNoPriv` / `authNoPriv` /
`authPriv` (RFC 3414). `credentials.py::SNMPProfile` artık v3 için
yalnızca `username` zorunlu tutuyor; `auth_protocol`/`priv_protocol`
alanların DOLU olup olmamasına göre güvenlik seviyesi kendiliğinden
belirleniyor (`SNMPProfile.security_level` property'si) — eskiden
(Faz 7) `auth_protocol` her zaman zorunlu tutulduğu için `noAuthNoPriv`
temsil edilemiyordu, bu Faz 22.4'te bilinçli olarak genişletildi.

**Algoritmalar:** Auth — SHA-1 + tam SHA-2 ailesi (SHA224/256/384/512),
pysnmp 7.1.29'da `usmHMAC{128SHA224,192SHA256,256SHA384,384SHA512}
AuthProtocol` sabitleriyle doğrulandı. Priv — AES (128/192/256-bit,
`usmAesCfb{128,192,256}Protocol`). MD5/DES yalnızca eski ajan uyumluluğu
için `Literal` tipinde tutuluyor ama **hiçbir yerde varsayılan değil** —
`SNMPProfile.auth_protocol`/`priv_protocol` her zaman zorunlu, açıkça
seçilen alanlar. Bu önemli çünkü pysnmp'nin kendi `UsmUserData`
kurucusu, `authKey` verilip `authProtocol` verilmezse **sessizce MD5'e**,
`privKey` verilip `privProtocol` verilmezse **sessizce DES'e** düşüyor
(pysnmp kaynağında doğrulandı) — `client.py::_build_usm_user_data` bu
tuzağa düşmemek için ikisini HER ZAMAN birlikte, açıkça geçiriyor.

**Credential:** `username` bir secret-ref DEĞİL, düz bir alan olarak
kaldı (RFC 3414 username'i auth/priv parolası gibi ele almaz; mevcut
Faz 7 testleri de bunu zaten bu şekilde varsayıyordu) — ama hiçbir yeni
log satırı `profile.username`'i yazmıyor, yalnızca `asset_id`/`host`
gibi credential-olmayan bağlam loglanıyor. `auth_credential_ref`/
`priv_credential_ref` aynı `resolve_secret()` mekanizmasıyla çözülüyor;
biri eksikse (env'de yoksa) sonuç `not_configured`.

**`profile_store.py`** genişletildi: `SNMP_TARGET_VERSION=v3` iken
`SNMP_TARGET_USERNAME`/`_AUTH_PROTOCOL`/`_AUTH_CREDENTIAL_REF`/
`_PRIV_PROTOCOL`/`_PRIV_CREDENTIAL_REF` env değişkenleriyle tek bir v3
hedefi çözer — v2c ile aynı "yalnızca kullanıcının açıkça verdiği tek
hedef" kısıtı, kalıcı depolama hâlâ yok.

### 10.3 Karar (Faz 22.5) — SNMP Profile Storage mimarisi (tablo HENÜZ uygulanmadı)

**Durum:** Bu bir mimari KARAR dokümanıdır — otonom çalışma modunun
kendi durma kuralı ("yeni kritik DB schema kararı") gereği, bu karar
onaylansa bile gerçek `CREATE TABLE`/migration bu fazda UYGULANMADI.
Aşağıdaki plan, kullanıcı açıkça onaylayana kadar yalnızca bir tasarım
taslağıdır.

**Neden şimdi tekrar ele alındı:** Faz 22.2/22.4 SNMPv2c ve SNMPv3'ü
gerçek hale getirdi, ama `profile_store.py` hâlâ yalnızca **tek bir**
`.env`-tanımlı hedefi destekliyor. Birden fazla gerçek cihaz izlenmeye
başlanacaksa (Faz 23 Polling Engine'in asıl amacı) çoklu-asset bir
profil kaynağı gerekecek — bu karar o ihtiyacı önceden tasarlıyor.

**1) Profile ↔ Asset ilişkisi:** 1-1. Bir asset'in en fazla bir AKTİF
SNMP profili olur (mevcut `SNMPProfile.asset_id: UUID` alanı zaten bunu
varsayıyor). Çoklu profil/failover (ör. birincil+yedek community)
kasıtlı olarak bu kararın kapsamı dışında — ihtiyaç doğarsa ayrı bir
karar gerektirir.

**2) Credential reference:** Mevcut `*_ref` deseni AYNEN korunur —
`community_ref`/`auth_credential_ref`/`priv_credential_ref` DB satırında
yalnızca birer REFERANS (bugün: bir `.env` değişken adı) olarak
saklanır, gerçek secret değeri asla. `resolve_secret(ref)` tek
çözümleme noktası olmaya devam eder — DB'ye taşındığında bile bu
fonksiyonun imzası/davranışı değişmez, yalnızca `ref`'in KAYNAĞI (bugün
`os.environ`, ileride belki bir secret manager) değişebilir.

**3) Secret storage:** MVP'de env-var tabanlı `resolve_secret()`
korunur. **Plaintext bir secret DEĞERİ PostgreSQL'e asla yazılmaz** —
bu, CLAUDE.md'nin güvenlik kuralı ve bu dokümanın §10 kararıyla
tutarlıdır. Harici bir secret manager (Vault, AWS Secrets Manager vb.)
şu an KURULMUYOR — gerçek ihtiyaç (çok sayıda gerçek cihaz, ekip
paylaşımlı erişim) doğmadan bu bir erken/gereksiz operasyonel yük olur;
`resolve_secret()`'ın tek sorumluluğu (isimden değere çözme) ileride bu
fonksiyonun içini değiştirerek bir secret manager'a geçmeyi mümkün
kılar — çağıran kod (`client.py`) hiç değişmez.

**4) Encryption ihtiyacı:** DB satırı hiçbir zaman secret DEĞERİ
taşımadığı için (yalnızca `*_ref` isimleri) column-level encryption
gerekmez. PostgreSQL bağlantısının TLS'i ve disk-level encryption genel
altyapı kararlarıdır, SNMP'ye özel değildir — kapsam dışı.

**5) Rotation:** Bir secret rotasyonu yalnızca `.env`'de (veya ileride
secret manager'da) yapılır; `ref` isim DEĞİŞMEDİĞİ sürece DB satırına
hiç dokunulmaz — **sıfır migration ile rotasyon** bu tasarımın doğrudan
bir sonucu. `ref` isminin kendisi değişirse (nadir) tek satırlık bir
`UPDATE` yeterlidir.

**6) Deletion:** Asset silinirse profili de silinir
(`ON DELETE CASCADE`, aşağıdaki plan şemasında zaten var — bkz. §10).
Profil silinirse İLGİLİ SECRET DEĞERİ silinmez (çünkü DB'de zaten hiç
yoktu) — `.env`/secret manager'daki referansı temizlemek kullanıcının
sorumluluğunda kalır; bu, uygulama tarafından otomatikleştirilmez
(otomatik secret silme, "kullanıcı verisi silme" kadar tehlikeli bir
yan etki olur).

**7) Audit:** Profil oluşturma/güncelleme/silme olaylarının (kim, ne
zaman, hangi asset, hangi versiyon/security_level — **SECRET DEĞERİ
hariç**) izlenmesi ayrı bir kapsam: Faz 32 (Audit/History). Bu fazda
ayrı bir audit tablosu eklenmiyor.

**8) Frontend'de secret gösterilmemesi:** İleride eklenecek herhangi
bir `GET/POST /api/snmp/profiles/{asset_id}` endpoint'i `*_ref`
alanlarını (isim) dönebilir ama gerçek secret değerini ASLA response'a
koymaz — mevcut `SNMPPollResult` sözleşmesiyle (Faz 22.2) aynı ilke.
Frontend hiçbir zaman ham secret değeri alan bir form/alan
göstermeyecek (yalnızca `*_ref` isim girişi, tıpkı backend'deki desen).

**9) Geçiş yolu / abstraction:** `profile_store.py`'nin dışa açtığı
`get_profile_for_asset(asset_id: UUID) -> SNMPProfile | None` imzası,
env-tabanlı bugünkü implementasyon ile ileride DB-tabanlı bir
implementasyon arasındaki KARARLI sınırdır — bu imza değişmeden,
fonksiyonun GÖVDESİ `.env` okumaktan bir `SELECT ... FROM
snmp_profiles WHERE asset_id = $1` sorgusuna geçebilir; hiçbir çağıran
kod (`routes/snmp.py`, `client.py`) bu geçişte değişmez. Bu yüzden şu an
ayrı bir `Protocol`/`ABC` sınıfı eklenmedi (YAGNI — tek implementasyon
varken erken soyutlama) — fonksiyon imzasının kendisi zaten yeterli
sınır.

**Plan (henüz UYGULANMADI, `docs/decisions.md` §10'daki taslak şema
geçerliliğini koruyor):**

```sql
-- PLAN — henüz uygulanmadı, kullanıcı onayı olmadan migration atılmayacak
CREATE TABLE snmp_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL UNIQUE REFERENCES assets(id) ON DELETE CASCADE,
    version TEXT NOT NULL,              -- 'v2c' | 'v3'
    port INTEGER NOT NULL DEFAULT 161,
    timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 2.0,
    retries INTEGER NOT NULL DEFAULT 1,
    community_ref TEXT,                 -- yalnızca referans, secret değil
    username TEXT,                      -- RFC 3414: secret sayılmaz
    auth_protocol TEXT,
    auth_credential_ref TEXT,           -- yalnızca referans
    priv_protocol TEXT,
    priv_credential_ref TEXT,           -- yalnızca referans
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Sonraki adım:** Kullanıcı bu kararı onaylar VE gerçek çoklu-cihaz
ihtiyacı somutlaşırsa (Faz 23 Polling Engine birden fazla asset'i poll
etmeye başladığında) — önce bu migration ayrı bir onay turunda
uygulanır, sonra `profile_store.py::get_profile_for_asset` DB-tabanlı
implementasyona geçirilir. O ana kadar Faz 23, mevcut env-tabanlı tek-
hedef `profile_store.py` üzerinden ilerler (birden fazla asset
poll edilebilir ama yalnızca `SNMP_TARGET_ASSET_ID` ile eşleşen biri
gerçek veri döner, diğerleri dürüstçe `not_configured`).

### 10.4 Uygulama (Faz 29) — `snmp_profiles` GERÇEKTEN oluşturuldu, şema §10.3'ten SAPTI

**Durum:** `snmp_profiles` tablosu artık GERÇEKTEN var (`infra/postgres/
init.sql`, `apps/api/app/db/snmp_profiles.py`) — additive bir migration,
`assets`/`scans`/`agents` tablolarına dokunmadı. Bu, önceki fazların
"kullanıcı onayı olmadan tablo oluşturma" duruşundan bilinçli bir
sapmadır: kullanıcının Faz 29 talimatı açıkça "Bu faz artık gerçek
configuration UI istediği için kalıcı storage gerekiyorsa additive
tablo oluştur" diyordu — bu, gerekli onayın kendisiydi.

**Şema §10.3'ün planından SAPTI — kasıtlı:**
- §10.3 planı `asset_id UUID NOT NULL UNIQUE REFERENCES assets(id)`
  öngörüyordu (profil ↔ asset 1-1). Kullanıcının Faz 29 talimatı ise
  açıkça `id, name, target_host, port, version, timeout_seconds,
  retries, credential_ref, enabled, created_at, updated_at` alan
  listesini verdi — **`asset_id` YOK**, bunun yerine `target_host`
  (IP/hostname) doğrudan profile'ın kendi kimliği.
- **Gerekçe:** Bir "SNMP Configuration Center", kullanıcının bir asset
  KEŞFEDİLMEDEN ÖNCE bile bir SNMP hedefi tanımlayabilmesini gerektirir
  (ör. henüz discovery ile bulunmamış yeni bir switch'in IP'sini
  önceden yapılandırmak). `asset_id`'yi zorunlu tutmak bunu engellerdi.
  `name` (ör. "Core Switches") artık profilin birincil, insan-okur
  kimliği — UNIQUE kısıt `asset_id` yerine `name` üzerinde.
- Bir asset ile ilişkilendirme KASITLI olarak henüz yok — Agent↔Asset
  eşleştirmesi (bkz. §12/matching.py) ile AYNI ilke: güvenilmeyen/
  belirsiz bir otomatik bağlama yapılmadı. `app/db/snmp_profiles.py::
  get_enabled_profile_by_target_host` bir asset'in IP'sine karşılık
  gelen etkin bir profili SORGULAYABİLİR (Faz 30+ poller entegrasyonu
  için hazır) ama bu fazda hiçbir çağıran taraf bunu kullanmıyor —
  `profile_store.py` bilerek DEĞİŞTİRİLMEDİ (kullanıcının "mevcut SNMP
  client'ı yeniden yazma" talimatına uyularak).

**SNMP Credential Storage — kullanıcının açıkça istediği netlik:**
- Plaintext credential (`community_string`, `auth_password`,
  `priv_password` gibi ham DEĞERLER) DB'de **ASLA** saklanmaz —
  `snmp_profiles` tablosunda yalnızca `community_ref`/`auth_credential_
  ref`/`priv_credential_ref` (birer İSİM) sütunları var.
  `docs/decisions.md` §10.3(2)'deki `resolve_secret()` tek-nokta
  çözümleme ilkesi AYNEN korunuyor.
- Gerçek secret DEĞERİ hiçbir API response'una dönmez —
  `SNMPProfileResponse` yalnızca `credential_configured: bool`
  (secret'ın ŞU AN `.env`'de çözülüp çözülemediği) ve `status`
  (`ready`/`not_configured`/`disabled`) TÜRETİLMİŞ alanlarını taşır.
  `*_ref` İSİMLERİ (değer değil) response'ta var — düzenleme formunun
  mevcut referansı geri gösterebilmesi için (bir env değişken adını
  göstermek güvenlik riski değildir, yalnızca DEĞERİ göstermek risktir).
- Frontend secret'ı asla geri OKUYAMAZ — `SnmpConfigurationCenter.tsx`
  formu yalnızca bir `*_ref` İSİM alanı sunar (`SNMP_CORE_SWITCH_
  COMMUNITY` gibi), gerçek parola/community değerini hiçbir zaman
  içermez veya göstermez.
- **v2c** tam desteklenmektedir (gerçek poll, Faz 22.2'den beri). **v3
  mimarisi/UI'si hazırdır VE gerçek polling implementation'ı da zaten
  VAR** (Faz 22.4'te tamamlandı) — kullanıcının Faz 29 talimatı "v3
  backend polling implementation değilse bile UI hazır olsun" diyordu,
  ama repository incelemesi bunun artık GEÇERSİZ bir varsayım
  olduğunu gösterdi (bkz. `client.py::_poll_v3`, 15 test). Bu yüzden
  "Test Connection" v3 profillerinde de GERÇEK bir poll dener — sahte
  "not_supported" göstermek, gerçek bir yeteneği gizlemek olurdu, bu da
  "sahte veri/durum üretme" yasağının bir başka biçimidir.

**"Test Connection" akışı — güvenlik kararı:** Yalnızca ZATEN KAYITLI
bir profile karşı çalışır (`POST /api/snmp/profiles/{id}/test`).
Kullanıcının önerdiği "kaydetmeden de test edilebilsin" alternatifi
KASITLI olarak eklenmedi — bu, ham bir secret DEĞERİNİN (henüz DB'de
olmayan) bir HTTP request body'sinde taşınmasını gerektirirdi, mevcut
"secret yalnızca `resolve_secret()` ile poll anında okunur" mimarisiyle
çelişirdi. Kullanıcı önce profili kaydeder (secret `.env`'e zaten
konulmuş olmalı), sonra test eder — ekstra bir adım ama sıfır yeni
güvenlik yüzeyi.

**Retention/Agent DB kararı (Faz 29):** `agent_telemetry` için
`AGENT_TELEMETRY_RETENTION_DAYS` (varsayılan 30 gün, credential
DEĞİL — sıradan bir sayısal ayar) + `app/db/agents.py::
delete_expired_telemetry` (idempotent DELETE). Henüz hiçbir zamanlayıcı
tarafından otomatik ÇAĞRILMIYOR (Faz 38 Scheduler'ın kapsamı) —
bilinçli olarak bu fazda bir cron/APScheduler eklenmedi (erken
altyapı riski, henüz gerçek trafik hacmi yok). `AgentStatus` (`online`/
`offline`/`unknown`) `agents.last_heartbeat_at`'ten TÜRETİLİR, DB'de
ayrı bir sütun olarak SAKLANMAZ (Faz 28'in kararıyla aynı ilke).

**Agent↔Asset eşleştirme (Faz 29):** `app/agents/matching.py::
evaluate_asset_match` — hostname/IP/MAC'ten en az İKİ bağımsız sinyal
aynı asset'i işaret etmedikçe `confirmed` sayılmaz (tek sinyal =
`candidate`, insan onayı gerekir). `GET /api/agents/{id}/asset-match`
yalnızca DEĞERLENDİRİR, `POST /api/agents/{id}/asset-match` AÇIKÇA
onaylanmış bir eşleşmeyi uygular — hiçbir arka plan süreci `agents.
asset_id`'yi kendiliğinden doldurmaz.

### 10.5 Uygulama (Faz 29.5) — `asset_snmp_profiles` ilişki tablosu: Asset ↔ SNMP Profile gerçek bağlanıyor

**Mimari karar (kullanıcının kendi ifadesiyle, olduğu gibi korunuyor):**

> SNMP Profile bağlantı/credential configuration'ını temsil eder. Asset
> gerçek cihazı temsil eder. Asset ile SNMP Profile arasındaki ilişki
> `asset_snmp_profiles` üzerinden kurulur. Bir profile birden fazla
> asset atanabilir; her asset aynı anda en fazla bir aktif profile
> sahip olabilir.

**Şema:** `infra/postgres/init.sql`'e additive bir tablo eklendi —
`asset_snmp_profiles(asset_id UUID PRIMARY KEY REFERENCES assets(id)
ON DELETE CASCADE, snmp_profile_id UUID NOT NULL REFERENCES
snmp_profiles(id) ON DELETE CASCADE, created_at, updated_at)` + bir
index (`snmp_profile_id` üzerinde, `GET /api/snmp/profiles/{id}/assets`
için). `asset_id`'nin **PRIMARY KEY** olması — `asset_snmp_profiles`'ın
kendi ayrı bir `id`'si YOK — "her asset'in en fazla bir aktif profili
olabilir" kısıtını veritabanı seviyesinde, uygulama kodu hiç
güvenilmeden garanti eder. `snmp_profiles`'a doğrudan `asset_id` EKLEME
(§10.4'ün 1-1 tasarımını tekrar etmeme) kararı — bir profilin birden
fazla asset'e atanabilmesi (ör. "Core Switches" adlı tek bir profilin
10 switch'e atanması) bu ayrı ilişki tablosuyla mümkün.

**Katmanlar:** `app/db/asset_snmp_profiles.py` (repository — `assign_
profile_to_asset` `ON CONFLICT (asset_id) DO UPDATE` ile yeniden atamayı
[reassignment] doğal olarak destekler, ayrı bir "önce sil sonra ekle"
adımı gerekmez) → `app/snmp/asset_profile_service.py` (asset/profil
var mı doğrulama, `target_host_matches_asset` hesaplama) → `app/routes/
asset_snmp_profiles.py` (`GET/PUT/DELETE /api/assets/{id}/snmp-profile`,
`GET /api/snmp/profiles/{id}/assets`). `profile_config.py::row_to_
domain_profile` iki farklı `correlation_id` anlamıyla PAYLAŞILIYOR:
profilin kendi "Test Connection"ında `correlation_id = profile.id`,
asset'e bağlı gerçek poll'da `correlation_id = asset.id` — ikisi de
`SNMPClient.poll_asset`'in aynı imzasını kullanıyor, kod tekrarlanmadı.

**`target_host` davranışı — kullanıcının "ÇOK ÖNEMLİ" diye vurguladığı
nokta:** Gerçek poll HER ZAMAN `asset["ip_address"]`'e gider —
`profile.target_host` asset'e bağlı poll'da HİÇ okunmaz (yalnızca
profilin kendi bağımsız "Test Connection" akışında kullanılır, bkz.
§10.4). Bu, kod incelemesiyle doğrulandı: `routes/snmp.py` ve `poller.
py` zaten yalnızca `asset["ip_address"]`'i `SNMPClient.poll_asset`'e
geçiriyordu — yani "yanlış cihaza poll gönderme" güvenlik özelliği
YAPISAL olarak zaten garantiliydi, kod değişikliği gerektirmedi. Buna
rağmen UI şeffaflığı için `target_host_matches_asset: bool | None` alanı
eklendi (`AssetSnmpProfileResponse`'ta) — profilin kendi hedefi asset'in
IP'sinden farklıysa `false` (frontend bunu bir UYARI olarak gösterir,
bkz. `assetDetails.snmp.targetMismatchWarning`), aynıysa `true`, DB
satırında `target_host` boşsa (yalnızca API validasyonunu atlayan eski/
elle düzenlenmiş bir kayıtta mümkün — yazma API'sinde `target_host` her
zaman zorunludur) `null`. Bu alan **bloklayıcı bir hata DEĞİL** —
bilinçli bir tercih: bir profilin birden fazla asset'e atanması zaten
tasarımın kendisi, çoğu atamada profilin kendi `target_host`'u
asset'lerin IP'siyle eşleşmeyecektir (bu normaldir), sert bir
validasyon hatası yanlış-pozitif sürtünme yaratırdı.

**`profile_store.py` entegrasyonu — geriye dönük uyumluluk korundu:**
`resolve_profile_for_asset(conn, asset)` yeni tercih edilen giriş
noktası — önce `asset_snmp_profiles` DB atamasını dener (`enabled=
False` ise env fallback'e DÜŞMEDEN doğrudan `None`/`not_configured`
döner — kullanıcının bilinçli devre dışı bırakma tercihine env sessizce
üstün gelmez), atama hiç yoksa (veya `conn` hiç verilmemişse) mevcut
`.env` tabanlı tek-hedef `get_profile_for_asset()` fallback'i AYNEN
korunur (bilinçli olarak kaldırılmadı). DB ataması her zaman env'e
ÖNCELİKLİDİR. `PollingEngine.poll_all` içinde bir GERÇEK bug bulunup
düzeltildi: profil çözümü başlangıçta `asyncio.gather` ile eşzamanlı
denenmişti, ama tek bir `asyncpg.Connection` aynı anda yalnızca bir
sorguyu destekler — birden fazla asset için paralel DB sorgusu `
InterfaceError: another operation is in progress` fırlatıyordu (test
`test_monitoring_returns_not_configured_for_assets_without_profile` bunu
yakaladı). Düzeltme: profil çözümü artık SIRAYLA (DB round-trip'leri
ucuzdur), yalnızca gerçek SNMP ağ poll'ları (`SNMPClient.poll_asset`,
DB'ye dokunmaz) `SNMP_MAX_CONCURRENCY` ile sınırlı eşzamanlılıkla
çalışır.

**Profil silme (409 Conflict):** `DELETE /api/snmp/profiles/{id}`
atanmış asset'i olan bir profili artık **409** ile reddeder
(`SNMPProfileHasAssignmentsError`, mesaj: "This profile is assigned to
one or more assets.") — kullanıcının kendi talimatı. Asset↔Profile
ilişkisi hiçbir zaman sessizce kaskad silinmez; kullanıcı önce
`DELETE /api/assets/{id}/snmp-profile` ile atamaları kaldırmalı. Asset
SİLİNDİĞİNDE ise (`assets` tablosundan) `ON DELETE CASCADE` ilişki
satırını temizler — bu YÖNDE kaskad kasıtlı ve güvenli (silinen bir
asset'in artık hiçbir SNMP ataması anlamlı değildir), profili ETKİLEMEZ.

**Dashboard SNMP Coverage (Faz 29.5):** `lib/monitoringCoverage.ts::
computeMonitoringCoverage(assets, snmpAssignedCount)` artık ikinci,
opsiyonel bir parametre alıyor — `MonitoringCoverage.tsx` bunu `GET
/api/snmp/profiles`'ın döndürdüğü her profilin `assigned_asset_count`
alanının TOPLAMI ile besliyor (tek bir ek API çağrısı, ağır bir grafik
değil — kullanıcının "heavy SNMP graph ekleme" kısıtına uyularak).
Parametre verilmezse (geriye dönük uyumluluk, mevcut testler) hâlâ 0
döner — önceki "SNMP Enabled her zaman 0" davranışı artık yalnızca
gerçekten hiçbir atama yokken doğru, uydurma değil.

## 11. Test izolasyonu — gerçek dev veritabanı testlerle kirletiliyordu (KRİTİK bulgu, düzeltildi)

**Bulgu:** `apps/api/.env`'deki TEK `DATABASE_URL` hem geliştirme hem
test için kullanılıyor (ayrı bir test veritabanı YOK). Birçok API-katmanı
testi (`test_assets_api.py`, `test_scans_api.py`, `test_snmp_api.py`,
`test_monitoring_api.py`, `test_scan_history_integration.py`) kendi
fixture'larında doğrudan `TRUNCATE TABLE assets`/`scans` çalıştırıp
GERÇEKTEN COMMIT ediyordu — yani her `pytest` çalıştırması, o dev
veritabanındaki gerçek discovery verisini (önceki fazlarda "13 gerçek
asset" olarak belgelenen) kalıcı olarak siliyordu. Bu proje boyunca
tekrar tekrar (özellikle bu oturumda çok sayıda `pytest -q` çalıştırması
sırasında) fark edilmeden gerçekleşmiş olması yüksek olasılık — kontrol
anında `assets`/`scans` tabloları 0 satır içeriyordu.

**Kök neden:** `app/db/assets.py`/`app/db/scans.py::get_connection()`
her çağrıda TAZE bir fiziksel bağlantı açıyor (pool/transaction yok);
testler `fastapi.testclient.TestClient` ile route'ları çağırıyor, route
kendi `get_connection()`'ını açıp normal (auto-commit) modda
`TRUNCATE`/insert çalıştırıyor — hiçbir rollback mekanizması yoktu.
(`tests/db/*` katmanı bu sorunu zaten YAŞAMIYORDU — `tests/db/conftest.py
::db_conn` fixture'ı baştan beri transaction+rollback kullanıyordu;
sorun yalnızca API/TestClient katmanındaydı.)

**Düzeltme (`tests/conftest.py`):**
- `isolated_db` fixture'ı — GERÇEK bir `asyncpg` bağlantısı açar,
  `assets`/`scans` şemasını garanti eder, bir transaction başlatır, ve
  `app.routes.{assets,discovery,monitoring,scans,snmp}.get_connection`
  + `app.db.{assets,scans}.get_connection`'ın HEPSİNİ bu TEK paylaşımlı
  bağlantıyı dönecek şekilde patch'ler. Route'ların `finally: await
  conn.close()` çağırması paylaşımlı bağlantıyı erken kapatmasın diye
  `.close()`'u no-op yapan ince bir vekil (`_NoCloseConnection`,
  `asyncpg.Connection.close` slotted/yalnızca-okunur olduğu için
  doğrudan atama yapılamıyor) kullanılır. Test bitince transaction
  ROLLBACK edilir, gerçek bağlantı kapatılır — `TRUNCATE` dahil hiçbir
  şey kalıcı olmaz.
- `client` fixture'ı — `fastapi.testclient.TestClient` YERİNE
  `httpx.AsyncClient` + `ASGITransport`. **Neden gerekli:** `TestClient`
  her isteği ayrı bir arka plan thread'inde (`anyio` blocking portal)
  çalıştırıyor — bu, `isolated_db`'nin asyncpg bağlantısının bağlı
  olduğu event loop'tan FARKLI bir loop demek, ve asyncpg bunu "Future
  attached to a different loop" hatasıyla reddediyor (gerçek testte
  doğrulandı). `httpx.AsyncClient` + `ASGITransport` isteği çağıran
  testin KENDİ event loop'unda çalıştırır — sorun ortadan kalkıyor.
- Etkilenen 5 dosya `isolated_db`/`client` fixture'larını kullanacak
  şekilde güncellendi (`TestClient`/ad-hoc `get_connection()`+
  try/except OSError kalıbı kaldırıldı).

**Doğrulama:** 234 testin TAMAMI (seed+truncate içerenler dahil)
çalıştırıldıktan SONRA gerçek `assets`/`scans` tabloları elle kontrol
edildi — 0/0, öncesiyle aynı (hiçbir kalıcı yazma sızmadı).

**Bilinçli olarak yapılmayan / kullanıcıdan beklenen:** Gerçekten AYRI
bir test veritabanı (ör. `itops_test`) oluşturmak denendi ama `itops`
rolünün `postgres` bakım veritabanına `CONNECT` yetkisi yok
(`InsufficientPrivilegeError`) — bu yüzden `CREATE DATABASE`
çalıştırılamadı. Mevcut `isolated_db` (aynı veritabanında transaction-
rollback) çözümü GÜVENLİ ve yeterli, ama ayrı bir test DB'si daha da
güçlü bir izolasyon sağlardı (ör. paralel test çalıştırmada). Kullanıcı
isterse: (a) `itops` rolüne `CREATEDB` yetkisi verebilir, ya da (b)
`itops_test` veritabanını kendisi oluşturabilir — bu durumda
`conftest.py` ayrı bir veritabanına geçecek şekilde güncellenebilir.
Şu anki çözüm bu olmadan da tamamen güvenlidir, bu yalnızca isteğe
bağlı bir iyileştirme notudur.

**Gerçek veri kaybı için not:** Silinen gerçek discovery verisi
(`10.0.213.0/24` üzerinde daha önce keşfedilen ~13 cihaz) kod/backup
yoluyla geri getirilemez — yalnızca kullanıcı gerçek CIDR'ı vererek
Network Discovery'yi yeniden çalıştırırsa yeniden keşfedilebilir (bu,
kullanıcının açıkça talep etmesi gereken bir ağ taraması eylemidir,
burada otomatik başlatılmadı).

## 12. Agent alt sistemi — dosya yerleşimi, token modeli, bilinen riskler (Faz 28)

**Dosya yerleşimi — kullanıcının önerdiği yapıdan bilinçli sapma:**
Kullanıcının prompt'u `apps/api/app/agents/{models,schemas,repository,
authentication,service,exceptions}.py` önerdi. Bunun yerine HİBRİT bir
yapı kullanıldı: `app/agents/{models,authentication,exceptions,
service}.py` (SNMP alt sisteminin `app/snmp/` deseniyle birebir aynı —
domain/iş mantığı) + `app/db/agents.py` (mevcut `app/db/assets.py`/
`scans.py` ile AYNI dizinde — gerçek DB erişimi). Gerekçe: bu
repository'de "feature package kendi repository.py'sini taşır" deseni
HİÇ yok; tüm DB erişimi tek bir `app/db/` dizininde toplanmış
(CLAUDE.md: "Discovery katmanı, database katmanı ve API katmanı
birbirinden bağımsız test edilebilir kalmalı"). Kullanıcının kendi
talimatı da zaten bu sapmaya izin veriyordu ("mevcut mimariye uymayan
gereksiz abstraction oluşturma"). Ayrıca `schemas.py` oluşturulmadı —
`models.py` hem API request/response hem domain tipini taşıyor (`app/
snmp/models.py`'nin de yaptığı gibi) — API ve domain modelleri arasında
bugün gerçek bir fark yok, ayrı bir dosya erken/gereksiz olurdu.

**Token modeli:** Kayıt anında `secrets.token_urlsafe(32)` (256 bit)
üretilir, PLAINTEXT olarak YALNIZCA `AgentRegistrationResponse`'ta bir
kez döner. DB'de yalnızca SHA-256 hex digest'i (`agents.token_hash`,
UNIQUE) saklanır. **Neden bcrypt/argon2 DEĞİL:** bu algoritmalar düşük
entropili İNSAN parolalarına karşı brute-force'u YAVAŞLATMAK için var;
burada token zaten 256 bit rastgele (2^256 olasılık, insan hafızasında
tutulan bir parola değil) — yavaş hash gereksiz bir CPU maliyeti
getirir, güvenlik kazancı yoktur. Bu, GitHub/GitLab personal-access-
token hash'leme modeliyle aynı yaklaşımdır. `AgentAuthenticationError`
eksik/geçersiz/bilinmeyen/iptal edilmiş token'ların HEPSİNİ aynı 401'e
çevirir — bir saldırganın "bu token formatı geçerli ama agent yok" ile
"token tamamen geçersiz" arasındaki farkı öğrenmesini (enumeration)
önlemek için.

**Registration — kasıtlı olarak "enrollment secret" YOK:** Kullanıcının
otonom-mod kurallarında "Credential gerekiyorsa DUR" maddesi var; bu
fazda kullanıcıdan HİÇBİR ön-paylaşılan sır istenmedi (self-service
registration — herhangi bir agent `POST /api/agents/register`'ı
çağırıp kendi başına bir kimlik alabilir). Bu, MVP/geliştirme için
kabul edilebilir ama production'da açık bir güvenlik açığıdır (rastgele
biri sahte bir "agent" kaydedip veri gönderebilir) — sertleştirme
(paylaşılan bir enrollment/join-code, IP allowlist, admin onayı) Faz
31 — Agent Security'nin kapsamı olarak roadmap'e işlendi, bu fazda
UYGULANMADI.

**`AgentStatus` DB'de SAKLANMAZ:** `online`/`offline`/`unknown` her
zaman `last_heartbeat_at`'ten (+ `AGENT_OFFLINE_THRESHOLD_SECONDS`,
configurable, varsayılan 120s) anlık türetilir — SNMP tarafındaki
"hiçbir zaman uydurma/eskimiş bir durum saklama" ilkesiyle tutarlı
(bkz. `app/snmp/models.py::SNMPPollResult` docstring'i, aynı felsefe).

**`asset_id` HER ZAMAN NULL (Faz 28'de):** `agents.asset_id` sütunu
(nullable FK → `assets(id)` ON DELETE SET NULL) şema-hazırlığı olarak
eklendi ama bu fazda hiçbir kod onu doldurmuyor — güvenilir olmayan bir
hostname/IP eşleştirmesi otomatik yapılmadı (kullanıcının açık talebi:
"Otomatik yanlış eşleştirme yapma"). Gerçek eşleştirme mantığı Faz
29'un kapsamı.

**Bilinen risk — telemetry retention/aggregation:** `agent_telemetry`
yüksek frekanslı (potansiyel olarak dakikada bir, cihaz başına) yazılan
bir tablo — hiçbir retention/downsampling politikası YOK. Gerçek bir
Agent filosu üretime alınmadan önce (Faz 30+) bu tablo sınırsız
büyüyecek. Karar: bu fazda bir cron/retention sistemi ERKEN kurulmadı
(henüz gerçek trafik hacmi yok, erken optimizasyon riski) — Faz 38
(Scheduler) veya ayrı bir "Telemetry Retention" kararı ile ele
alınmalı, üretime geçmeden önce ZORUNLU.

**Test izolasyonu etkisi:** `agents.asset_id`'nin `assets`'e FK
referansı yüzünden düz `TRUNCATE TABLE assets` PostgreSQL tarafından
reddediliyor (`FeatureNotSupportedError`) — etkilenen tüm test
dosyaları `TRUNCATE TABLE assets CASCADE`'e güncellendi (bkz. §11'in
`isolated_db` fixture'ı, davranış aynı kalıyor — hâlâ tamamen rollback
içinde, gerçek veriye etkisi yok).

## 13. Windows/Linux Agent — bağımsız uygulama, veri akışı, güvenlik (Faz 30)

**`apps/agent/` bağımsız bir uygulama, backend'e gömülü DEĞİL:**
Kullanıcının talimatı zaten bunu açıkça istiyordu. Yapı `apps/agent/
agent/{main,config,client,authentication,heartbeat,telemetry,
inventory}.py` + `collectors/{system,cpu,memory,disk,network,
processes,services}.py` + `platform/{windows,linux}.py`. `platform/`
adı stdlib `platform` modülüyle ÇAKIŞMAZ — Python 3'te implicit
relative import kaldırıldığı için `agent/collectors/*.py` içindeki
`import platform` her zaman stdlib'i bulur, `agent.platform`'u değil
(yalnızca `from agent import platform as agent_platform` gibi açık,
nitelikli bir import ile erişilir — bkz. `agent/platform/__init__.py::
resolve()`).

**Tek çalışma zamanı bağımlılığı: `psutil==7.2.2`.** Kontrol edildi:
PyPI'daki en güncel sürüm, BSD-3-Clause (izin verici, projeyle uyumlu),
Python 3.14 ile çalışıyor (gerçek ortamda `pip install` ile doğrulandı).
Gerekçe: CPU/RAM/disk/network/process bilgisi VE Windows Service listesi
(`psutil.win_service_iter()`) için TEK, cross-platform, iyi bakımlı bir
API — bunu stdlib ile (özellikle Windows Service Control Manager
tarafı) yeniden yazmak ciddi bir güvenilirlik riski ve gereksiz kod
hacmi olurdu. **HTTP istemcisi (`client.py`) BİLİNÇLİ olarak `requests`/
`httpx` KULLANMIYOR** — stdlib `urllib.request` bu agent'ın ihtiyaç
duyduğu basit JSON POST/GET'i karşılıyor; dış bağımlılık yüzeyi
`psutil` ile sınırlı tutuldu (kullanıcının "yeni dependency'yi
gerekçelendir" talimatına uyularak).

**Kimlik ve yerel state — self-service registration'ın "ghost agent"
sorunu çözüldü:** `.env`'de `AGENT_ID`/`AGENT_TOKEN` verilmemişse agent
`POST /api/agents/register` ile kendi kendine kaydolur, ama aldığı
kimliği bir YEREL dosyaya (`AGENT_STATE_FILE`, varsayılan
`.itops-agent-state.json`) kalıcı olarak yazar (bkz. `agent/
authentication.py::save_local_state`) — bir sonraki `start` çağrısında
BU dosyadan okunur, yeniden kayıt OLMAZ. Bu olmasaydı her yeniden
başlatma (ör. bir sistem yeniden başlatması sonrası servis restart'ı)
backend'de yeni bir "ghost" agent kaydı biriktirirdi. `authentication.py
::redact_token` token'ı hiçbir log/debug çıktısında tam olarak GÖSTERMEZ
(yalnızca son 4 karakter) — Faz 28'in "token asla plaintext loglanmaz"
ilkesi agent tarafında da aynen uygulandı.

**Retry/backoff — `_Loop` sınıfı (`agent/main.py`):** Heartbeat/
telemetry/inventory ÜÇ BAĞIMSIZ arka plan thread'inde çalışır (asyncio
DEĞİL — basit, üç kısa döngü için yeterli, ek bir event-loop karmaşası
gerekmiyor). Bağlantı hatalarında (`BackendUnavailableError`/
`BackendServerError`) sonlu bir backoff çizelgesi (`2, 5, 10, 30, 60`
saniye, son değerde sabitlenir — SONSUZ agresif retry YOK, kullanıcının
açık talimatı). `BackendAuthenticationError` (401/403 — token iptal
edilmiş) döngüyü TAMAMEN durdurur (tekrar denemek anlamsız, insan
müdahalesi gerekir); `BackendValidationError` (422 — backend payload'ı
reddetti, muhtemelen bir agent-tarafı bug) sonraki normal interval'de
YENİDEN dener (backoff uygulanmaz, bağlantı sorunu değil).

**Offline davranış — kasıtlı olarak basit (MVP):** Backend erişilemezken
kaçırılan telemetry/inventory turları KAYBOLUR — yerel bir disk buffer/
kuyruk YOK. Kullanıcının kendi talimatı bunu açıkça MVP-kabul edilebilir
işaretledi ("kaçırılan telemetry → kaybolabilir, bunu dokümante et").
Offline queue Faz 30'un kapsamı dışında bırakıldı.

**Process collector — command-line KASITLI olarak toplanmıyor:**
`agent/collectors/processes.py` yalnızca PID/isim/CPU%/memory%/
kullanıcı/durum toplar. Birçok uygulama secret/token/parola'yı komut
satırı argümanı olarak geçirir; bunu toplamak agent'ı istemeden bir
credential-harvesting aracına çevirirdi. Süreç listesi CPU/memory'e göre
sıralanıp en yoğun N (`MAX_PROCESSES_REPORTED`, varsayılan 50) ile
sınırlanır — payload boyutu ve DB büyümesi kontrol altında tutulur.

**Network interface tip sınıflandırması — kesin değil, bilgilendirici:**
`agent/collectors/network.py::classify_interface_type` isim tabanlı bir
kalıp eşleştirmesi (ethernet/wifi/loopback/docker/virtual/vpn/other) —
işletim sistemi interface isimlendirmesi standart olmadığı için %100
doğruluk garanti EDİLMEZ, eşleşmeyen bir isim dürüstçe `"other"` kalır
(uydurma bir sınıflandırma yapılmaz).

**Additive backend şema değişiklikleri (migration YOK — JSONB veya
`ADD COLUMN IF NOT EXISTS` ile):**
- `agent_inventory.processes` (yeni JSONB sütun, `ADD COLUMN IF NOT
  EXISTS` ile zaten var olan gerçek/geliştirme veritabanlarını da
  kapsayacak şekilde) — `AgentInventoryRequest.processes: list[
  ProcessInfo] = []`.
- `agents.fqdn` (yeni TEXT sütun, aynı `ADD COLUMN IF NOT EXISTS`
  deseni) — `AgentRegistrationRequest.fqdn`/`AgentSummary.local_ip`/
  `AgentDetail.fqdn` (liste görünümünde agent'ın GERÇEK IP'sini
  göstermek için `local_ip` da `AgentSummary`'ye taşındı — önceden
  yalnızca `AgentDetail`'deydi).
- `NetworkInterfaceSample.addresses`/`.interface_type` (Pydantic
  modeline yeni alanlar — `network_interfaces` zaten JSONB olduğu için
  DB migration'a hiç gerek yok, yalnızca model genişletildi).
Hiçbiri mevcut veriyi SİLMEDİ/DEĞİŞTİRMEDİ, hepsi `DEFAULT`'lu/
opsiyonel — geriye dönük tam uyumlu.

**Windows Service / systemd — kod YAPISAL olarak hazır, KURULUM
yapılmadı:** `python -m agent start` blocking, SIGINT/SIGTERM destekli
— ileride bir Windows Service wrapper'ın (`pywin32`, henüz eklenmedi)
veya systemd'nin (`apps/agent/deploy/systemd/itops-agent.service`,
yalnızca REFERANS dosya) çağırabileceği şekilde tasarlandı. MSI/EXE
installer, code signing, otomatik güncelleme, gerçek `systemctl
enable` — hiçbiri bu fazda yapılmadı (kullanıcının açık kapsam-dışı
listesi).

**SNMP ile karışmama:** SNMP fiziksel/ağ cihazları için (switch/router/
firewall — bkz. §10.5), Agent Windows/Linux işletim sistemi çalışan
makineler için. İkisi aynı `Asset` üzerinde birleşebilir (bir sunucunun
hem bir Agent'ı hem SNMP'si olabilir) ama veri kaynakları/API'leri/DB
tabloları tamamen AYRI kalır — hiçbir noktada birleştirilmedi/
karıştırılmadı. `AssetDetails`'te SNMP ve Agent artık İKİ AYRI sekme.

## 14. Agent Enrollment — self-service registration'ın sertleştirilmesi (Faz 31, kısmi)

**Kapsam — kullanıcının geniş "Faz 30+" master prompt'undan yalnızca
Enrollment/Security kısmı, küçük ve doğrulanabilir bir parça olarak
seçildi.** Kullanıcının prompt'u remote command execution, audit
logging, Windows/Linux'a özgü derin donanım envanteri (WMI/dmidecode),
installer/packaging, offline queue gibi çok daha geniş bir kapsam da
istiyordu — bunlar KASITLI olarak bu increment'e dahil EDİLMEDİ (bkz.
kullanıcının kendi talimatı: "fazları kendin küçük ve doğrulanabilir
parçalara ayır"). Faz 31 numarası zaten roadmap'te "Agent Security"
için ayrılmıştı (bkz. §12/§13) — kullanıcının yeni prompt'undaki "31
Enrollment/Security" isteğiyle birebir örtüştüğü için YENİDEN
NUMARALANDIRMA yapılmadı, mevcut plan aynen kullanıldı.

**Enrollment code — bir credential DEĞİL:** İnsan-okur (`XXX-XXX-XXX`,
karışabilecek karakterler — 0/O, 1/I/L — alfabede YOK), `secrets.
choice()` ile kriptografik olarak rastgele, varsayılan 10 dakika
geçerli, TEK KULLANIMLIKTIR. Tek başına hiçbir kaynağa erişim vermez
— yalnızca "bu kaydı bir insan başlattı" onayıdır; gerçek yetkilendirme
hâlâ kayıt sonrası alınan 256-bit bearer token'da yaşar (Faz 28,
değişmedi). Bu yüzden plaintext saklanması/dönmesi (`GET /api/agents/
enrollment-codes`) SNMP community/agent token modeliyle KARIŞTIRILMAMALI
— o ikisi gerçek secret, bu bir tek-kullanımlık davetiye kodu.

**Atomiklik — "rogue agent" riskine karşı sıra kritik:** `register_agent`
önce kodu ATOMİK olarak tüketir (`UPDATE ... WHERE used_at IS NULL`,
tek bir SQL ifadesi — önce SELECT sonra UPDATE YAPILMAZ, iki eşzamanlı
isteğin aynı kodu tüketmesi yapısal olarak imkansız), SONRA agent'ı
oluşturur, EN SON (yalnızca audit amaçlı, başarısız olsa güvenliği
etkilemez) `used_by_agent_id`'yi bağlar. Ters sırada (önce agent
oluştur, sonra kodu doğrula) geçersiz bir kod agent oluşturulduktan
SONRA reddedilseydi, DB'de sahibi olmayan bir "rogue" agent kaydı
kalırdı — bu tasarım bunu yapısal olarak engelliyor.

**Zorunlu hale getirme — bilinçli bir BREAKING değişiklik (veri değil,
sözleşme):** `AgentRegistrationRequest.enrollment_code` artık ZORUNLU
alan — kodsuz `POST /api/agents/register` artık `422` döner (önceden
serbestti). Bu, Faz 28'in kendi kararında ("self-service registration,
production'da açık bir güvenlik açığı, sertleştirme Faz 31'in kapsamı")
zaten önceden planlanmış, beklenen bir değişiklik — mevcut hiçbir GERÇEK
veriye (zaten kayıtlı agent'lara) dokunmadı, yalnızca YENİ kayıtların
kuralını sıkılaştırdı.

**Additive DB değişikliği:** `agent_enrollment_codes` (yeni tablo,
`code TEXT PRIMARY KEY`, `expires_at`, `used_at`, `used_by_agent_id`
FK → `agents(id) ON DELETE SET NULL` — agent silinirse enrollment
kaydı SİLİNMEZ, yalnızca bağlantısı temizlenir, audit izi korunur).
Mevcut `agents`/`agent_telemetry`/`agent_inventory`/`snmp_profiles`/
`asset_snmp_profiles` şemasına dokunulmadı.

**Secure token storage (Windows Credential Manager/DPAPI, Linux
keyring) — KASITLI olarak bu increment'e dahil EDİLMEDİ:** Kullanıcının
prompt'u (§30.16) bunu istiyordu. Değerlendirildi: `keyring` kütüphanesi
(Apache-2.0, cross-platform — Windows Credential Manager/macOS Keychain/
Linux Secret Service) teknik olarak uygun bir aday, ama (1) bu tek
geliştirme/test ortamı (Windows Server, gerçek bir Linux Secret Service
arka ucu YOK) yalnızca Windows tarafını test edebilir — Linux tarafını
YARIM/doğrulanmamış bırakmak, "gerçek kapasiteyi iddia etme" ilkesine
aykırı olurdu; (2) mevcut yerel-dosya + `chmod 600` (Linux) yöntemi
zaten makul bir taban çizgi sağlıyor. Karar: bu geliştirme YARIM
bırakılmadı, TAMAMEN ERTELENDİ — gerçek bir Linux test ortamı
mevcut olduğunda ayrı bir alt fazda ele alınmalı. `README.md`
"Bilinen Sınırlar" bunu açıkça belirtiyor.

**TLS:** `VERIFY_TLS` varsayılan `true` (Faz 30'dan beri) — bu fazda
DEĞİŞMEDİ, yalnızca `BACKEND_URL` `http://` ile başlıyorsa her
başlatmada GÖRÜNÜR bir uyarı loglanır (`main.py::
_warn_if_insecure_backend`) — SERT bir engelleme değil (yerel
geliştirme ortamı gerçekten HTTP kullanıyor olabilir), yalnızca
bilgilendirme. Global bir sertifika doğrulama kapatma (`verify=False`
benzeri) hiçbir yerde YOK ve eklenmedi (bkz. Faz 30 kararı, §13 —
değişmedi).

**Bilinçli olarak yapılmayan (bu increment'in kapsamı dışı, kullanıcının
kendi "küçük parçalara ayır" talimatına uyularak):** Remote command
execution (allowlist tasarımı dahil), command audit log, Windows Event
Log/Linux journal toplama, kullanıcı/session bilgisi toplama, software
inventory (Faz 30'da zaten ertelenmişti), agent self-update, installer/
packaging (`AgentSetup.exe`), gerçek Windows Credential Manager/DPAPI
entegrasyonu (yukarı bkz.), offline telemetry queue. Bunların hepsi
ayrı, kendi başına doğrulanabilir alt fazlar olarak roadmap'e
eklenmelidir — bu increment'te YAPILMADI.

## 15. Windows Agent Packaging & Web Download (Faz 32)

**Kapsam bilinçli olarak dar tutuldu:** kullanıcının kendi talimatı
("KAPSAMI KÜÇÜK TUT") — yalnızca (1) Windows EXE packaging, (2) backend
üzerinden download, (3) web UI download butonu, (4) version/build
metadata, (5) testler. Remote Command Execution, Audit, Linux
packaging, Windows Service kurulumu, auto-update, OS credential
manager, enrollment güvenlik modelinde değişiklik — HİÇBİRİ bu
increment'e dahil edilmedi (kullanıcının kendi kısıt listesi).

**PyInstaller — dependency değerlendirmesi:** `pyinstaller==6.22.2`,
Python 3.14.7 ile GERÇEKTEN test edildi (bu makinede, bu ortamda) —
sorunsuz çalıştı. Lisans: GPL-2.0-or-later **"bootloader exception"**
ile — derlenmiş bootloader stub'ı istisna kapsamında, PyInstaller'ın
kendisi yalnızca bir BUILD ARACI olarak kullanılıyor (agent'ın çalışma
zamanı bağımlılığı DEĞİL — `apps/agent/requirements.txt`'e değil, ayrı
`packaging/windows/requirements-build.txt`'e eklendi). Bu, PyInstaller
projesinin kendi belgelediği, üçüncü taraf (GPL olmayan) yazılımları
paketlemek için standart kullanım modelidir — agent'ın kendi kaynak
koduna GPL şartı BULAŞMAZ.

**Build ve download BİLİNÇLİ olarak ayrı süreçler:** Backend hiçbir
zaman (başlangıçta veya bir request sırasında) PyInstaller
ÇALIŞTIRMAZ — yalnızca `apps/agent/dist/build-info.json`'ı (build.ps1
tarafından ÖNCEDEN üretilir) okur. `GET /api/agents/download/windows`
bu manifest yoksa veya işaret ettiği EXE dosyası yoksa dürüst bir
`404` döner — hiçbir sahte/placeholder dosya üretilmez.

**Path traversal — yapısal olarak imkansız:** İndirme endpoint'i
kullanıcıdan/istekten HİÇBİR dosya adı/yol PARAMETRESİ almaz — tek
kaynak sunucu tarafındaki sabit `build-info.json` dosyası (bkz. `app/
agents/download.py`). Savunma amaçlı ek katmanlar: (1) dosya adı
regex ile doğrulanır (`^[A-Za-z0-9._-]+\.exe$`, `..`/yol ayırıcı
YASAK), (2) çözülen mutlak yolun gerçekten `dist/` dizini içinde
kaldığı ayrıca doğrulanır. Bu iki katman, `build-info.json`'ın
kendisi manipüle edilse bile (yalnızca sunucu-yerel bir dosya,
kullanıcı erişimi yok) path traversal'ı engeller.

**Versiyon — TEK doğruluk kaynağı:** `apps/agent/agent/__init__.py::
__version__` (zaten Faz 30'dan beri vardı). `.spec` dosyası ve
`build.ps1` versiyonu buradan OKUR, elle tekrar YAZMAZ (bkz.
`apps/agent/tests/test_packaging.py`'deki regresyon testleri — spec/
build script'in versiyon literal'i İÇERMEDİĞİNİ doğrular). Backend de
kendi versiyonunu build-info.json'dan okur — üçüncü bir "backend'in
bildiği versiyon" kaynağı YOK.

**Gerçek build sırasında bulunan ve düzeltilen bir hata — Windows
PowerShell 5.1 BOM sorunu:** İlk `build.ps1` taslağı `Set-Content
-Encoding utf8` kullanıyordu — Windows PowerShell 5.1'de bu, dosyanın
başına bir UTF-8 BOM (byte order mark) EKLER. Python'un `json.loads()`'u
(via `.read_text(encoding="utf-8")`) bunu `Unexpected UTF-8 BOM` hatasıyla
reddediyordu — gerçek bir build+download denemesinde YAKALANDI (mock
testlerle DEĞİL, gerçek EXE build edilip gerçek HTTP isteğiyle
denendiğinde ortaya çıktı). İki katmanlı düzeltme: (1) `build.ps1`
`-Encoding ascii` kullanacak şekilde değiştirildi (içerik zaten saf
ASCII — versiyon/dosya adı/ISO zaman damgası), (2) `app/agents/
download.py` `encoding="utf-8-sig"` ile okuyor (BOM varsa şeffafça
çıkarır, yoksa normal utf-8 gibi davranır) — ikinci bir savunma
katmanı, gelecekte farklı bir araçla üretilen bir `build-info.json`
BOM'lu olsa bile kırılmaz. Regresyon testi: `test_agent_download.py::
test_resolve_artifact_handles_utf8_bom_from_powershell`.

**Gerçek E2E doğrulama (bu increment'te, mock'la YETİNİLMEDİ):** EXE
gerçekten build edildi (`packaging/windows/build.ps1`, 8.9 MB), gerçek
`version`/`inventory` komutlarıyla çalıştırıldı, backend üzerinden
GERÇEK bir HTTP isteğiyle indirildi (indirilen kopya `dist/`'teki
orijinaliyle byte-byte özdeş doğrulandı), İNDİRİLEN kopya (orijinal
`dist/` klasöründen ayrı bir dizine kopyalanmış, kendi başına
çalıştırılan bir kopya) gerçek bir enrollment koduyla (Settings UI'dan
üretilen) gerçek backend'e kaydoldu, aynı kodla ikinci kayıt denemesi
`401 Enrollment code daha önce kullanılmış` ile reddedildi (ikinci
agent OLUŞMADI, `GET /api/agents` tek kayıt gösterdi). Test agent'ı ve
enrollment kodu doğrulama sonrası silindi.

**Console mode (`console=True`) bilinçli tercih:** Agent'ın `.exe`'si
çift tıklandığında bir terminal penceresi AÇAR ve `start` komutunun
canlı loglarını gösterir — gizli/arka planda sessizce çalışan bir
process DEĞİL. Bu, projenin "gizli izleme YOK" ilkesiyle (bkz. Faz 30
kapsam-dışı listesi — keylogger/gizli izleme YASAK) tutarlı bir
şeffaflık tercihi; Windows Service olarak arka planda çalıştırma
(`console=False`/`--windowed`) henüz roadmap'e alınmadı (installer/
service kurulumu gibi, kasıtlı olarak bu fazın dışında).

### 15.1 Bugfix (Faz 32 sonrası) — çift tıklanan EXE anında kapanıyordu

**Bulunan hata (gerçek kullanıcı bildirimi, ekran görüntüsüyle):**
indirilen EXE Explorer'dan çift tıklandığında `itops-agent: error: the
following arguments are required: command` yazıp konsol penceresi
ANINDA kapanıyordu — kullanıcı hatayı okuyamadan. Kök neden: Explorer
çift tıklamada HİÇBİR komut satırı argümanı geçmez, `argparse`'ın
`required=True` alt-komut ayrıştırıcısı argümansız çağrıda hemen hata
verip `SystemExit` fırlatıyor, konsol penceresi process çıkışında
otomatik kapanıyor. Bu, Faz 32'nin kendi "HEDEF AKIŞ"ının ("kullanıcı
EXE'yi çalıştırır → Backend URL + Enrollment Code girer → agent kayıt
olur") hiç implemente edilmemiş bir parçasıydı — `.env` tabanlı
yapılandırma vardı ama interaktif ilk-kurulum istemi hiç yazılmamıştı.

**Düzeltme (`apps/agent/agent/main.py`):** (1) `main()` argümansız
çağrıldığında varsayılan olarak `start` komutuna düşer; (2) frozen
(PyInstaller) + gerçek bir konsolda (`sys.stdin.isatty()`)
çalışıyorken herhangi bir hata/erken çıkışta (`SystemExit` dahil)
pencere kapanmadan önce `input("Devam etmek için Enter'a basın...")`
ile duraklatılır — bu TEK, merkezi bir noktada (`main()`'in kendisi)
yapılır, komutların içine dağıtılmaz; (3) yapılandırma tamamen eksikse
(`.env` yok) frozen+interaktif modda kullanıcıdan DOĞRUDAN Backend URL
+ Enrollment Code istenir ve `.env`'e yazılır (Faz 32'nin asıl
hedeflediği akış, şimdi gerçekten var); yalnızca Enrollment Code
eksikse (Backend URL zaten biliniyorsa) sadece kod istenir. Dev modu
(`python -m agent`) ve otomasyon/CI (frozen değil VEYA interaktif
değil) davranışı DEĞİŞMEDİ — `_pause_before_exit`/`_prompt_for_*`
fonksiyonları bu durumlarda hiçbir şey yapmaz, stdin'i asla bekletmez
(bkz. `test_pause_before_exit_is_noop_when_not_frozen`,
`test_load_config_or_exit_does_not_prompt_when_not_interactive`).

**Kendi kendine yakalanan bir regresyon — çift duraklatma:** İlk
taslakta `_prompt_for_initial_setup()`'ın kendi `except (EOFError,
KeyboardInterrupt)` bloğu HEM kendi içinde `_pause_before_exit()`
çağırıyor HEM `sys.exit(1)` ile çıkıyordu — bu `SystemExit`'i `main()`
zaten yakalayıp AYRICA duraklatıyordu, yani kullanıcı "Enter'a basın"
istemini İKİ KEZ görüyordu. Gerçek EXE'yi (mock değil, `dist/`'teki
gerçek `.exe`) argümansız/boş girdiyle çalıştırarak YAKALANDI, iç
`_pause_before_exit()` çağrısı kaldırılarak düzeltildi — duraklatma
artık yalnızca `main()`'de, tek yerde oluyor
(`test_initial_setup_cancelled_pauses_only_once_via_main`).

**Gerçek EXE ile doğrulanan senaryolar (mock'la YETİNİLMEDİ, `dist/
IT-Operations-Agent-1.0.0.exe` yeniden build edilip gerçekten
çalıştırıldı):** (1) hiç yapılandırma yokken argümansız çalıştırma →
ilk kurulum istemi → iptal → TEK duraklatma; (2) yalnızca
`BACKEND_URL` varken argümansız çalıştırma → doğrudan `start`'a düşüp
yalnızca enrollment kodu istiyor → iptal → TEK duraklatma; (3) tam
yapılandırma var ama backend erişilemezken → kayıt denemesi net bir
hatayla başarısız oluyor, pencere sessizce kapanmıyor; (4) YEREL STATE
DOSYASI (önceden kayıtlı agent) varken argümansız çalıştırma → doğrudan
`start` döngüsüne giriyor, mevcut backoff/retry davranışı (Faz 30)
aynen çalışıyor — bu, gerçek kullanımda en sık karşılaşılacak senaryo
(kurulum bir kez yapıldıktan sonra kullanıcı EXE'yi tekrar tekrar çift
tıklar). Her testten sonra oluşturulan `.env`/`.itops-agent-state.json`
dosyaları silindi, gerçek `assets`/`agents` verisine dokunulmadı (bu
senaryolarda gerçek bir backend'e kayıt hiç denenmedi — yalnızca
kapanmama/duraklatma davranışı doğrulandı).

**Test:** `apps/agent/tests/test_main_interactive.py`'e 1 yeni
regresyon testi eklendi (13→14), agent test suite'i 113→114. Bu fazda
backend/frontend dosyalarına DOKUNULMADI (yalnızca `apps/agent/agent/
main.py` + testler) — enrollment güvenlik modeli (tek kullanımlık/10
dakika/atomik tüketim) DEĞİŞMEDİ.

## 16. SNMP — ilk gerçek cihazda canlı doğrulama, iki bug bulundu (Faz 22'nin bekleyen kısmı)

Kullanıcının kendi Windows PC'sine karşı ilk gerçek SNMP bağlantı
denemesi başarısız oldu. Gerçek nedenler (mock'la değil, canlı Windows
SNMP servisiyle bulundu):

1. **Kullanıcı hatası değil, UX tuzağı:** `LOCAL` profilinin "Community
   String Referansı" alanına gerçek community değeri (`mycommunity`)
   yazılmış — bu alan bir `.env` değişken ADI olmalı
   (`resolve_secret()`, bkz. §10.1). `apps/api/.env`'de hiç SNMP
   community satırı yoktu, secret hep `None` çözülüyordu. Düzeltme:
   `.env`'e `mycommunity=mycommunity` eklendi (referans adı da
   `mycommunity` olduğu için isim=değer çakışması var, kafa
   karıştırıcı ama doğru).
2. **Gerçek kod bug'ı — `ifXTable` fallback hiç çalışmıyordu:**
   `client.py::_get_interface_info` tüm interface kolonlarını (ifTable
   + ifXTable) TEK bir GET'te birleştiriyordu; Windows'un yerleşik SNMP
   servisi `ifXTable`'ı (ifName/ifHCInOctets/ifHCOutOctets) hiç
   desteklemiyor, bu da TÜM PDU'yu `noSuchName` ile başarısız kılıyordu
   — docstring'in vaat ettiği "64-bit yoksa 32-bit'e düş" davranışı hiç
   implemente edilmemişti. Düzeltme: `ifTable` (zorunlu) ve `ifXTable`
   (opsiyonel) artık AYRI GET'ler — ikincisi başarısız olursa yalnızca
   o alanlar `None` kalır, 32-bit `ifInOctets`/`ifOutOctets`'e düşülür,
   tüm interface sorgusu iptal edilmez.

Gerçek doğrulama: `POST /api/snmp/profiles/{id}/test` ile bu makinenin
kendi SNMP servisine karşı — düzeltmeden önce `status=connected` ama
`message`'da 18 tane `noSuchName` hatası, düzeltmeden sonra temiz
`"Bağlantı başarılı."`. `tests/snmp/test_client.py` güncellendi (interface
mock'ları artık 2 ardışık GET simüle ediyor) — backend 378/378 geçiyor.
Ayrıca gerçek DB'de bu oturumun kendi test kayıtlarından kalan 2 süresi
dolmuş `agent_enrollment_codes` satırı (`delete_expired_codes`'ın kendi
tasarımına göre zaten silinmesi gereken, kullanıcının gerçek agent
kaydını etkilemeyen) temizlendi — `test_delete_expired_codes_removes_
only_expired` artık geçiyor.

## 19. Bugfix — Süreç CPU% çok çekirdekli makinede %100'ü aşıyordu

**Gerçek kullanıcı bildirimi** (ekran görüntüsüyle): "Süreçler"
sekmesinde `System Idle Process` `%1124.0` gösteriyordu. Kök neden:
`psutil.Process.cpu_percent()` NORMALİZE EDİLMEMİŞ döner — bir sürecin
BİRDEN FAZLA çekirdek üzerindeki toplam kullanımını (çekirdek başına
%100 üzerinden) toplar, bu yüzden 12 mantıksal çekirdekli, çoğunlukla
boşta bir makinede boşta duran süreç ~1100%'e kadar çıkabiliyordu —
Windows Görev Yöneticisi'nin (her zaman 0-100%) davranışından farklı.

**Düzeltme:** `apps/agent/agent/collectors/processes.py::
_normalize_cpu_percent()` — ham değeri `psutil.cpu_count()`'a böler,
üst sınır 100.0 (zamanlama kaynaklı ölçüm gürültüsüne karşı güvenlik
payı). `cpu_count()` başarısız olursa (nadir) 1'e düşülür — hiç
normalize edilmemiş ham değer göstermekten iyi bir "en kötü durum"
(sayı hâlâ yanlış olabilir ama artık en azından tutarlı bir hataya
düşer, sessizce yanlış bir "düzeltme" UYDURULMAZ).

**Gerçek doğrulama:** EXE yeniden build edilip bu makinede çalıştırıldı,
`refresh_inventory` komutuyla taze bir envanter tetiklendi — `System
Idle Process` artık gerçekten `%88.8` gösteriyor (bu makinenin
12-çekirdek, çoğunlukla boşta durumuyla tutarlı: ~1124/12 ≈ 93.7,
iki poll penceresi arasındaki küçük fark normal). Hem backend'in
sakladığı ham JSON hem web arayüzü ayrı ayrı doğrulandı. Agent test
suite'ine 5 yeni test eklendi (normalizasyon, 100 üst sınırı, `None`
değer, `cpu_count()` hatası fallback'i) — 164→169.
