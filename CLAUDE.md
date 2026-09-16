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

Faz 39 de tamamlandı: **SNMP Auto-Assign, Arka Plan Polling Worker'ı,
CPU/Bellek (HOST-RESOURCES-MIB) ve İzleme/Dashboard Canlı Telemetri
Yenilemesi**. Bir SNMP profili kaydedilince/test edilince `target_host`
bir asset IP'siyle eşleşiyorsa otomatik atanıyor (elle atama ASLA
üzerine yazılmaz). `app/snmp/scheduler.py` — FastAPI lifespan'da
başlayan, periyodik (varsayılan 30sn) arka plan polling worker'ı,
sonucu `monitoring_cache.py`'ye (süreç-içi) yazıyor. CPU/Bellek artık
HOST-RESOURCES-MIB destekleyen cihazlarda GERÇEK okunuyor (desteklemeyen
çoğu switch/router/firewall'da dürüstçe `None`, poll status'unu
etkilemiyor). `GET /api/health/snmp` artık gerçek durumu yansıtıyor,
yeni `GET /api/monitoring/history` (poll tetiklemez, yalnızca önbellek
okur). "İzleme" sayfası tamamen yenilendi: KPI bar + Recharts bant
genişliği grafiği + arayüz tablosu + poll log akışı, 7sn'de bir sessiz
auto-refresh. Dashboard KPI kartları artık `/assets`'e filtrelenmiş
hızlı bağlantılar + tooltip + Yenile butonu taşıyor, sol/sağ kolon 2/3-
1/3'e ayarlandı, `DashboardDataProvider` 8sn'de bir sessizce (layout
sıçraması olmadan) kendini yeniliyor. Backend 443→469, frontend
294→304 test. Yan bulgular (kapsam dışı bırakıldı, ayrı görevlere not
düşüldü): `delete_expired_codes`'ın süresi dolmamış kodları da silmesi
ve birçok route'un her istekte `ensure_schema()` (DDL) çalıştırmasının
eşzamanlı yükte gerçek bir Postgres deadlock'ı üretmesi (canlı
doğrulandı).

