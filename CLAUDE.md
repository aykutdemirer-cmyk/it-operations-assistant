# IT Operations Assistant — Proje Kuralları

Web tabanlı bir IT altyapı keşif ve yönetim platformu. Detaylı mimari için
`docs/architecture.md`, faz planı için `docs/roadmap.md`, karar
gerekçeleri için `docs/decisions.md` dosyalarına bakın. Bu dosya yalnızca
çalışma kurallarını özetler.

## Proje Amacı

Kurumsal ağdaki cihazları (firewall, router, switch, server, Windows/Linux
host, access point, printer, NAS, IP kamera, IoT, diğer network cihazları)
keşfedip merkezi bir veritabanında tutmak, dashboard üzerinden göstermek
ve ilerleyen fazlarda AI ile sorgulanabilir hale getirmek.

MVP akışı: `CIDR gir → Network Discovery → IP → MAC → Hostname → Vendor →
Open ports → Device type → Database → Web Dashboard`.

## Teknoloji Stack

- **Frontend:** Next.js, React, TypeScript (strict).
- **Backend:** Python, FastAPI.
- **Database:** PostgreSQL, ORM yok (ham SQL/`asyncpg`).
- **Discovery:** Python — ICMP, ARP, TCP, DNS (MVP); SNMP ileri faz.
- **AI:** Claude API (ileri faz).
- **Infrastructure:** Docker (ileri faz, bkz. Faz 10).

## Faz Bazlı Çalışma Yöntemi (ZORUNLU)

Bu proje `docs/roadmap.md` içindeki fazlara göre geliştirilir. Bu, hem
kod kalitesini hem de token/context verimliliğini korumak için zorunludur.

- **Bir seferde yalnızca tek bir fazın kapsamındaki işi yap.** Bir sonraki
  fazın dosyalarına dokunma, onun kodunu yazma.
- Bir faza başlamadan önce `docs/roadmap.md`'de o fazın **amaç, kapsam,
  kapsam dışı, değişecek dosyalar, testler, tamamlanma kriterleri**
  bölümünü oku ve yalnızca orada listelenen dosyalara dokun.
- Kapsam dışı olarak işaretlenmiş bir şeyi fark edersen (eksik özellik,
  refactor fırsatı vb.), onu yapmak yerine not düş ve mevcut faza devam
  et.
- Bir faz tamamlanmadan (testleri geçmeden) bir sonraki faza geçilmez.
- Yeni bir faz gerektiren bir ihtiyaç ortaya çıkarsa, önce
  `docs/roadmap.md`'ye o faz için amaç/kapsam/testler/tamamlanma kriteri
  eklenir, sonra koda geçilir.

## Token / Context Verimliliği

- Bir görev için yalnızca ilgili fazın dosyalarını oku/değiştir;
  tamamlanmış fazların dosyalarına gereksiz yere dokunma.
- Büyük/monolitik dosyalar oluşturma; her modül (özellikle
  `discovery/` altındaki her adım) tek sorumluluk taşır ve ayrı dosyada
  yaşar.
- Gereksiz abstraction, wrapper, generic interface katmanı ekleme
  (örn. genel `Repository<T>` yazma — repository'ler tek tabloya karşılık
  gelir).
- Aynı veriyi birden fazla kez serialize/deserialize etme.
- Backend↔frontend arasında yalnızca gerekli alanları taşı.
- Kısa, gerekçesiz yorum yazma; yalnızca WHY açık değilse yorum ekle.
- Gereksiz dosya oluşturma; bir fazın kapsamında olmayan dosyayı yaratma.

## Geliştirme Kuralları

- Yeni bir discovery adımı eklerken: mevcut adımların arayüzünü takip et
  (belirli bir girdi tipi al, sonucu/`None` döndür, exception ile akışı
  durdurma — bir adımın başarısızlığı diğerlerini engellemez).
- Discovery katmanı, database katmanı ve API katmanı birbirinden
  bağımsız test edilebilir kalmalı; bir katman diğerinin implementasyon
  detayına sızmamalı.
- Frontend, backend'e yalnızca REST API üzerinden konuşur; database'e
  veya discovery katmanına doğrudan erişimi yoktur.
- `AIInsightService` (ileri faz), discovery/aggregator katmanının
  interface'ini implemente etmez; girdisi yalnızca DB'den okunan,
  zaten normalize edilmiş veridir. AI çıktısı kaynak veriyi değiştirmez,
  ayrı ve salt-okunur bir alan/tablodur.
- Mevcut kod tabanının deseni neyse (dosya yapısı, isimlendirme) onu
  takip et; tek başına yeniden yapılandırma yapma.

## Güvenlik Kuralları

- Discovery Engine yalnızca kullanıcının açıkça girdiği CIDR aralığını
  tarar; örtük/otomatik geniş ağ taraması yapılmaz.
- API key, SNMP community string, veritabanı kimlik bilgisi gibi
  sırlar yalnızca backend `.env` dosyasında tutulur; koda, frontend'e,
  loglara veya commit'lere asla yazılmaz.
- Loglarda kimlik bilgisi veya ham kimlik doğrulama verisi bulunmaz.
- Ham socket (ICMP/ARP) gerektiren yetkiler yalnızca backend/discovery
  sürecinde tutulur; frontend'in bu yetkilere hiçbir zaman erişimi
  olmaz.