Faz 40 de tamamlandı: **Agent Windows Servisi / systemd Otomasyonu**.
`agent/scripts/install_windows_service.ps1`/`uninstall_windows_
service.ps1` (Service Name `ITOpsAgent`, Automatic başlangıç, `sc.exe
create`/`start`/`stop`/`delete`) ve `install_linux_service.sh`/
`uninstall_linux_service.sh` (`Restart=always`/`RestartSec=5`,
`/opt/itops-agent`, `systemctl enable/start`). **Kritik bulgu (gerçek
testle keşfedildi):** düz `sc.exe create` + ham konsol EXE'si Windows
SCM protokolünü implemente etmediği için `sc start` başarısız oluyor
VE `sc stop` gerçek bir graceful-shutdown sinyali göndermiyor (SCM
timeout'ta sert kesiyor) — bu yüzden yeni `agent/winservice.py`
(`pywin32`, yalnızca Windows build-time bağımlılığı) eklendi, `SvcStop`
mevcut `AgentRuntime.stop()` yolunu çağırıyor. Ayrı bir PyInstaller
spec'i + `build_service.ps1` (sabit çıktı adı `dist/itops-agent.exe`).
`start` komutu artık konsola ek olarak boyut sınırlı (rotating) bir
dosyaya da logluyor (`AGENT_LOG_FILE`). Agent 184→207 test (yeni
regresyon testi: hiçbir `.ps1` `Write-*` satırı em/en dash içeremez —
gerçek bir sözdizimi hatası bu şekilde bulunup düzeltildi, BOM'suz
`.ps1` + PowerShell 5.1 + em dash'in UTF-8 baytları cp1252'de bir
"akıllı tırnak"a denk gelip string'i erken sonlandırıyordu). **Gerçek
E2E (Windows, bu makinede, Administrator yetkisiyle):** servis
gerçekten kaydedildi, RUNNING oldu, gerçek enrollment koduyla backend'e
kayıt oldu, heartbeat/telemetry/inventory gönderdi, `sc stop` GERÇEKTEN
graceful durdurdu (log kanıtlı), `sc delete` ile kaldırıldı, test
verisi temizlendi. **Linux tarafı gerçek bir makinede DOĞRULANMADI**
(bu ortamda yok) — yalnızca `bash -n` + mantık incelemesi.

Faz 40 sonrası bir bugfix de tamamlandı — kullanıcı servisi GERÇEKTEN
kalıcı kurmak isteyince (test-kur-kaldır döngüsü değil) YAKALANDI:
Windows SCM bir servisi başlatırken CWD'yi `C:\Windows\System32`
yapıyor, `AGENT_STATE_FILE`'ın eski göreli varsayılanı bu yüzden
System32'ye yazılıyordu (EXE'nin yanına değil) — servis yeniden
kurulunca System32'de kalan eski/geçersiz bir token okunup sessizce
kimlik doğrulama hatası veriyordu. `.env`/`agent.log` için zaten var
olan "frozen EXE'de kendi dizinine çöz" deseni artık state dosyası
için de var (`main.py::_default_state_file_path`, `load_config`'e
yeni `default_state_file` parametresi). Ayrıca `install_windows_
service.ps1`'de build adımının servis durdurulmadan ÖNCE çalıştığı
(çalışan eski süreç EXE'yi kilitlediği için yeniden kurulumun
`Access is denied` ile başarısız olduğu) bir bug daha bulunup adım
sırası düzeltildi. Agent 207→211 test. Bu makinede artık kalıcı,
gerçek bir `ITOpsAgent` servisi RUNNING durumda.

Faz 40 sonrası bir özellik daha eklendi: **Windows Servisi Paketi web
indirmesi** — kullanıcı isteğiyle ("başka bir bilgisayara kurmam için
GUI'ye indirme koy"). `app/agents/download.py` önceden build edilmiş
`itops-agent.exe` + kurulum/kaldırma script'leri + otomatik bir
README.txt'i TEK bir ZIP olarak bellekte paketliyor (`GET /api/agents/
download/windows-service`, mevcut CLI EXE indirmesiyle AYNI "backend
PyInstaller'ı asla çalıştırmaz" ilkesi). `install_windows_service.ps1`
çift modlu: kaynak ağacından çalıştırılırsa build eder, indirilen bir
ZIP'ten (EXE script'in yanında) çalıştırılırsa build adımını atlar —
hedef bilgisayarda Python gerekmez. Settings'e yeni bir "Windows
Servisi Paketi" indirme bölümü eklendi. Backend 469→477, frontend
304→307 test. Gerçek E2E: canlı backend'den gerçek bir ZIP indirilip
içindeki dosyaların gerçek disk dosyalarıyla bayt-bayt özdeş olduğu
doğrulandı.

Faz 41 de tamamlandı: **Agent Lifecycle Management** — kullanıcı
isteğiyle ("Agent'lar sayfasına ve backend altyapısına tam yaşam
döngüsü yönetimi, uzaktan sürüm güncelleme ve otomatik temizleme
mekanizmaları ekle"). Kullanıcının önerdiği ayrı `archived_agents`
tablosu YERİNE (bilinçli sapma), mevcut `agents`'a soft-delete
kolonları eklendi (`archived_at`/`archived_reason`/`archived_after_
inactive_days`) — `agent_telemetry`/`agent_inventory`/`agent_commands`
FK geçmişini kaybetmeden korur, arşivleme mevcut `revoked_at`
mekanizmasını (Faz 28) da doldurarak ek kod olmadan kimlik doğrulamayı
kapatır. Yeni `agent_retention_policy` (tek satır config) + `app/
agents/scheduler.py` (arka plan worker, `AGENT_MAINTENANCE_ENABLED`
varsayılan açık ama GERÇEK arşivleme yalnızca DB politikası
`enabled=true`'yken — `ENABLE_REMOTE_COMMANDS` ile AYNI iki-anahtarlı
opt-in ilkesi; Faz 29'dan beri bağlı olmayan `cleanup_expired_
telemetry`'yi de devreye aldı). Yeni route'lar: `DELETE /api/agents/
{id}` (opsiyonel uninstall komutu), `POST .../restore`, `GET .../
archived`, `GET`/`PUT .../retention-policy`, `POST .../update`
(`update_self` komutu — mevcut Faz 33 `agent_commands` kuyruğu AYNEN
reuse edildi). `AgentSummary.update_available`/`latest_available_
version` sunucudaki GERÇEK build'i (`service-build-info.json`)
karşılaştırıyor, yoksa dürüstçe `false`/`null`. **Yan ürün olarak
GERÇEK bir deadlock bug'ı kök nedeninden düzeltildi:** `ensure_schema()`
artık 6 route dosyasında HER İSTEKTE değil, `app/main.py::lifespan`'da
yalnızca BİR KEZ çalışıyor (bu oturumda canlı yükte tekrar tekrar
gerçek `DeadlockDetectedError` gözlemlenmişti). Agent tarafı: yeni
`apps/agent/agent/lifecycle.py` — Windows-ONLY, `uninstall_service()`
(`sc.exe` stop+delete) ve `update_self()` (mevcut Faz 40 ZIP indirmesini
reuse eder, `.exe`'yi çıkarır, DETACHED bir PowerShell yardımcı süreci
ile swap+restart yapar — agent kendi çalışan EXE'sini kendisi
değiştiremez). Frontend: `/agents`'e Aktif/Arşiv sekmeleri
(`ArchivedAgentsList.tsx` — Geri Yükle), `AgentRetentionPolicyPanel.tsx`,
`AgentsList.tsx`'e Sil (mevcut `ConfirmModal` stilleriyle, opsiyonel
uninstall checkbox'ı) + Güncelle butonları + rozet + toplu güncelleme.
Backend 477→508, Agent 211→226, frontend 307→322 test. Gerçek E2E:
canlı backende geçici bir test agent'ı kaydedilip GERÇEK UI'dan
silindi/arşivlendi, Arşiv sekmesinde doğru sebep/süreyle göründü, Geri
Yükle ile geri alındı, sonra temizlendi — gerçek üç agent'a
DOKUNULMADI. `update_self`/`uninstall_service`'in gerçek bir Windows
servisi üzerinde çalıştırılması bu increment'e dahil EDİLMEDİ (yalnızca
mock'lanmış birim testleri) — kullanıcının kalıcı `ITOpsAgent`
servisine karşı canlı bir deneme bilinçli olarak yapılmadı.

Faz 42 de tamamlandı: **Ağ Bağlantı Sorunu Debug/Logging + Windows
Update Tarama Motoru**. Kod tabanında sabit `127.0.0.1`/`localhost`
YOKTU (`BACKEND_URL` zaten zorunlu tek yapılandırma kaynağı) — yeni bir
`SERVER_URL` da EKLENMEDİ, gerçek kök neden bulundu: `BACKEND_URL`
eksikken bir Windows Servisi (konsolsuz) olarak çalışırken hata
`agent.log`'a hiç yazılmıyordu (yalnızca kimsenin görmediği stderr).
`agent/main.py::_log_fatal_config_error()` (yeni, `winservice.py`
tarafından da kullanılıyor) bunu düzeltti. `client.py::heartbeat()`
artık tam `HttpResponse` (status kodu dahil) döner ve `main.py` bunu
açıkça loglar; bağlantı hataları `_categorize_connection_error()` ile
"Connection Refused"/"Timeout"/"DNS çözümlenemedi" gibi açık
kategorilerle loglanıyor, HTTP hataları mesajlarında `HTTP {kod}`
taşıyor. Yeni `agent/collectors/windows_updates.py` — birincil COM
(`Microsoft.Update.Session`, GERÇEKTEN bekleyen güncellemeler), COM
başarısız olursa `Get-CimInstance Win32_QuickFixEngineering`'e düşer
(**kullanıcının önerdiği `Search-WindowsUpdate` DEĞİL** — üçüncü parti
modül gerektirir; yedek yöntem ZATEN KURULMUŞ hotfix'leri döner, farklı
bir anlam — `scan_method` alanında AÇIKÇA ayırt edilir, asla
karıştırılmaz). Yeni additive `agent_windows_updates` tablosu + `POST`/
`GET /api/agents/{id}/updates` (**`/api/v1/...` DEĞİL** — projenin
versiyonsuz URL şemasıyla tutarlı). Frontend'e yeni "Windows
Güncellemeleri" sekmesi, yedek yöntemde kırmızı bir dürüstlük uyarısı
ile. Yan ürün olarak GERÇEK iki bug bulunup düzeltildi: (1)
`tests/conftest.py`'nin `get_connection` patch listesi yeni route
modülünü içermiyordu — gerçek, tekrarlanabilir bir test-izolasyon
deadlock'ına yol açıyordu, düzeltildi; (2) bu oturumun önceki (context-
compaction öncesi) E2E doğrulamasından kalma, GERÇEKTEN açık bırakılmış
`agent_retention_policy.enabled=true` VE iki gerçek agent'ın
(`WIN-G4E9UGRTH8E`, `WIN-27EVDRJ3O31`) arşivlenmiş kalmış olması
keşfedilip hemen düzeltildi (politika kapatıldı, iki agent geri
yüklendi). Agent 250→257, Backend 508→516 test. Gerçek E2E: bu
makinede gerçek bir COM taraması (0 bekleyen güncelleme) çalıştırılıp
canlı backend'e gönderildi/doğrulandı; yedek yöntem senaryosu gerçek
UI'da görüntülenip doğrulandı; test verisi temizlendi.

Faz 42 sonrası bir bugfix de tamamlandı — gerçek kullanıcı bildirimiyle
("başka bir pc'ye agent yüklüyorum GUI'de görmüyorum") bulundu: Windows
Servisi bağlamında `ensure_registered()`'daki HERHANGİ bir istisna
`agent.log`'a hiç yazılmıyordu (thread'in excepthook'u yalnızca
stderr'e yazıyordu). `AgentRuntime.start()` artık hatayı loglayıp
yeniden fırlatıyor, `winservice.py`'nin runtime thread'i de savunma
amaçlı ikinci bir katmanla sarmalandı. Gerçek `ITOpsAgent` servisi bu
düzeltmeyle yeniden build edilip başlatıldı. Agent 257→260 test.

Faz 43 de tamamlandı: **Windows Update Tarama Motoruna Anlık Tarama**
— "Windows Güncellemeleri" sekmesine "🔄 Güncellemeleri Kontrol Et"
butonu. Kullanıcının "mevcut komut kuyruğunu bozma" talimatına uyularak
yeni bir endpoint yerine mevcut `agent_commands` kuyruğu genişletildi:
yeni `check_updates`/`scan` komut tipi, `refresh_inventory` ile AYNI
"OS-dispatcher'dan geçmeyen özel komut" deseni. Buton tıklanınca
`submitAgentCommand`+`pollAgentCommand` ile komut kuyruğa alınır,
"Windows Update servisi sorgulanıyor..." bildirimi gösterilir, komut
tamamlanınca tablo ve "Tarama Zamanı" otomatik tazelenir. Agent 260→263,
Backend 517 test. Gerçek E2E: gerçek bir agent süreciyle UI'dan tetiklenen
GERÇEK bir COM taraması bu makinede o an bekleyen gerçek bir Windows
Defender güncellemesini (KB2267602) buldu, arayüz otomatik güncellendi.
Gerçek `ITOpsAgent` servisi bu değişiklikle de yeniden build edilip
güvenle yeniden başlatıldı.

Faz 44 de tamamlandı: **Windows Update Yükleme Tetikleme + KB Detay/
Bağlantı**. Canlı yüzde ilerleme (`%XX`) KASITLI UYGULANMADI — COM'un
gerçek zamanlı ilerleme için event sink gerektirmesi mevcut poll-
tabanlı komut mimarisiyle uyuşmuyor, uydurma bir yüzde göstermek
"gerçek veri" ilkesini ihlal ederdi; bunun yerine dürüst, ayrık
durumlar ("Yükleniyor..." → gerçek başarı/başarısızlık) kullanıldı.
Mevcut `agent_commands` kuyruğu (yeni endpoint AÇILMADI) yeni
`install_update`/`install` komutuyla genişletildi — `agent/collectors/
windows_updates.py::install_updates()` YALNIZCA COM üzerinden
(Search→AcceptEula→Download→Install) gerçek yükleme yapar, yedek
PowerShell yolu yükleme YAPAMAZ. Yeni `reboot_required` alanı HER
taramada `Microsoft.Update.SystemInfo().RebootRequired` ile TAZE
sorgulanır (kendi bayrağımızı tutmak yerine); `true` ise UI'da kırmızı
banner + mevcut `power_control`/reboot komutuna (Faz 37, yeni mekanizma
DEĞİL) tek tıkla kısayol. KB numarası artık Microsoft Support'a
tıklanabilir bağlantı, başlığa tıklanınca COM'dan gelen gerçek
`description` (Faz 42'den, yeni veri YOK) accordion ile açılıyor.
Yükleme butonları yalnızca `scan_method==="com"` iken gösterilir.
Agent 282, Backend 521, Frontend 339 test. Gerçek E2E (dikkatli/
güvenli): var olmayan bir KB hedefiyle gerçek bir `install_update`
komutu gönderildi, gerçek COM `Search()` uçtan uca çalıştı (~70sn)
ama hiçbir şey indirilmedi/yüklenmedi, dürüstçe "eşleşme bulunamadı"
döndü — tam bir gerçek kurulum (paylaşımlı makinede gerçek bant
genişliği/disk tüketimi + geri dönüşü olmayan sistem değişikliği
anlamına gelirdi) KASITLI denenmedi, bu yol kapsamlı mock'lanmış
testlerle doğrulandı. Gerçek `ITOpsAgent` servisi yeniden build edilip
güvenle yeniden başlatıldı. **Not:** bu increment sırasında test
agent kayıtları GERÇEK kullanıcının panelinde göründüğü için kullanıcı
tarafından iki kez yanlışlıkla gerçek iki agent (`WIN-G4E9UGRTH8E`,
`WIN-27EVDRJ3O31`) ile birlikte silinmiş/arşivlenmiş bulundu, her
ikisinde de hemen `restore` edildi — paylaşımlı canlı ortamda test
agent'ı riskinin bir kaydı.

Faz 45 de tamamlandı: **SNMP Verisinin Gerçekten Ekrana Gelmesi** —
kullanıcı bildirimiyle ("bağlı görüyor ama hiçbir veri gelmiyor")
bulunup düzeltilen İKİ AYRI, gerçek üretim hatası. (1) ICMP'yi
engelleyen SNMP-only cihazlar (kullanıcının GERÇEK FortiGate'i)
Network Discovery ile HİÇBİR ZAMAN asset olmuyordu — SNMP profili
"Bağlandı" gösterse bile arkasında asset olmadığı için poller hiç
görmüyordu. `_auto_assign_if_ip_matches` artık `test_connection`'ın
GERÇEK başarı kanıtıyla (sysName/sysDescr + profil adından çıkarılan
device_type) yeni bir asset oluşturup atıyor — `create_profile`/
`replace_profile` (canlı poll yapmadıkları için) hâlâ asset UYDURMUYOR.
(2) DAHA DERİN, sistemik bir hata: `assets.ip_address` (INET) asyncpg'de
`str` değil `ipaddress.IPv4Address` NESNESİ olarak gelir — `poller.py`/
`routes/snmp.py` bunu `str()` OLMADAN pysnmp'ye geçiriyordu, gerçek
bir `TypeError` ile çöküyordu; bu, DB'ye bağlı HİÇBİR asset'in ŞİMDİYE
KADAR gerçekten poll edilememiş olduğu anlamına geliyordu (yalnızca
`.env` tek-hedef fallback'i çalışıyordu). Bunu test EDEBİLECEK bir
entegrasyon testi zaten VARDI ama iki AYNI bozuk nesneyi karşılaştırıp
yanlışlıkla geçiyordu — `isinstance(..., str)` eklenerek düzeltildi.
Ayrıca `app/db/snmp_profiles.py::get_connection()`'a (asset'lere
yazabilen yeni kod yolu yüzünden) `assets.py` ile AYNI jsonb codec
kaydı eklendi. Backend 536→542 test. **Gerçek E2E (bu oturumun en
önemli doğrulaması):** kullanıcının GERÇEK FortiGate'i için Test
Connection yeniden çalıştırıldı → gerçek asset oluşup atandı → arka
plan poller'ı GERÇEKTEN poll etti → **59 gerçek arayüz** (kullanıcının
kendi VLAN yapısıyla) canlı Monitoring sayfasında göründü. **Yan not:**
bu turda gerçek production backend'in (`--host 0.0.0.0`, LAN'daki
gerçek agent'ların kullandığı süreç) bu oturumun `preview_start`
(`127.0.0.1`-yalnızca) dev kopyasından AYRI olduğu keşfedildi — her
düzeltme sonrası AYNI komut satırıyla güvenle yeniden başlatıldı.

Faz 46 de tamamlandı: **Ayrıcalıklı Erişim Yönetimi (PAM) + Rol Tabanlı
Yetkilendirme (RBAC)** — kullanıcının açık isteğiyle. Bu projede insan
kullanıcı Auth/RBAC bu faza kadar HİÇ yoktu (`docs/decisions.md` §17) —
kullanıcının "mevcut JWT auth yapısıyla entegre et" talimatı GERÇEKTE
var olmayan bir altyapıyı varsayıyordu; bu faz onu UYDURMADI, gerçek
bir önkoşul olarak inşa etti: `app/auth/*` (bcrypt parola hash'leme +
PyJWT oturum token'ı, ikisi de yeni bağımlılık, lisansları
`requirements.txt`'te belgelendi) + `users` tablosu (`role`:
ADMIN/OPERATOR/VIEWER, RBAC'ın tek doğruluk kaynağı) + `POST /api/
auth/login`/`GET /api/auth/me`. İlk ADMIN, `.env`'deki
`BOOTSTRAP_ADMIN_USERNAME`/`PASSWORD` ile bir kerelik oluşturuluyor
(`app/main.py::_ensure_bootstrap_admin`). **Kasa:** `vault_credentials`
— parola/SSH anahtarı asla düz metin, `cryptography`'nin (Faz 35'ten
beri zaten mevcut bağımlılık — YENİ bir kripto kütüphanesi EKLENMEDİ)
Fernet'i ile şifrelenir (`PAM_VAULT_SECRET_KEY`, `.env`); API
yanıtları her zaman maskeli, gerçek değer yalnızca Admin-only `POST
.../reveal` ile döner. **Erişim kuralları:** `pam_access_rules`
(`user_id`+`asset_id` UNIQUE, `allow_rdp`/`allow_ssh`,
`max_session_duration_mins`, `valid_until`) + `GET /api/pam/my-access`
(OPERATOR/VIEWER yalnızca kendi, süresi dolmamış yetkili sunucularını
görür — `credential_id` bu yanıtta hiç yok). **Denetim:**
`pam_session_logs` + Admin-only `GET /api/pam/audit`. **Zero-Knowledge
SSH (yalnızca SSH, RDP DEĞİL):** mevcut Faz 35 WebSocket SSH proxy'sinin
yanına yeni bir fonksiyon + `WS /api/pam/ssh/{asset_id}` — kullanıcıdan
kimlik bilgisi hiç istenmez, backend PAM kuralını çözüp kasadaki
kimlik bilgisini sunucu tarafında deşifre ederek doğrudan `asyncssh`'e
geçirir, tarayıcıya kimlik bilgisi DEĞERİ hiç ulaşmaz; JWT (tarayıcı
WebSocket API'sinin header sınırlaması yüzünden) query string'de taşınır
— bilinçli, belgelenmiş bir ödünleşim. Faz 35'in mevcut manuel-kimlik-
bilgili SSH akışı AYNEN kalıyor (PAM kuralı olmayanlar için fallback).
**Kasıtlı kapsam dışı:** RDP zero-knowledge (gerçek bir Guacamole/guacd
altyapısı gerektirir, kurulmadı — RDP mevcut `.rdp` indirme akışında
kalıyor), `group_id` bazlı kural ataması (kullanıcı grupları kavramı
hiç yok), ve **uygulama genelinde bir login duvarı** (canlı, aktif
kullanılan bir sistemde riskli bir erişim değişikliği olurdu — yalnızca
`/pam/*` sayfaları+API'leri gerçek auth ile korunuyor, geri kalan tüm
uygulama kasıtlı olarak açık kalmaya devam ediyor). Frontend: `/login`,
`/my-access`, `/pam/{users,vault,rules,audit}`, `/pam/ssh/[assetId]`
(zero-knowledge terminal), Sidebar'da admin-only "PAM / Erişim
Yönetimi" grubu, `TopHeader`'da oturum göstergesi. Backend 542→559,
frontend 339 test (`tsc`/`eslint` temiz). **Gerçek E2E:** kullanıcı
onayıyla canlı production backend (`--host 0.0.0.0 --port 8000`)
yeniden başlatıldı — yeni şema otomatik kuruldu, gerçek bootstrap
ADMIN hesabı oluştu, gerçek bir login GERÇEK bir JWT döndürdü, o
token'la `GET /api/pam/users` GERÇEKTEN çalıştı; restart sırasında
gerçek üç agent kesintisiz yeniden bağlandı. PAM zero-knowledge SSH'in
gerçek bir hedefe karşı canlı denemesi (Faz 44'ün paylaşımlı-ortam
temkinliliğiyle tutarlı olarak) bu increment'e dahil edilmedi.

Faz 47 de tamamlandı: **Dinamik RBAC (İnce Taneli İzinler) + Cihaz
Bazlı PAM Yetkilendirme + Uygulama Genelinde Route Guard** —
kullanıcının açık isteğiyle, Faz 46'nın kaba `role`-tabanlı RBAC'ını ve
"yalnızca `/pam/*` korunuyor" sınırını bilinçli olarak genişletti/
değiştirdi. Yeni `user_permissions` tablosu + kod-içi sabit katalog
(`app/auth/permissions.py::ALL_PERMISSIONS` — 9 `*_VIEW` izni +
`PAM_ADMIN` + `PAM_ACCESS`) — kullanıcının açık örneği ("yalnızca
`PAM_ACCESS`'i olan biri Dashboard dahil hiçbir menüyü göremesin") artık
gerçekten mümkün: her kullanıcının izin seti rolünden BAĞIMSIZ olarak
admin panelinden (`UserPermissionsModal.tsx`) tamamen özelleştirilebilir.
`permissions` HER İSTEKTE DB'den taze okunur (JWT'de saklanmaz) — bir
izin geri alınınca kullanıcının geçerli token'ı bunu hemen yansıtır.
Backend `require_permission(*any_of)` tüm `/api/pam/*` route'larını
korumaya aldı (`require_role("ADMIN")`'in yerini aldı); `my-access`/
PAM SSH artık `PAM_ACCESS` + asset-bazlı `pam_access_rules` kuralının
İKİSİNİ birden gerektiriyor. **Uygulama genelinde route guard:**
Faz 46'nın "yalnızca PAM korunuyor" kararı GENİŞLETİLDİ — artık HER
sayfa `RequirePermission.tsx` ile sarmalı, giriş yapılmamışsa `/login`'e
yönlendirir, izin yoksa (menüde görünmeyen bir URL elle yazılsa bile)
dürüst bir 403 gösterir; `Sidebar.tsx` artık statik değil, her öğe
`currentUser.permissions`'a göre dinamik filtreleniyor. **Bilinçli
kapsam sınırı korunuyor:** bu guard yalnızca FRONTEND'de — genel
sayfaların backend API'lerine (`/api/assets`, `/api/discovery`, ...)
auth EKLENMEDİ, yalnızca PAM API'leri gerçek backend yetkilendirmesine
sahip (onlarca route'a canlı sistemde tek seferde auth retrofit etmek
ayrı, çok daha büyük ve riskli bir iş). **Cihaz bazlı yetkilendirme
matrisi:** yeni `/pam/users/{id}` sayfası (`UserDeviceAccessPanel.tsx`)
— her asset için ayrı RDP/SSH checkbox'ı + kasa hesabı seçimi +
opsiyonel süre; yeni bir "batch" API EKLENMEDİ, mevcut Faz 46
`pam_access_rules` CRUD'u doğrudan kullanılıyor. **RDP — kısmi
zero-knowledge:** tam parola-gizleme RDP için hâlâ mümkün DEĞİL (gerçek
Guacamole/guacd gerektirir, Faz 46'da belgelenen sınır yeniden teyit
edildi); yeni `GET /api/pam/rdp/{asset_id}` mevcut Faz 34 `.rdp`
üretimini asset'ten çalıştırıp yalnızca kullanıcı adını ön dolduruyor,
her indirme `pam_session_logs`'a tek satırlık bir denetim kaydı
düşüyor. **Geçiş:** `app/main.py::_ensure_default_permissions_backfill()`
Faz 46'nın bootstrap ADMIN'i dahil hiç izin satırı olmayan her
kullanıcıya rolünün varsayılan iznini bir kerelik atadı — bu OLMADAN
şema geçişi sonrası ADMIN dahil KİMSE giriş yapamazdı, gerçek bir
kilitlenme riskiydi. Backend 559→565, frontend 339→342 test (`tsc`/
`eslint` temiz). **Gerçek E2E:** kullanıcı onayıyla canlı production
backend tekrar yeniden başlatıldı — `user_permissions` şeması otomatik
kuruldu, backfill mevcut bootstrap ADMIN hesabına gerçek varsayılan
izinleri atadı, restart sırasında gerçek agent'lar kesintisiz yeniden
bağlandı.

Faz 48 de tamamlandı — **Gerçek Zero-Knowledge Web RDP (Apache
Guacamole/guacd)**, kod olarak yazılıp SONRA gerçek bir Windows RDP
oturumuna karşı CANLI doğrulandı. Kullanıcının açık isteğiyle Faz
47'nin `.rdp` dosya indirme akışı TAMAMEN KALDIRILDI, yerine gerçek,
istemcisiz (clientless) bir HTML5 RDP oturumu geldi. Kullanıcı Docker/
WSL2'yi kendi ekranından kurdu — bir "Virtualization support not
detected" engeliyle karşılaştı, kök neden bu makinenin KENDİSİNİN bir
VMware sanal makinesi olması (nested virtualization host tarafında
kapalıydı, guest içinden düzeltilemezdi) — kullanıcı vSphere'den
"Expose hardware assisted virtualization"ı açıp çözdü. Gerçek `guacd`
container'ı ayağa kalktıktan sonra GERÇEK bir Windows RDP hedefine
karşı canlı denemelerle **dört ayrı, gerçek üretim hatası** bulunup
düzeltildi (hiçbiri sahte testlerle yakalanamazdı): (1) `security:
"any"` → `"nla"` (modern Windows Server NLA zorunlu tutuyor), (2)
Docker loopback hatası (`127.0.0.1` guacd konteynerinin KENDİSİNİ
işaret ediyordu, host'a değil — `host.docker.internal`'a
yeniden-yazma eklendi), (3) WebSocket subprotocol reddi
(`guacamole-common-js` "guacamole" alt protokolü İSTİYOR,
`websocket.accept()` bunu kabul ETMEYİNCE tarayıcı bağlantıyı kendisi
iptal ediyordu), (4) instruction-sınırı bölünmesi (tarayıcı ayrıştırıcısı
her WS mesajının TAM instruction içerdiğini varsayıyor, ham baytları
rastgele sınırda bölmek "source image could not be decoded"'a ve
guacd'nin bağlantıyı kendisinin kesmesine yol açıyordu — artık
`split_complete_instructions` ile tamponlanıyor). **Gerçek E2E:** guacd
loglarında `RDPDR user logged on` — GERÇEK bir Windows hesabıyla GERÇEK
bir RDP oturumu kimlik doğrulamasını geçip bağlandı. Ardından
kullanıcının isteğiyle `GuacamoleRdpViewer` CyberArk/Teleport tarzı bir
oturum ekranına yeniden tasarlandı (koyu tema, camsı araç çubuğu, PAM
kuralının GERÇEK süresinden geri sayan bir zamanlayıcı — sahte bir
"ping/ms" DEĞERİ hiçbir yerde gösterilmiyor) — kullanıcı Tailwind/
Shadcn istedi ama proje 48 faz boyunca hiç kullanmadığı için (yalnızca
CSS Modules) aynı görsel sonuç mevcut desenle üretildi, yalnızca
`lucide-react` (ikonlar) eklendi. **Backend:** `app/pam/guacamole_protocol.py` Apache
Guacamole'ün uzunluk-önekli metin protokolünü sıfırdan implemente
ediyor (üçüncü parti kütüphane EKLENMEDİ — protokol küçük/tam
belgeli). `app/pam/guacd.py::open_rdp_connection` guacd'ye TCP ile
bağlanıp el sıkışmayı (`select`→`args`→`size`/`audio`/`video`/`image`→
`connect`→`ready`) TAMAMLIYOR — kimlik bilgisi enjeksiyonu TAM OLARAK
`connect` instruction'ında (kasadan çözülmüş gerçek parola, YALNIZCA bu
sunucu-sunucu TCP bağlantısında), tarayıcı bu değeri HİÇBİR ZAMAN
görmüyor. `app/pam/service.py::authorize_rdp_session` artık Faz 47'nin
yalnızca-kullanıcı-adı döndüren haliyle KIYASLA tam kimlik bilgisini
döndürüyor. Yeni bir `pam_active_sessions` tablosu EKLENMEDİ — mevcut
`pam_session_logs` (`ended_at IS NULL` = aktif) zaten aynı ihtiyacı
karşılıyor. **Frontend:** `guacamole-common-js@1.5.0` (Apache-2.0,
resmi TypeScript tipi yok, `any` ile bildirildi) + `components/
GuacamoleRdpViewer.tsx` (`/pam/session/{assetId}` — Canvas ekran +
fare/klavye + Tam Ekran + Ekrana Sığdır + Panoyu Gönder). **Test
stratejisi (guacd olmadan):** `tests/pam/test_guacd_handshake.py`
GERÇEK guacd yerine el sıkışma sırasını taklit eden sahte bir asyncio
TCP sunucusuna karşı TAM el sıkışmayı VE kimlik bilgisi enjeksiyonunun
doğru sırada/değerde olduğunu doğruluyor — protokol katmanının
doğruluğu gerçekten test edildi; GERÇEK guacd/RDP sunucusu üçlüsüne
karşı canlı deneme SONRADAN yapıldı (yukarıya bkz. — dört gerçek hata
bulundu/düzeltildi, gerçek RDP oturumu doğrulandı). Backend 565→577
test (12 yeni), frontend 342 (değişmedi — `GuacamoleRdpViewer`
component testi kapsam dışı bırakıldı, gerçek DOM canvas+WebSocket+
3.parti kütüphane mock'lamak ayrı bir iş). `tsc`/`eslint` temiz.
**Yan bulgu:** gerçek kullanıcı bu
oturum sırasında Faz 47'nin `.rdp` indirme akışını GERÇEKTEN kullanmış
(canlı `pam_session_logs`'ta gerçek "Aykut" kullanıcısının WIN-
G4E9UGRTH8E'ye 2 gerçek RDP dosya indirmesi bulundu) — bu, PAM
sistemine artık gerçek, boş-olmayan canlı veri olduğu anlamına
geliyor; bir test (`test_audit_log_empty_when_no_sessions`) bunun
üzerine güncellendi (artık global listenin boş olduğunu DEĞİL, YENİ
oluşturulan bir kullanıcının kayıtlarda GÖRÜNMEDİĞİNİ doğruluyor).

Faz 49 de tamamlandı: **LDAP / Active Directory Entegrasyonu**. Ayarlar'a
"Active Directory / LDAP" bölümü (host/port/SSL/domain FQDN/base DN/
bind DN/bind parolası, "Bağlantıyı Test Et"/"Şimdi Senkronize Et") +
`app/services/ldap.py` (`ldap3` — `python-ldap` DEĞİL, bu Windows Server
ortamında C derleme zinciri gerektirmediği için tercih edildi) gerçek
LDAP bind/arama yapıp `ad_groups`/`ad_users`/`ad_group_memberships`'i
(yalnızca DOĞRUDAN `memberOf` üyelikleri, nested grup ÇÖZÜMLENMEDİ)
senkronize ediyor. Gece yarısı otomatik senkronizasyon Celery YERİNE
mevcut `app/snmp/scheduler.py` deseniyle (FastAPI lifespan task'ı,
`LDAP_SCHEDULED_SYNC_ENABLED`/`LDAP_SYNC_HOUR`). `pam_access_rules`
artık `user_id` (yerel) VEYA yeni `ad_group_id` (AD grubu) hedefleyebiliyor
(XOR CHECK constraint, aynı asset için doğrudan kural her zaman grup
kuralının önünde) — `/pam/rules` ekranına "Kullanıcı Tipi" seçimi
eklendi. Bir yerel kullanıcı bir AD hesabına `users.ad_username` ile
ELLE bağlanır (`/pam/users`'a satır içi bir alan+buton eklendi,
`PUT /api/pam/users/{id}` artık bunu kabul ediyor) — LDAP ile GİRİŞ
(bind auth) YOK, kullanıcı girişi hâlâ Faz 46'nın yerel bcrypt'i.
LDAP bind parolası YENİ bir şifreleme anahtarı EKLENMEDEN mevcut
`PAM_VAULT_SECRET_KEY` (Fernet) ile şifreleniyor. **Yan ürün olarak
gerçek bir bug bulunup düzeltildi:** `infra/postgres/init.sql`'deki
idempotent `DO $$ ... EXCEPTION WHEN duplicate_object` kalıbı (CHECK
kısıtları için doğru) bir `ADD CONSTRAINT ... UNIQUE` için yetersizdi —
Postgres UNIQUE kısıtı için isimdeş bir destek INDEX de oluşturuyor,
ikinci çalıştırmada bu `duplicate_table` (42P07) ile reddediliyordu
(`duplicate_object`/42710 DEĞİL) — test suite'inin ilk çalıştırmasında
gerçekten yakalandı, ikisini birden yakalayacak şekilde düzeltildi.
Backend 577→606, frontend 342→347 test. Gerçek bir AD sunucusuna karşı
canlı doğrulama henüz yapılmadı — kullanıcı gerçek bağlantı bilgilerini
verdiğinde ele alınacak.

Faz 49 sonrası bir dizi bugfix de tamamlandı — kullanıcının gerçek bir
Active Directory'ye (`lab.local`) karşı canlı testleriyle bulunup
düzeltildi: yalın bir `sAMAccountName` girildiğinde otomatik UPN→NTLM
bind fallback'i (`_bind_candidates`), NTLM'in bu sunucuda MD4 hash
desteği olmaması yüzünden GERÇEKTEN 500'e düşen bir hata (artık
yakalanıp bir sonraki formata geçiliyor), denenen her formatın gerçek
LDAP sonuç açıklamasını (`data 52e` gibi) döndüren detaylı hata
mesajları, IP tabanlı DC'ler için TLS'siz bir TCP ön-kontrolü, ve
frontend'de TÜM 422 doğrulama hatalarını etkileyen gerçek bir
"[object Object]" bug'ı (`detail` bir DİZİ, obje değil). Bind parolası
artık Vault güncellemesiyle aynı ilkeyle boş bırakılırsa KORUNUYOR
(placeholder metni artık doğru). Backend 606→618, frontend 347→353 test.

Faz 50 de tamamlandı: **PAM Oturum Kaydı (Session Recording), Canlı
Oturum Sonlandırma, Tuş Loglama (SSH) ve Video Replay**. Kullanıcının
istediği SQLAlchemy/Celery/`/api/v1/*`/Shadcn UI'nin HİÇBİRİ
kullanılmadı — bu proje 50 faz boyunca hiç ORM/versiyonlu URL/Celery/
Tailwind kullanmadı. RDP oturum kaydı guacd'nin `connect`
instruction'ına `recording-path`/`recording-name` eklenerek guacd'nin
KENDİSİNE `.guac` dosyası yazdırılıyor; oynatma sunucu tarafında bir
ffmpeg/`guacenc` dönüşümü OLMADAN, `guacamole-common-js`'in (zaten
yüklü) `Guacamole.SessionRecording`'iyle TARAYICIDA yapılıyor (Apache
Guacamole'ün kendi resmi web uygulamasının da kullandığı yöntem).
Canlı oturum sonlandırma tek-süreçli bir bellek-içi kayıt defteri
(`app/pam/session_registry.py`) ile — mevcut Faz 48 `asyncio.wait
(FIRST_COMPLETED)` köprüleme desenine üçüncü bir "kill" bekleyicisi
eklendi. `pam_session_logs`'a iki additive kolon (`recording_file_
path`, `terminated_by`) + yeni `pam_keystrokes` (yalnızca SSH) —
paralel bir `pam_sessions` tablosu AÇILMADI. `/pam/audit` artık Canlı
Oturumlar (geçen süre sayacı + anlık kapatma) ve Oturum Geçmişi (video
replay + komut logu) sekmelerine ayrıldı. Backend 618→633, frontend
347→353 test. **Gerçek bir guacd'ye karşı canlı doğrulama henüz
yapılmadı** (Faz 48'in Docker kısıtı burada da geçerli).

Faz 51 de tamamlandı: **PAM Durum Senkronizasyonu, Canlı Oturum İzleme
(Shadowing), WebSocket Heartbeat**. Gerçek bug'ın kök nedeni: `session_
registry.unregister()` her zaman çalışıyordu ama onu izleyen `close_
session_log` DB yazımı başarısız olursa satır DB'de sonsuza kadar
"aktif" görünebilirdi — `GET /api/pam/audit?active=true` artık DB'yi
`session_registry`'ye karşı ÇAPRAZ KONTROL ediyor (kendi kendini
düzeltir), yeni bir `/api/v1/...` endpoint'i AÇILMADI. WebSocket
heartbeat uygulama-seviyesinde DEĞİL (RDP kanalı ham Guacamole
protokolü taşıyor, özel bir ping mesajı tarayıcı ayrıştırıcısını
bozardı) — uvicorn'un native `--ws-ping-interval`/`--ws-ping-timeout`
bayraklarıyla (`.claude/launch.json`) çözüldü. Canlı Oturum İzleme
(`👁️ Canlı İzle`) gerçek Guacamole "join" paylaşım protokolünü
KULLANAMADI (o, bu projenin Faz 48'de kasıtlı eklemediği resmi
`guacamole-client` Java web uygulamasının bir özelliği) — bunun yerine
`session_registry`'ye salt-okunur bir pub/sub eklenip birincil
oturumun guacd çıktısı izleyicilere de yayınlanıyor; Oturum Kaydı
etkinse katılma anında `.guac` dosyasından "yakalama" (catch-up)
yapılıyor, değilse izleyici yalnızca katıldığı andan itibaren gelen
güncellemeleri görüyor (dürüstçe belgelenen bir sınır). Backend
633→639, frontend 353→354 test. **Gerçek bir guacd'ye karşı canlı
doğrulama henüz yapılmadı.**

Faz 52 de tamamlandı: **LDAP Bind-Auth Girişi (opt-in) + "Kullanıcılar &
Yetkiler" Ekranına AD Kullanıcı İçe Aktarma**. Faz 49'un "gerçek LDAP
SSO/bind-auth login KASITLI kapsam dışı" kararı kullanıcının açık
isteğiyle tersine çevrildi — ama Faz 33/41'in `ENABLE_REMOTE_COMMANDS`/
`AGENT_MAINTENANCE_ENABLED` deseniyle AYNI iki-anahtarlı opt-in ile:
`LDAP_AUTH_ENABLED` (`.env`, varsayılan `false`) açık olmadan `login()`
LDAP'a hiç düşmez; `LDAP_AUTH_DEFAULT_ROLE` varsayılanı kullanıcının
önerdiği `OPERATOR` DEĞİL, en güvenli rol olan `VIEWER`. Yeni `app/
services/ldap_auth.py::authenticate_and_provision()` yerel bind
başarısız olursa Faz 49'un mevcut `_bind_candidates`/`_bind_connection`
mantığını AYNEN reuse ederek dener; başarılıysa kullanıcı ÖNCEDEN
senkronize edilmiş `ad_users`'ta aranır (senkronize edilmemiş bir AD
hesabı asla otomatik provizyon edilmez) ve ya mevcut bağlı yerel
hesabın profili tazelenir ya da `password_hash=NULL`/`is_ad_user=true`
ile yeni bir hesap açılır — bir AD kullanıcı adı, AD'ye BAĞLI OLMAYAN
mevcut bir yerel `username`'le çakışırsa satır asla sessizce ele
geçirilmez (login reddedilir). `users.password_hash` artık NULLABLE;
yeni `users.is_ad_user`/`users.email`, `ad_users.email` (additive).
**Frontend:** `PamUsersPanel.tsx`'in "Yeni Kullanıcı" formuna bir
Yerel/AD kaynak seçici eklendi — AD seçilince Faz 49'un `GET /api/
settings/ldap/users`'ından doldurulan bir AD kullanıcı seçici + rol
seçici, gönderim yeni `POST /api/pam/users/from-ad` ile; "AD Hesabı"
sütunu artık bağlıysa yeşil "✅ AD Senkronize" rozeti gösteriyor.
`app/api/v1/...` gibi versiyonlu bir yol AÇILMADI, `AUDITOR` rolü
EKLENMEDİ, Cihaz/PAM AD grup desteği zaten Faz 49'da tamamdı (bu fazda
tekrar yazılmadı). Backend 639→668, frontend 354→362 test (`tsc`/
`eslint` temiz). **Canlı production backend'e henüz uygulanmadı** —
şema geçişi (`password_hash` nullable + yeni kolonlar) bir sonraki
restart'ta uygulanacak, gerçek bir AD hesabıyla uçtan uca giriş
doğrulaması da o zaman yapılacak.

Faz 52 sonrası bir dağıtım düzeltmesi de tamamlandı: kullanıcı gerçek
bir AD hesabıyla (`aykutd`, önceden "AD'den İçe Aktar" ile oluşturulmuş)
giriş yapamayınca ("kullanıcı adı veya parola hatalı" sürekli)
bulundu — `LDAP_AUTH_ENABLED` canlı `.env`'de hiç set edilmemişti
(varsayılan `false`), bu yüzden `login()`'in LDAP fallback'i hiç
denenmiyordu. Kod DEĞİL, yalnızca yapılandırma sorunuydu — Faz 52'nin
kendi güvenli varsayılanı (opt-in kapalı) beklendiği gibi çalışıyordu.
Kullanıcı onayıyla `LDAP_AUTH_ENABLED=true` eklenip backend yeniden
başlatıldı.

Faz 53 de tamamlandı: **PAM Canlı İzleme & Oturum Kaydı — Tam Ekran +
Zaman Çubuğu İşaretleri (Timeline Activity Markers)**. Kullanıcının
isteği Faz 50/51'de ZATEN tamamlanmış olan Canlı İzleme (Shadowing)/
Oturum Kaydı-Tekrar mimarisiyle büyük ölçüde çakışıyordu — bu faz
onları yeniden yazmadı, yalnızca gerçekten eksik iki parçayı ekledi:
(1) `SessionReplayModal.tsx`/`LiveSessionShadowModal.tsx`'e Faz 48'in
`GuacamoleRdpViewer.tsx`'teki AYNI `requestFullscreen()` deseniyle
"Tam Ekran" butonu, (2) yeni `app/pam/recording_analysis.py::
extract_activity_markers()` — kayıtlı `.guac` dosyasının KENDİSİNDEKİ
GERÇEK `key` (tuş basma) instruction'larını mevcut `guacamole_protocol.
py::read_instruction` ile ayrıştırıp zaman çubuğunda tıklanabilir
işaretlere çeviriyor (YENİ veri UYDURULMADI — kayıt bu olayları zaten
içeriyordu). Yeni `GET /api/pam/audit/{id}/activity-markers` (mevcut
`PAM_ADMIN`-only router'da, yeni namespace AÇILMADI). Kullanıcının
önerdiği `/backend/services/pam_proxy`/`/frontend/components/pam`
dizin yapısı ve `/ws/pam/stream/{id}/shadow` (Faz 51'in zaten çalışan
`/api/pam/audit/{id}/shadow`'unun yerine) AÇILMADI; kayıt formatı
`.guac` olarak kaldı (`.mp4`/`.webm`'e dönüştürülmedi, Faz 50 kararı).
Backend 668→676 test (`app/pam/recording_analysis.py` + route testleri).
Frontend `tsc`/`eslint` temiz, mevcut 362 test değişmeden geçti (yeni
component testi açılmadı — Faz 48'in `GuacamoleRdpViewer` kararıyla
AYNI gerekçe). Canlı production backend'e henüz uygulanmadı.

Faz 53 sonrası bir bugfix de tamamlandı — kullanıcının "Oturum kaydı
yüklenemedi" bildirimiyle bulundu: gerçek kök neden `guacamole-common-
js@1.5.0`'ın KENDİ hatasıydı — `Guacamole.SessionRecording` bir `Blob`
ile çağrıldığında kütüphanenin iç `recordingBlob`'u `source`'a HİÇBİR
ZAMAN atanmıyor (kaynakta doğrulandı), bu yüzden kurucudan senkron bir
`TypeError` fırlıyordu (backend'in kendisi HER ZAMAN doğru 200/bytes
döndürüyordu — canlı bir istekle doğrulandı). `node_modules`'a
DOKUNULMADAN, `SessionReplayModal.tsx` artık kütüphanenin doğru
çalışan tünel dalını sahte bir tünel nesnesiyle tetikleyip `Guacamole.
Parser` ile besliyor. Ayrıca gerçek hatalar artık `console.error`'a
loglanıyor, `GET /api/pam/audit/{id}/recording` boş dosyada 404 DEĞİL
400 dönüyor, ve `LiveSessionShadowModal.tsx`'e `GuacamoleRdpViewer`'ın
Faz 48'de bulduğu AYNI ölçekleme eksikliği (artık `display.scale()`
otomatik uygulanıyor) düzeltildi. Backend 676→677, frontend değişmeden
362 test. Gerçek E2E: canlı bir 4.7 MB'lık kayıt tarayıcıda GERÇEKTEN
yüklenip oynatıldı.

Bu bugfix'in ARDINDAN ikinci bir tur daha tamamlandı — kullanıcı "tam
ekranda görebiliyorum, bu ekranda ekran gelmiyor" bildirince iki GERÇEK
hata daha bulundu: (1) `SessionReplayModal.tsx`'e de (diğer iki
Guacamole görüntüleyicisinde zaten düzeltilmiş) `display.scale()`
fit-to-container mantığı hiç uygulanmamıştı. (2) DAHA DERİN kök neden:
oynatma döngüsü bir sonraki hedefi `recording.getPosition()+STEP_MS`
ile hesaplıyordu — ama bu metod kayıtta o anda GERÇEKTEN ULAŞILAN
kareyi döner, istenen HEDEFİ değil; kayıtta bir "boşluk" (ekran
güncellemesi olmayan bir aralık) varsa `getPosition()` DEĞİŞMEDEN
kalıyor ve döngü SONSUZA KADAR aynı hedefi tekrar istiyordu (adım adım
`console.log` enstrümantasyonuyla canlı doğrulandı). Çözüm: kütüphanenin
kare-hizalı pozisyonundan bağımsız kendi `virtualPositionRef`'ini
tutmak. Frontend `tsc`/`eslint` temiz, 362 test değişmeden geçti (yalnız
`SessionReplayModal.tsx` içi mantık, backend'e dokunulmadı). Gerçek E2E:
28 saniyelik, admin tarafından sonlandırılmış gerçek bir kayıt baştan
sona oynatıldı — gerçek Windows masaüstü (simgeler, görev çubuğu, saat)
ekranda göründü, piksel-örnekleme ile %96+ dolu canvas doğrulandı.

Faz 54 de tamamlandı: **PAM "Denetim Kaydı" & "Erişim Kuralları"
Kurumsal UI Yükseltmesi**. `PamAuditPanel.tsx`'e 4 KPI kartı (her zaman
TAM oturum geçmişinden, filtrelerden bağımsız), backend'e giden gerçek
arama/protokol/bitiş-nedeni filtreleri + istemci taraflı tarih hızlı
filtresi, renkli protokol/bitiş-nedeni rozetleri. `PamRulesPanel.tsx`'e
arama barı, ✅/❌ RDP/SSH rozetleri, kalan gün gösteren Geçerlilik
sütunu, "Kuralı Düzenle" modalı ve yeni bir `pam_access_rules.is_active`
— YALNIZCA kozmetik değil, `authorize_ssh_session`/`authorize_rdp_
session`/`/my-access` GERÇEKTEN erişimi reddeder/gizler. `GET /api/pam/
audit` artık `search`/`protocol`/`reason`/`limit`/`offset`, `GET /api/
pam/rules` artık `search`/`limit`/`offset` opsiyonel query parametreleri
kabul ediyor (`/api/v1/...` AÇILMADI, proje hiç kullanmadı). Backend
677→683, frontend 362→369 test. **Canlı production backend'e henüz
uygulanmadı** — yeni şema (`is_active` kolonu) bir sonraki restart'ta
uygulanacak.

Faz 55 de tamamlandı: **PAM Cihaz Etiketleri (Tags) + Statik Cihaz
Grupları (Server Groups)** — kullanıcının istediği "Enterprise PAM"
yol haritasının 1. maddesi. `pam_access_rules` artık TEK bir `asset_id`
YERİNE bir etikete (`tag_id`) veya statik bir cihaz grubuna
(`server_group_id`) atanabiliyor — üçünden TAM OLARAK biri dolu
(yeni `pam_access_rules_device_target_xor` CHECK, mevcut `user_id`/
`ad_group_id` XOR deseniyle AYNI ilke). Yeni `tags`/`asset_tag_
assignments`/`server_groups`/`server_group_members` tabloları (Discovery'nin
`assets`'ine PAM kavramı SIZDIRILMADI). `authorize_ssh_session`/
`authorize_rdp_session`/`/my-access` artık üç kademeli çözüyor:
doğrudan asset > etiket > cihaz grubu (en spesifik kazanır). Yeni
`GET/POST/DELETE /api/pam/tags` + `GET/POST/PUT/DELETE /api/pam/
server-groups` (`PAM_ADMIN`). Frontend: `PamRulesPanel.tsx`'e "Cihaz
Hedefi Tipi" seçici (Tek Cihaz/Etiket/Cihaz Grubu, mevcut "Kullanıcı
Tipi" seçicisiyle AYNI desen), yeni `/pam/tags` + `/pam/groups`
sayfaları (checkbox'lı "Cihazları Yönet" modalı). Backend 683→694,
frontend 369→376 test (`tsc`/`eslint` temiz). **Canlı production
backend'e henüz uygulanmadı.**

Faz 56 de tamamlandı: **PAM Erişim Talepleri (Access Requests)** —
Enterprise PAM yol haritasının 2. maddesi. Kullanıcıların artık
`/pam/rules`'tan Admin'in elle kural yazmasını BEKLEMEDEN, kendileri
"bana X cihazına Y süreliğine SSH/RDP lazım, sebebi Z" diye bir talep
açması ve Admin'in onaylaması/reddetmesi mümkün — **paralel bir
yetkilendirme motoru AÇILMADI**: yeni `pam_access_requests` tablosu
(Faz 55 ile AYNI 3'lü cihaz-hedefi XOR deseni: `asset_id`/`tag_id`/
`server_group_id`) yalnızca talebi/durumu tutuyor, onaylama mevcut
`create_rule`/`update_rule`'u (Faz 46/55) ÇAĞIRARAK gerçek bir
`pam_access_rules` satırı oluşturuyor/genişletiyor — aynı (kullanıcı,
cihaz) için zaten kural varsa izinler birleştirilip `valid_until`
UZATILIYOR (kısaltılmıyor), yoksa yeni kural açılıyor. Durum geçişi
(`pending→approved/rejected`) atomik `UPDATE ... WHERE status='pending'`
ile önce denenip BAŞARISIZ olursa hiçbir yan etki (kural
oluşturma/genişletme) tetiklenmiyor — çifte onay/red yapısal olarak
imkansız. `POST/GET /api/pam/access-requests` (+`/mine`, +`/{id}/
approve`, +`/{id}/reject`) — Faz 51'in `router`/`my_access_router`
ayrımıyla AYNI ilke (`PAM_ADMIN`: listele/onayla/reddet, `PAM_ACCESS`:
kendi talebini aç/gör). Onaylayan Admin kasa hesabını SEÇER, talep eden
kullanıcı hiçbir zaman hangi hesabın kullanılacağını görmez (Faz 46'nın
zero-knowledge ilkesiyle tutarlı). **Bilinçli sapma:** planın öngördüğü
"talep formunda Faz 55'in 3'lü cihaz-hedefi seçicisi" YERİNE
`MyAccessPanel.tsx`'in talep formu YALNIZCA tek-cihaz (`asset_id`)
sunuyor — `GET /api/pam/tags`/`server-groups` router seviyesinde
TAMAMEN `PAM_ADMIN` gerektirdiği için `PAM_ACCESS`-only bir kullanıcı bu
listeleri backend'den hiç çekemiyor (backend API'si `tag_id`/
`server_group_id`'yi hâlâ kabul ediyor, bu yalnızca bir frontend UI
sınırı). Yeni Admin-only `/pam/requests` sayfası (`PamAccessRequestsPanel.
tsx` — durum filtresi, kasa hesabı seçimli Onayla modalı, Reddet).
Backend 694→702, frontend 376→382 test (`tsc`/`eslint` temiz). **Gerçek
E2E:** kullanıcı onayıyla canlı production backend yeniden başlatıldı,
`pam_access_requests` şeması otomatik kuruldu, restart sırasında gerçek
iki agent kesintisiz yeniden bağlandı; gerçek bir erişim talebi açılıp
onaylandı, bunun GERÇEKTEN yeni bir `pam_access_rules` satırı
oluşturduğu ve `/my-access`'in GERÇEKTEN yetki verdiği doğrulandı, test
verisi (kural + talep) sonra temizlendi.

Faz 57 de tamamlandı: **İzin Matrisi (Permission Matrix)** — Enterprise
PAM analizinin 3. maddesi. Kullanıcıya kapsam soruldu: tam özel/DB-
tanımlı rol yönetimi (`users.role`'ün sabit ADMIN/OPERATOR/VIEWER
üçlüsünden çıkması) login/LDAP-provizyon gibi birçok yeri etkileyen
büyük bir mimari değişiklik olacağından, kullanıcı yalnızca "İzin
Matrisi ekranı"nı onayladı — özel rol yönetimi bilinçli olarak kapsam
dışı bırakıldı. Yeni `/pam/permissions` sayfası (`PermissionMatrixPanel.
tsx`) — tüm kullanıcıları/tüm izinleri satır×sütun grid'inde gösterip
hücre bazlı düzenlemeye izin veriyor. **Backend'e HİÇ dokunulmadı** —
Faz 47'nin `GET /api/pam/users`/`PUT .../permissions`'ı zaten yeterliydi;
her hücre tıklaması bu mevcut endpoint'i (kullanıcının GÜNCEL tam izin
listesiyle) çağırıyor, `UserPermissionsModal`'ın "yer değiştirme"
sözleşmesiyle AYNI (`PERMISSION_LABEL_KEY` oradan export edilip
KOPYALANMADI). İyimser (optimistic) UI güncellemesi — başarısız istekte
checkbox eski durumuna geri alınıyor. `PamUsersPanel.tsx`'e bağlantı +
Sidebar'a "📊 İzin Matrisi" eklendi. Frontend 382→385 test (`tsc`/
`eslint` temiz). Backend değişmediği için canlıya ayrı bir
restart/deploy GEREKMEDİ.

Faz 58 de tamamlandı: **"Yetkili Sunucularım" Kurumsal PAM Launchpad
Yükseltmesi**. Kullanıcının detaylı spesifikasyonundaki birkaç bilinçli
sapma belgelendi: `UserServersPanel.tsx`/`MyAuthorizedServers.tsx`
YENİDEN ADLANDIRMASI yapılmadı (mevcut `MyAccessPanel.tsx` yerinde
genişletildi), `GET /api/v1/pam/my-servers` YENİ/versiyonlu endpoint
AÇILMADI (mevcut `GET /api/pam/my-access`, Faz 46, genişletildi — bu
proje hiç `/api/v1` kullanmadı), yeni bir `os_type` alanı EKLENMEDİ
(Windows/RDP ⋅ Linux/SSH rozetleri zaten var olan `allow_rdp`/
`allow_ssh`'ten türetildi — gerçek bir OS tespiti YOK, uydurulmadı),
yeni bir canlı ping probe'u TETİKLENMEDİ ("Erişilebilirlik" Faz 0-9'un
gerçek `assets.status` discovery/SNMP verisini kullanıyor). `Authorized
AssetResponse`'a `is_online`/`active_sessions_count` eklendi —
`active_sessions_count` YENİ bir sayaç tablosu GEREKTİRMEDİ, Faz 51'in
`session_registry` çapraz kontrollü `list_session_logs`'u reuse eden
yeni bir `_active_session_counts_by_asset()` yardımcı fonksiyonuyla
hesaplanıyor. `MyAccessPanel.tsx`: 3 KPI kartı, Sunucu+IP alt metni,
canlı Online/Offline rozeti (Faz 41'in Agent durum noktalarından reuse),
Aktif Oturum rozeti, protokol rozetleri, `daysRemainingLabel` (Faz
54'ten export edilip reuse edildi) ile renkli kalan-süre, "Taleplerim"e
arama/durum filtresi + gerekçe tooltip'i. Backend 702→704, frontend
385→388 test (`tsc`/`eslint` temiz), tam regresyon paketleri temiz
(tam paket koşusunda görülen 3 hata bu oturumun önceki fazlarında da
belgelenen, GERÇEK canlı veriye bağlı önceden var olan bir ortam
sorunu — Faz 58'e dokunulmadı, ayrı çalıştırıldığında hepsi geçiyor).

Faz 59 de tamamlandı: **Çoklu Tema Motoru + Sürüklenebilir
Özelleştirilebilir Dashboard** (yalnızca frontend). Kullanıcının
spesifikasyonundaki sapmalar `AskUserQuestion` ile onaylandı: Tailwind
EKLENMEDİ (mevcut `ThemeProvider` 2→4 temaya genişletildi, CSS
değişkenleriyle — `fortios-dark`/`cyber-neon`/`midnight-blue`/
`enterprise-light`; eski `dark`/`light` localStorage değerleri yeni
isimlere migrate ediliyor, dark mode kırılmadı), kalıcılık
`localStorage` (istek `/api/v1/.../dashboards.py` + `user_preferences`
tablosu diyordu — proje hiç `/api/v1` kullanmadı, tema/dil zaten
`localStorage`'da), backend/DB değişikliği YOK. Header'a
`ThemeSwitcher` (native `<select>`), `SettingsPanel` 4 temalı seçiciye
döndü. Dashboard: **`react-grid-layout` yeni bağımlılık** —
**GÜVENLİK:** registry'deki `1.5.2` sürümü repo'da olmayan bir
`ip_fetcher` ikilisi + `.c` kaynağı içeriyordu (npm bu sürümleri BU
NEDENLE `deprecated` etmiş, bkz. react-grid-layout#2269); postinstall
hook YOK ve `1.5.4` bayt-bayt aynı-ama-temiz olduğu için hemen
`1.5.4`'e yükseltildi (`^1.5.4` sabitlendi, stray dosyaların gittiği
doğrulandı; bağımlılıkları yalnızca MIT `react-draggable`/
`react-resizable`). Yeni `components/dashboard/DashboardGrid.tsx` — 11
mevcut widget'ın (hiçbiri değişmedi) kayıt defteri + 4 hazır görünüm +
"Özel", görünüm seçici + `+ Widget Ekle` modalı + `💾 Kaydet` + `🔄
Sıfırla` araç çubuğu, düzen görünüm başına `localStorage`'da.
`app/page.tsx` statik layout yerine `<DashboardGrid />` render ediyor.
`tests/testUtils.tsx::renderWithProviders` artık `ThemeProvider` de
sarıyor. Frontend 388→396 test (`tsc`/`eslint` temiz). **Canlı
doğrulama:** 4 tema da canlıda (`data-theme`+`--accent`+`color-scheme`
JS ile) doğrulandı, dashboard grid render oldu, görünüm değişimi
çalıştı; test sonrası paylaşımlı admin'in `itops-theme`/`itops-
dashboard-*` localStorage anahtarları temizlendi. Backend değişmediği
için restart YAPILMADI.

Faz 60 de tamamlandı: **Agent Detay ekranına PAM bağlantı butonları**
(yalnızca `AgentDetailView.tsx` + çeviriler + testi). Kullanıcının
"3 buton: RDP/SSH/CMD" isteğindeki sapmalar `AskUserQuestion` ile
onaylandı: `/api/v1/pam/sessions/start` AÇILMADI (proje hiç `/api/v1`
kullanmadı) — RDP → `/pam/session/{asset_id}` (Faz 48 Guacamole), SSH →
`/pam/ssh/{asset_id}` (Faz 46 zero-knowledge); "IP + varsayılan kasa
hesabıyla doğrudan tünel" YAPILMADI (PAM modeli o kullanıcı+asset için
AÇIK bir `pam_access_rules` satırı gerektirir, bypass edilmedi) —
butonlar yalnızca agent GERÇEK bir cihaza bağlıysa (`agent.asset_id`)
tıklanabilir, yetkilendirme hedef PAM sayfasında aynen zorunlu; gerçek
interaktif "Agent Shell" (komut kanalı üzerinden PTY — Auth/RBAC'sız
RCE) YAPILMADI — "CMD / Terminal" butonu Faz 35'in web SSH terminalini
(`/remote-control/ssh/{agentId}`) açıyor, etiketi `agent.os`'a göre
(windows → "CMD / PowerShell", linux → "Bash"; `agent.os` Faz 30'dan
GERÇEK bir alan). Bu ekrandan eski `.rdp` indirme (Faz 34) + eski
"SSH ile Bağlan" butonu kaldırıldı (backend endpoint'i ve
`AssetAgentPanel.tsx`'teki akış aynen duruyor). Frontend 396→398 test
(`tsc`/`eslint` temiz). Backend değişmedi, restart YOK.

Faz 61 de tamamlandı: **Firewall/Router asset detayına PAM CLI/SSH
kısayolu** (yalnızca `AssetDetails.tsx` + CSS + çeviriler + testi).
Kullanıcının "Web Konsolu (HTTPS) + CLI/SSH + kasadan admin/read-only
hesap türü" isteğindeki sapmalar `AskUserQuestion` ile onaylandı:
**"Web Konsolu (HTTPS) — kimlik-enjeksiyonlu PAM Web Proxy" YAPILMADI**
(PAM yalnızca ssh/rdp protokoller, guacd HTTP reverse-proxy değil;
kimlik-enjeksiyonlu HTTPS proxy'si SSRF/sertifika/cookie/CSRF yüzeyi
olan ayrı bir güvenlik-kritik alt sistem — ayrı faza bırakıldı, buton
HİÇ eklenmedi); **"kasadan admin/read-only_admin hesap türü çek"
YAPILMADI** (vault'ta "hesap türü" kavramı yok; PAM her zaman açık bir
`pam_access_rules` satırındaki belirli `credential_id`'yi kullanır,
Faz 60'la aynı). Eklenen: `device_type` `firewall`/`router` olan asset
detayında tek bir "💻 CLI / SSH (PAM)" butonu → `/pam/ssh/{asset_id}`
(Faz 46 zero-knowledge terminal) yeni sekmede; yetkilendirme hedef
sayfada aynen zorunlu. Frontend 398→400 test (`tsc`/`eslint` temiz).
Backend değişmedi, restart YOK.

Faz 62 de tamamlandı: **IT Helpdesk / Arıza Yönetimi (Ticket
Management)** — PAM'den TAMAMEN bağımsız, additive bir modül.
Kullanıcının spec'indeki `/api/v1/endpoints/tickets.py` KULLANILMADI
(proje hiç `/api/v1` kullanmadı) — `app/routes/tickets.py` → `/api/
tickets`, modeller `app/tickets/` + `app/db/tickets.py`. Yeni şema
(additive): `tickets` (`ticket_number` `INC-YYYY-NNNN`, yıl bazlı
atomik `ticket_number_seq` sayacından; category/priority/status CHECK;
`created_by`/`assigned_to` → `users`; serbest metin `related_device`,
FK YOK), `ticket_comments` (zaman çizelgesi: created/comment/
status_change/assignment). `sla_due_at` oluşturmada önceliğe göre
(CRITICAL 4s / HIGH 24s / MEDIUM 72s / LOW 168s). **Yetkilendirme
(`AskUserQuestion`):** yeni `TICKETS_VIEW` izni (diğer OPERASYON
menüleriyle tutarlı, Faz 47), `main.py::_ensure_tickets_permission_
backfill()` her başlangıçta mevcut kullanıcılara bir kerelik ekliyor
(`grant_permission`, tek izin — diğerlerine dokunmaz); atama/durum
değişikliği "izni olan herkes" (talep-eden/teknisyen ayrımı ileride).
`GET /api/tickets` filtre (status/priority/category/search) + sayfalama
+ `stats` (4 KPI). `GET .../assignable-users` (`GET /api/pam/users`
`PAM_ADMIN` gerektirdiği için ayrı, id+username). Frontend: Sidebar'a
`🎫 Destek / Biletler`, `app/tickets/page.tsx`, `TicketsPanel.tsx`
(KPI + filtre barı + tablo, renkli rozetler), `CreateTicketModal.tsx`
(varlık/agent datalist), `TicketDetailModal.tsx` (sol zaman çizelgesi +
yanıt, sağ metadata + atama + durum + ilgili cihaz linkleri). Mevcut
4 temayla (Faz 59) uyumlu — CSS Modules token'ları + 2 yeni rozet
rengi. Backend 703→714 test, frontend 400→405 test (`tsc`/`eslint`
temiz). **Canlı E2E:** kullanıcı onayıyla production backend yeniden
başlatıldı, şema + `TICKETS_VIEW` backfill'i çalıştı, agent'lar
kesintisiz bağlandı; gerçek bir bilet uçtan uca doğrulandı (oluştur →
`INC-2026-0001`, SLA +24s; yorum + durum geçişi → zaman çizelgesinde
3 olay), test verisi (`tickets` + `ticket_number_seq`) temizlendi.

Faz 63 de tamamlandı: **Bilet Sistemi — Dinamik Departman & Kategori
Yönetimi.** Faz 62'nin sabit `category` enum'ı (6 değer) + `related_
device` serbest metni KALDIRILDI; yerine admin tarafından yönetilen
`ticket_departments` + `ticket_categories` tabloları (`id`, `name`
UNIQUE, `is_active`) geldi. `tickets.category` → `category_id` (uygulama
katmanında zorunlu), yeni `department_id` (opsiyonel), her ikisi de FK.
**"Silme" = soft-delete** (`is_active=false`; mevcut biletlerin FK'si
korunur), aynı adı yeniden eklemek pasif satırı reaktive eder, aktif
dup → 409. `infra/postgres/init.sql` idempotent seed (4 departman + 8
kategori). Faz 62'yle canlıya çıkmış `tickets` tablosu `ALTER ... DROP
COLUMN IF EXISTS category/related_device` + `ADD COLUMN IF NOT EXISTS
{category,department}_id` ile geçiriliyor (prod boş). Endpoint'ler:
`GET /api/tickets/{departments,categories}` (`TICKETS_VIEW`; `?include_
inactive=true`), `POST`/`DELETE /{id}` (**yalnızca `ADMIN`**,
`require_role`). `create_ticket` kategoriyi doğrular (yok/pasif → 400).
Liste filtresi `category`→`category_id` + `department_id`. Frontend:
`TicketsPanel.tsx` filtre dropdown'ları dinamik + tablodan "Cihaz"
sütunu çıkıp "Departman"+"Kategori" geldi + Admin'e "⚙️ Bilet Ayarları"
butonu; yeni `TicketSettingsModal.tsx` (2 sekme, liste+ekle+pasife al);
`CreateTicketModal.tsx` cihaz alanı kaldırıldı, kategori/departman
dinamik select; `TicketDetailModal.tsx` cihaz/Agent linkleri kaldırıldı,
departman+kategori metadata. Backend 714→715, frontend 405→406 test
(`tsc`/`eslint` temiz). **Canlı E2E:** kullanıcı onayıyla production
backend yeniden başlatıldı, yeni tablolar + seed (8 kategori / 4
departman) kuruldu, `tickets` ALTER'landı (DB kolonlarıyla doğrulandı),
agent'lar kesintisiz bağlandı; bilet dinamik kategori+departmanla
açıldı, admin bir kategori ekleyip soft-delete etti (aktif listeden
düştü), test verisi temizlendi.

Faz 64 ("Bilet RBAC — Departman Bazlı Kullanıcı Yönetimi") tam olarak
uygulanıp canlıya alınmış, ardından kullanıcı isteğiyle 19 dosyada
**GERİ ALINMIŞTIR** — yalnızca `infra/postgres/init.sql`'deki additive
kolonlar (`users.ticket_role`, `users.ticket_department_id`,
`ticket_comments.is_internal`/`priority_*`/`department_*`) canlı DB
tutarlılığı için korundu; kod onlara referans vermez.

Faz 65 de tamamlandı: **Bilet Detay UI Düzeltmesi + Basit REQUESTER
RBAC + SMTP E-Posta Bildirimi.** Faz 64'ün departman-kapsamlı
görünürlüğü/gizli iç notları/öncelik-transfer olayları GETİRİLMEDİ —
kural tek cümle: `users.ticket_role IN ('TECHNICIAN','ADMIN')` → tüm
şirket biletleri; `REQUESTER` (varsayılan) → yalnızca `created_by = ben`
(`get_ticket_detail`/`add_comment` kapsam dışı bilette **API
seviyesinde 403**). `ticket_role` kolonu init.sql'de zaten vardı (Faz
64'ten) — şema değişikliği YOK; `_ensure_ticket_roles_backfill()`
(idempotent) ilk kez `role='ADMIN'` olanları bilet ADMIN'ine yükseltir.
`create_ticket` `department_id` verilmezse **"IT" seed departmanını**
otomatik atar. `app/services/email_service.py` — `smtplib` (stdlib,
YENİ BAĞIMLILIK YOK), `asyncio.to_thread` + ateşle-unut
(`loop.create_task`); e-posta hatası bilet işlemini ASLA bozmaz.
`SMTP_SERVER` yoksa tamamen no-op (opt-in). 3 tetik: yeni bilet →
`SMTP_IT_GROUP_EMAIL`, yeni yanıt → bilet sahibi (`users.email`), durum
RESOLVED/CLOSED → sahip; kurumsal HTML şablon (bilet no + başlık +
oluşturan + `TICKET_BASE_URL` linki). `TicketDetailModal.tsx`: modal
`min(1040px, 96vw)`, esnek 2 kolon grid, `<textarea>` `width:100%` +
`min-height:120` + `box-sizing:border-box` + `overflow-wrap:break-word`
(dikey kırılma düzeltmesi). `PamUsersPanel.tsx`: "Bilet Rolü" kolonu +
form alanı geri geldi. `CurrentUser`/`/api/auth/me`/`/api/pam/users`
`ticket_role` taşır. Backend 61→67 ticket/auth/pam testi (+ yeni
`test_email_service.py` 5 test), frontend 406→407 test (`tsc`/`eslint`
temiz). **Canlı SMTP deployment kullanıcı onayı bekliyor** (backend
restart + gerçek SMTP değerleri) — kod ve testler hazır, canlıya
uygulanmadı.

Faz 66 de tamamlandı: **SMTP Yapılandırması Ayarlar Ekranında
(DB-Tabanlı).** Kullanıcı isteği — SMTP değerlerini `.env` yerine
Ayarlar > "E-Posta Bildirimi (SMTP)" ekranından yönet. Tek satırlık
`smtp_config` tablosu (`ldap_config` deseni), parola `app.pam.vault`
Fernet'iyle şifreli, `require_role("ADMIN")`. `GET`/`PUT /api/settings/
smtp` + `POST /api/settings/smtp/test` (gerçek test e-postası, hata →
`success=false`). `email_service.py` YENİDEN DÜZENLENDİ: `SmtpConfig`
dataclass + `load_config()` (async, **önce DB `smtp_config` satırı,
yoksa `.env`**); DB satırı `enabled=false` ise gönderim yok.
`notify(recipients=None)` → IT grup adresi config'den çözülür. Frontend:
`SmtpConfigurationCenter.tsx` (LDAP merkezi deseni), `SettingsPanel`'e
ADMIN'e görünür bölüm, `lib/api.ts` + `translations.ts`. Backend yeni
`test_smtp_settings_api.py` (6) + `test_email_service.py` 5→9, frontend
407→410 test (`SmtpConfigurationCenter.test.tsx` 3). `tsc`/`eslint`
temiz. `conftest.py` patch listesi + `.env.example` güncellendi.
**Canlı deployment YAPILMADI** — `smtp_config` tablosu bir sonraki
restart'ta kurulur; kullanıcı döndüğünde Ayarlar ekranından değerleri
girip "Test Et" ile doğrulayacak.

Faz 66 tamamlama de yapıldı: **Gönderen Adı + Gerçek SSL/TLS/None
Şifreleme.** Kullanıcı Faz 66'nın zaten karşıladığı bir spesi tekrar
istedi — YENİDEN YAZILMADI, yalnızca 2 gerçek eksik kapatıldı: (1)
`smtp_config.from_name` (önceden e-posta gövdesinde hardcode'du,
Ayarlar'da "Gönderen Adı" alanı + `SMTP_FROM_NAME` fallback); (2)
`smtp_config.encryption` (`'tls'|'ssl'|'none'`) — eski `use_tls: bool`
yalnızca STARTTLS aç/kapa yapıyordu, gerçek implicit-SSL (port 465,
STARTTLS'ten farklı el sıkışma) desteklenmiyordu; `send_email_blocking`
artık `encryption`'a göre `smtplib.SMTP_SSL`/`SMTP+starttls()`/düz
`SMTP` arasında seçim yapıyor. Şema henüz canlıya hiç uygulanmamıştı
ama dev/test Postgres'inde tablo test koşularından ZATEN (eski
şekilde) oluşmuştu — idempotent `ALTER TABLE`+veri taşıma bloğu
eklendi. Frontend: "STARTTLS Kullan" checkbox'ı → Şifreleme Türü
dropdown'u (port alanı türe göre öneri günceller, elle girilen port
asla ezilmez), "Gönderen Adı" yeni alan. Backend 45/45 ilgili test
(+3 yeni: SSL yolu, none yolu, uçtan uca SSL testi), frontend 426→427
(`tsc`/`eslint` temiz). **Canlı deployment hâlâ YAPILMADI** — Faz 66
ile aynı restart'ta uygulanacak.

Faz 67 de tamamlandı: **Bilet SLA Politikası (Yapılandırılabilir) +
Gecikmiş Bilet Filtresi.** Faz 64/65'in "SLA yönetimi ayrı faza"
kararı. `ticket_sla_policy` tablosu (öncelik PK + `sla_hours`) + seed
(mevcut 4/24/72/168). `service.py::_sla_hours()` DB politikasını okur,
satır yoksa `SLA_HOURS_BY_PRIORITY` sabiti fallback. `sla_due_at`
YALNIZCA oluşturmada hesaplanır — politika sonradan değişirse eski
biletlerin taahhüt edilmiş `sla_due_at`'i DEĞİŞMEZ. `GET /api/tickets/
sla-policy` (`TICKETS_VIEW`), `PUT /api/tickets/sla-policy/{priority}`
(`require_role("ADMIN")`). `GET /api/tickets?overdue=true` → yalnızca
SLA'sı aşılmış AÇIK biletler. Frontend: `TicketSettingsModal`'a "SLA"
sekmesi, `TicketsPanel` filtre barına "Yalnızca gecikmişler"
checkbox'ı. Backend `test_tickets_api.py` +4 SLA testi, frontend
410→412 (`tsc`/`eslint` temiz). **Canlı deployment YAPILMADI** —
`ticket_sla_policy` + seed bir sonraki restart'ta kurulur.

Faz 68 de tamamlandı: **Bilet Metrikleri / Raporlama Paneli
(salt-okunur).** **Şema değişikliği YOK** — hepsi mevcut `tickets`
üzerinde agregasyon. `db.ticket_metrics()` (durum/öncelik/kategori/
departman dağılımı + ort. çözüm saati + SLA uyum % + son 30 gün
açılan/çözülen). `GET /api/tickets/metrics` (`TICKETS_VIEW`; REQUESTER
yalnızca kendi biletleri — Faz 65 `_is_it_staff`). Frontend:
`TicketMetricsPanel.tsx` (5 sayı kartı + CSS dağılım barları +
`recharts` 30 günlük çift çizgi), `TicketsPanel`'e "📊 Raporlar"
toggle'ı. Backend `test_tickets_api.py` +3 metrik testi, frontend
412→413 (`tsc`/`eslint` temiz). Additive — yeni tablo yok.

Faz 69 de tamamlandı: **"Bana Atananlar" Bilet Filtresi + CSV Dışa
Aktarma.** **Şema değişikliği YOK.** `db.list_tickets` `assignee_scope`
+ `list_tickets_route` `mine: bool`. Yeni `GET /api/tickets/export.csv`
(`TICKETS_VIEW`, `/{ticket_id}`'den ÖNCE) — stdlib `csv`, 11 kolon,
`limit=5000`, aynı REQUESTER `created_by_scope` RBAC'ı. Frontend
`downloadTicketsCsv()` auth'lu `fetch` + `Blob` indirmesi (JWT query'e
konmaz), `TicketsPanel` filtre barına "Bana atananlar" (yalnızca IT
ekibi) + "⬇ CSV". Backend `test_tickets_api.py` +3, frontend 413→415
(`tsc`/`eslint` temiz). Additive — canlı restart gerekmez.

**Faz 66-69 test altyapısı düzeltmesi:** `email_service.notify()`
ateşle-unut `asyncio` task'ı `isolated_db`'nin PAYLAŞIMLI test
connection'ında eşzamanlı sorgu çalıştırıp DB'ye bağlı TÜM ticket
testlerini kilitliyordu — `conftest.py::isolated_db` artık test
sırasında `notify`'ı no-op'a patch'liyor (e-posta ayrıca `test_email_
service.py`'de izole test ediliyor).

Faz 70 de tamamlandı: **SNMP Tabanlı Alert Kurallarının Canlıya
Bağlanması (Faz 26/27 kalanı).** Faz 26'da eklenen 6 SNMP-tabanlı alert
kuralı (`interface_down`/`interface_error`/`high_bandwidth`/`snmp_
poll_failure`/`device_unreachable`/`high_utilization`) `computeAlerts`'in
`options.monitoring`'i hiçbir çağrı noktasında geçilmediği için bugüne
kadar YALNIZCA testlerde çalışıyordu. `DashboardDataProvider`'a
`monitoring: Record<string, SnmpPollResult>` eklendi — `fetchMonitoring
History()` (Faz 39, poll TETİKLEMEZ) ile ilk yükte + mevcut 8sn'lik
sessiz auto-refresh döngüsünde dolduruluyor (yeni bir istek döngüsü
AÇILMADI). `AlertsPanel`/`AlertsList`/`DeviceHealthSummary` zaten
`useDashboardData()` kullanıyordu, `AssetDetails.tsx`'e YENİ bir
`useDashboardData()` çağrısı eklendi (provider tüm uygulamayı sarmaladığı
için güvenli). `tests/testUtils.tsx::mockAssetsAndScans`'ın Faz 39'dan
beri hazır duran `monitoringHistory` parametresi ilk kez gerçekten
kullanıldı — 4 component testine gerçek bir SNMP alert'inin artık
render edildiğini doğrulayan testler eklendi. Frontend 415→419 test
(`tsc`/`eslint` temiz). Backend'e dokunulmadı — bu faz bir sonraki
frontend deploy'unda canlıda hemen etkili olur, restart gerekmiyor.

Faz 71 de tamamlandı: **Zamanlanmış Ağ Taraması (Scheduled Discovery).**
Kullanıcının Ayarlar'da AÇIKÇA kaydettiği bir CIDR'ın periyodik TEKRARI
— CLAUDE.md'nin "örtük/otomatik geniş ağ taraması yapılmaz" kuralı
korunuyor (yeni/keşfedilen bir aralık ASLA otomatik taranmaz). Yeni
`scheduled_scans` tablosu + `app/discovery/scheduler.py` (`app/snmp/
scheduler.py` ile AYNI arka plan worker deseni) — elle taramayla
TAMAMEN aynı kod yolunu (`app/routes/discovery.py`'nin zaten "tek temas
noktası" olarak belgeli yardımcıları) reuse ediyor, yeni bir tarama
motoru YOK. `GET/POST /api/discovery/schedules` + `PUT/DELETE .../
{id}` — elle taramanın (`/icmp`) AKSİNE `require_role("ADMIN")` (kalıcı
arka plan kaynağı olduğu için bilinçli sapma). Frontend
`ScheduledScansPanel.tsx` (Ayarlar, ADMIN-only). Backend 96/96 ilgili
discovery testi (8 CRUD + 5 scheduler, `scan_network` sahtelenerek —
gerçek ağ taraması hiç yapılmadı), frontend 419→424 test (`tsc`/
`eslint` temiz). **Canlı deployment YAPILMADI** — `scheduled_scans`
tablosu bir sonraki restart'ta kurulur.

Faz 59 sonrası bir UX düzeltmesi de tamamlandı — kullanıcı canlı
dashboard ekran görüntüsüyle bildirdi: `DashboardGrid.tsx`'in
düzenleme araç çubuğu ("Widget Ekle"/"Kaydet"/"Sıfırla" + sürükle/
boyutlandır/"Kaldır") artık varsayılan GİZLİ — yeni "✏️ Düzenle"
butonuyla açılır, "💾 Kaydet" (veya "✅ Bitti") ile otomatik kapanır;
mod kalıcı değil, her sayfa açılışında temiz başlar. Frontend 424→426
test (`tsc`/`eslint` temiz). Backend'e dokunulmadı.

**Faz 66/66-tamamlama/67/71 canlı deployment tamamlandı:** kullanıcı
onayıyla production backend (`--host 0.0.0.0 --port 8000`) yeniden
başlatıldı — `smtp_config` (`encryption`/`from_name` dahil), `ticket_
sla_policy` (+ seed 4/24/72/168), `scheduled_scans` tabloları hatasız
kuruldu, gerçek 2 agent kesintisiz yeniden bağlandı. Canlı doğrulama:
Ayarlar'da SMTP paneli (Şifreleme Türü dropdown + Gönderen Adı dahil)
ve Zamanlanmış Taramalar paneli doğru render oldu; Dashboard'da Faz
70'in SNMP tabanlı `snmp_poll_failure` alert'i GERÇEKTEN görüldü
("PSL-HQ-70G-1.alb.local için SNMP poll başarısız oldu"); Biletler
sayfasında Raporlar/Bana atananlar/CSV/Yalnızca gecikmişler kontrolleri
doğrulandı. SMTP değerleri henüz KAYDEDİLMEDİ — kullanıcı gerçek
sunucu bilgilerini girip "Test E-Postası Gönder" ile doğrulayacak.

Faz 32/40 sonrası bir UX sadeleştirmesi de tamamlandı — kullanıcı
canlı Ayarlar ekran görüntüsüyle bildirdi: `AgentDownloadPanel.tsx`'teki
düz CLI EXE indirmesi ("Agent İndir") panelden KALDIRILDI — Faz 40'ın
Windows Servisi Paketi zaten AYNI EXE'yi kapsayarak daha eksiksiz bir
kurulum sunuyor. Backend endpoint'i (`GET /api/agents/download/
windows`) KALDIRILMADI, yalnızca panelden bağlantısı kesildi. Frontend
427→424 test (`tsc`/`eslint` temiz). Backend'e dokunulmadı — `next dev`
HMR ile canlıda anında doğrulandı, restart gerekmedi.

Faz 29.5 sonrası bir UI iyileştirmesi de tamamlandı: SNMP Yapılandırması
tablosundaki "Atanmış Cihazlar" hücresi artık yalnızca bir sayı DEĞİL,
mevcut `GET /api/snmp/profiles/{id}/assets` (Faz 29.5) üzerinden
gerçek atanmış cihaz(lar)ı `hostname || ip_address` olarak, her biri
gerçek IP'sine `/topology?ip=...` ile giden bir link olarak gösteriyor
(mevcut Faz 20 deep-link deseni reuse edildi, yeni backend endpoint'i
AÇILMADI). Frontend 425 test. Backend'e dokunulmadı, restart YOK.

Faz 72 de tamamlandı: **vCenter / vSphere Sanallaştırma İzleme ve
Yönetim Modülü.** Kullanıcının açık seçimiyle vCenter REST API
(pyVmomi/SOAP DEĞİL) — `httpx` (proje zaten bağımlı, yeni kütüphane
YOK) ile `app/vcenter/{models,client,service}.py`. Yeni `VCENTER_VIEW`/
`VCENTER_ADMIN` izinleri (görüntüleme/güç işlemleri AYRI), `vcenter_
config` tek-satır tablo (`ldap_config`/`smtp_config` deseni, Fernet
şifreli parola). `GET /api/vcenter/{summary,vms,vms/{id},hosts}` +
`POST /api/vcenter/vms/{id}/power` + `/api/settings/vcenter` CRUD+test.
**Dürüstlük sınırı:** anlık CPU/RAM kullanım YÜZDESİ vCenter REST
Inventory API'sinde yok (Performance Manager/SOAP gerekir) — `cpu_
usage_percent`/`memory_usage_percent` HER ZAMAN `None`, UI'da açık bir
notla gösteriliyor, uydurulmadı. Frontend: Sidebar'a "☁️ vCenter /
vSphere" (KEŞİF grubu), `/vcenter` sayfası (KPI kartları + datastore
doluluk çubukları + VM tablosu + detay modalı + güç butonları), Ayarlar'a
`VCENTER_ADMIN`-only yapılandırma bölümü. VM Detay Modalı'ndan mevcut
`CreateTicketModal` VM bilgisi ön-dolu açılıyor (yeni tablo YOK). Backend
708→741, frontend 426→434 test (`tsc`/`eslint` temiz). **Canlı
deployment YAPILMADI** — kullanıcı gerçek vCenter bağlantı bilgilerini
verdiğinde restart + E2E yapılacak.

Faz 73 de tamamlandı: **vCenter Paneli — Enterprise UI/UX Yükseltmesi.**
`VMListTable.tsx`'e vCLS sistem VM filtresi ("Sistem VM'leri" toggle,
backend'den GİZLENMİYOR yalnızca varsayılan görünüm süzülüyor),
"İşlemler" sütunu (güç dropdown'u + 🎫 bilet, VM gerçek IP'si de
açıklamaya ekleniyor), `VCenterSummaryCards.tsx` datastore renk
eşikleri (70/85), yeni `guest_reboot` güç eylemi (VMware Tools üzerinden
graceful, sert reset'ten AYRI uç nokta). Kullanıcının "anlık CPU/RAM
%" isteği `AskUserQuestion` ile reddedildi/netleştirildi — vCenter
REST API'sinde bu veri yok, uydurulmadı; web VNC/MKS konsolu da ayrı
bir faza bırakıldı (guacd/RDP büyüklüğünde bir alt sistem). **Gerçek
vCenter'a karşı canlı E2E'de kritik bir hata bulunup düzeltildi:**
`guest/identity.full_name` düz string değil, vSphere REST'in
`LocalizableMessage` yapısı (`{id, default_message, args}`) — mock
testler bunu yakalayamamıştı, gerçek veri `/api/vcenter/vms`'i
TAMAMEN 500'e düşürüyordu. Düzeltme sonrası kullanıcının GERÇEK 14
VM'i, 2 host'u, 4 datastore'u canlıda doğru göründü (gerçek IP/OS/
doluluk verisiyle). Backend 741→755, frontend 434→437 test (`tsc`/
`eslint` temiz).

Faz 74 de tamamlandı: **PAM RDP — Çift Yönlü Pano + Sürücü Yönlendirme
(Dosya Transferi).** `app/pam/guacd.py::drive_config()` (`GUACD_DRIVE_
PATH`, opt-in) + her oturumun kendi `{root}/{session_id}` sürücü
dizini; `disable-copy`/`disable-paste` guacd sürüm varsayımına
BIRAKILMADAN her zaman açık `false`. `infra/docker-compose.yml`'e
`pam-drives` bind mount. Frontend `GuacamoleRdpViewer.tsx`: `onclipboard`
(uzak→yerel pano, `navigator.clipboard.writeText()` dener) + sürükle-
bırak/buton ile GERÇEK dosya yükleme (`Guacamole.Object.
createOutputStream`+`BlobWriter`) + "Dosya Transferi" durum paneli.
**Bilinçli daraltma:** uzak dizin gezme/indirme bu artırıma DAHİL
DEĞİL (yalnızca yükleme). GPO gereksinimi kod DEĞİL, `docs/
decisions.md` §20'de belgelendi. Backend 10 yeni guacd handshake testi.
**Canlı deployment YAPILMADI** — `disable-copy`/`disable-paste`
düzeltmesi kod-only restart ile hemen etkili olur, `GUACD_DRIVE_PATH`
kullanıcının `.env`'ine eklemesini bekliyor (opt-in).

Faz 75 de tamamlandı: **PAM Oturum Kaydı — İnaktif Süre Atlama.**
Kullanıcının varsaydığı "guacd inaktivite suppression parametresi"
GERÇEKTE YOK (protokol zaten olay-güdümlü) — UYDURULMADI, bunun yerine
`app/pam/recording_analysis.py::extract_idle_gaps()` kayıttaki GERÇEK
`sync` zaman damgalarından uzun boşlukları çıkarıyor (`GET /api/pam/
audit/{id}/idle-gaps`, Faz 53'ün `activity-markers`'ıyla AYNI desen).
`SessionReplayModal.tsx`: zaman çubuğunda soluk bant + "İnaktif
Süreleri Atla" checkbox'ı (varsayılan açık) — Faz 73'ün
`virtualPositionRef` mekanizmasını YENİDEN YAZMADAN hedefi boşluğun
bitişine sıçratıyor. `guacenc`/`ffmpeg`/`mpdecimate` MP4 post-processing
madde 3 bu projede hiç yok (Faz 50 kararı, kayıt `.guac` kalıyor) —
kapsam dışı. Backend 14 yeni test (tam paket 811/815, 4 önceden bilinen
ortam hatası), frontend 437/437 (`tsc`/`eslint` temiz). **Canlı
deployment YAPILMADI** — şema gerektirmiyor, kullanıcı onayı bekliyor.

Faz 75 sonrası bir UX düzeltmesi de tamamlandı — kullanıcı canlı
oynatma ekran görüntüsüyle bildirdi: "İnaktif Süreleri Atla" checkbox'ı
KALDIRILDI, kullanıcıya SORULMADAN her zaman uygulanıyor (`skipIdle`
state'i/toggle'ı silindi, `tick()` idle-gap atlamasını koşulsuz
yapıyor). Frontend `tsc`/`eslint` temiz.

Faz 74 sonrası bir dağıtım düzeltmesi de tamamlandı: bu makinede
ilgisiz bir başka Docker projesi (`securetransfer-backend-1`) de
port 8000'i (host publish) kullanıyordu — Next.js'in sunucu-taraflı
`/api/*` proxy'si (`next.config.ts`, `localhost:8000`) Docker'ın
loopback port yönlendirmesi yüzünden YANLIŞ konteynere gidiyordu, web
arayüzü tüm kullanıcılar için kırıktı (gerçek Windows Agent'lar LAN IP
üzerinden doğrudan bağlandığı için ETKİLENMEMİŞTİ). Kullanıcı onayıyla
backend portu 8000'de KORUNDU (hiçbir agent yeniden yapılandırılmadı)
— yalnızca `apps/web/.env.local`'e `BACKEND_INTERNAL_URL=http://
10.0.213.30:8000` (LAN IP, Docker'ın loopback proxy'sini bypass eder)
eklenip frontend yeniden başlatıldı. Ayrıca `docker compose up -d`
komutumun (yalnızca `guacd`'yi yeniden oluşturmak için) beklenmedik
şekilde ek, boş bir `itops-db` konteyneri de oluşturduğu fark edildi
— gerçek veriye dokunmadığı doğrulandı (canlı `assets`/`users` sayıları
değişmedi), ama durdurma/kaldırma girişimim otomatik onay
sınıflandırıcısı tarafından engellendi — kullanıcıya bildirilip karar
kendisine bırakıldı.

Faz 76 de tamamlandı: **PAM Web Konsolu — Zero-Knowledge HTTPS Kimlik
Enjeksiyonu.** Kullanıcının açık isteğiyle (Firewalla gibi yalnızca
web arayüzü olan cihazlar için RDP/SSH'daki AYNI zero-knowledge
erişim), Faz 61'in bilinçli olarak ertelediği "Web Konsolu" özelliği
tamamlandı — `AskUserQuestion` ile TAM zero-knowledge kimlik enjeksiyonu
(basit tünel DEĞİL) + ilk sürüm yalnızca Firewalla + HTML form-login
(Basic Auth DEĞİL) onaylandı. `app/pam/web_console.py` — kendi yazılan,
BİLİNÇLİ olarak dar kapsamlı ters proxy (RDP'nin hazır guacd'si gibi
bir motor YOK): giriş sayfasını GET edip gizli alanları toplar, kimlik
bilgisini sunucu tarafında POST eder, dönen çerezlerle sonraki istekleri
yönlendirir, kök-göreli linkleri proxy önekine yeniden yazar (best-
effort regex — tam SPA uyumluluğu YOK, dürüst bir sınır). Giriş
formunun alan adları koda UYDURULMADI — `pam_web_console_profiles`
tablosunda Admin tarafından gerçek cihaza bakılarak yapılandırılıyor.
Yeni `pam_access_rules.allow_web` (allow_rdp/allow_ssh ile aynı yerde),
`AssetDetails.tsx`/`PamRulesPanel.tsx`/`MyAccessPanel.tsx`'in HER
ÜÇÜNDE de RDP/SSH ile tutarlı "Web Konsolu" erişimi. Backend +20 test,
frontend 437→439 (`tsc`/`eslint` temiz). **Canlı deployment YAPILMADI**
— yeni şema gerektiriyor; giriş formunun gerçek alan adları ancak
gerçek Firewalla'ya karşı canlı denemeyle kesinleşecek (RDP/SNMP/
vCenter fazlarındaki aynı desen — muhtemelen gerçek hatalar bulunup
düzeltilecek).

Faz 10 (Docker — Faz 48'in guacd'si için de aynı engel geçerli) ve
kalan ileri fazlar (Faz 25 LLDP/CDP gerçek implementasyon, Remote
Command Execution + Audit'in geri
kalanı (numaralandırılmamış), Linux Agent packaging (paketlenmiş
binary — kaynak koddan kurulumun AKSİNE), `update_self`/
`uninstall_service`'in gerçek bir cihazda canlı doğrulaması, AI,
genel audit log, genel sayfa API'lerinin backend
yetkilendirmesi, Faz 48'in guacd'ye karşı canlı doğrulaması — Docker/
WSL2 kurulumu kullanıcıyı bekliyor) henüz başlanmadı/tamamlanmadı.