- Yeni bir dış bağımlılık (kütüphane, API) eklerken güvenlik/lisans
  etkisini göz önünde bulundur; sessizce ekleme.

## Test Kuralları

- **Backend:** `pytest`. Discovery modülleri gerçek ağa bağımlı
  olmadan, mock socket/DNS/ARP yanıtlarıyla test edilir. Gerçek ağda
  manuel doğrulama testlerin yerine geçmez, ona ek yapılır.
- **Frontend:** `vitest` + Testing Library. API çağrıları mock'lanır.
- Yeni bir discovery adımı veya repository fonksiyonu eklerken mutlaka
  bağımsız test yaz; testsiz kod bir sonraki faza taşınmaz.
- Her fazın tamamlanma kriteri, o fazın testlerinin geçmesini içerir
  (bkz. `docs/roadmap.md`).
- **Gerçek PostgreSQL'e bağlı testler ASLA gerçek/kalıcı veriye
  dokunmaz.** Ayrı bir test veritabanı YOK (`itops` rolünün `CREATEDB`
  yetkisi yok) — bunun yerine `apps/api/tests/conftest.py::isolated_db`
  fixture'ı TÜM route `get_connection()` çağrılarını testin sonunda
  ROLLBACK edilen tek bir paylaşımlı transaction'a yönlendirir; aynı
  dosyadaki `client` fixture'ı (`httpx.AsyncClient` + `ASGITransport`,
  `TestClient` DEĞİL — event loop uyuşmazlığı için bkz. `docs/
  decisions.md` §11) bu transaction'la aynı event loop'ta çalışır. Yeni
  bir API-katmanı DB testi yazarken `isolated_db`/`client` fixture'larını
  kullan; kendi `TestClient(app)`/ad-hoc `get_connection()`+`TRUNCATE`
  kalıbını YENİDEN OLUŞTURMA (bkz. `docs/decisions.md` §11 — bu kalıp
  gerçek discovery verisinin silinmesine yol açmıştı).

## Şu Anki Durum

`docs/roadmap.md`'deki Faz 0-9 tamamlandı: CIDR → ICMP → ARP/MAC →
Vendor (OUI) → Reverse DNS → TCP Port Discovery → Device Classification
→ PostgreSQL (tek `assets` tablosu) → `POST /api/discovery/icmp` +
`GET /api/assets` → Web UI akışı uçtan uca çalışıyor ve gerçek
PostgreSQL 16.15 üzerinde doğrulanmış durumda. (Network Discovery ve
Asset Inventory o dönem aynı ana sayfada component olarak gösteriliyordu
— Faz 21'de kendi gerçek route'larına [`/discovery`, `/assets`]
taşındı, bkz. aşağı.) Gerçekleşen mimarinin
detayları için `docs/architecture.md`, faz bazlı ayrıntılar için
`docs/roadmap.md`'ye bakın — implementasyon bazı noktalarda (tek
`assets` tablosu, farklı endpoint isimleri, ayrı sayfa yerine
component'ler) ilk taslaktan kasıtlı olarak sapmıştır; gerekçeler
`docs/roadmap.md`'nin ilgili faz bölümlerinde ve `docs/architecture.md`
§7'de belgelenmiştir.

Faz 10.1 de tamamlandı: `scans` tablosu + `GET /api/scans` (tarama
geçmişi), `/topology` sayfası (gerçek `assets` verisinden device-type
bazlı görsel gruplama — uydurma bağlantı yok), sol sidebar navigasyonu
ve `RecentScans`/`NetworkTopology` component'leri.

Faz 4.4–4.24 de tamamlandı (bkz. `docs/roadmap.md` ilgili bölüm):
dashboard NOC paneline genişletildi (Infrastructure Health, Device
Distribution, Open Ports Overview, Active Alerts), Topology'ye arama/
filtre eklendi, Asset Details sekmelere ayrıldı (Overview/Network/
Discovery/Ports/Monitoring), ve `apps/api/app/snmp/` altında gerçek bir
ajan olmadan SNMP-ready backend mimarisi (OID eşlemesi, veri modelleri,
bant genişliği hesabı, `POST /api/snmp/poll/{asset_id}` — her zaman
dürüstçe `not_configured` döner) kuruldu. Hiçbir noktada CPU/RAM/
sıcaklık/bant genişliği/uptime/SNMP durumu/interface/alert uydurulmadı;
veri yoksa her zaman "Not monitored"/"No data available" gösterilir.

Faz 5 (Dashboard Data Architecture) ve Faz 6 (Advanced NOC Dashboard) de
tamamlandı: `DashboardDataProvider` (paylaşımlı assets/scans context,
tek dashboard yüklemesinde `GET /api/assets` 7'den 1'e düştü) ve
`DeviceHealthSummary`/`MonitoringCoverage`/`NetworkPerformance`
component'leri (bkz. `docs/roadmap.md`). Gerçek bir SNMP ajanı
olmadığından Monitoring Coverage'ta SNMP Enabled her zaman 0, Network
Performance her zaman "No interface monitoring data available."

Faz 7 (Real SNMP Foundation) kullanıcı onayıyla yalnızca mimariye
daraltıldı: `apps/api/app/snmp/credentials.py` (`SNMPProfile`, v2c/v3,
yalnızca credential referansları — gerçek secret değeri yok). Gerçek
bir SNMP kütüphanesi (`pysnmp` vb.) ve `snmp_profiles` DB tablosu henüz
eklenmedi (plan `docs/decisions.md` §10'da) — kullanıcı gerçek bir SNMP
ajanı/cihaz bilgisi verdiğinde ele alınacak.

Faz 20 (Search/Filter/Drilldown) de tamamlandı — SNMP'ye bağlı olmadığı
için Faz 8-19'dan önce sıraya alındı: `GlobalSearch` (tüm sayfalarda,
`TopHeader`'da), `AssetDetails`'e cihaza özel Alerts sekmesi ve
Topology'ye `?ip=` ile derin bağlantı.

Faz 21 (Frontend NOC Platform Dönüşümü) de tamamlandı — yalnızca
frontend: Türkçe (varsayılan) / İngilizce dil desteği
(`apps/web/lib/i18n/`, `localStorage`'da kalıcı, hydration-safe), Dark
(varsayılan) / Light tema seçimi (`apps/web/lib/theme/ThemeProvider.tsx`,
aynı desen), her ana menü öğesi için gerçek route (`/discovery`,
`/assets`, `/topology`, `/scans`, `/alerts`, `/monitoring`, `/settings`
— Dashboard `/` artık yalnızca özet/analitik widget'ları gösteriyor),
Sidebar GENEL/KEŞİF/OPERASYON/SİSTEM gruplarına ayrıldı, yeni
`AlertsList`/`MonitoringOverview`/`SettingsPanel`/`LanguageToggle`
component'leri. `DashboardDataProvider`'ın 7→1 API çağrısı
optimizasyonu ve mevcut GlobalSearch/Topology deep-link davranışı
korundu; hiçbir noktada teknik gerçek veri (IP/MAC/OID/CIDR/SNMP
version) çevrilmedi, hiçbir SNMP/monitoring metni uydurulmadı.

Faz 22 de tamamlandı: 22.1'de ortam keşfi yapıldı (yerelde SNMP ajanı
YOK — Windows SNMP servisi/özelliği kapalı, `.env`'de credential yok;
hiçbir canlı SNMP probe'u gönderilmedi). 22.2'de gerçek bir **SNMPv2c**
client eklendi: `pysnmp==7.1.29` (uyumluluk kontrolünden geçti, lisans
BSD benzeri) — `apps/api/app/snmp/{exceptions,secrets,profile_store,
client}.py`. `secrets.py::resolve_secret()` tek merkezi secret çözümleme
noktası (`.env`'den okur, asla loglanmaz/response'a yazılmaz);
`profile_store.py` kalıcı bir DB tablosu OLMADAN (bilinçli, plan
`docs/decisions.md` §10'da duruyor) `.env`'deki `SNMP_TARGET_*` ile
kullanıcının açıkça verdiği tek bir hedefi çözer. `client.py` System
MIB + Interface MIB (64-bit sayaç tercihli) gerçek poll yapar,
`bandwidth.py`'yi (rollover-safe, ilk poll'da her zaman `None`) aynen
kullanır. `SNMPPollResult.status` artık `not_configured`/`unreachable`/
`timeout`/`authentication_failed`/`success`/`partial` — hiçbiri sahte
`200 success` ile gizlenmez. `POST /api/snmp/poll/{asset_id}` profil
yoksa hâlâ `not_configured`, varsa gerçek poll yapar. SNMPv3 mimarisi
korundu ama implemente edilmedi. 20 mock-transport unit testi + 2 route
entegrasyon testi eklendi (gerçek ağ/cihaz kullanılmadı) — backend
166→188 test. **Gerçek cihazda canlı doğrulama henüz yapılmadı**;
kullanıcı açık bir hedef (IP/VERSION/PORT/CREDENTIAL REF) verene kadar
bekleniyor.

Faz 22.4 de tamamlandı: `apps/api/app/snmp/client.py` artık **SNMPv3**
de destekliyor (`pysnmp.hlapi.v3arch.asyncio` — `SnmpEngine`/
`UsmUserData`/`get_cmd`/`bulk_cmd`), üç güvenlik seviyesiyle
(`noAuthNoPriv`/`authNoPriv`/`authPriv`). Auth: SHA-1 + tam SHA-2 ailesi
(SHA224/256/384/512); Priv: AES (128/192/256-bit). MD5/DES yalnızca eski
ajan uyumluluğu için `Literal` tipinde duruyor, hiçbir yerde varsayılan
değil — `_build_usm_user_data` `authKey`/`authProtocol` ve `privKey`/
`privProtocol`'ü HER ZAMAN birlikte geçiriyor, çünkü pysnmp'nin kendi
`UsmUserData` kurucusu ikisi ayrı verilirse sessizce MD5/DES'e düşüyor
(kaynakta doğrulandı, bkz. `docs/decisions.md` §10.2). MIB parsing kodu
`_Transport` soyutlamasıyla (`_V2cTransport`/`_V3Transport`) v2c/v3
arasında hiç tekrarlanmıyor. `credentials.py::SNMPProfile` artık v3 için
yalnızca `username` zorunlu tutuyor (`security_level` property'si
alanlara göre kendiliğinden hesaplanıyor). `profile_store.py`
`SNMP_TARGET_VERSION=v3` ile tek bir v3 hedefini de çözebiliyor. 30 yeni
test (v3 client 15, `profile_store` 11, `credentials` 4) — backend
188→218 test. **Gerçek cihazda (v2c veya v3) canlı doğrulama henüz
yapılmadı.**

Faz 22.5 de tamamlandı — yalnızca bir mimari KARAR dokümanı
(`docs/decisions.md` §10.3): SNMP profile↔asset ilişkisi (1-1),
credential reference deseni, secret storage (env-tabanlı kalıyor,
secret manager kurulmadı), rotation/deletion/audit gerekçeleri,
`profile_store.py::get_profile_for_asset` imzasının DB-tabanlı bir
implementasyona geçişte kararlı sınır olacağı. **`snmp_profiles`
tablosu kullanıcı onayı olmadan UYGULANMADI** (otonom modun kendi durma
kuralı: yeni kritik DB schema kararı).

Faz 23 de tamamlandı: `apps/api/app/snmp/poller.py` — `PollingEngine.
poll_all(assets)`, `asyncio.Semaphore` ile sınırlı eşzamanlılık
(`SNMP_MAX_CONCURRENCY`, varsayılan 5), bir cihazın hatası diğerlerini
durdurmuyor (ham exception detayı sızdırılmıyor), `asyncio.
CancelledError` hiç yutulmuyor (graceful shutdown). Yeni `PollBatchResult`
mevcut `SNMPPollResult.status` sözleşmesine dokunmadan sarmalıyor. Henüz
hiçbir API route'una bağlı değil (Faz 24'ün kapsamı) ve
`profile_store.py` hâlâ tek-hedef olduğu için pratikte bir batch'te en
fazla 1 asset gerçekten poll ediliyor. 10 yeni test — backend 218→228.

Faz 24 de tamamlandı: `GET /api/monitoring` (`apps/api/app/routes/
monitoring.py`) — tüm asset'leri okuyup `PollingEngine.poll_all` ile
gerçek bir polling turu çalıştırıyor, `PollBatchResult`'ı olduğu gibi
dönüyor. Yeni bir response modeli YOK (`SNMPPollResult` zaten sistem/
uptime/interface/bps/durum/zaman damgasının hepsini taşıyor — duplicate
API'den kaçınıldı). `POST /api/snmp/poll/{asset_id}` (tek-asset, anlık)
İLE bu endpoint (tüm-filo, tek-tur) AYRI kalmaya devam ediyor, ikisi de
aynı `SNMPClient`'ı paylaşıyor. **Frontend `/monitoring` sayfası bu
endpoint'e HENÜZ bağlanmadı** — bilinçli olarak Faz 27/29'a bırakıldı.
5 yeni test — backend 228→233.

Faz 26 de tamamlandı (Faz 25 LLDP/CDP atlandı — gerçek cihaz OID/
response örneği olmadan anlamlı mock yazılamayacağı için, sıra Faz 26'ya
verildi): `lib/alerts.ts`'e 6 yeni SNMP-tabanlı kural eklendi
(`interface_down`/`interface_error`/`high_bandwidth`/
`snmp_poll_failure`/`device_unreachable`/`high_utilization`).
`computeAlerts(assets, messages, options?)` — yeni opsiyonel
`{monitoring, thresholds}`; `monitoring` geçilmezse (bugün hiçbir çağrı
noktası geçmiyor) SNMP kuralları hiç tetiklenmiyor. Tüm eşikler
`lib/alertThresholds.ts`'te merkezi, hardcode yok. `high_latency` artık
iki kademeli (WARNING/CRITICAL). Backend'e `ifInErrors`/`ifOutErrors`
(IF-MIB) eklendi — `interface_error` kuralının gerçek veri kaynağı
(kümülatif sayaç, rate değil). **Hiçbir gerçek çağrı noktası henüz
`GET /api/monitoring`'i çağırıp `monitoring` geçmiyor** — bilinçli
olarak Faz 27/29'a bırakıldı, bu yüzden yeni kurallar canlı uygulamada
şu an hiç tetiklenmiyor (yalnızca testlerde). Backend 234, frontend 193
test (13 yeni frontend + 1 yeni backend).

Faz 27 (kısmi) de tamamlandı — yalnızca `/monitoring` sayfası: `lib/
api.ts`'e `fetchMonitoring()`/`PollBatchResult`, `MonitoringOverview.tsx`
artık mount'ta gerçek `GET /api/monitoring`'i çağırıyor. SNMP Coverage/
Monitored Devices Faz 6'nın heuristiğinden (her zaman %0) gerçek
`total`/`polled` sayılarına geçti. Interface Monitoring/Bandwidth
bölümleri gerçek poll edilen interface'leri (varsa) gösteriyor, yeni bir
**Recent Polls** bölümü eklendi. CPU/Memory HÂLÂ her zaman "veri yok"
(backend hiç poll etmiyor — dürüst bir sınır, eksik değil). Dashboard
(`/`) widget'ları ve `AlertsList`/`AlertsPanel` (Faz 26'nın `monitoring`
parametresi) bu increment'te DEĞİŞMEDİ — bilinçli olarak ayrı bir
increment'e bırakıldı. Frontend 193→194 test.

**Faz 28 — Agent API + Data Model de tamamlandı** (kullanıcının Agent/
NOC master prompt'undaki "Faz 27+" numaralandırması, mevcut Faz 27'yle
çakışmayı önlemek için Faz 28'den başlatıldı — eşleme tablosu
`docs/roadmap.md`'de): `apps/api/app/agents/{models,authentication,
exceptions,service}.py` + `apps/api/app/db/agents.py` (mevcut `app/db/`
deseniyle aynı dizin — kullanıcının önerdiği `app/agents/repository.py`
YERİNE, gerekçe `docs/decisions.md` §12'de) + `apps/api/app/routes/
agents.py`. Endpoint'ler: `POST /api/agents/register` (`{agent_id,
token}`, token yalnızca burada plaintext), `POST /api/agents/heartbeat`
(Bearer auth), `POST /api/agents/{agent_id}/telemetry`+`/inventory`
(Bearer auth + path id'nin token'ın sahibiyle eşleşme kontrolü, aksi
halde 403), `GET /api/agents`+`/{agent_id}`. Token: `secrets.
token_urlsafe(32)`, DB'de yalnızca SHA-256 hash'i (bcrypt/argon2
DEĞİL — gerekçe kararda). Yeni additive tablolar (`agents`/
`agent_telemetry`/`agent_inventory`, `assets`/`scans`'a dokunulmadı):
`AgentStatus` (`online`/`offline`/`unknown`) DB'de SAKLANMAZ,
`last_heartbeat_at`'ten türetilir. `agents.asset_id` şema-hazır ama Faz
28'de HER ZAMAN NULL (güvenilmeyen otomatik eşleştirme yapılmadı, bkz.
Faz 29). Kullanıcıdan bir enrollment secret istenmedi (self-service
registration, sertleştirme Faz 31). **KRİTİK bir yan-etki keşfedildi ve
düzeltildi:** `agents.asset_id`'nin `assets`'e FK referansı yüzünden
mevcut testlerin düz `TRUNCATE TABLE assets`'i PostgreSQL tarafından
reddedildi — etkilenen dosyalar `TRUNCATE ... CASCADE`'e güncellendi
(hâlâ tam rollback-izolasyonlu, gerçek veriye etki yok). 26 yeni test
(auth 8 + API 18) — backend 234→260. Gerçek bir Agent süreci henüz
yazılmadı (Faz 30); frontend `/agents` sayfası da henüz yok (Faz 33+).

Faz 29 de tamamlandı: **Agent↔Asset eşleştirme** (`app/agents/
matching.py::evaluate_asset_match` — hostname/IP/MAC'ten en az 2
bağımsız sinyal olmadan asla `confirmed` sayılmaz; `GET .../asset-match`
yalnızca değerlendirir, `POST .../asset-match` AÇIKÇA onaylanmış bir
eşleşmeyi yazar, otomatik doldurma YOK). **Telemetry retention**
(`AGENT_TELEMETRY_RETENTION_DAYS`, varsayılan 30 gün, idempotent —
henüz bir zamanlayıcıya bağlı değil, Faz 38). **SNMP Configuration
Center** — kalıcı `snmp_profiles` tablosu (additive, `target_host`-
tabanlı, `asset_id` YOK — kasıtlı sapma, `docs/decisions.md` §10.4)
+ tam CRUD API (`GET/POST/PUT/DELETE /api/snmp/profiles`, `POST .../
{id}/test`) + `/settings`'te gerçek bir "SNMP Yapılandırması" bölümü
(profil tablosu, ekle/düzenle/sil, v2c↔v3 alan toggle'ı, secret her
zaman yalnızca `*_ref` isim alanı). "Test Connection" mevcut
`SNMPClient`'ı (değiştirilmeden) kullanarak GERÇEK bir poll dener —
yalnızca kayıtlı, kullanıcının kendi verdiği bir hedefe karşı. v3
polling zaten Faz 22.4'te tamamlanmıştı — bu fazda "v3 henüz
desteklenmiyor" gibi YANLIŞ/dürüst-olmayan bir UI durumu YAZILMADI.
`profile_store.py` bilinçli olarak DEĞİŞTİRİLMEDİ — gerçek asset
polling hâlâ yalnızca `.env` tek-hedefini kullanıyor, `snmp_profiles`
tablosuna henüz bağlı değil (sonraki adım). 48 yeni backend test (260→
308), 11 yeni frontend test (194→205).

Faz 29.5 de tamamlandı: **Asset ↔ SNMP Profile ilişkisi** — yeni
`asset_snmp_profiles` tablosu (additive, `asset_id UUID PRIMARY KEY
REFERENCES assets(id) ON DELETE CASCADE` + `snmp_profile_id UUID NOT
NULL REFERENCES snmp_profiles(id) ON DELETE CASCADE` — bir profil
birden fazla asset'e atanabilir, her asset en fazla bir aktif profile
sahip olabilir; karar `docs/decisions.md` §10.5). Yeni `app/db/
asset_snmp_profiles.py` + `app/snmp/asset_profile_service.py` + `app/
routes/asset_snmp_profiles.py`: `GET/PUT/DELETE /api/assets/{id}/
snmp-profile`, `GET /api/snmp/profiles/{id}/assets`. `profile_store.
py::resolve_profile_for_asset(conn, asset)` artık gerçek entegrasyon
noktası — önce DB ataması, yoksa (veya `conn` verilmezse) `.env`
tek-hedef fallback'i AYNEN korunur (geriye dönük uyumluluk, kaldırılmadı).
`routes/snmp.py` ve `poller.py` buna bağlandı; `PollingEngine.poll_all`
içinde eşzamanlı DB sorgusundan kaynaklanan gerçek bir `asyncpg.
InterfaceError` bug'ı bulunup düzeltildi (profil çözümü artık sırayla,
yalnızca gerçek SNMP ağ poll'ları eşzamanlı). Profil silme artık
atanmış asset'i varsa `409 Conflict` döner (sessiz kaskad YOK). Settings
UI'da "Atanmış Cihazlar" sütunu, `/assets`'te per-device SNMP durumu
(🟢/⚪ + profil adı), `AssetDetails`'e yeni SNMP sekmesi (`AssetSnmpPanel.
tsx` — Durum/Profil/Versiyon/Port/Timeout/Retries/Son Poll, SNMP
Yapılandır/Ata/Kaldır/Şimdi Poll Et), Dashboard'da gerçek "SNMP
Coverage: Configured/Not Configured" sayıları (`computeMonitoringCoverage`
artık gerçek `assigned_asset_count` toplamını kullanıyor, ağır grafik
eklenmedi). Faz 30 Windows/Linux Agent'a KASITLI olarak başlanmadı. 36
yeni backend test (308→344), 17 yeni frontend test (205→222).

Faz 30 de tamamlandı: **Windows/Linux IT Operations Agent** — gerçek,
bağımsız bir Python uygulaması (`apps/agent/`, backend'e gömülü değil).
`agent/{main,config,client,authentication,heartbeat,telemetry,
inventory}.py` + `collectors/{system,cpu,memory,disk,network,processes,
services}.py` + `platform/{windows,linux}.py`. Tek runtime bağımlılığı
`psutil==7.2.2` (Python 3.14 uyumluluğu doğrulandı); HTTP istemcisi
bilinçli olarak `requests`/`httpx` DEĞİL, stdlib `urllib.request`.
Kendi kendine kayıt (`POST /api/agents/register`) sonrası kimliğini
yerel bir dosyaya yazar (yeniden başlatmada tekrar kayıt OLMAZ). Üç
bağımsız thread (heartbeat/telemetry/inventory), bağlantı hatasında
sonlu exponential backoff (2-60s), 401/403'te tam durma. Network
collector interface tipini (ethernet/wifi/loopback/docker/vpn/other)
sınıflandırıyor; process collector command-line'ı KASITLI toplamıyor
(credential riski). Backend'e additive değişiklikler — yeni route YOK,
mevcut Faz 28 endpoint'leri aynen kullanıldı: `AgentInventoryRequest.
processes` (+ `agent_inventory.processes` JSONB, `ADD COLUMN IF NOT
EXISTS`), `agents.fqdn` (aynı desen), `AgentSummary.local_ip`,
`NetworkInterfaceSample.addresses`/`.interface_type` (JSONB, migration
gerekmedi). Frontend: `/agents` + `/agents/[id]` (gerçek route'lar,
8 sekim: Genel Bakış/Sistem/CPU/Bellek/Disk/Ağ/Süreçler/Servisler),
`AssetDetails`'e SNMP'den AYRI bir Agent sekmesi, Dashboard'a Agent
Sağlığı widget'ı, Settings linki güncellendi, Sidebar'a "Agent'lar"
eklendi. Backend 344→349, Agent uygulaması 88 yeni test (`apps/agent &&
pytest`), frontend 222→245. Gerçek backend'e karşı E2E doğrulandı
(gerçek CPU/RAM/disk/network/241 servis/50 process bu makineden
toplanıp gönderildi, sonra test verisi temizlendi — `assets`/`scans`
sayıları değişmedi). Windows Service/systemd kod olarak hazır ama
gerçek kurulum yapılmadı (yalnızca referans `deploy/systemd/
itops-agent.service`). Offline telemetry buffer'ı yok (MVP kararı,
dokümante edildi).

Faz 31 de tamamlandı (kısmi — kullanıcının geniş "Faz 30+" master
prompt'undan yalnızca Enrollment/Security kısmı, bkz. `docs/
decisions.md` §14): **Agent Enrollment**. `POST /api/agents/register`
artık geçerli, süresi dolmamış, tek kullanımlık bir `enrollment_code`
gerektiriyor (kodsuz kayıt `422`, geçersiz/kullanılmış kod `401`) —
Faz 28'in bilinçli olarak açık bıraktığı self-service güvenlik açığı
kapatıldı. Yeni additive tablo `agent_enrollment_codes` + `app/agents/
enrollment.py` (kod üretimi: `XXX-XXX-XXX`, karışabilecek karakter
yok, `secrets.choice`, atomik tek-kullanımlık tüketim — "rogue agent"
riskine karşı kod ÖNCE tüketilir, agent SONRA oluşturulur) + `POST/GET
/api/agents/enrollment-codes`. Agent uygulaması: `ENROLLMENT_CODE` env
değişkeni, `EnrollmentCodeMissingError` ile net hata, `BACKEND_URL
http://` ise görünür (sert olmayan) TLS uyarısı. Frontend:
`AgentEnrollmentPanel.tsx` (Settings > Agent Configuration — "Kod
Üret", canlı geri sayım, aktif kodlar listesi). Windows Credential
Manager/DPAPI + Linux keyring entegrasyonu DEĞERLENDİRİLDİ ama
KASITLI ERTELENDİ (bu ortamda yalnızca Windows tarafı test edilebilir
— yarım bırakmak yerine tamamen erteleme tercih edildi). Backend
349→366, Agent uygulaması 90→92, frontend 245→250. Gerçek E2E: Settings
UI'dan üretilen gerçek bir kodla agent gerçek backend'e kaydoldu, aynı
kod ikinci kez reddedildi (401), test verisi sonra temizlendi.
Kullanıcının geniş prompt'undaki kalan parçalar (Remote Command
Execution + Audit, Windows/Linux derin donanım envanteri, installer/
packaging, offline queue) KASITLI olarak bu increment'e dahil edilmedi
— henüz numaralandırılmamış, ayrı küçük alt fazlar bekliyor.

Faz 32 de tamamlandı: **Agent Packaging & Web Download**. Windows için
PyInstaller ile tek dosya, Python runtime GEREKTİRMEYEN bir `.exe`
(`apps/agent/packaging/windows/{IT-Operations-Agent.spec,build.ps1,
requirements-build.txt}` — versiyon TEK doğruluk kaynağından, `agent/
__init__.py::__version__`, okunur, elle tekrar yazılmaz). Backend
additive: `GET /api/agents/download/windows/info` (gerçek build
metadata'sı) + `GET /api/agents/download/windows` (EXE indirme,
`Content-Disposition: attachment`) — PyInstaller'ı ASLA kendisi
çalıştırmaz (build/download bilinçli olarak ayrı), dosya adı/yol
kullanıcıdan hiç alınmaz (path traversal yapısal olarak imkansız).
Frontend: `AgentDownloadPanel.tsx` — Settings > Agent Configuration'a
"Agent İndir" bölümü (mevcut Enrollment UI'sinin altına, tasarım
bozulmadı). Gerçek bir hata GERÇEK build+download denemesinde
bulunup düzeltildi: Windows PowerShell 5.1'in `Set-Content -Encoding
utf8`'i BOM ekliyordu, Python'un `json.loads()`'unu bozuyordu — iki
katmanlı düzeltme (`build.ps1` artık `-Encoding ascii`, backend
`utf-8-sig` ile okuyor). Backend 366→378, Agent uygulaması 92→100,
frontend 250→254. Gerçek E2E: EXE gerçekten build edildi (8.9 MB),
backend'den GERÇEK bir HTTP isteğiyle indirildi (orijinaliyle
byte-byte özdeş), indirilen kopya Settings UI'dan üretilen gerçek bir
enrollment koduyla gerçek backend'e kaydoldu, aynı kod ikinci kez
401 ile reddedildi, test verisi sonra temizlendi. Remote Command
Execution, Audit, Linux packaging, Windows Service kurulumu, OS
credential manager entegrasyonu KASITLI olarak bu increment'e dahil
edilmedi (kullanıcının kendi kısıt listesi).

Faz 32 sonrası bir bugfix de tamamlandı: gerçek kullanıcı bildirimiyle
("bu şekilde oluyor exe sonra kapanıyor") bulunan bir hata — indirilen
EXE Explorer'dan çift tıklanınca argparse "command required" hatasıyla
ANINDA kapanıyordu (Faz 32'nin kendi hedeflediği "EXE'yi çalıştır →
Backend URL + Enrollment Code gir" akışı hiç implemente edilmemişti).
`apps/agent/agent/main.py` düzeltildi: argümansız çalıştırma artık
`start`'a düşüyor, yapılandırma eksikse frozen+interaktif konsolda
Backend URL + Enrollment Code doğrudan isteniyor, herhangi bir hata/
erken çıkışta pencere duraklatılıyor (dev/CI modunda etkisiz). Gerçek
EXE yeniden build edilip 4 senaryoda gerçekten çalıştırılarak
doğrulandı (bkz. `docs/decisions.md` §15.1). Agent test suite
100→114; backend/frontend'e dokunulmadı, enrollment güvenlik modeli
değişmedi.

Faz 33 de tamamlandı: **Remote Command Execution — Process Kill +
Service Control**. Kullanıcının açık isteğiyle (kullanıcı Node.js
önermişti, mevcut Python stack'e uygunluğu ve Auth/RBAC'sız risk
netleştirilip AskUserQuestion ile onaylandı) additive bir `agent_commands`
tablosu (hem kuyruk hem minimal audit izi — kim/ne zaman/hangi hedefe/
sonuç), backend'de `POST/GET /api/agents/{id}/commands` (auth yok,
bilinen risk) + `GET .../commands/pending`/`POST .../commands/{id}/
result` (Bearer auth, yalnızca Agent). Agent'ta yeni `agent/commands.py`
— OTORİTER blacklist (kritik süreç/servis + agent'ın kendi PID'i,
backend'in bilemeyeceği bir koruma) + gerçek `taskkill`/`kill -9`/`sc`/
`systemctl` çağrıları (her zaman argüman listesiyle, `shell=True` YOK).
Yeni 4. polling thread `ENABLE_REMOTE_COMMANDS` ile varsayılan KAPALI
(opt-in). Frontend: Processes/Services sekmelerine aksiyon butonları,
yeni `ConfirmModal`/`Toast` component'leri, komut sonucu için kısa
client-side polling. Backend 378→394, Agent 114→143, frontend 254→260
test. Gerçek E2E: bu makinenin kendi kayıtlı Agent'ının GERÇEK süreç/
servis listesi görüntülendi, onay modalı gerçek bir PID'le doğrulandı,
GERÇEK bir kill komutu gönderilmeden iptal edildi. Auth/RBAC (Faz 13)
hâlâ yok — bu, kullanıcıya açıkça bildirilip kabul edilmiş bilinen bir
risk (bkz. `docs/decisions.md` §17).

Faz 34 de tamamlandı: **Hızlı Bağlantı (RDP/SSH) + Kullanıcı Oturumu
Takibi**. Agent'a `quser`/`who` çıktısını parse eden bir session
collector eklendi (aktif + son oturum açan kullanıcı). Backend
`GET /api/agents/{id}/connect/rdp` GERÇEK bir `.rdp` dosyası üretip
indiriyor (yalnızca `local_ip`, kimlik bilgisi YOK). SSH ilk halinde
yalnızca komut kopyalama/`ssh://` URI açma dropdown'ıydı (Faz 35'te web
terminaline yükseltildi).

Faz 35 de tamamlandı: **Web SSH Terminal**. `asyncssh` (EPL-2.0)
tabanlı bir WebSocket SSH proxy (`app/agents/ssh_proxy.py`, `app/
routes/agent_ssh.py`) + `xterm.js` tabanlı frontend terminal
(`components/SshTerminal.tsx`, yeni route `/remote-control/ssh/
[agentId]`). Kimlik bilgisi ASLA saklanmaz, her oturumda kullanıcı
girer; `known_hosts=None` bilinçli/belgelenmiş bir sınırlama (TOFU/
host-key pinning yok). Gerçek E2E: geçici bir Windows local hesabı +
OpenSSH server ile doğrulanıp sonra temizlendi. RDP tarafı kasıtlı
olarak `.rdp` indirme olarak KALDI (kullanıcı onayıyla — gerçek bir
Guacamole/guacd altyapısı kurulmadı).

Faz 36 de tamamlandı: **Production UI/UX Yenilemesi**. Agent süreç
tablosunda sütun sıralama + arama + PID-0 "Boşta (Idle)" etiketleme;
Varlık Envanteri'nde port badge'leri (`PortBadges.tsx`, en fazla 3 +
"+X daha" popover, risk'e göre gruplu); Dashboard yeniden tasarımı
(`DashboardSummary.tsx` 9→4 KPI kartı, `InfrastructureHealth.tsx` CSS
conic-gradient donut, `DeviceHealthSummary.tsx` renkli pill etiketler,
2 sütunlu grid layout).

Faz 37 de tamamlandı: **Güç ve Oturum Yönetimi (Power & Session
Control) + Wake-on-LAN**. Faz 33'ün `agent_commands` kuyruğunun doğal
uzantısı — reboot/shutdown/logoff yeni `power_control` komut tipi
(agent OS komutunu 3sn gecikmeyle çalıştırıyor ki kendi sonucunu
backend'e bildirebilsin, `/t 0` ile anında ölmesin). `app/agents/
wol.py` — standart Wake-on-LAN magic packet, `POST /api/agents/{id}/
wake` agent'ın kendisiyle HİÇ konuşmadan DB'deki MAC'e UDP broadcast
gönderiyor (agent çevrimdışıyken de çalışır). Frontend: `AgentDetailView`
header'ına kırmızı "Güç Seçenekleri" dropdown'u. Reboot/shutdown/logoff
GERÇEKTEN bu makinede tetiklenmedi (yalnızca onay modalı + mock test ile
doğrulandı); Wake-on-LAN güvenle gerçek test edildi.

Faz 38 de tamamlandı: **Network Topology — İnteraktif Graph Görünümü**.
`/topology`'nin statik grid'i `@xyflow/react` (React Flow, MIT) tabanlı
interaktif bir graph'a dönüştürüldü — gerçek `ip_address`'ten türetilen
subnet'e göre merkezi hub + dairesel (radial) düzen, sürükle/mouse-wheel
zoom/Fit View React Flow'un kendi `Controls`'undan. Kırmızı "BİLİNMİYOR"
işaretleri kaldırıldı, cihaz tipine göre nötr SVG ikonlar
(`lib/deviceIcons.tsx`) + çevrimiçi cihazlarda yeşil glow/durum noktası.
Bir düğüme tıklayınca mevcut `AssetDetails` sağ drawer'ı açılıyor
(zaten Faz 20/29.5'ten Sheet'ti); Agent sekmesine (`AssetAgentPanel.tsx`)
gerçek bir Agent bağlıysa RDP/SSH hızlı bağlantı butonları eklendi
(`AgentDetailView.tsx`'teki aynı desen). Üst metrik kartları
kompaktlaştırıldı, "Bağlantılar" artık gerçek aktif kenar sayısını
gösteriyor (uydurma sabit DEĞİL). Kenar çizgileri hâlâ subnet/gateway
ilişkisinden türetiliyor — gerçek Layer-2/kablolama verisi DEĞİL (Faz 25
LLDP/CDP hâlâ ertelenmiş), bu `connectionsNote` metninde açıkça
belirtiliyor. Yalnızca frontend değişikliği, backend/agent'a
dokunulmadı. Frontend 292/292 test.

Faz 10 (Docker) ve kalan ileri fazlar (Faz 25 LLDP/CDP gerçek
implementasyon, Faz 27'nin geri kalanı [Dashboard widget'ları, Alert
bağlama], Remote Command Execution + Audit'in geri kalanı
(numaralandırılmamış), Linux Agent packaging, gerçek Windows Service
kurulumu, periyodik/zamanlanmış SNMP poll döngüsü (numaralandırılmamış),
AI, insan kullanıcı Auth/RBAC, zamanlanmış tarama, genel audit log)
henüz başlanmadı.
