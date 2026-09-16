# Roadmap — Faz Bazlı Geliştirme Planı

Her faz bağımsız, küçük ve test edilebilir olacak şekilde tasarlanmıştır.
Bir faz tamamlanmadan bir sonrakine geçilmez. Sıra, `architecture.md`
§3'teki veri akışını (CIDR → discovery → enrichment → DB → API →
dashboard) takip eder.

---

## Faz 0 — Mimari & Dokümantasyon

**Durum:** ✅ Tamamlandı

**Amaç:** Projenin mimarisini, kararlarını ve faz planını netleştirmek.

**Kapsam:**
- `docs/architecture.md`, `docs/roadmap.md`, `docs/decisions.md`, `CLAUDE.md`

**Kapsam dışı:** Uygulama kodu, dependency kurulumu, database, Docker,
frontend, backend.

**Değişecek dosyalar:**
- `docs/architecture.md` (yeni)
- `docs/roadmap.md` (yeni)
- `docs/decisions.md` (yeni)
- `CLAUDE.md` (yeni)

**Testler:** Yok (dokümantasyon fazı).

**Tamamlanma kriterleri:**
- Dört doküman da mevcut ve MVP akışını, tech stack'i, faz planını
  eksiksiz kapsıyor.
- Hiçbir kod/dependency/config dosyası oluşturulmamış.

---

## Faz 1 — Proje İskeleti

**Durum:** ✅ Tamamlandı

**Amaç:** Monorepo yapısını, iki paketin (web, api) boş iskeletini ve
minimal health-check uçlarını kurmak.

**Kapsam:**
- `apps/api`: FastAPI uygulaması, tek `GET /health` endpoint'i.
- `apps/web`: Next.js uygulaması, tek statik sayfa ("IT Operations
  Assistant" başlığı).
- Kök seviye `package.json`/workspace config (web için), `apps/api` için
  `requirements.txt` veya `pyproject.toml`.

**Kapsam dışı:** Discovery mantığı, database, Docker, gerçek dashboard
UI, auth.

**Değişecek dosyalar:**
- `apps/api/app/main.py`
- `apps/api/requirements.txt` (veya `pyproject.toml`)
- `apps/web/` (Next.js `create-next-app` çıktısı, minimum haliyle)
- Kök `package.json` (workspace tanımı)

**Testler:**
- `apps/api`: `GET /health` → `200 {"status": "ok"}` (pytest + httpx).
- `apps/web`: sayfa render testi (Testing Library) — başlık metni var mı.

**Tamamlanma kriterleri:**
- `uvicorn app.main:app` çalışır, `/health` 200 döner.
- `npm run dev -w apps/web` çalışır, sayfa açılır.
- İki paket birbirinden bağımsız çalışır (henüz proxy/entegrasyon yok).

---

## Faz 2 — Discovery: ICMP Host Keşfi

**Durum:** ✅ Tamamlandı

**Amaç:** Bir CIDR aralığındaki canlı host'ları ICMP ping sweep ile
bulmak.

**Kapsam:**
- `apps/api/app/discovery/icmp.py`: CIDR alır, canlı IP listesi döner.
- Standalone, DB'ye bağımlı olmayan saf fonksiyon.

**Kapsam dışı:** MAC/hostname/vendor/port/device type, database
yazımı, API endpoint'i.

**Değişecek dosyalar:**
- `apps/api/app/discovery/icmp.py`
- `apps/api/tests/discovery/test_icmp.py`

**Testler:**
- Mock/sahte yanıtlarla: bilinen canlı IP'ler döner mi.
- Geçersiz CIDR girişinde anlamlı hata fırlatır mı.
- Boş sonuç (tüm host'lar down) durumunu doğru işler mi.

**Tamamlanma kriterleri:**
- Fonksiyon izole olarak `pytest` ile test edilebiliyor.
- Gerçek bir yerel ağda manuel çalıştırıldığında en az bir canlı host
  buluyor (manuel doğrulama, otomatik test değil).

---

## Faz 3 — Discovery: ARP MAC Çözümleme

**Durum:** ✅ Tamamlandı

**Amaç:** Faz 2'de bulunan IP'ler için (aynı L2 segmentindeyse) MAC
adresini çözmek.

**Kapsam:**
- `apps/api/app/discovery/arp.py`: IP alır, MAC adresi (varsa) döner.

**Kapsam dışı:** Farklı segmentteki host'lar için MAC çözümü (bilinen
sınırlama olarak dokümante edilir, çözülmeye çalışılmaz).

**Değişecek dosyalar:**
- `apps/api/app/discovery/arp.py`
- `apps/api/tests/discovery/test_arp.py`

**Testler:**
- Mock ARP tablosuyla: bilinen IP → doğru MAC.
- ARP tablosunda olmayan IP → `None`/boş sonuç, hata fırlatmaz.

**Tamamlanma kriterleri:**
- Fonksiyon izole test edilebiliyor.
- Faz 2 çıktısıyla zincirlenip aynı segmentteki bir cihazın MAC'i manuel
  doğrulamada doğru çıkıyor.

---

## Faz 4 — Discovery: DNS Hostname + Vendor (OUI) Lookup

**Durum:** ✅ Tamamlandı

**Amaç:** IP için reverse DNS ile hostname, MAC için OUI veritabanından
vendor bilgisini çözmek.

**Kapsam:**
- `apps/api/app/discovery/dns_lookup.py`: IP → hostname (varsa).
- `apps/api/app/discovery/vendor_lookup.py`: MAC → vendor adı (varsa),
  statik/gömülü bir OUI veri kaynağı kullanır.

**Kapsam dışı:** Harici canlı vendor API'lerine bağımlılık (offline OUI
veri kaynağı tercih edilir).

**Değişecek dosyalar:**
- `apps/api/app/discovery/dns_lookup.py`
- `apps/api/app/discovery/vendor_lookup.py`
- `apps/api/tests/discovery/test_dns_lookup.py`
- `apps/api/tests/discovery/test_vendor_lookup.py`

**Testler:**
- Bilinen IP → beklenen hostname (mock resolver).
- PTR kaydı olmayan IP → `None`, hata fırlatmaz.
- Bilinen OUI önekiyle MAC → doğru vendor adı.
- Bilinmeyen OUI → `None`/"Unknown".

**Tamamlanma kriterleri:**
- İki modül de bağımsız test ediliyor ve dış ağ bağımlılığı olmadan
  (mock ile) çalışıyor.

---

## Faz 5 — Discovery: TCP Port Tarama + Device Type Heuristic

**Durum:** ✅ Tamamlandı

**Amaç:** Açık portları tespit etmek ve toplanan bilgilerden cihaz
tipini tahmin etmek.

**Kapsam:**
- `apps/api/app/discovery/port_scan.py`: IP + port listesi alır, açık
  portları döner (sınırlı, önceden tanımlı yaygın port seti).
- `apps/api/app/discovery/device_classifier.py`: portlar + vendor +
  hostname → tahmini `device_type` (örn. "printer", "server", "unknown").

**Kapsam dışı:** Tüm 65535 portun taranması, derin servis parmak izi
(banner grabbing ötesi analiz), makine öğrenmesi tabanlı sınıflandırma.

**Değişecek dosyalar:**
- `apps/api/app/discovery/port_scan.py`
- `apps/api/app/discovery/device_classifier.py`
- `apps/api/tests/discovery/test_port_scan.py`
- `apps/api/tests/discovery/test_device_classifier.py`

**Testler:**
- Mock socket ile: açık/kapalı port doğru ayrıştırılıyor mu.
- Timeout durumunda port "kapalı/erişilemez" sayılıyor mu.
- Bilinen port+vendor kombinasyonları için classifier doğru tip
  döndürüyor mu (örn. 9100 açık + vendor "HP" → "printer").
- Eşleşme yoksa `"unknown"` dönüyor mu.

**Tamamlanma kriterleri:**
- Faz 2–5 zincirlenip tek bir CIDR için uçtan uca (DB'siz, bellekte)
  bir sonuç listesi üretilebiliyor; manuel script ile doğrulanıyor.

---

## Faz 6 — Database Katmanı

**Durum:** ✅ Tamamlandı — planlanandan farklı bir tasarımla (aşağıya
bakın).

**Amaç:** Keşfedilen veriyi PostgreSQL'de kalıcı hale getirmek.

**Gerçekleşen kapsam:** Bu fazın orijinal taslağı ayrı `scans`,
`devices`, `device_ports` tabloları öngörüyordu. Bunun yerine **tek bir
`assets` tablosu** (IP başına tek, upsert'lenen satır) uygulandı — bkz.
`architecture.md` §7 ve gerekçesi için `decisions.md`. Bağlantı
yönetimi ve repository fonksiyonları tek tabloya karşılık geldiği için
genel bir `Repository<T>` soyutlaması yok (`decisions.md` §3'e uygun).

**Gerçekleşen dosyalar:**
- `apps/api/app/db/connection.py` — `DATABASE_URL`, `check_db_connection`
- `apps/api/app/db/assets.py` — şema (`infra/postgres/init.sql`'den
  okunur, `ensure_schema` ile idempotent uygulanır), `upsert_asset`,
  `get_asset_by_ip`, `list_assets`
- `infra/postgres/init.sql` — `assets` şeması, tek doğruluk kaynağı
- `apps/api/tests/db/` (gerçek PostgreSQL'e karşı testler)

**Testler:** Migration temiz bir veritabanında ve tekrar çalıştırıldığında
hatasız çalışıyor; upsert CRUD senaryoları (insert/update/NULL alan
davranışı/JSONB round-trip/SQL injection güvenliği/transaction rollback);
aynı IP tekrar keşfedildiğinde `last_seen`/`updated_at` güncelleniyor,
yeni satır açılmıyor — gerçek PostgreSQL 16.15 üzerinde doğrulandı.

---

## Faz 7 — Backend API

**Durum:** ✅ Tamamlandı — planlanandan farklı endpoint isimleriyle
(aşağıya bakın).

**Amaç:** Discovery + DB katmanlarını REST API olarak dışa açmak.

**Gerçekleşen kapsam:** Orijinal taslaktaki `/discovery/scans` ve
`/devices` endpoint'leri yerine gerçek implementasyon: `POST
/api/discovery/icmp` (zaten Faz 1-5 sırasında eklenmişti, bu fazda
DB'ye yazma davranışı eklendi) ve `GET /api/assets` (bkz.
`architecture.md` §6). Tarama senkron çalıştığı için ayrı bir "scan
durumu" kaynağına ihtiyaç duyulmadı. Endpoint başına bir router dosyası
prensibi korundu.

**Gerçekleşen dosyalar:**
- `apps/api/app/routes/discovery.py` — `POST /api/discovery/icmp` +
  `persist_scan_result` (discovery→DB köprüsü)
- `apps/api/app/routes/assets.py` — `GET /api/assets` + `AssetResponse`
  şeması
- `apps/api/app/routes/health.py` — `GET /api/health`, `GET /api/health/db`
- `apps/api/app/main.py` (router kayıtları)
- `apps/api/tests/routes/`, `apps/api/tests/db/test_discovery_persistence.py`,
  `apps/api/tests/test_assets_api.py`, `apps/api/tests/test_health*.py`

**Testler:** Her endpoint için başarılı yanıt ve hata durumu testleri
(FastAPI `TestClient`); geçersiz CIDR → `400`; DB erişilemezse → `503`;
discovery→DB entegrasyonunun host bazında hata izolasyonu — gerçek
PostgreSQL 16.15 üzerinde doğrulandı.

**Tamamlanma kriterleri:** Tüm endpoint'ler OpenAPI şemasında
görünüyor (`/docs`); uçtan uca: CIDR gönder → tarama tetiklenir → UP
host'lar DB'ye yazılır → sonuç `GET /api/assets` ile okunabilir
(manuel ve otomatik olarak doğrulandı).

---

## Faz 8 — Frontend: Asset Inventory

**Durum:** ✅ Tamamlandı — ayrı sayfa yerine ana sayfada component
olarak (aşağıya bakın).

**Amaç:** Keşfedilen cihazları (asset'leri) listeleyen temel
dashboard'u kurmak.

**Gerçekleşen kapsam:** Orijinal taslak ayrı `/devices` liste ve detay
sayfaları öngörüyordu. Bunun yerine `AssetInventory` component'i
mevcut ana sayfaya (`apps/web/app/page.tsx`) `NetworkDiscovery`'nin
altına eklendi — proje henüz çok sayfalı bir routing yapısına
geçmedi, tek sayfa üzerinde component'ler yeterli. Detay sayfası
(port listesi zaten Asset Inventory tablosunda "Open Ports" kolonunda
gösteriliyor) henüz yok.

**Gerçekleşen dosyalar:**
- `apps/web/components/AssetInventory.tsx`
- `apps/web/lib/api.ts` (`Asset` tipi, `fetchAssets()`)
- `apps/web/app/page.tsx` (component eklendi)
- `apps/web/tests/AssetInventory.test.tsx`

**Testler:** Mock API yanıtıyla liste render, çoklu asset, NULL alan
(`-`), open_ports serileştirme, loading/empty/error state, refresh —
`vitest` ile (bkz. `CLAUDE.md` Test Kuralları: API çağrıları mock'lanır).

**Tamamlanma kriterleri:** Gerçek backend'e karşı manuel olarak
tarayıcıda doğrulandı — cihaz listesi görüntülenebiliyor.

---

## Faz 9 — Frontend: Tarama Tetikleme UI

**Durum:** ✅ Tamamlandı — Faz 1 sırasında temel iskeleti eklenmiş,
Faz 6-7'de gerçek DB entegrasyonuyla tamamlanmıştı; ayrı sayfa yerine
ana sayfada component olarak (aşağıya bakın).

**Amaç:** Kullanıcının CIDR girip tarama başlatabilmesini ve durumu
takip edebilmesini sağlamak.

**Gerçekleşen kapsam:** Orijinal taslak ayrı bir `/scan` sayfası
öngörüyordu. Bunun yerine `NetworkDiscovery` component'i ana sayfada;
CIDR giriş formu + doğrulama + tarama durumu (scanning/done/error)
zaten mevcuttu. Gerçek zamanlı (WebSocket) ilerleme yok — tarama zaten
senkron bir HTTP isteği olarak tamamlanıyor, polling'e de gerek
kalmadı.

**Gerçekleşen dosyalar:**
- `apps/web/components/NetworkDiscovery.tsx`
- `apps/web/lib/api.ts` (`scanNetwork()`)
- `apps/web/tests/NetworkDiscovery.test.tsx`

**Testler:** Geçersiz CIDR'de form hata gösteriyor mu; geçerli CIDR'de
API çağrısı doğru payload ile yapılıyor mu (mock); tarama sonucu
tabloda gösteriliyor mu — `vitest` ile.

**Tamamlanma kriterleri:** Uçtan uca manuel akış doğrulandı: CIDR gir
→ tarama başlat → sonuç tabloda görünür → aynı taramada bulunan UP
host'lar Asset Inventory'de de görünür (Faz 8 ile birlikte).

---

## Faz 10 — Docker & Orkestrasyon

**Durum:** ⏳ Beklemede — henüz başlanmadı

**Amaç:** Tüm sistemi (web, api, db) Docker Compose ile ayağa
kaldırılabilir hale getirmek.

**Kapsam:**
- `apps/api/Dockerfile`, `apps/web/Dockerfile`, `docker-compose.yml`.
- Discovery Engine'in ihtiyaç duyduğu ağ yetkileri (`NET_RAW`/host
  network) için açık, dokümante edilmiş container config'i (bkz.
  `decisions.md` §6).

**Kapsam dışı:** Production orchestration (Kubernetes vb.), CI/CD.

**Değişecek dosyalar:**
- `apps/api/Dockerfile`
- `apps/web/Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

**Testler:**
- `docker compose up` sonrası `/health` ve dashboard erişilebilir mi
  (manuel/smoke test).
- Container içinden gerçek bir ping sweep çalışıyor mu (ağ yetkisi
  doğrulaması).

**Tamamlanma kriterleri:**
- Tek komutla (`docker compose up`) tüm sistem ayağa kalkıyor ve MVP
  akışı (CIDR → dashboard) uçtan uca çalışıyor.

---

## Faz 10.1 — Scan History, Network Topology & Dashboard UI

**Durum:** ✅ Tamamlandı — Faz 10'dan (Docker, beklemede) bağımsız
olarak, MVP dashboard'unun doğal bir uzantısı olarak erken tamamlandı.

**Amaç:** Discovery taramalarının geçmişini kalıcı hale getirmek,
keşfedilen asset'leri görsel bir topoloji olarak sunmak ve dashboard'u
sol navigasyonlu, çok sayfalı bir arayüze dönüştürmek.

**Gerçekleşen kapsam:**
- **Scan History:** Yeni `scans` tablosu (bkz. `architecture.md` §7) —
  her `POST /api/discovery/icmp` çağrısı best-effort bir `running` kaydı
  açar, sonuçta `completed`/`failed` olarak günceller. `GET /api/scans`
  ile okunur. Scan history yazımı discovery'nin ana işlevini asla
  bloke etmez (DB erişilemezse veya yazım başarısız olursa yalnızca
  loglanır, response değişmez).
- **Network Topology:** Yeni `/topology` sayfası — `GET /api/assets`
  verisini device-type'a göre (Infrastructure/Network Devices/
  Servers/Endpoints/Other) gruplandırıp görsel node'lar olarak çizer.
  Gerçek bağlantı (edge) verisi olmadığı için node'lar arası bağlantı
  **uydurulmadı** — yalnızca "Topology relationships are not yet
  available" notu ve device-type bazlı görsel gruplama var. Node
  tıklamaları mevcut `AssetDetails` drawer'ını yeniden kullanır (yeni
  bir detay paneli oluşturulmadı). Zoom/pan/reset düz CSS transform +
  mouse event'leriyle uygulandı — yeni bir graph/topology kütüphanesi
  **eklenmedi**.
- **Sidebar navigasyonu:** `apps/web/app/layout.tsx`'e sol sidebar +
  üst header eklendi (Dashboard/Network Discovery/Network Topology/
  Recent Scans/Asset Inventory + "Coming Soon" olarak işaretli
  Monitoring/SNMP/AI Assistant/Settings). Mobilde hamburger menüye
  dönüşür.
- **Recent Scans:** `NetworkDiscovery`, başarılı taramadan sonra
  `window.dispatchEvent(new CustomEvent("network-scan-completed"))`
  tetikler; `RecentScans` bu event'i dinleyip kendini yeniler — yeni
  bir state yönetim kütüphanesi eklenmeden.
- Dashboard renk paleti genişletildi (cyan/violet accent'ler, durum
  renkleri) — mevcut CSS custom property deseni korunarak.

**Değişen/yeni dosyalar:**
- `infra/postgres/init.sql` (scans tablosu eklendi, assets'e dokunulmadı)
- `apps/api/app/db/scans.py`, `apps/api/app/routes/scans.py`
- `apps/api/app/routes/discovery.py` (best-effort scan history entegrasyonu)
- `apps/web/app/layout.tsx`, `apps/web/app/topology/page.tsx`
- `apps/web/components/Sidebar.tsx`, `TopHeader.tsx`, `RecentScans.tsx`,
  `NetworkTopology.tsx` (+ ilgili `.module.css` dosyaları)

**Testler:** Backend — gerçek PostgreSQL 16.15 üzerinde repository/API/
şema/discovery-entegrasyon testleri (create/complete/fail scan, sıralama,
503, discovery response'unun DB hatasında bozulmadığı). Frontend —
`vitest` ile RecentScans (loading/empty/error/badge/event-refresh) ve
NetworkTopology (empty state, gerçek asset render, node click, uydurma
bağlantı olmadığının doğrulanması).

**Tamamlanma kriterleri:** `pytest -v`, `npm run test:web`, `npm run
lint`, `npm run build` hepsi geçti; gerçek backend+PostgreSQL ile
tarayıcıda uçtan uca doğrulandı (127.0.0.1/32 taraması → Recent Scans'te
otomatik görünme → Asset Inventory/Topology'de görünme → mevcut gerçek
asset verisine dokunulmadan test verisi temizlendi).

---

## Faz 4.4–4.24 — Advanced NOC Dashboard + SNMP-Ready Backend

**Durum:** ✅ Tamamlandı.

**Amaç:** Mevcut dashboard'u, ileride gerçek bir SNMP ajanına
bağlanmaya mimari olarak hazır, profesyonel bir NOC (Network Operations
Center) paneline dönüştürmek — hiçbir noktada CPU/RAM/sıcaklık/
bant genişliği/uptime/SNMP durumu/topology bağlantısı/alert **uydurmadan**.
Veri yoksa her zaman açık bir "Not monitored" / "No data available" /
"No interface monitoring data available" metni gösterilir.

**Gerçekleşen kapsam:**
- **Dashboard analytics:** `DashboardSummary` 9 karta genişletildi
  (Total/Online/Offline/Unknown/Firewalls/Network Devices/Servers/Open
  Ports/Last Seen). Yeni `InfrastructureHealth` (availability yüzdesi),
  `DeviceDistribution` (device-type dağılımı), `OpenPortsOverview`
  (port → risk sınıflandırması, tek doğruluk kaynağı `lib/portRisk.ts`)
  eklendi. `RecentActivity` gerçek `assets`+`scans` verisinden olay
  akışı üretecek şekilde yeniden yazıldı (`lib/activity.ts`).
- **Scan detayları:** `ScanDetails` drawer'ı (`AssetDetails`'le aynı
  desen) + `RecentScans`'e tıklanabilir satırlar eklendi.
- **Topology 2.0:** `NetworkTopology`'ye arama (IP/hostname/MAC/vendor),
  status filtresi ve device-type filtresi eklendi; üst istatistik satırı
  bilinçli olarak filtrelenmemiş tam asset listesinden hesaplanmaya
  devam ediyor (KPI'lar global kalır, canvas filtrelenir).
- **Asset Details 2.0:** `AssetDetails` paneli sekmelere ayrıldı
  (Overview/Network/Discovery/Ports/Monitoring — ARIA `tablist`/`tab`/
  `tabpanel` ile). Ports sekmesi `classifyPortRisk` ile risk rozeti
  gösterir. Monitoring sekmesi SNMP Status/CPU/Memory/Uptime/
  Temperature/Network Interfaces için **her zaman** "Not monitored" /
  "No data available" / "No interface monitoring data available"
  gösterir — henüz hiçbir SNMP ajanı olmadığı için.
- **SNMP-ready backend mimarisi (gerçek ajan olmadan):**
  `apps/api/app/snmp/` paketi — `oid_map.py` (MIB-II/IF-MIB standart
  OID'leri: sysName/sysDescr/sysObjectID/sysUpTime, ifName/ifDescr/
  ifOperStatus/ifAdminStatus/ifSpeed/ifInOctets/ifOutOctets),
  `models.py` (`SystemInfo`/`InterfaceInfo`/`SNMPPollResult` Pydantic
  modelleri), `bandwidth.py` (iki ardışık counter örneğinden bps
  hesabı; negatif delta = counter rollover → asla tahmini bir hız
  üretmez, `None` döner). `pysnmp` gibi gerçek bir SNMP kütüphanesi
  **eklenmedi** — henüz canlı bir ajan yok, gerçek polling yapılmadı
  (bkz. `decisions.md`). `POST /api/snmp/poll/{asset_id}` endpoint'i
  eklendi; asset var olsa bile SNMP credential/community henüz
  tanımlı olmadığından yanıt her zaman dürüstçe
  `status: "not_configured"` döner — `system`/`interfaces` asla
  doldurulmaz.
- **Alert Foundation:** `lib/alerts.ts` — gerçek `assets` verisinden
  `device_down` (CRITICAL), `high_latency` (>100ms, WARNING),
  `high_risk_port` (WARNING) alert'leri üretir. `interface_down` ve
  `snmp_poll_failure` kuralları **tanımlı ama hiç tetiklenmez** — bu
  ikisinin gerçek bir veri kaynağı (SNMP) henüz yok. Yeni
  `AlertsPanel` component'i + Sidebar'a gerçek "Alerts" linki
  (`/#alerts`) eklendi.
- **Erişilebilirlik:** ikon-only butonlarda `aria-label`, form
  input'larında `<label>`/`aria-label`, `AssetDetails` sekmelerinde tam
  ARIA tabs deseni (`role="tablist"`/`"tab"`/`"tabpanel"` +
  `aria-controls`/`aria-labelledby`), tek `<h1>` + tutarlı `<h2>`
  hiyerarşisi doğrulandı.
- **Responsive doğrulama:** 1440/1024/768/375px'de hem `/` hem
  `/topology` sayfalarında `document.body.scrollWidth ===
  window.innerWidth` (yatay taşma yok) gerçek tarayıcıda doğrulandı.
- **Performans ölçümü (optimize edilmedi, bkz. `decisions.md` §9):**
  tek dashboard yüklemesinde 7 component'in bağımsız `GET /api/assets`
  çağırdığı ölçüldü; veri seti küçük olduğu için şimdilik dokunulmadı,
  gerekçe ve gelecekteki tetikleyici koşul dokümante edildi.

**Bilinçli olarak yapılmayanlar:**
- Gerçek bir SNMP client/kütüphane entegrasyonu (agent yok).
- SNMP credential/community string için kalıcı bir DB tablosu — güvenlik
  açısından erken bir karar olacağından, gerçek bir ajan devreye
  girmeden tasarlanmadı.
- Dashboard veri getirme katmanının paylaşılan cache/context'e taşınması
  (ölçüldü, şimdilik gerek görülmedi).

**Değişen/yeni dosyalar (özet):**
- Backend: `apps/api/app/snmp/{__init__,models,oid_map,bandwidth}.py`,
  `apps/api/app/routes/snmp.py`, `apps/api/app/db/assets.py`
  (`get_asset_by_id` eklendi), `apps/api/tests/snmp/`,
  `apps/api/tests/test_snmp_api.py`, `apps/api/tests/conftest.py`
  (`.env` yükleme sırası düzeltmesi — bkz. testler notu).
- Frontend: `apps/web/lib/{health,portRisk,time,activity,alerts}.ts`,
  `apps/web/components/{InfrastructureHealth,DeviceDistribution,
  OpenPortsOverview,ScanDetails,AlertsPanel}.tsx` (+ `.module.css`),
  `AssetDetails.tsx`/`NetworkTopology.tsx`/`RecentActivity.tsx`/
  `RecentScans.tsx`/`DashboardSummary.tsx`/`Sidebar.tsx`/`page.tsx`
  güncellendi, ilgili tüm `apps/web/tests/*.test.tsx` dosyaları.

**Testler:** Backend `pytest -v` — 153+ test (SNMP models/oid_map/
bandwidth, `POST /api/snmp/poll` başarı/404/422/503, `get_asset_by_id`)
gerçek PostgreSQL üzerinde. Frontend `npm run test:web` — 110 test
(yeni component'lerin her biri için loading/empty/error/success/
interaction durumları, `computeAlerts` kural bazlı testler, Sidebar
mobil menü etkileşimi).

**Tamamlanma kriterleri:** `pytest -v`, `npm run test:web`, `npm run
lint`, `npm run build` hepsi geçti; gerçek backend+PostgreSQL ile
tarayıcıda uçtan uca doğrulandı — gerçek `10.0.213.0/24` ve
`127.0.0.1/32` taramaları, Topology filtreleri, Asset Details
sekmeleri (Ports risk rozetleri, Monitoring'in her zaman "no data"
göstermesi), Active Alerts'in gerçek yüksek-riskli port/latency/down
durumlarından tetiklenmesi, 1440/1024/768/375px'de taşma olmaması.
Test suite'in kendi `TRUNCATE` fixture'larının (bkz.
`tests/test_assets_api.py`, `tests/test_scan_history_integration.py`)
canlı dev veritabanını temizlediği gözlemlendi; gerçek asset verisi
gerçek bir tarama ile geri yüklendi (test verisi silinmedi/uydurulmadı
— gerçek 127.0.0.1/32 ve 10.0.213.0/24 taramaları tekrar çalıştırıldı).

---

## Faz 5 — Dashboard Data Architecture

**Durum:** ✅ Tamamlandı.

**Amaç:** Faz 4.21'de ölçülen (7 bağımsız `GET /api/assets` + 2
bağımsız `GET /api/scans` çağrısı, tek dashboard yüklemesinde)
duplicate fetch sorununu, yeni bir dependency eklemeden, paylaşımlı bir
frontend veri katmanıyla çözmek.

**Gerçekleşen kapsam:** `apps/web/lib/DashboardDataProvider.tsx` — React
`Context` tabanlı `DashboardDataProvider` + `useDashboardData()` hook'u.
Kök `app/layout.tsx`'e bağlandı (tüm sayfalar için tek instance).
`DashboardSummary`, `InfrastructureHealth`, `AlertsPanel`,
`DeviceDistribution`, `OpenPortsOverview`, `RecentActivity`,
`RecentScans`, `AssetInventory`, `NetworkTopology` bağımsız fetch'lerini
bırakıp context'i tüketecek şekilde güncellendi.
`network-scan-completed` event dinleyicisi tek noktaya taşındı. Detaylı
gerekçe ve ölçüm sonuçları `docs/decisions.md` §9'da.

**Değişen/yeni dosyalar:** `apps/web/lib/DashboardDataProvider.tsx`
(yeni), `apps/web/app/layout.tsx`, yukarıdaki 9 component, ilgili tüm
`apps/web/tests/*.test.tsx` dosyaları + yeni `apps/web/tests/testUtils.tsx`
(`mockAssetsAndScans`/`renderWithDashboardData` paylaşımlı test
yardımcıları).

**Testler:** Mevcut 110 frontend testinin tamamı `DashboardDataProvider`
ile sarmalanarak (`renderWithDashboardData`) çalışacak şekilde
güncellendi — her component'in kendi render/loading/empty/error/success
testleri korundu, yalnızca fetch mekanizması değişti.

**Tamamlanma kriterleri:** `npm run test:web` (110/110), `npm run lint`,
`npm run build` geçti; gerçek tarayıcıda `read_network_requests` ile
doğrulandı — dashboard yüklemesinde `GET /api/assets` 7'den 1'e düştü,
`/` → `/topology` client-side navigasyonunda ek istek atılmadı.

---

## Faz 6 — Advanced NOC Dashboard

**Durum:** ✅ Tamamlandı (SNMP verisine bağlı olmayan kısımlar).

**Amaç:** Dashboard'u gerçek bir NOC ekranına yaklaştırmak: cihaz
sağlığı sınıflandırması, SNMP kapsama özeti, alert özeti ve ağ
performansı bölümleri.

**Gerçekleşen kapsam:**
- `DeviceHealthSummary` — `lib/deviceHealth.ts`: Critical (down),
  Warning (up + en az bir WARNING alert'i var), Healthy (up, alert yok),
  Unmonitored (= toplam asset sayısı, çünkü hiçbir asset için SNMP
  yapılandırılmadı). Hepsi gerçek `assets`+`alerts` verisinden.
- `MonitoringCoverage` — `lib/monitoringCoverage.ts`: Total/SNMP
  Enabled (her zaman 0)/SNMP Disabled (= total)/Unreachable (= down
  sayısı). SNMP profil/credential özelliği henüz yok; bu sayılar
  uydurulmadı, mimari gerçeği yansıtıyor.
- `AlertsPanel`'e Critical/Warning/Info sayı özeti eklendi (mevcut
  `computeAlerts` çıktısından, yeni bir hesaplama gerekmedi).
- `NetworkPerformance` — Network Load + Top Talkers, ikisi de her zaman
  "No interface monitoring data available." (SNMP interface verisi yok).

**Bilinçli olarak yapılmayanlar (gerekçeli):**
- **Device Health Matrix (cihaz başına ayrı tablo):** `AssetInventory`
  ve `NetworkTopology` zaten her cihazın gerçek UP/DOWN durumunu
  gösteriyor; ayrı, kısmen çakışan bir tablo eklemek "mevcut çalışan
  UI'ları yeniden yazma" kuralına aykırı olurdu. Bunun yerine
  `DeviceHealthSummary` fleet-seviyesinde bir özet sağlıyor.
- **Infrastructure Events (cihaz up/down GEÇİŞ olayları):**
  `RecentActivity` zaten gerçek scan completed/failed + asset
  discovered/updated olaylarını gösteriyor. Ancak "cihaz X DOWN oldu"
  gibi gerçek bir *durum geçişi* olayı, geçmiş durumun saklanmasını
  gerektirir (örn. bir `status_history` tablosu) — bu, CLAUDE.md'nin
  "yeni tablolar gerekiyorsa önce mimari karar ver" kuralı gereği
  burada tek taraflı eklenmedi. İhtiyaç netleşirse ayrı bir faz olarak
  planlanmalı.

**Değişen/yeni dosyalar:** `apps/web/lib/{deviceHealth,monitoringCoverage}.ts`,
`apps/web/components/{DeviceHealthSummary,MonitoringCoverage,
NetworkPerformance}.tsx` (+ `.module.css`), `AlertsPanel.tsx`/`.module.css`
güncellendi, `app/page.tsx`, ilgili `apps/web/tests/*.test.tsx`.

**Testler:** `npm run test:web` — 134 test (yeni 3 component'in her biri
için loading/empty/error/success), lint/build geçti.

**Tamamlanma kriterleri:** Gerçek tarayıcıda doğrulandı — gerçek 13
asset üzerinden Device Health/Monitoring Coverage/Alert Overview/Network
Performance bölümleri doğru render oluyor, 1280px ve 375px'de taşma yok.

---

## Faz 7 — Real SNMP Foundation (yalnızca mimari)

**Durum:** ✅ Tamamlandı — kapsam kullanıcı onayıyla mimariye
daraltıldı (bkz. `docs/decisions.md` §10).

**Amaç:** Gerçek bir SNMP ajanı geldiğinde kullanılacak credential/
profil sözleşmesini, hiçbir secret değeri veya yeni dependency
eklemeden tasarlamak.

**Gerçekleşen kapsam:** `apps/api/app/snmp/credentials.py` —
`SNMPProfile` (v2c/v3, v1 yok), yalnızca credential *referansları*
taşıyor (gerçek değer değil). `SNMPVersion` `Literal["v2c", "v3"]`
olarak genişletildi (`models.py`).

**Bilinçli olarak yapılmayanlar:** `pysnmp` (veya başka bir SNMP
kütüphanesi) eklenmedi; kalıcı bir `snmp_profiles` DB tablosu
oluşturulmadı (yalnızca planı `decisions.md`'de var); `client.py`/
`poller.py`/`exceptions.py` henüz yok — bunlar gerçek bir kütüphane
seçilmeden anlamlı bir şekilde yazılamaz.

**Testler:** `tests/snmp/test_credentials.py` — v2c/v3 zorunlu alan
doğrulaması, model'in hiçbir plaintext secret alanı taşımadığının
doğrulanması. Backend `pytest -v` — 164 test geçti (bkz. testler notu,
1 bilinen test-sıralama artefaktı hariç).

**Sonraki adım:** Kullanıcı gerçek bir SNMP ajanı/cihaz bilgisi
verdiğinde — Faz 8+ (Polling Engine, System MIB, Interface Monitoring,
Monitoring Database) buradan devam eder.

---

## Faz 20 — Search / Filter / Drilldown

**Durum:** ✅ Tamamlandı. SNMP'ye bağlı olmadığı için Faz 8-19'dan önce,
kullanıcı onayıyla (bkz. Faz 7 notu) sırayla ele alındı.

**Amaç:** Herhangi bir sayfadan cihaz aramak ve bir cihazdan
Dashboard → Alerts → Topology arası gezinebilmek.

**Gerçekleşen kapsam:**
- `GlobalSearch` — `TopHeader`'a eklendi (tüm sayfalarda görünür, çünkü
  `layout.tsx`'te). IP/hostname/MAC/vendor/device type/status'a göre
  gerçek zamanlı arama; sonuç seçilince mevcut `AssetDetails` paneli
  açılır (yeni bir detay bileşeni yazılmadı).
- `AssetDetails`'e yeni bir **Alerts** sekmesi eklendi —
  `computeAlerts([asset])` ile yalnızca o cihaza ait gerçek alert'leri
  gösterir (alert yoksa "No active alerts for this device.").
- `AssetDetails`'e **"View in Topology"** linki eklendi
  (`/topology?ip=<ip>`). `NetworkTopology`, `useSearchParams()` ile
  `ip` parametresini okuyup arama kutusunu dolduruyor ve o cihazın
  detay panelini otomatik açıyor (bir kere uygulanır — panel kapatılırsa
  arka planda asset listesi yenilense bile tekrar açılmaz).

**Değişen/yeni dosyalar:** `apps/web/components/GlobalSearch.tsx` (+
`.module.css`), `TopHeader.tsx`, `AssetDetails.tsx`/`.module.css`,
`NetworkTopology.tsx`, `app/topology/page.tsx` (`useSearchParams` için
`Suspense` sınırı eklendi), ilgili testler.

**Testler:** `npm run test:web` — 143 test (GlobalSearch: bulma/no-match/
seçim; AssetDetails: Alerts sekmesi + Topology linki; NetworkTopology:
deep-link ile arama+detay paneli otomatik açılması).

**Tamamlanma kriterleri:** Gerçek tarayıcıda uçtan uca doğrulandı —
gerçek "DC01" araması gerçek cihazı buluyor, Alerts sekmesi o cihaza
özel gerçek alert'leri gösteriyor, "View in Topology" tıklanınca
`/topology?ip=...`'a gidip arama kutusunu dolduruyor ve doğru cihazın
detay panelini açıyor; 1280px ve 375px'de taşma yok.

**Ek:** `GET /api/health/snmp` eklendi (Faz 24'ün küçük, SNMP'ye bağlı
olmayan bir parçası) — her zaman dürüstçe `{"snmp": "not_configured"}`
döner.

**Test altyapısı düzeltmesi:** `tests/db/test_scans.py::
test_list_scans_returns_empty_list_when_no_scans` tekrarlayan bir
şekilde flaky'di — gerçek tarayıcıda yapılan manuel taramalar `scans`
tablosuna commit edilmiş satırlar bıraktığında, testin varsaydığı "boş
tablo" durumu artık gerçek olmuyordu (bu bir kod hatası değil, test
izolasyon eksikliğiydi). Test artık kendi `db_conn` transaction'ı
içinde açıkça `TRUNCATE TABLE scans` çalıştırıyor (transaction rollback
ile bitiyor, gerçek veriye kalıcı bir etkisi yok) — artık tabloda
gerçek veri olsa bile deterministik geçiyor.

---

## Faz 21 — Frontend NOC Platform Dönüşümü (i18n, gerçek route'lar, tema)

**Durum:** ✅ Tamamlandı.

**Amaç:** Frontend'i, tek sayfada component olarak gösterilen bir
dashboard'dan, gerçek route'lara sahip, Türkçe/İngilizce dil desteği ve
Dark/Light tema seçimi olan profesyonel bir NOC platformuna dönüştürmek.
Mevcut `DashboardDataProvider` (7→1 API çağrısı optimizasyonu), mevcut
alert/health/topology mantığı ve mevcut testler korunarak.

**Gerçekleşen kapsam:**

- **i18n (`apps/web/lib/i18n/`):** `translations.ts` — `tr`/`en` iki
  tam sözlük (nav, common, status, confidence, risk, severity,
  deviceType, dashboard, discovery, assets, assetDetails, topology,
  scans, alerts, monitoring, settings, globalSearch, alertMessages,
  timeAgo). `LocaleProvider.tsx` — React context, varsayılan `tr`,
  seçim `localStorage`'da kalıcı. Hydration mismatch riski yok: sunucu
  ve ilk client render'ı her zaman `tr`; kalıcı seçim yalnızca mount
  sonrası bir `useEffect`'te okunup uygulanıyor (çok kısa bir "tr"
  karesi görünebilir, kabul edilebilir ödünleşim — bkz. dosya içi
  yorum). `lib/alerts.ts` (`computeAlerts`) ve `lib/time.ts`
  (`timeAgo`) artık çeviri sözlüğünü parametre olarak alıyor — saf
  hesaplama katmanı dile bağımlı değil, mesaj metnini çağıran taraf
  enjekte ediyor.
- **Tema sistemi (`apps/web/lib/theme/ThemeProvider.tsx`):** Aynı
  desen — varsayılan `dark`, `localStorage`'da kalıcı,
  `document.documentElement.dataset.theme` ile uygulanıyor.
  `globals.css`'e `:root[data-theme="light"]` ve `:root[data-theme="dark"]`
  açık seçiciler eklendi (var olan `prefers-color-scheme` medya
  sorgusu, açık bir "dark" seçimini asla ezmeyecek şekilde
  `:not([data-theme="dark"])` ile korundu).
- **Gerçek route'lar (Next.js App Router):** `/discovery` (
  `NetworkDiscovery`), `/assets` (`AssetInventory`), `/scans`
  (`RecentScans`, artık opsiyonel `limit` prop'u ile — sayfa `500`
  geçip tüm geçmişi gösteriyor, dashboard widget'ı varsayılan `5`'i
  koruyor), `/alerts` (yeni `AlertsList` — filtre + arama), `/monitoring`
  (yeni `MonitoringOverview` — dürüst placeholder), `/settings` (yeni
  `SettingsPanel` — tema/dil seçimi + gerçek backend/DB/SNMP durum
  kontrolü). `/topology` zaten vardı, değiştirilmedi. `/` (Dashboard)
  artık yalnızca özet/analitik widget'ları gösteriyor;
  `NetworkDiscovery`/`AssetInventory` kendi sayfalarına taşındı.
  Yeni `apps/web/app/shared.module.css` — basit sayfalar için ortak
  `.page` sarmalayıcı stili (Dashboard'un kendi `page.module.css`'i
  ayrı kaldı).
- **Sidebar:** `GENEL / KEŞİF / OPERASYON / SİSTEM` gruplarına
  bölündü, her öğe gerçek bir route; "Coming Soon" listesi kaldırıldı
  (Monitoring/Settings artık gerçek sayfalar). Aktif route
  `aria-current="page"` ile işaretleniyor.
- **GlobalSearch:** Davranışı korundu (sonuç tıklanınca doğrudan
  `AssetDetails` paneli açılıyor — `/assets?search=` yönlendirmesi
  yerine, çünkü bu zaten var olan, doğrulanmış davranıştı ve talimat
  "mevcut davranış bozulmayacak" diyordu). Artık her sayfada
  (`TopHeader`, tüm route'larda ortak) çalışıyor.
- **Header dil seçici:** `LanguageToggle.tsx` — `TopHeader`'da her
  zaman görünür TR|EN butonu.
- **Responsive düzeltme:** `TopHeader`'a `GlobalSearch` + dil seçici +
  backend durumu eklenince 375px'te body 8px taşıyordu (`flex-wrap`
  yoktu) — `topNav`'a `flex-wrap` ve arama kutusuna mobilde tam
  genişlik/ayrı satır (`order: 3`) eklenerek düzeltildi.

**Bilinçli olarak yapılmayanlar:**
- Backend'e dokunulmadı (bu faz yalnızca frontend — talimatın açık
  kısıtı).
- Yeni bir dependency eklenmedi (i18n/tema tamamen mevcut
  React/Next.js primitifleriyle).
- `/assets?search=` query param deep-link'i eklenmedi — mevcut
  GlobalSearch → doğrudan `AssetDetails` davranışı korundu (talimatın
  "mevcut davranışı bozma" kuralı gereği); `/topology?ip=` deep-link'i
  zaten vardı ve dokunulmadan korundu.

**Değişen/yeni dosyalar (özet):** `apps/web/lib/i18n/{translations,
LocaleProvider}.tsx`, `apps/web/lib/theme/ThemeProvider.tsx`,
`apps/web/lib/{alerts,time}.ts` (imza değişikliği), `apps/web/app/
{discovery,assets,scans,alerts,monitoring,settings}/page.tsx`,
`apps/web/app/shared.module.css`, `apps/web/app/page.tsx` (daraltıldı),
`apps/web/app/layout.tsx` (Provider'lar eklendi), `apps/web/app/
globals.css` (açık tema seçicileri), `apps/web/components/
{AlertsList,MonitoringOverview,SettingsPanel,LanguageToggle}.tsx` (+
`.module.css`, yeni), neredeyse tüm mevcut component'ler (çeviri
uygulandı: `DashboardSummary`, `InfrastructureHealth`,
`DeviceHealthSummary`, `MonitoringCoverage`, `AlertsPanel`,
`DeviceDistribution`, `OpenPortsOverview`, `NetworkPerformance`,
`RecentActivity`, `RecentScans`, `ScanDetails`, `AssetDetails`,
`AssetInventory`, `NetworkTopology`, `NetworkDiscovery`, `GlobalSearch`,
`Sidebar`, `TopHeader`, `BackendStatus`), `apps/web/vitest.setup.ts`
(jsdom `localStorage` polyfill — jsdom 27+ `url` verilmeden origin'i
"opaque" sayıp Storage API'yi tamamen kapatıyor; bu, bu fazda ilk kez
`localStorage` kullanan koddan önce hiç ortaya çıkmamış, mevcut bir
jsdom davranışıydı), `apps/web/tests/testUtils.tsx`
(`renderWithProviders`, `LocaleProvider` eklendi), ilgili tüm testler
+ yeni `apps/web/tests/{LocaleProvider,ThemeProvider,AlertsList,
MonitoringOverview,SettingsPanel,LanguageToggle,TopHeader,pages}.test.tsx`.

**Testler:** `npm run test:web` — 180 test (i18n: varsayılan dil,
dil değişimi, kalıcılık, hydration-safe mount; tema: varsayılan dark,
light'a geçiş, kalıcılık; her yeni sayfa için smoke test; mevcut tüm
component testleri Türkçe metne göre güncellendi).

**Tamamlanma kriterleri:** `npm run test:web` (180/180), `npm run
lint`, `npm run build` (8 yeni route dahil tüm sayfalar `○ Static`)
geçti. Gerçek tarayıcıda uçtan uca doğrulandı: `/`, `/discovery`,
`/assets`, `/topology`, `/scans`, `/alerts`, `/monitoring`, `/settings`
gerçek veriyle render oluyor; TR→EN→TR ve Dark→Light→Dark hem UI hem
`localStorage` hem sayfa yenileme sonrası doğrulandı; GlobalSearch her
sayfada çalışıyor; Topology `?ip=` deep-link korunmuş durumda; browser
geri/ileri doğru route'a dönüyor; 1440px ve 375px'te (mobil menü açıkken
dahil) tüm sayfalarda taşma yok; dashboard'da `GET /api/assets`
sayfa başına 1 kez (dev modda StrictMode ile 2) çağrılıyor, sayfalar
arası client-side gezinmede ek çağrı yok.

---

## Faz 22 — Gerçek SNMP Entegrasyonu

**Durum:** ✅ Tamamlandı (SNMPv2c, mock transport ile test edildi;
gerçek cihaz testi kullanıcının vereceği hedefi bekliyor — bkz. altta).

### Faz 22.1 — Ortam keşfi

**Amaç:** Kod yazmadan önce gerçek ortamda bir SNMP ajanı olup olmadığını
doğrulamak (yalnızca yerel/salt-okunur kontroller — ağa hiçbir SNMP
probe'u gönderilmedi).

**Bulgular:** Yerelde çalışan bir SNMP ajanı YOK — Windows `SNMPTrap`
servisi durdurulmuş durumda, `SNMP`/`WMISnmpProvider`/`Server-RSAT-SNMP`
Windows özellikleri devre dışı. `.env`'de SNMP community/credential
tanımlı değil. Var olan discovery port taraması (`port_scan.py`) TCP
tabanlı olduğu için UDP/161'i zaten kapsamıyor. Sonuç: "SNMP agent
bulunamadı" — gerçek bir cihaz/hedef verilene kadar canlı SNMP testi
yapılmadı, yalnızca mock transport ile ilerlendi (aşağıdaki 22.2).

### Faz 22.2 — Gerçek SNMPv2c client (`pysnmp`)

**Amaç:** `apps/api/app/snmp/` altındaki mimariyi (Faz 7) gerçek bir
SNMPv2c client ile tamamlamak — SNMPv3 mimarisi korunuyor ama bu fazda
implemente edilmedi (yarım/aceleye getirilmiş bir v3 yazmamak bilinçli
bir tercih).

**Dependency seçimi:** `pysnmp==7.1.29` (LeXtudio fork, aktif
geliştiriliyor — eski/ölü `pysnmp` 4.x DEĞİL). Python 3.14 için resmi
sınıflandırıcı var, tek runtime bağımlılığı `pyasn1==0.6.4`, BSD-2-Clause
benzeri izin verici lisans. Eklemeden önce `pip install --dry-run` +
PyPI JSON API + GitHub `LICENSE.rst` ile doğrulandı (bkz.
`docs/decisions.md` §10 güncellemesi).

**Gerçekleşen kapsam:**
- `app/snmp/exceptions.py` — `SNMPError` hiyerarşisi (`SNMPTimeoutError`,
  `SNMPAuthenticationError`, `SNMPUnavailableError`,
  `SNMPProtocolError`). pysnmp'nin kendi `ErrorIndication`/exception
  tipleri asla bu modülün dışına (route/log) sızmaz.
- `app/snmp/secrets.py` — `resolve_secret(ref)`: tek, merkezi secret
  çözümleme noktası; yalnızca ortam değişkeni OKUR, hiçbir yerde
  saklamaz/loglamaz.
- `app/snmp/profile_store.py` — `get_profile_for_asset(asset_id)`:
  kalıcı bir credential tablosu YOK (bilinçli, bkz. Faz 7 ve
  `decisions.md` §10); bunun yerine `.env`'deki `SNMP_TARGET_*`
  değişkenleriyle **tek bir**, kullanıcının açıkça verdiği hedefi
  çözer. Eşleşme yoksa (varsayılan durum) `None` döner ve
  `POST /api/snmp/poll/{asset_id}` mevcut `not_configured` davranışını
  korur.
- `app/snmp/client.py` — `SNMPClient.poll_asset(profile, host, asset_id)`:
  pysnmp `Slim` (v1arch/asyncio) API'si üzerine ince katman.
  - System MIB: sysDescr/sysObjectID/sysUpTime/sysName → `SystemInfo`.
  - Interface MIB: önce `ifDescr` subtree'si GETBULK ile dolaşılıp
    mevcut `ifIndex` kümesi keşfedilir, sonra her interface için tüm
    kolonlar (`ifDescr/ifAdminStatus/ifOperStatus/ifSpeed/ifInOctets/
    ifOutOctets/ifName/ifHCInOctets/ifHCOutOctets`) tek bir GET ile
    okunur → `InterfaceInfo`. 64-bit sayaçlar (`ifHCInOctets`/
    `ifHCOutOctets`, ifXTable) mevcutsa tercih edilir, değilse 32-bit'e
    düşülür — hangisinin kullanıldığı `if_counters_64bit` alanında
    açıkça işaretlenir.
  - Bant genişliği: mevcut `bandwidth.py` (rollover-safe delta)
    aynen kullanılıyor; önceki örnek süreç-içi (in-memory,
    `asset_id+ifIndex+yön` anahtarlı) bir önbellekte tutuluyor — ilk
    poll'da baseline olmadığı için `if_in_bps`/`if_out_bps` her zaman
    `None`, ikinci poll'dan itibaren gerçek değer hesaplanıyor.
    Backend yeniden başlarsa önbellek sıfırlanır (bilinen sınırlama).
  - `SNMPPollResult.status` altı değere genişletildi (`models.py`):
    `not_configured` / `unreachable` / `timeout` /
    `authentication_failed` / `success` / `partial` (eskiden yalnızca
    `ok`/`timeout`/`unreachable`/`not_configured` vardı — `ok` →
    `success` olarak yeniden adlandırıldı, iki yeni durum eklendi).
    `duration_ms` alanı eklendi (gerçek poll süresi).
- `POST /api/snmp/poll/{asset_id}` (`app/routes/snmp.py`) güncellendi:
  profil çözülmezse davranış AYNEN korunuyor (`not_configured`); profil
  çözülürse gerçek `SNMPClient.poll_asset` çağrılıyor. Hiçbir SNMP/
  kütüphane hatası sahte bir HTTP 200 "success" olarak gizlenmiyor —
  `status` gerçek sonucu yansıtıyor; beklenmeyen bir istisna bile HTTP
  katmanına çıplak sızmadan dürüst bir `unreachable` sonucuna çevriliyor.

**Credential güvenliği:** Community string hiçbir noktada kaynak koda,
git'e, loga veya API response'una yazılmıyor — yalnızca `resolve_secret()`
üzerinden, poll anında, bellekte okunuyor. Test fixture'larında bile
gerçek bir secret değeri hardcode edilmedi (testler kendi sahte
placeholder değerlerini kullanıyor, `monkeypatch.setenv` ile).

**Bilinçli olarak yapılmayanlar:**
- SNMPv3 implementasyonu (mimari — `SNMPProfile` — hazır, `client.py`
  yalnızca v2c'yi destekliyor; `profile.version != "v2c"` durumunda
  açıkça `SNMPProtocolError`).
- Kalıcı bir `snmp_profiles` DB tablosu — `profile_store.py`'nin
  `.env`-tabanlı tek-hedef çözümü kasıtlı bir ara adım; çoklu-asset
  kalıcı profil yönetimi ayrı bir faz gerektirir (bkz. `decisions.md`
  §10).
- Gerçek cihaza canlı SNMP probe — kullanıcı açıkça bir hedef
  (IP/VERSION/PORT/CREDENTIAL REF) vermedi; CLAUDE.md'nin "örtük/
  otomatik geniş ağ taraması yapılmaz" kuralı SNMP'ye de uygulandı.
- Frontend'de büyük bir değişiklik — `/monitoring` sayfası (Faz 21'de
  zaten bağımsız alt-bölümler halinde kurulmuştu) yapısal olarak zaten
  hazır; gerçek veri bağlanana kadar dürüst "veri yok" metnini
  göstermeye devam ediyor.

**Değişen/yeni dosyalar:** `apps/api/app/snmp/{exceptions,secrets,
profile_store,client}.py` (yeni), `apps/api/app/snmp/{models,oid_map}.py`
(genişletildi — `PollStatus`, `InterfaceInfo.if_counters_64bit/if_in_bps/
if_out_bps`, `ifHCInOctets`/`ifHCOutOctets`), `apps/api/app/routes/
snmp.py` (gerçek client'a bağlandı), `apps/api/requirements.txt`
(`pysnmp==7.1.29`, `pyasn1==0.6.4`), `apps/api/tests/snmp/test_client.py`
(yeni, 20 test), `apps/api/tests/snmp/{test_models,test_oid_map}.py`
(güncellendi), `apps/api/tests/test_snmp_api.py` (2 yeni entegrasyon
testi).

**Testler:** Backend `pytest -v` — 188 test (166 + 22 yeni: `test_client.py`
20 test [başarılı GET, çoklu OID, timeout, retry, auth hatası,
ulaşılamayan cihaz, bozuk yanıt, sysName/sysUpTime parsing, interface
parsing, admin/oper status, 64-bit sayaç, bant genişliği hesabı, counter
rollover, ilk poll davranışı, secret log'da/response'ta hiç görünmüyor,
not_configured davranışı, kısmi interface hatası, bozuk OID], + 2 route
entegrasyon testi). Hepsi gerçek ağ/cihaz olmadan, mock `Slim.get`/
`Slim.bulk` ile çalışıyor. Backend'de tanımlı bir lint aracı yok (mevcut
proje yapısı — sessizce eklenmedi); frontend `npm run lint`/`npm run
build`/`npm run test:web` bu fazda dokunulmayan koddan etkilenmedi.

**Gerçek cihaz testi:** Yapılmadı — kullanıcı açık bir SNMP hedefi
(IP/VERSION/PORT/CREDENTIAL REF) verdiğinde `SNMP_TARGET_*` ortam
değişkenleri ile `profile_store.py` üzerinden bağlanıp doğrulanacak.

**Sonraki adım:** Gerçek cihaz doğrulaması (kullanıcı hedefi verince);
ardından SNMPv3, kalıcı profil/credential storage, periyodik polling
döngüsü ve monitoring UI'nin gerçek veriye bağlanması.

---

## Faz 22.4 — SNMPv3

**Durum:** ✅ Tamamlandı (mock transport ile test edildi; gerçek cihaz
testi kullanıcının vereceği hedefi bekliyor).

**Amaç:** `apps/api/app/snmp/client.py`'ye production-quality bir
SNMPv3 implementasyonu eklemek — v2c'yi bozmadan, MIB parsing kodunu
tekrarlamadan.

**Gerçekleşen kapsam:**
- **Refactor:** `client.py` içinde `_Transport` protokolü
  (`_V2cTransport`/`_V3Transport`) — system/interface GET+GETBULK
  orkestrasyonu ve parsing artık versiyon-agnostik `_poll_with_
  transport()` içinde, iki versiyon arasında tek kopya. Mevcut 20 v2c
  testi hiçbir değişiklik gerektirmeden geçmeye devam ediyor (transport
  soyutlaması `Slim.get`/`Slim.bulk`'ı birebir aynı argümanlarla
  çağırıyor).
- **`credentials.py`:** `SNMPProfile` v3 validasyonu genişletildi —
  artık yalnızca `username` zorunlu; güvenlik seviyesi
  (`noAuthNoPriv`/`authNoPriv`/`authPriv`) dolu alanlara göre
  kendiliğinden belirleniyor (yeni `security_level` property'si).
  `SNMPAuthProtocol` SHA-2 ailesiyle (`SHA224/256/384/512`),
  `SNMPPrivProtocol` `AES192`/`AES256` ile genişledi.
- **`client.py`:** `pysnmp.hlapi.v3arch.asyncio` (`SnmpEngine`/
  `UsmUserData`/`get_cmd`/`bulk_cmd`) ile gerçek v3 poll. `_build_usm_
  user_data` `authKey`/`authProtocol` ve `privKey`/`privProtocol`'ü HER
  ZAMAN birlikte geçirir — pysnmp'nin sessiz MD5/DES varsayılanına asla
  düşülmez (bkz. `docs/decisions.md` §10.2, kaynakta doğrulandı).
  `SnmpEngine` her poll sonunda (başarılı/başarısız fark etmeksizin)
  `finally` ile kapatılıyor.
- **`profile_store.py`:** `SNMP_TARGET_VERSION=v3` desteği eklendi
  (`SNMP_TARGET_USERNAME`/`_AUTH_PROTOCOL`/`_AUTH_CREDENTIAL_REF`/
  `_PRIV_PROTOCOL`/`_PRIV_CREDENTIAL_REF`).

**Credential güvenliği:** `username` düz alan (RFC 3414 gereği secret
değil — Faz 7'den beri böyle), auth/priv parolaları yine yalnızca
`resolve_secret()` ile poll anında okunuyor. Yeni testler: secret
loglarda/response'ta hiç görünmüyor (v3 için de, tıpkı v2c gibi).

**Değişen/yeni dosyalar:** `apps/api/app/snmp/{client,credentials,
profile_store}.py`, `apps/api/tests/snmp/{test_client_v3,
test_profile_store}.py` (yeni), `apps/api/tests/snmp/test_credentials.py`
(4 yeni test), `apps/api/.env.example` (v3 örnek değişkenler).

**Testler:** Backend `pytest -v` — 218 test (188 + 30 yeni: v3 client
15 test [noAuthNoPriv/authNoPriv/authPriv başarılı GET, MD5/DES'e asla
sessizce düşmeme, auth/priv secret eksikse not_configured, timeout,
kimlik doğrulama reddi, decryption error, ortak parsing kodunun v3'te
de çalıştığı, secret log/response'ta yok, engine her zaman kapatılıyor]
+ `profile_store.py` 11 test [v2c + v3 çözümleme, eşleşmeyen asset,
eksik alan, geçersiz kombinasyon, desteklenmeyen versiyon, bozuk sayısal
alan] + `credentials.py` 4 yeni test [noAuthNoPriv geçerli, auth_protocol
tek başına geçersiz, priv auth'suz geçersiz, security_level property]).
Frontend değişmedi — 180/180. `npm run lint:web` temiz.

**Gerçek cihaz testi:** Yapılmadı — kullanıcı açık bir SNMPv3 hedefi
(IP/PORT/USERNAME/AUTH PROTOCOL/AUTH REF/PRIV PROTOCOL/PRIV REF)
vermedi; CLAUDE.md'nin örtük/otomatik tarama yasağı burada da uygulandı.

**Sonraki adım:** Gerçek cihaz doğrulaması (v2c ve v3); ardından Faz
22.5 (SNMP Profile Storage mimari kararı).

---

## Faz 22.5 — SNMP Profile Storage mimari kararı

**Durum:** ✅ Karar dokümanı tamamlandı — ⏸️ **tablo UYGULANMADI**
(otonom çalışma modunun kendi durma kuralı: "yeni kritik DB schema
kararı" kullanıcı onayı gerektirir).

**Amaç:** Birden fazla gerçek cihaz izlenmeye başlandığında (Faz 23)
gerekecek çoklu-asset profil depolamasını, bir DB tablosu eklemeden
ÖNCE tasarlamak.

**Gerçekleşen kapsam:** `docs/decisions.md` §10.3 — profile↔asset
ilişkisi (1-1), credential reference deseni (korunuyor), secret storage
(env-tabanlı kalıyor, secret manager kurulmadı), encryption
gerekmediği gerekçesi, rotation (sıfır-migration), deletion (asset
CASCADE, secret silme kullanıcı sorumluluğunda), audit (Faz 32'ye
bırakıldı), frontend'de secret gösterilmemesi, geçiş yolu (`profile_
store.py::get_profile_for_asset` imzası kararlı sınır — ayrı bir
`Protocol` sınıfı YAGNI gerekçesiyle eklenmedi).

**Bilinçli olarak yapılmayan:** `snmp_profiles` tablosu (plan §10'da
zaten vardı, §10.3 sadece etrafındaki kararları netleştirdi) — kullanıcı
onayı olmadan hiçbir migration uygulanmadı. Hiçbir secret manager
kurulmadı.

**Sonraki adım:** Kullanıcı bu kararı onaylarsa VE Faz 23 gerçekten
çoklu-asset polling'e ihtiyaç duyarsa, migration ayrı bir onay turunda
uygulanır. O ana kadar Faz 23 mevcut env-tabanlı `profile_store.py`
üzerinden ilerler.

---

## Faz 23 — SNMP Polling Engine

**Durum:** ✅ Tamamlandı (mock client ile test edildi; henüz hiçbir
API route'una bağlanmadı — bu Faz 24'ün kapsamı).

**Amaç:** Asset listesi → profil → `SNMPClient` → poll akışını,
eşzamanlılık sınırı + hataya dayanıklılık + iptal edilebilirlik ile
gerçek bir "engine" haline getirmek.

**Gerçekleşen kapsam:** `apps/api/app/snmp/poller.py` —
`PollingEngine.poll_all(assets)`:
- Her asset için `profile_store.get_profile_for_asset` çağrılır;
  profil yoksa (bugün hemen hemen her zaman) dürüst bir
  `not_configured` `SNMPPollResult` üretilir — asset ATLANMAZ.
- Profili olan asset'ler `asyncio.Semaphore` ile sınırlı eşzamanlılıkta
  (`SNMP_MAX_CONCURRENCY`, varsayılan **5** — güvenli/düşük) gerçek
  `SNMPClient.poll_asset` ile poll edilir.
- Bir asset'in BEKLENMEYEN hatası (ör. kütüphane içi bir bug) diğer
  asset'leri asla durdurmaz — her poll kendi try/except'i içinde izole
  edilir, ham exception detayı asla `SNMPPollResult.error`'a
  sızdırılmaz (yalnızca genel bir mesaj).
- `asyncio.CancelledError` hiçbir yerde yutulmaz — dış bir
  `task.cancel()` (graceful shutdown) her zaman normal şekilde yukarı
  yayılır.
- Yeni `PollBatchResult` (Pydantic) — `started_at`/`completed_at`/
  `duration_ms`/`total`/`polled`/`not_configured`/`results`. Mevcut
  `SNMPPollResult.status` sözleşmesine yeni bir değer EKLENMEDİ — altı
  değer (bkz. Faz 22.2) batch modunda da aynen kullanılıyor.

**Bilinçli olarak yapılmayan:** Henüz hiçbir API endpoint'i bu engine'i
çağırmıyor (Faz 24'ün kapsamı); periyodik/zamanlanmış çalıştırma yok
(Faz 30); `profile_store.py` hâlâ tek-hedef olduğu için pratikte bir
batch'te en fazla 1 asset gerçekten poll edilir — engine'in kendisi
zaten çoklu-asset'e hazır, `profile_store.py` DB-tabanlı hale
geldiğinde (Faz 22.5 onaylanırsa) hiçbir değişiklik gerekmeden gerçek
çoklu-cihaz polling'e geçer.

**Değişen/yeni dosyalar:** `apps/api/app/snmp/poller.py` (yeni),
`apps/api/tests/snmp/test_poller.py` (yeni, 10 test), `.env.example`
(`SNMP_MAX_CONCURRENCY`).

**Testler:** Backend `pytest -v` — 228 test (218 + 10 yeni: profilsiz
asset'ler atlanmıyor, yalnızca profili olan poll ediliyor, eşzamanlılık
limiti aşılmıyor, bir cihazın hatası diğerlerini durdurmuyor + ham hata
sızdırmıyor, iptal düzgün yayılıyor, `SNMP_MAX_CONCURRENCY` env okunuyor
+ varsayılan güvenli/düşük + geçersiz değerde varsayılana düşme, boş
liste, batch sayıları doğru). Frontend değişmedi — 180/180.

**Sonraki adım:** Faz 24 (Monitoring Backend) — bu engine'i gerçek bir
`GET`/`POST` endpoint'ine bağlamak.

---

## Faz 24 — Monitoring Backend

**Durum:** ✅ Tamamlandı (backend). Frontend'de bağlanma yok — kasıtlı
olarak sonraki bir faza bırakıldı (bkz. altta).

**Amaç:** `poller.py`'yi (Faz 23) gerçek bir API endpoint'ine bağlamak
— fake veri üretmeden.

**Gerçekleşen kapsam:** `GET /api/monitoring` (`apps/api/app/routes/
monitoring.py`) — `list_assets()` ile tüm asset'leri okur,
`PollingEngine().poll_all(assets)` ile gerçek bir polling turu
çalıştırır, `PollBatchResult`'ı olduğu gibi döner. Sistem/uptime/
interface sayısı/durumu/hızı/inbound-outbound bps/poll zaman
damgası/poll durumu — hepsi zaten `SNMPPollResult`/`SystemInfo`/
`InterfaceInfo` içinde var (Faz 22.2/22.4); **yeni bir response modeli
oluşturulmadı** (duplicate API'den kaçınmak için, bkz. CLAUDE.md).

**Bilinçli tasarım kararı:** `POST /api/snmp/poll/{asset_id}` (tek asset,
anlık poll — `AssetDetails` Monitoring sekmesi için) İLE `GET /api/
monitoring` (tüm filo, tek turda — `/monitoring` sayfası için) AYRI
endpoint'ler; ikisi de aynı alttaki `SNMPClient`'ı kullanır, hiçbir
mantık tekrarlanmadı.

**Bilinçli olarak yapılmayan:** `/monitoring` frontend sayfası bu
endpoint'e HENÜZ bağlanmadı — `MonitoringOverview.tsx` hâlâ Faz 6'nın
`computeMonitoringCoverage` (assets tablosundan heuristik, her zaman
0%) mantığını kullanıyor. Bu kasıtlı: frontend entegrasyonu (Faz 27
Advanced Dashboard / Faz 29 Device Detail) ayrı, backend'in test
edilmiş/stabil olduğu bir noktadan başlasın diye ayrı fazlara bırakıldı
— aynı anda hem backend hem frontend değiştirmek, bir hata durumunda
kaynağını ayırt etmeyi zorlaştırır.

**Değişen/yeni dosyalar:** `apps/api/app/routes/monitoring.py` (yeni),
`apps/api/app/main.py` (router eklendi), `apps/api/tests/
test_monitoring_api.py` (yeni, 5 test).

**Testler:** Backend `pytest -v` — 233 test (228 + 5 yeni: asset yokken
boş batch, profilsiz asset'ler not_configured, profili çözülen asset
gerçekten poll ediliyor [mock client], DB erişilemezse 503, community
secret hiçbir koşulda response'ta görünmüyor). Frontend değişmedi —
180/180.

**Sonraki adım:** Faz 25 (LLDP/CDP Topology) veya Faz 26 (Alert Engine)
— ikisi de gerçek cihaz/SNMP interface verisine bağımlı olduğu için şu an
yalnızca mimari/mock tarafı ilerletilebilir.

---

## Faz 26 — Advanced Alert Engine

**Durum:** ✅ Tamamlandı (mimari + testler; gerçek çağrı noktası yok —
bkz. altta, bilinçli).

**Amaç:** `lib/alerts.ts`'e SNMP-tabanlı 6 yeni alert kuralı eklemek
(`interface_down`/`interface_error`/`high_bandwidth`/
`snmp_poll_failure`/`device_unreachable`/`high_utilization`) — gerçek
veri yoksa asla ateşlenmeden, threshold'ları hardcode etmeden.

**Gerçekleşen kapsam:**
- Backend: `oid_map.py`'ye `ifInErrors`/`ifOutErrors` (IF-MIB) OID'leri,
  `models.py`'ye `InterfaceInfo.if_in_errors`/`if_out_errors` eklendi;
  `client.py` bunları gerçek poll'da parse ediyor (kümülatif sayaç,
  rate DEĞİL — bilinçli bir basitleştirme, dosya içi yorumda açık).
  Bu, `interface_error` kuralının gerçek bir veri kaynağına sahip
  olması için gerekliydi (aksi halde uydurma bir alert olurdu).
- Frontend: `apps/web/lib/alertThresholds.ts` (yeni) —
  `AlertThresholds`/`DEFAULT_ALERT_THRESHOLDS` (latencyWarning/
  Critical, interfaceUtilizationWarning/Critical, highBandwidthBps) —
  hiçbir eşik `alerts.ts` içinde hardcode değil.
- `apps/web/lib/api.ts`'e `SnmpPollResult`/`SnmpSystemInfo`/
  `SnmpInterfaceInfo`/`SnmpPollStatus` tipleri eklendi (backend
  `models.py` ile birebir).
- `computeAlerts(assets, messages, options?)` — yeni opsiyonel 3.
  parametre: `{ monitoring?: Record<assetId, SnmpPollResult>;
  thresholds?: Partial<AlertThresholds> }`. `monitoring`
  geçilmezse (bugün hiçbir çağrı noktası geçmiyor) SNMP-tabanlı
  kurallardan HİÇBİRİ tetiklenmez — mevcut çağrı noktaları
  (`AlertsList`, `AlertsPanel`, `AssetDetails`) hiç değişmeden aynı
  şekilde çalışmaya devam ediyor.
- `high_latency` artık iki kademeli: `latencyWarningMs` (varsayılan
  100ms, WARNING) / `latencyCriticalMs` (varsayılan 500ms, CRITICAL) —
  eskiden tek kademeli, her zaman WARNING'di; varsayılan değerler
  mevcut testlerin davranışını bozmayacak şekilde seçildi.
- 6 yeni kural: `device_unreachable` (CRITICAL, `status=unreachable`),
  `snmp_poll_failure` (WARNING, `status=timeout|authentication_failed`),
  `interface_down` (WARNING, admin=up + oper=down — RFC'ye uygun
  tanım, admin=down asla alert değil), `interface_error` (WARNING,
  toplam hata sayacı > 0), `high_bandwidth` (WARNING, mutlak bps eşiği),
  `high_utilization` (WARNING/CRITICAL, `bps / if_speed_bps` yüzdesi —
  `if_speed_bps` yoksa hiç hesaplanmaz).

**Bilinçli olarak yapılmayan:** Hiçbir gerçek çağrı noktası (`AlertsList.
tsx` vb.) henüz `GET /api/monitoring`'i çağırıp `computeAlerts`'e
`monitoring` geçmiyor — bu, Faz 24'ün "frontend'de büyük değişiklik
yok" kararıyla tutarlı ve Faz 27/29'un kapsamı. Bu yüzden yeni 6 kural
şu an CANLI uygulamada asla tetiklenmiyor (test dışında) — bu, "gerçek
veri yoksa alert üretme" kuralının en katı hali. `lib/api.ts`'e
`fetchMonitoring()` gibi bir fonksiyon EKLENMEDİ (henüz hiçbir
tüketicisi olmadığı için — mevcut proje konvansiyonu her `fetch*`
fonksiyonunun gerçek bir çağıranla birlikte eklenmesi).

**Değişen/yeni dosyalar:** `apps/api/app/snmp/{oid_map,models,client}.py`,
`apps/api/tests/snmp/{test_oid_map,test_client}.py`,
`apps/web/lib/alertThresholds.ts` (yeni), `apps/web/lib/alerts.ts`,
`apps/web/lib/api.ts` (SNMP tipleri), `apps/web/lib/i18n/translations.ts`
(6 yeni `alertMessages` fonksiyonu, tr+en), `apps/web/tests/alerts.test.ts`.

**Testler:** Backend `pytest -v` — 234 test (233 + 1 yeni:
`ifInErrors`/`ifOutErrors` parsing; `test_oid_map` içindeki mevcut bir
assertion güncellendi, yeni test sayılmadı). Frontend `npm run test:web`
— 193 test (180 + 13 yeni: 2 kademeli latency + custom threshold + 9
SNMP-tabanlı kural testi + "monitoring geçilmezse hiçbiri ateşlenmez"
testinin genişletilmesi). `npm run lint`/`npm run build` temiz.

**Sonraki adım:** Faz 27 (Advanced Dashboard) veya Faz 29 (Device
Detail) — `GET /api/monitoring`'i gerçekten çağırıp `computeAlerts`'e
bağlamak.

---

## Faz 27 (kısmi) — `/monitoring` sayfasını gerçek veriye bağlama

**Durum:** ✅ Tamamlandı — **yalnızca `/monitoring` sayfası** kapsamında
(Faz 27'nin tam listesindeki Infrastructure Health/Device Health/Active
Alerts/Top Talkers gibi Dashboard widget'ları bu increment'te ELE
ALINMADI, bkz. altta). Dashboard (`/`) hiç değiştirilmedi.

**Amaç:** Faz 24'te eklenen `GET /api/monitoring`'i gerçekten çağırıp
`/monitoring` sayfasını Faz 6'nın heuristik-tabanlı (her zaman %0)
`computeMonitoringCoverage`'ından gerçek backend verisine geçirmek.

**Gerçekleşen kapsam:**
- `apps/web/lib/api.ts` — `PollBatchResult` tipi + `fetchMonitoring()`
  (artık gerçek bir çağıranı var, bu yüzden eklendi).
- `MonitoringOverview.tsx` — mount'ta `fetchMonitoring()` çağırıyor
  (loading/error/done durumları). SNMP Coverage/Monitored Devices
  artık gerçek `PollBatchResult.total`/`.polled`'dan hesaplanıyor.
  Interface Monitoring ve Bandwidth bölümleri gerçek poll edilen
  interface'leri (varsa) tablo halinde gösteriyor; CPU/Memory HÂLÂ her
  zaman "veri yok" (backend hiç poll etmiyor — HOST-RESOURCES-MIB yok,
  bu bir eksik değil, dürüst bir sınır). Yeni **Recent Polls** bölümü —
  yalnızca gerçekten denenen (`not_configured` olmayan) poll'ları
  gösteriyor.
- `i18n/translations.ts` — `monitoring.{recentPolls,loadError,columns,
  pollStatus}` (tr+en).
- `tests/testUtils.tsx::mockAssetsAndScans` — yeni opsiyonel 3.
  parametre (`monitoring`, varsayılan boş bir `PollBatchResult`) —
  mevcut TÜM diğer çağıranlar (çoğu component testi) değişmeden
  çalışmaya devam ediyor.

**Bilinçli olarak yapılmayan:** Dashboard (`/`) widget'ları
(Infrastructure Health, Device Health, Active Alerts, Network
Performance, Bandwidth, Interface Status, SNMP Polling Status, Top
Talkers) bu increment'te DEĞİŞMEDİ — hâlâ Faz 5/6'nın heuristiklerini
kullanıyor. `computeAlerts`'e (Faz 26) `monitoring` parametresi HÂLÂ
hiçbir yerden geçilmiyor — `AlertsList`/`AlertsPanel` hâlâ yalnızca
discovery-tabanlı 3 kuralı (device_down/high_latency/high_risk_port)
gösteriyor. Bunlar ayrı, daha büyük bir Faz 27 devamı/Faz 29 gerektirir.

**Değişen/yeni dosyalar:** `apps/web/lib/api.ts`, `apps/web/components/
MonitoringOverview.{tsx,module.css}`, `apps/web/lib/i18n/translations.ts`,
`apps/web/tests/{MonitoringOverview,testUtils,pages}.test.tsx`.

**Testler:** Frontend `npm run test:web` — 194 test (193 + 1 yeni net;
`MonitoringOverview.test.tsx` 3→4 test: not_configured mesajı, boş
batch'te %0/0, **gerçek/sıfır-olmayan** coverage+interface+bandwidth
verisi, cpu/memory+recentPolls'un boş batch'te dürüst "veri yok"
göstermesi [5 bölüm]). `npm run lint`/`npm run build` (TypeScript dahil)
temiz. Backend değişmedi — 234/234.

**Sonraki adım:** Dashboard widget'larını (Faz 27'nin geri kalanı) ve
`AlertsList`/`AlertsPanel`'i (Faz 26'nın `monitoring` parametresi) gerçek
veriye bağlamak; `AssetDetails` Monitoring sekmesi (Faz 29).

---

## Faz numaralandırma notu — Agent track (Faz 28+)

Kullanıcının "IT OPERATIONS ASSISTANT — OTONOM GELİŞTİRME MASTER
PROMPT" (Windows/Linux Agent + SNMP + NOC Platform) talimatı kendi "Faz
27+" numaralandırmasını kullanıyor, ama bu repository'nin gerçek Faz 27'si
zaten farklı bir işi (yukarıdaki `/monitoring` gerçek veri bağlama)
temsil ediyor. Çakışmayı önlemek için Agent track'i **Faz 28**'den
başlatıldı ve kullanıcının prompt'undaki sıralama +1 kaydırılarak
eşlendi:

| Kullanıcı prompt'u | Bu roadmap'te | Konu |
|---|---|---|
| Agent API + Data Model | **Faz 28** | ✅ Tamamlandı (aşağıda) |
| Agent Database | Faz 29 | Asset↔Agent eşleştirme, retention kararı |
| Agent Authentication (sertleştirme) | Faz 31 | Bkz. Faz 28'in temel auth'u zaten var |
| Windows Agent | Faz 30 (sıra revize edilebilir) | `apps/agent/windows/` |
| Linux Agent | Faz 30 (sıra revize edilebilir) | `apps/agent/linux/` |
| Heartbeat/Inventory/Telemetry | Faz 28 | ✅ Tamamlandı (API sözleşmesi) |
| Monitoring/Alerts/Topology (agent+SNMP birleşik) | Faz 32+ | |
| Agent Management UI (`/agents`) | Faz 33+ | |
| Scheduler | Faz 38 | |
| Reports | Faz 36 | |
| Production Hardening | Faz 45 | |

Bu tablo kesin bir taahhüt değil, yalnızca çakışmayı önlemek için bir
eşleme — ilerledikçe gerçek bağımlılıklara göre sıra revize edilebilir
(ör. Windows/Linux Agent, Agent Database'den sonra değil önce
gerekebilir).

## Faz 28 — Agent API + Data Model

**Durum:** ✅ Tamamlandı.

**Amaç:** Windows/Linux host'larda çalışacak Agent'ların merkezi
backend ile güvenli şekilde haberleşebilmesi için API + veri modelini
kurmak — henüz gerçek bir Agent süreci (Faz 30) yazılmadan.

**Mimari karar — dosya yerleşimi:** Kullanıcının önerdiği `apps/api/app/
agents/{models,schemas,repository,authentication,service,exceptions}.py`
yapısı yerine, mevcut katman ayrımına uyacak şekilde HİBRİT bir yapı
kullanıldı: agent'a özel domain/iş mantığı `app/agents/{models,
authentication,exceptions,service}.py` altında (bkz. `app/snmp/`'nin
aynı deseni), ama gerçek DB erişimi `app/db/agents.py` altında (mevcut
`app/db/assets.py`/`scans.py` ile AYNI dizinde, aynı desende) —
`schemas.py` ayrıca oluşturulmadı, `models.py` hem API hem domain
sözleşmesini taşıyor (mevcut `snmp/models.py` ile aynı ikili rol).
Gerekçe `docs/decisions.md` §12'de.

**API (`app/routes/agents.py`):**
```
POST /api/agents/register              -> {agent_id, token} (201, token yalnızca burada)
POST /api/agents/heartbeat             -> AgentSummary (Bearer auth)
POST /api/agents/{agent_id}/telemetry  -> {status:"ok"} (Bearer auth + agent_id eşleşme kontrolü)
POST /api/agents/{agent_id}/inventory  -> {status:"ok"} (Bearer auth + agent_id eşleşme kontrolü)
GET  /api/agents                       -> list[AgentSummary]
GET  /api/agents/{agent_id}            -> AgentDetail (404 yoksa)
```
`telemetry`/`inventory` path'inde `{agent_id}` var (kullanıcının en
son talimatındaki şekil) — ama bu ID tek başına GÜVENİLİR kabul
edilmiyor: Bearer token'ın ait olduğu agent, path'teki id ile
eşleşmezse `403` (bkz. `_require_matching_agent`). `heartbeat` düz
kaldı (agent kimliği yalnızca token'dan, body'de ayrı bir `agent_id`
alanı yok — token zaten tek anlamlı kimliktir, body'de tekrarlamak
tutarsızlık riski yaratır).

**Kimlik doğrulama (`app/agents/authentication.py`):** Kayıt anında
`secrets.token_urlsafe(32)` (256 bit) ile bir bearer token üretilir,
YALNIZCA `AgentRegistrationResponse`'ta bir kez döner. DB'de SADECE
SHA-256 hash'i (`agents.token_hash`) saklanır — bcrypt/argon2 DEĞİL
(gerekçe: token zaten yüksek entropili rastgele, düşük entropili insan
parolalarına karşı yavaş hash'in getirisi yok — GitHub/GitLab PAT
modeliyle aynı yaklaşım). Bu fazda kullanıcıdan bir "enrollment secret"
istenmedi (self-service registration) — bu bilinçli bir kapsam kararı,
sertleştirme (registration token, rotation, revocation) Faz 31'e
bırakıldı.

**Veri modeli (`infra/postgres/init.sql`, additive — mevcut `assets`/
`scans` tablolarına DOKUNULMADI):**
- `agents` — kimlik + `token_hash` + `asset_id` (nullable FK →
  `assets(id)` ON DELETE SET NULL, Faz 29'a kadar HER ZAMAN NULL —
  otomatik/güvenilmez eşleştirme yapılmadı) + `last_heartbeat_at`
  (status buradan TÜRETİLİR, ayrı bir "status" sütunu YOK — saklanan
  bir durum gerçekle çakışabilir).
- `agent_telemetry` — yüksek frekanslı CPU/RAM/disk/network örnekleri;
  disk/network JSONB (normalize edilmedi, MVP). Retention/aggregation
  POLİTİKASI henüz yok — `docs/decisions.md` §12'de bilinen risk olarak
  işaretlendi (gerçek periyodik toplama, Faz 38 Scheduler, devreye
  girmeden netleştirilmeli).
- `agent_inventory` — agent başına TEK satır (tarihçe değil, "şu anki
  durum"); hardware/os/network/software/services JSONB.

**Status türetme:** `AgentStatus = "online"|"offline"|"unknown"`,
`last_heartbeat_at`'ten hesaplanır (`AGENT_OFFLINE_THRESHOLD_SECONDS`,
varsayılan 120s, configurable — hardcode değil). `unknown`: hiç
heartbeat gelmemiş. `offline`: eşik aşılmış.

**Güvenlik:** Token hiçbir response'ta (kayıt hariç), logda veya
exception mesajında görünmez — testlerle doğrulandı. `AgentAuthentication
Error` eksik/geçersiz/bilinmeyen/iptal edilmiş token'ların HEPSİNİ aynı
401'e çevirir (token'ın var olup olmadığını sızdırmamak için).

**Bilinçli olarak yapılmayan:** Windows/Linux Agent süreçleri (Faz 30),
Asset↔Agent eşleştirme (Faz 29), token rotation/revocation UI (Faz 31),
`/agents` frontend sayfası (Faz 33+), telemetry retention/aggregation
implementasyonu (yalnızca risk olarak not düşüldü).

**Değişen/yeni dosyalar:** `apps/api/app/agents/{models,authentication,
exceptions,service}.py` (yeni), `apps/api/app/db/agents.py` (yeni),
`apps/api/app/routes/agents.py` (yeni), `apps/api/app/main.py` (router
eklendi), `infra/postgres/init.sql` (3 yeni tablo, additive),
`apps/api/tests/agents/test_authentication.py` (yeni, 8 test),
`apps/api/tests/test_agents_api.py` (yeni, 18 test),
`apps/api/tests/conftest.py` (`_ROUTE_GET_CONNECTION_TARGETS`e agents
eklendi), `apps/api/tests/{test_assets_api,test_monitoring_api,
test_snmp_api,test_scan_history_integration}.py` (`TRUNCATE TABLE
assets` → `... CASCADE`, çünkü `agents.asset_id` artık `assets`'e FK
ile referans veriyor).

**Testler:** Backend `pytest -v` — **260 test** (234 + 26 yeni: agent
auth 8 + agent API 18). Gerçek bir agent süreci hiç çalıştırılmadı,
hiçbir gerçek ağ/SNMP trafiği yok. Çalıştırmadan sonra gerçek `agents`/
`agent_telemetry`/`agent_inventory` tabloları elle kontrol edildi: 0/0/0
(hiçbir kalıcı yazma sızmadı — bkz. `docs/decisions.md` §11'in
`isolated_db` fixture'ı yeni tabloları da otomatik kapsıyor).

**Gerçek doğrulama:** Yapılmadı — henüz gerçek bir Agent süreci yok
(Faz 30). Kullanıcı ağ testi/gerçek cihaz istemedi, bu faz saf API/DB
mimarisi.

**Sonraki adım:** Faz 29 — Agent Database (retention/aggregation
kararı + Asset↔Agent eşleştirme mimarisi).

---

## Faz 29 — Agent Database + SNMP Configuration Center + Asset/Agent Eşleştirme

**Durum:** ✅ Tamamlandı.

**Amaç:** (1) Agent↔Asset güvenilir eşleştirme altyapısı, (2) telemetry
retention politikası, (3) SNMP ayarlarını `/settings` içinde gerçek bir
Configuration Center haline getirmek — kalıcı `snmp_profiles` tablosu
dahil.

**Gerçekleşen kapsam:**
- **Agent↔Asset eşleştirme (`app/agents/matching.py`, yeni):**
  `evaluate_asset_match(agent, assets)` — SALT-OKUNUR değerlendirme,
  hostname/IP/MAC'ten en az 2 bağımsız sinyal aynı asset'i işaret
  etmedikçe `confirmed` sayılmaz (`candidate`/`unmatched` diğer
  durumlar). `GET /api/agents/{id}/asset-match` değerlendirir, `POST
  /api/agents/{id}/asset-match` (body: `{asset_id}`) AÇIKÇA onaylanmış
  bir eşleşmeyi `agents.asset_id`'ye yazar — hiçbir otomatik süreç bunu
  kendiliğinden yapmaz.
- **Telemetry retention (`app/db/agents.py::delete_expired_telemetry`,
  `app/agents/service.py::telemetry_retention_days`/
  `cleanup_expired_telemetry`):** `AGENT_TELEMETRY_RETENTION_DAYS`
  (varsayılan 30 gün) ile configurable, idempotent DELETE. Henüz
  hiçbir zamanlayıcı tarafından otomatik çağrılmıyor (Faz 38'in
  kapsamı) — karar ve gerekçe `docs/decisions.md` §10.4'te.
- **SNMP Profile Configuration Center — TAM CRUD:**
  `infra/postgres/init.sql`'e additive `snmp_profiles` tablosu
  (`target_host`-tabanlı, `asset_id` YOK — kasıtlı, gerekçe
  `docs/decisions.md` §10.4), `app/db/snmp_profiles.py`, `app/snmp/
  {profile_config,profile_service}.py`, `app/routes/snmp_profiles.py`:
  ```
  GET    /api/snmp/profiles              -> list[SNMPProfileResponse]
  POST   /api/snmp/profiles              -> 201 (create)
  GET    /api/snmp/profiles/{id}         -> detay | 404
  PUT    /api/snmp/profiles/{id}         -> güncelle | 404 | 409 (isim çakışması)
  DELETE /api/snmp/profiles/{id}         -> 204 | 404
  POST   /api/snmp/profiles/{id}/test    -> GERÇEK bir SNMP poll dener (kayıtlı profile karşı)
  ```
  Hiçbir response secret DEĞERİ taşımaz — yalnızca `credential_
  configured`/`status` (türetilmiş) ve `*_ref` İSİMLERİ. `main.py`'nin
  CORS middleware'i `PUT`/`DELETE`'i de kabul edecek şekilde genişletildi
  (önceden yalnızca GET/POST vardı).
- **"Test Connection" gerçek poll'a bağlı:** mevcut `SNMPClient`
  (değiştirilmedi) profilin kendi `id`'sini korelasyon anahtarı olarak
  kullanarak `target_host`'a karşı gerçek bir poll dener — yalnızca
  kullanıcı bu profili kaydederken kendisi verdiği bir hedefe karşı,
  kullanıcı butona tıkladığında (otomatik tarama DEĞİL).
- **Settings UI (`SnmpConfigurationCenter.tsx`, yeni + `SettingsPanel.
  tsx` genişletildi):** Genel/Agent Yapılandırması/SNMP Yapılandırması/
  Sistem bölümlerine ayrıldı. SNMP bölümü: profil tablosu (isim/hedef/
  versiyon/durum renkli nokta), "+ Profil Ekle", satır başına Düzenle/
  Bağlantıyı Test Et/Sil (silme onay gerektirir), v2c/v3 alan toggle'ı,
  community/auth/priv secret alanları her zaman yalnızca birer REFERANS
  ismi metin kutusu (gerçek değer asla). Agent Yapılandırması bölümü
  gerçek `GET /api/agents` sayısını gösteriyor (sahte veri yok).

**Bilinçli olarak yapılmayan:** `profile_store.py` DEĞİŞTİRİLMEDİ —
`GET /api/monitoring`/`POST /api/snmp/poll/{asset_id}` hâlâ yalnızca
`.env`-tabanlı tek-hedefi kullanıyor, yeni `snmp_profiles` tablosunu
henüz OKUMUYOR (`get_enabled_profile_by_target_host` sorgusu hazır ama
bağlanmadı) — bu, gerçek bir sonraki fazın kapsamı. Kaydedilmemiş bir
profili test etme akışı eklenmedi (güvenlik kararı, §10.4). Retention
hiçbir zamanlayıcı tarafından otomatik çağrılmıyor.

**Değişen/yeni dosyalar:** `apps/api/app/agents/matching.py`,
`apps/api/app/snmp/{profile_config,profile_service}.py`,
`apps/api/app/db/snmp_profiles.py`, `apps/api/app/routes/
snmp_profiles.py` (hepsi yeni); `apps/api/app/{agents/service,
db/agents,snmp/credentials,routes/agents,main}.py`, `infra/postgres/
init.sql` (güncellendi); `apps/web/components/SnmpConfigurationCenter.
{tsx,module.css}` (yeni), `apps/web/components/SettingsPanel.tsx`,
`apps/web/lib/{api,i18n/translations}.ts` (güncellendi); testler
aşağıda.

**Testler:** Backend `pytest -v` — **308 test** (260 + 48 yeni: matching
9, retention 8, agent asset-match API 5, SNMP profile CRUD API 26).
Frontend `npm run test:web` — **205 test** (194 + 11 yeni: SettingsPanel
+2, SnmpConfigurationCenter +9). `npm run lint`/`npm run build` temiz.
Gerçek `assets`/`scans`/`agents`/`agent_telemetry`/`agent_inventory`/
`snmp_profiles` tabloları test çalıştırmasından SONRA elle kontrol
edildi — değişmedi (isolated_db izolasyonu yeni tabloları da kapsıyor).

**Gerçek doğrulama:** Gerçek tarayıcıda uçtan uca doğrulandı — `/settings`
sayfası GENEL/AGENT YAPILANDIRMASI/SNMP YAPILANDIRMASI/SİSTEM
bölümleriyle render oluyor, "+ Profil Ekle" formu açılıyor, v2c↔v3 alan
toggle'ı canlı çalışıyor, TR↔EN çalışıyor, 375px'te taşma yok, mevcut
`/assets` sayfası gerçek 14 asset'i (kullanıcının kendi ağ taramasından)
sorunsuz gösteriyor — hiçbir mevcut özellik bozulmadı. **Gerçek bir SNMP
cihazına karşı "Test Connection" denenmedi** (kullanıcı açık bir hedef
vermedi, otomatik/keşfedici bir test başlatılmadı — yalnızca mock'lanmış
testlerle doğrulandı).

**Sonraki adım:** `profile_store.py`'yi `snmp_profiles` tablosuna
bağlamak (gerçek asset polling'in Configuration Center'daki profilleri
kullanması için); Faz 30 (Windows/Linux Agent); Faz 31 (Agent Security
sertleştirme — enrollment secret, token rotation/revocation).

---

## Faz 29.5 — SNMP Profile ↔ Asset İlişkilendirme ve Polling Mimarisinin Tamamlanması

**Durum:** ✅ Tamamlandı.

**Amaç:** Faz 29'un "Sonraki adım" notunu kapatmak — `snmp_profiles`
Configuration Center'ı gerçek asset'lere bağlamak, bir profilin birden
fazla asset'e atanabildiği (ama her asset'in en fazla bir aktif profili
olduğu) kalıcı bir ilişki modeli kurmak, ve gerçek poll akışının
(`POST /api/snmp/poll/{asset_id}`, `GET /api/monitoring`) bu ilişkiyi
kullanmasını sağlamak — geriye dönük uyumluluğu (mevcut `.env` fallback'i)
bozmadan.

**Gerçekleşen kapsam:**
- **`asset_snmp_profiles` ilişki tablosu** (additive, `infra/postgres/
  init.sql`): `asset_id UUID PRIMARY KEY REFERENCES assets(id) ON
  DELETE CASCADE`, `snmp_profile_id UUID NOT NULL REFERENCES
  snmp_profiles(id) ON DELETE CASCADE` + index. `asset_id`'nin PRIMARY
  KEY olması "asset başına en fazla 1 profil" kısıtını DB seviyesinde
  garanti eder. Tam mimari gerekçe: `docs/decisions.md` §10.5.
- **Repository/servis/route katmanları (yeni):** `app/db/
  asset_snmp_profiles.py` (`assign_profile_to_asset` —
  `ON CONFLICT (asset_id) DO UPDATE` ile reassignment doğal, `unassign_
  profile_from_asset`, `get_profile_for_asset`, `list_assets_for_
  profile`, `count_assets_for_profile`, `count_assets_by_profile`),
  `app/snmp/asset_profile_service.py`, `app/routes/asset_snmp_
  profiles.py`:
  ```
  GET    /api/assets/{asset_id}/snmp-profile              -> {configured, profile, target_host_matches_asset}
  PUT    /api/assets/{asset_id}/snmp-profile/{profile_id}  -> {"status": "assigned"} | 404
  DELETE /api/assets/{asset_id}/snmp-profile               -> {"status": "unassigned"} | 404
  GET    /api/snmp/profiles/{profile_id}/assets            -> list[AssetSummary] | 404
  ```
  Hiçbir response secret DEĞERİ taşımaz (mevcut `SNMPProfileResponse`
  sözleşmesi aynen korunur).
- **`profile_store.py::resolve_profile_for_asset(conn, asset)`** —
  yeni tercih edilen entegrasyon noktası: önce DB ataması, yoksa (veya
  `conn` verilmezse) mevcut `.env` tek-hedef fallback'i AYNEN korunur.
  `routes/snmp.py` ve `snmp/poller.py` bu yeni fonksiyona bağlandı;
  `PollingEngine.poll_all` artık profil çözümünü SIRAYLA yapıyor (tek
  bir `asyncpg.Connection` eşzamanlı sorguyu desteklemediği için bulunan
  gerçek bir concurrency bug'ı düzeltildi), yalnızca gerçek SNMP ağ
  poll'ları eşzamanlı kalıyor. Detay: `docs/decisions.md` §10.5.
- **Profil silme artık 409 döndürebiliyor:** atanmış asset'i olan bir
  profil `DELETE /api/snmp/profiles/{id}` ile silinemez
  (`SNMPProfileHasAssignmentsError` → 409) — sessiz kaskad silme YOK.
- **Settings UI:** `SnmpConfigurationCenter.tsx` profil tablosuna
  "Atanmış Cihazlar" sütunu eklendi (`assigned_asset_count`), 409
  hata mesajı UI'da gösteriliyor (önceden sessizce yutuluyordu).
- **Assets UI:** `AssetInventory.tsx`'e SNMP durum sütunu (🟢
  Yapılandırıldı — profil adıyla / ⚪ Yapılandırılmadı), her asset için
  `GET /api/assets/{id}/snmp-profile` ile ayrı ayrı sorgulanıyor.
- **Asset Details:** yeni "SNMP" sekmesi (`AssetSnmpPanel.tsx`, yeni) —
  Durum/Profil/Versiyon/Port/Timeout/Retries/Son Poll, "SNMP Yapılandır"
  (profil seç + ata), "Atamayı Kaldır", "Şimdi Poll Et" (gerçek `POST
  /api/snmp/poll/{asset_id}` çağırır), `target_host_matches_asset ===
  false` ise uyarı metni. Veri yoksa her zaman dürüst "Yapılandırılmadı"
  /"SNMP poll verisi mevcut değil" gösterir.
- **Dashboard SNMP Coverage:** `lib/monitoringCoverage.ts::
  computeMonitoringCoverage(assets, snmpAssignedCount)` artık gerçek
  `GET /api/snmp/profiles`'ın `assigned_asset_count` toplamını
  kullanıyor — "SNMP Enabled" alanı artık gerçek bir sayı (önceden her
  zaman 0 sabitti). Ağır bir grafik/görselleştirme eklenmedi.

**Bilinçli olarak yapılmayan (kapsam dışı, kullanıcı talimatınca):**
Windows/Linux Agent (Faz 30), Agent installer/service, WebSocket, Agent
telemetry scheduler, SNMP scheduler/periyodik poll, yeni SNMPv3
implementasyonu (zaten Faz 22.4'te vardı, dokunulmadı), otomatik ağ
keşfi/SNMP taraması, Auth sistemi, Docker/Kubernetes.

**Değişen/yeni dosyalar:** `apps/api/app/db/asset_snmp_profiles.py`,
`apps/api/app/snmp/asset_profile_service.py`, `apps/api/app/routes/
asset_snmp_profiles.py` (hepsi yeni); `apps/api/app/snmp/{profile_
config,profile_service,profile_store,poller}.py`, `apps/api/app/routes/
{snmp,snmp_profiles,monitoring}.py`, `apps/api/app/main.py`,
`infra/postgres/init.sql` (güncellendi); `apps/web/components/
AssetSnmpPanel.{tsx,module.css}` (yeni); `apps/web/components/
{SnmpConfigurationCenter,AssetInventory,AssetDetails,
MonitoringCoverage}.tsx`, `apps/web/lib/{api,monitoringCoverage,
i18n/translations}.ts` (güncellendi); testler aşağıda.

**Testler:** Backend `pytest -v` — **344 test** (308 + 36 yeni: repository
13, API 17, poller DB entegrasyonu 6). Frontend `npm run test:web` —
**222 test** (205 + 17 yeni: AssetSnmpPanel 6, AssetDetails SNMP sekmesi
4, AssetInventory SNMP sütunu 2, SnmpConfigurationCenter 2,
MonitoringCoverage 1, monitoringCoverage.ts 2). `npm run lint:web`/
`npm run build -w apps/web` temiz. Gerçek `assets`/`scans`/`agents`/
`agent_telemetry`/`agent_inventory`/`snmp_profiles`/
`asset_snmp_profiles` tabloları test çalıştırmasından SONRA elle
kontrol edildi — değişmedi (isolated_db izolasyonu yeni tabloyu da
kapsıyor, bkz. `tests/conftest.py::_ROUTE_GET_CONNECTION_TARGETS`).

**Sonraki adım:** Faz 30 (Windows/Linux Agent — bu fazda kasıtlı olarak
BAŞLANMADI, kullanıcı talimatı).

---

## Faz 30 — Windows / Linux IT Operations Agent

**Durum:** ✅ Tamamlandı.

**Amaç:** Mevcut Faz 28-29.5 Agent API'sine (`apps/api/app/agents/`)
konuşan, gerçek bir Windows/Linux Agent uygulaması eklemek — sistem/
donanım/OS/network/process/service envanterini ve CPU/RAM/disk/network
telemetry'sini backend'e gönderebilen, kendi kendine kaydolan, kontrollü
retry/backoff ile çalışan bağımsız bir Python uygulaması. SNMP'ye
dokunulmadı — SNMP fiziksel/ağ cihazları için, Agent Windows/Linux
işletim sistemi için, iki ayrı veri kaynağı olarak kalmaya devam ediyor.

**Gerçekleşen kapsam:**
- **`apps/agent/` — bağımsız uygulama** (backend'e gömülü değil):
  `agent/{main,config,client,authentication,heartbeat,telemetry,
  inventory}.py` + `agent/collectors/{system,cpu,memory,disk,network,
  processes,services}.py` + `agent/platform/{windows,linux}.py`. CLI:
  `python -m agent {start,status,inventory,test-connection,version}`.
  Tam mimari detay: `docs/architecture.md` §7.2, `docs/decisions.md`
  §13.
- **Tek runtime bağımlılığı `psutil==7.2.2`** (BSD-3-Clause, Python
  3.14 uyumluluğu doğrulandı) — CPU/RAM/disk/network/process bilgisi VE
  Windows Service listesi için. HTTP istemcisi (`client.py`) BİLİNÇLİ
  olarak `requests`/`httpx` KULLANMIYOR, stdlib `urllib.request`
  yeterli — dış bağımlılık yüzeyi tek kütüphaneyle sınırlı.
- **Kimlik/kayıt:** `.env`'de `AGENT_ID`/`AGENT_TOKEN` yoksa `POST
  /api/agents/register` ile kendi kendine kaydolur, aldığı kimliği
  yerel bir dosyaya (`AGENT_STATE_FILE`) kalıcı yazar — her başlatmada
  YENİDEN kayıt olmaz ("ghost agent" birikimi önlendi). Token hiçbir
  log/debug çıktısında tam gösterilmez.
- **Retry/backoff:** heartbeat/telemetry/inventory üç bağımsız
  thread'de çalışır, bağlantı hatalarında sonlu bir backoff (`2,5,10,
  30,60`s) uygular, kimlik doğrulama hatasında (401/403) tamamen durur.
  Backend erişilemezken agent ÇÖKMEZ.
- **Network collector özellikle zenginleştirildi** (§8 kullanıcı
  talimatı): her interface için isim/tip (ethernet/wifi/loopback/
  docker/virtual/vpn/other, isim-tabanlı kalıp eşleştirme)/tüm IPv4+
  IPv6 adresleri/MAC/durum/hız/sayaçlar. `NetworkInterfaceSample`'a
  additive `addresses`/`interface_type` alanları eklendi (JSONB
  sütun olduğu için DB migration gerekmedi).
- **Process collector bilinçli olarak dar:** yalnızca PID/isim/CPU%/
  memory%/kullanıcı/durum — command-line argümanları HİÇ toplanmaz
  (credential/token içerebilir). En yoğun N (varsayılan 50) süreçle
  sınırlanır.
- **Backend additive değişiklikler (yeni route YOK, mevcut Faz 28
  endpoint'leri aynen kullanıldı):** `AgentInventoryRequest.processes`
  (+ yeni `agent_inventory.processes` JSONB sütunu, `ADD COLUMN IF NOT
  EXISTS`), `AgentRegistrationRequest.fqdn` + `agents.fqdn` (aynı
  desen), `AgentSummary.local_ip` (liste görünümünde agent'ın GERÇEK
  IP'sini göstermek için), `schema_version` alanları (Faz 30.5+ için
  ileriye dönük uyumluluk). Sunucu tarafı string alanlarına makul uzunluk
  limitleri (`max_length=255`) eklendi (§29 kullanıcı talimatı — client'tan
  gelen veriye körü körüne güvenilmiyor).
- **Frontend:** `/agents` (`AgentsList.tsx` — durum/hostname/OS/IP/
  versiyon/son heartbeat/bağlı asset/Görüntüle), `/agents/[id]`
  (`AgentDetailView.tsx` — Genel Bakış/Sistem/CPU/Bellek/Disk/Ağ/
  Süreçler/Servisler sekmeleri), `AssetDetails`'e yeni **Agent**
  sekmesi (`AssetAgentPanel.tsx` — SNMP sekmesinden tamamen ayrı),
  Dashboard'a **Agent Sağlığı** widget'ı (`AgentHealthSummary.tsx` +
  `lib/agentHealth.ts` — gerçek online/offline/unknown sayıları),
  Settings'in Agent Configuration bölümü artık `/agents`'a gerçek bir
  link içeriyor (önceden "sayfa henüz yok" diyen stale bir not vardı).
  Sidebar'a OPERASYON grubuna "Agent'lar" eklendi.
- **`docs/postgres/init.sql`:** `agents.fqdn` ve `agent_inventory.
  processes` additive sütunlar — hem `CREATE TABLE IF NOT EXISTS` hem
  zaten var olan gerçek/geliştirme veritabanları için ayrı `ALTER TABLE
  ... ADD COLUMN IF NOT EXISTS` (`CREATE TABLE IF NOT EXISTS` var olan
  bir tabloya yeni sütun eklemediği için).

**Bilinçli olarak yapılmayan (kapsam dışı, kullanıcı talimatınca):**
Agent auto-update, MSI/EXE installer, code signing, Kubernetes/Docker
agent, uzaktan komut çalıştırma/shell/dosya transferi/yazılım dağıtımı,
credential harvesting, otomatik ağ keşfi/SNMP taraması. Windows Service/
systemd kod olarak HAZIR ama gerçek kurulum yapılmadı (yalnızca
referans bir `apps/agent/deploy/systemd/itops-agent.service` dosyası).
Offline telemetry/inventory buffer'ı YOK (backend erişilemezken
kaçırılan turlar kaybolur, bkz. `docs/decisions.md` §13). Kurulu
yazılım envanteri (`software`) toplanmıyor (güvenilir cross-platform
bir yöntem bu fazın kapsamı dışında).

**Değişen/yeni dosyalar:** `apps/agent/` (tamamen yeni — `agent/`,
`tests/`, `deploy/systemd/`, `requirements.txt`, `.env.example`,
`README.md`); backend: `apps/api/app/agents/{models,service}.py`,
`apps/api/app/db/agents.py`, `infra/postgres/init.sql` (güncellendi);
frontend (yeni): `apps/web/components/{AgentsList,AgentDetailView,
AssetAgentPanel,AgentHealthSummary}.{tsx,module.css}`,
`apps/web/app/agents/{page.tsx,[id]/page.tsx}`,
`apps/web/lib/agentHealth.ts`; frontend (güncellendi):
`apps/web/components/{AssetDetails,SettingsPanel,Sidebar}.tsx`,
`apps/web/lib/{api,i18n/translations}.ts`, `apps/web/app/page.tsx`,
`.gitignore`; testler aşağıda.

**Testler:** Backend `pytest -v` — **349 test** (344 + 5 yeni: fqdn
round-trip 2, processes 2, hostname uzunluk limiti 1). Agent uygulaması
`apps/agent && pytest -v` — **88 yeni test** (config 8, authentication
7, client 8, collectors — system/cpu/memory/disk/network/processes/
services — toplam ~40, platform windows/linux/dispatch ~20, telemetry/
inventory/heartbeat/main entegrasyon ~13). Frontend `npm run test:web`
— **245 test** (222 + 23 yeni: AgentsList 7, AgentHealthSummary 3,
agentHealth.ts 3, AssetAgentPanel 3, AgentDetailView 6, Sidebar +1).
`npm run lint:web`/`npm run build -w apps/web` temiz.

**Gerçek E2E doğrulama:** Agent gerçek backend'e karşı çalıştırıldı —
`register`/`heartbeat`/`telemetry`/`inventory` uçtan uca doğrulandı
(gerçek CPU/RAM/disk/network/process/service verisi — bu makinenin
KENDİ verisi, 241 gerçek Windows servisi + 50 en yoğun process gerçek
olarak toplanıp gönderildi). Gerçek tarayıcıda `/agents`, `/agents/
[id]` (tüm sekmeler), Dashboard Agent Health widget'ı, Settings linki,
`AssetDetails` Agent sekmesi ("Bağlı bir Agent yok" — bu agent hiçbir
asset'e bağlı olmadığı için doğru/dürüst durum) doğrulandı. 375px'te
hiçbir sayfada yatay taşma yok. **Doğrulama sonrası test agent kaydı ve
telemetry/inventory verisi gerçek veritabanından silindi** — bu yalnızca
doğrulama amaçlı, gerçek kullanıcı verisi değildi; `assets`/`scans`
sayıları hiç değişmedi (14/2, çalışma öncesiyle aynı).

**Performans:** Agent süreci `psutil.process_iter`/`net_io_counters`
gibi çağrılar dışında hafif; ayrı, izole bir ölçüm (CPU/RAM profiling)
bu fazda YAPILMADI — gerçek bir sonraki adımda (Faz 31 veya gerçek
üretim dağıtımı öncesi) `time`/`psutil` ile agent'ın kendi sürecini
ölçmek gerekiyor, şu an yalnızca "çöker mi/gerçek veri üretiyor mu"
doğrulandı.

**Sonraki adım:** Faz 31 (Agent Security sertleştirme — enrollment
secret, token rotation/revocation, self-service registration'ın
production riskinin kapatılması).

---

## Faz 31 — Agent Enrollment (self-service registration'ın sertleştirilmesi)

**Durum:** ✅ Tamamlandı (kısmi — kullanıcının geniş "Faz 30+" master
prompt'undan yalnızca Enrollment/Security kısmı; kapsam kararı ve
gerekçesi için bkz. `docs/decisions.md` §14).

**Amaç:** Faz 28'de bilinçli olarak açık bırakılan self-service
registration güvenlik açığını kapatmak — artık `POST /api/agents/
register` geçerli, süresi dolmamış, tek kullanımlık bir enrollment
kodu gerektiriyor.

**Gerçekleşen kapsam:**
- **Backend (additive):** yeni `agent_enrollment_codes` tablosu
  (`code TEXT PRIMARY KEY`, `expires_at`, `used_at`,
  `used_by_agent_id` FK → `agents(id) ON DELETE SET NULL`), `app/db/
  agent_enrollment.py` (repository), `app/agents/enrollment.py`
  (kod üretimi — `XXX-XXX-XXX`, karışabilecek karakterler hariç
  alfabe, `secrets.choice`; doğrulama/atomik tüketim). Yeni
  endpoint'ler:
  ```
  POST /api/agents/enrollment-codes  -> {code, expires_at} (201)
  GET  /api/agents/enrollment-codes  -> aktif (süresi dolmamış + kullanılmamış) kodlar
  ```
  `AgentRegistrationRequest.enrollment_code` artık ZORUNLU — kodsuz
  kayıt `422`, geçersiz/süresi dolmuş/kullanılmış kod `401` döner.
  Atomiklik: kod önce tüketilir (`UPDATE ... WHERE used_at IS NULL`,
  tek SQL ifadesi), SONRA agent oluşturulur — "rogue agent" riskine
  karşı sıra bilinçli (bkz. `docs/decisions.md` §14).
- **Agent uygulaması:** `config.py`'ye `ENROLLMENT_CODE`, `main.py::
  ensure_registered` yeni kayıtlarda kodu payload'a ekliyor (zaten
  bilinen bir kimlik varsa kod hiç istenmiyor), `EnrollmentCodeMissingError`
  ile net bir hata mesajı. `_warn_if_insecure_backend` — `BACKEND_URL`
  `http://` ise her başlatmada görünür bir uyarı (sert engelleme değil).
- **Frontend:** `AgentEnrollmentPanel.tsx` — Settings > Agent
  Configuration'a eklendi: "Kod Üret" butonu, üretilen kodu canlı geri
  sayımla gösterir (kopyalanabilir), aktif kodlar listesi.
- **Secure token storage (Windows Credential Manager/DPAPI, Linux
  keyring) DEĞERLENDİRİLDİ ama KASITLI olarak ERTELENDİ** — gerekçe:
  bu geliştirme ortamında yalnızca Windows tarafı gerçek test
  edilebilir, Linux tarafı (Secret Service arka ucu yok) doğrulanamaz;
  yarım/doğrulanmamış bir entegrasyon yerine tamamen erteleme tercih
  edildi (bkz. `docs/decisions.md` §14).

**Bilinçli olarak yapılmayan (kullanıcının "küçük parçalara ayır"
talimatına uyularak, ayrı gelecek alt fazlar):** Remote command
execution + audit log, Windows Event Log/Linux journal toplama,
kullanıcı/session bilgisi, software inventory, agent self-update,
installer/packaging (`AgentSetup.exe`), gerçek OS credential store
entegrasyonu (yukarı bkz.), offline telemetry queue.

**Değişen/yeni dosyalar:** backend: `apps/api/app/agents/{enrollment,
exceptions,models,service}.py`, `apps/api/app/db/agent_enrollment.py`
(yeni), `apps/api/app/routes/agents.py`, `infra/postgres/init.sql`;
agent: `apps/agent/agent/{config,main}.py`, `.env.example`,
`README.md`; frontend: `apps/web/components/AgentEnrollmentPanel.
{tsx,module.css}` (yeni), `apps/web/components/SettingsPanel.tsx`,
`apps/web/lib/{api,i18n/translations}.ts`; testler aşağıda.

**Testler:** Backend `pytest -v` — **366 test** (349 + 17 yeni:
enrollment repository 9, enrollment/registration API 8). Agent
uygulaması — **92 test** (90 + 2 yeni: TLS uyarı testleri, artı
enrollment kodu akışı için güncellenen mevcut testler). Frontend
`npm run test:web` — **250 test** (245 + 5 yeni: AgentEnrollmentPanel).
`npm run lint:web`/`npm run build -w apps/web` temiz.

**Gerçek E2E doğrulama:** Settings UI'dan gerçek bir kod üretildi
(`VAM-DHX-K2U`), agent bu kodla gerçek backend'e karşı kaydoldu
(`test-connection` ile doğrulandı), kod kullanıldıktan sonra aktif
liste boşaldı ve AYNI kodla ikinci bir kayıt denemesi dürüstçe `401
Enrollment code daha önce kullanılmış` ile reddedildi (ikinci bir agent
OLUŞMADI — `GET /api/agents` tek kayıt gösterdi). TLS uyarısı
`BACKEND_URL=http://...` için gerçekten loglandı. **Doğrulama sonrası
test agent kaydı ve enrollment kodu gerçek veritabanından silindi** —
`assets`/`scans` sayıları hiç değişmedi (14/2).

**Sonraki faz:** Kullanıcının geniş prompt'undaki kalan parçalar
(Remote Command Execution + Audit, Windows/Linux derin donanım
envanteri, installer/packaging, offline queue) için henüz
numaralandırılmamış, ayrı küçük alt fazlar planlanmalı — bu increment
bilinçli olarak yalnızca Enrollment/Security'ye odaklandı.

---

## Faz 32 — Agent Packaging & Web Download

**Durum:** ✅ Tamamlandı.

**Amaç:** Agent'ın artık proje klasöründen Python ile elle
çalıştırılması gerekmesin — Windows için Python kurulumu gerektirmeyen,
tek dosya bir `.exe` web arayüzünden indirilebilsin. Mevcut enrollment
akışı (Faz 31) AYNEN korunarak.

**Gerçekleşen kapsam:**
- **PyInstaller packaging** (`apps/agent/packaging/windows/`):
  `IT-Operations-Agent.spec` (onefile mod, entry point `agent/
  __main__.py` — ayrı bir "shadow" entry point OLUŞTURULMADI),
  `build.ps1` (versiyonu TEK doğruluk kaynağından — `agent/
  __init__.py::__version__` — okur, elle tekrar YAZMAZ; `dist/
  IT-Operations-Agent-<version>.exe` + `dist/build-info.json` üretir),
  `requirements-build.txt` (yalnızca `pyinstaller==6.22.2` — agent'ın
  runtime bağımlılığı DEĞİL, ayrı tutuldu). Gerçek build GERÇEKTEN
  çalıştırıldı: 8.9 MB, Python 3.14.7 ile sorunsuz, `version`/
  `inventory` komutları frozen EXE içinde doğrulandı.
- **Backend (additive, DB migration YOK):** `app/agents/download.py`
  (artifact çözümleme — build/download BİLİNÇLİ olarak ayrı, backend
  hiçbir zaman PyInstaller çalıştırmaz), yeni endpoint'ler:
  ```
  GET /api/agents/download/windows/info  -> {available, version, filename, size_bytes, built_at}
  GET /api/agents/download/windows       -> EXE dosyası (Content-Disposition: attachment)
  ```
  Path traversal yapısal olarak imkansız — dosya adı/yol kullanıcıdan
  ASLA alınmaz, tek kaynak sunucu-yerel `build-info.json` + regex
  doğrulama + dizin-içi kontrolü (iki savunma katmanı, bkz.
  `docs/decisions.md` §15). Artifact yoksa dürüst `404`.
- **Frontend:** `AgentDownloadPanel.tsx` — Settings > Agent
  Configuration'a "Agent İndir" bölümü eklendi (mevcut Enrollment
  UI'sinin ALTINA, tasarımı bozmadan): gerçek versiyon/dosya boyutu,
  native `<a href>` indirme linki, henüz build edilmemişse dürüst
  "henüz build edilmemiş" durumu (sahte buton YOK).
- **Gerçek bir hata bulunup düzeltildi:** Windows PowerShell 5.1'in
  `Set-Content -Encoding utf8`'i BOM ekliyor, Python'un `json.loads()`'u
  bunu reddediyordu — yalnızca GERÇEK bir build+download denemesinde
  (mock testlerle DEĞİL) ortaya çıktı. İki katmanlı düzeltme:
  `build.ps1` artık `-Encoding ascii`, backend `encoding="utf-8-sig"`
  ile okuyor (bkz. `docs/decisions.md` §15).

**Bilinçli olarak yapılmayan (kullanıcının kendi kısıt listesi):**
Remote Command Execution, Audit, Linux packaging/installer, Windows
Service kurulumu, auto-update, OS credential manager (Faz 31'den
devam eden erteleme), enrollment güvenlik modelinde HİÇBİR değişiklik
(aynen korundu — tek kullanımlık, 10dk, atomik tüketim, önce kod sonra
agent).

**Değişen/yeni dosyalar:** yeni: `apps/agent/packaging/windows/{IT-
Operations-Agent.spec,build.ps1,requirements-build.txt}`, `apps/api/
app/agents/download.py`, `apps/api/tests/test_agent_download.py`,
`apps/agent/tests/test_packaging.py`, `apps/web/components/
AgentDownloadPanel.{tsx,module.css}`, `apps/web/tests/
AgentDownloadPanel.test.tsx`; değişen: `apps/api/app/{agents/models,
routes/agents}.py`, `apps/web/components/SettingsPanel.tsx`, `apps/web/
lib/{api,i18n/translations}.ts`, `.gitignore` (`apps/agent/{build,
dist}/` eklendi — build çıktısı commit edilmez).

**Testler:** Backend `pytest -v` — **378 test** (366 + 12 yeni: artifact
çözümleme birim 7 [BOM regresyonu dahil], HTTP route 5). Agent
uygulaması — **100 test** (92 + 8 yeni: packaging dosya/versiyon/BOM
regresyon smoke testleri — gerçek PyInstaller ÇALIŞTIRILMADI, çok ağır,
gerçek build elle/E2E'de doğrulandı). Frontend `npm run test:web` —
**254 test** (250 + 4 yeni: AgentDownloadPanel). `npm run lint:web`/
`npm run build -w apps/web` temiz.

**Gerçek E2E doğrulama (mock ile YETİNİLMEDİ):** EXE gerçekten build
edildi (8.9 MB), frozen haliyle çalıştırıldı, backend'den GERÇEK bir
HTTP isteğiyle indirildi (orijinaliyle byte-byte özdeş), İNDİRİLEN
kopya Settings UI'dan üretilen GERÇEK bir enrollment koduyla gerçek
backend'e kaydoldu, aynı kodla ikinci deneme dürüstçe `401` ile
reddedildi (`GET /api/agents` tek kayıt gösterdi — ikinci agent
OLUŞMADI). Test agent'ı, enrollment kodu ve indirilen EXE kopyası
doğrulama sonrası temizlendi; `assets`/`scans` (14/2) ve kullanıcının
kendi oluşturduğu gerçek `snmp_profiles` (2 kayıt) hiç değişmedi.

**Sonraki faz:** Numaralandırılmamış — Remote Command Execution + Audit
kullanıcının kapsam listesinde bir sonraki büyük parça olarak duruyor,
ama (önceki fazın raporunda da belirtildiği gibi) kapsamı/onay
çerçevesini netleştirmek için ayrı bir konuşma hak ediyor. Daha küçük
alternatifler: Linux packaging (systemd + benzer bir dağıtım paketi),
gerçek Windows Service kurulumu (bu fazda yalnızca referans dosya
vardı).

**Faz 32 sonrası bugfix (aynı faz kapsamında tamamlandı):** Gerçek
kullanıcı bildirimi — indirilen EXE çift tıklanınca `argparse` "command
required" hatasıyla ANINDA kapanıyordu (Faz 32'nin kendi "HEDEF AKIŞ"ı
hiç implemente edilmemişti). `apps/agent/agent/main.py` düzeltildi:
argümansız çalıştırma artık `start`'a düşüyor, frozen+interaktif
konsolda yapılandırma eksikse Backend URL + Enrollment Code doğrudan
isteniyor, herhangi bir hata/erken çıkışta pencere `input()` ile
duraklatılıyor (dev/CI modunda hiçbir etkisi yok). Gerçek EXE yeniden
build edilip 4 senaryoda (hiç config yok / yalnızca BACKEND_URL var /
tam config+erişilemeyen backend / önceden kayıtlı state dosyası)
GERÇEKTEN çalıştırılarak doğrulandı. Detay + kendi kendine yakalanan
çift-duraklatma regresyonu için bkz. `docs/decisions.md` §15.1. Agent
test suite 100→114 (backend/frontend dosyalarına dokunulmadı,
enrollment güvenlik modeli değişmedi).

---

## Faz 33 — Remote Command Execution: Process Kill + Service Control

**Durum:** ✅ Tamamlandı.

**Amaç:** Agent üzerinden uzaktaki bir Windows/Linux makinede süreç
sonlandırma (kill) ve servis yönetimi (start/stop/restart) — web
arayüzünden tetiklenen, Agent'ın kendi polling mimarisi üzerinden
teslim edilen komutlar.

**Kapsam:**
- Yeni additive tablo `agent_commands` (audit + komut kuyruğu — tek
  tablo iki amaca hizmet ediyor, ayrı bir "audit log" tablosu
  YARATILMADI, kullanıcının "minimal audit log" tercihiyle tutarlı).
- Backend: `POST /api/agents/{agent_id}/commands` (UI tetikler, auth
  yok — bkz. Bilinen Riskler), `GET /api/agents/{agent_id}/commands`
  (geçmiş), `GET .../commands/pending` + `POST .../commands/{id}/result`
  (Bearer auth, yalnızca Agent çağırır).
- Agent: `agent/commands.py` (blacklist + gerçek OS komutları —
  `taskkill`/`kill -9`, `sc`/`systemctl`), yeni 4. polling thread
  (`command_poll_interval`, YALNIZCA `ENABLE_REMOTE_COMMANDS=true` ise
  başlar — varsayılan KAPALI, opt-in).
- Frontend: Processes/Services sekmelerine aksiyon butonları, onay
  modalı, toast, komut sonucu için kısa client-side polling.

**Kapsam dışı:** Auth/RBAC (Faz 13), tam audit UI'ı (kim/IP), Linux
dışı platform desteği, komut whitelisting/rate-limiting, Windows
Service kurulumu (Agent hâlâ console modda).

**Bilinen risk (kullanıcıya açıkça bildirildi, kabul edildi):**
İnsan kullanıcı auth'u olmadığı için backend API'ye erişen HERKES
kayıtlı bir agent'ta komut oluşturabilir. Azaltıcı önlemler: (1) Agent
tarafında `ENABLE_REMOTE_COMMANDS` varsayılan `false` — komutlar
backend'de oluşsa bile agent açıkça etkinleştirilmemişse hiç
çalıştırılmaz, (2) agent-taraflı blacklist (kritik süreç/servis +
agent'ın kendi süreci) backend'in bilemeyeceği bir koruma katmanı
olarak duruyor, (3) her komut `agent_commands` tablosuna durumu/
sonucuyla kalıcı olarak yazılıyor (minimal audit iz).

**Testler:** Backend (`app/db/agent_commands.py`, route, blacklist
reddi), Agent (`agent/commands.py` blacklist + mock subprocess,
command-poll loop wiring), Frontend (buton/modal/toast davranışı).
Backend 378→394, Agent uygulaması 114→143, frontend 254→260 test —
hepsi geçiyor.

**Gerçek E2E doğrulama (mock ile YETİNİLMEDİ):** Gerçek backend +
gerçek web sunucusu ayağa kaldırılıp bu makinenin kendi (gerçek,
Faz 30-32'den kayıtlı) Agent'ının GERÇEK süreç/servis listesi
`/agents/{id}` sayfasında görüntülendi — "Görevi Sonlandır" butonu
gerçek bir PID (8240) için tıklanıp onay modalının doğru mesajı
("8240" (PID) sürecini sonlandırmak istediğinize emin misiniz? Bu
işlem geri alınamaz.") gösterdiği doğrulandı, ardından GERÇEK bir kill
komutu GÖNDERİLMEDEN "Vazgeç" ile iptal edildi (bu makinede gerçek bir
süreç kasıtlı olarak sonlandırılmadı). Servisler sekmesinde gerçek
Windows servis listesi (running/stopped durumuna göre buton
etkin/pasif) doğrulandı. `ENABLE_REMOTE_COMMANDS` bu makinede
etkinleştirilmedi — özellik varsayılan KAPALI kalmaya devam ediyor.

## Faz 34 — Hızlı Bağlantı (RDP/SSH) + User Sessions Tracking

**Durum:** ✅ Tamamlandı.

**Amaç:** Agent'ta o an açık olan kullanıcı oturumlarını (kim giriş
yapmış, ne zaman) göstermek ve tek tıkla RDP/SSH bağlantısı başlatmak.

**Kapsam:**
- Agent: `agent/collectors/sessions.py` + `agent/platform/{windows,
  linux}.py::list_sessions()` — Windows'ta `quser` (sabit-genişlikli
  ayrıştırma), Linux'ta `who`. `summarize_sessions()` en son giriş
  yapan kullanıcıyı (bilinen zaman formatlarıyla en-iyi-çaba
  ayrıştırma, uydurma sıralama YOK) ve aktif+bağlantısı-kesik oturum
  sayısını türetir. `telemetry.py`'ye eklendi (inventory'ye DEĞİL —
  oturum bilgisi CPU/RAM gibi sık değişir, 30s aralıkla gönderilir).
- Backend: `agent_telemetry`'ye additive `sessions_json`/
  `last_logged_in_user`/`active_sessions_count` sütunları,
  `AgentTelemetryRequest`'e karşılık gelen alanlar. Yeni `GET /api/
  agents/{id}/connect/rdp` — Agent'ın `local_ip`'siyle dinamik bir
  `.rdp` dosyası üretir (backend bağlantıyı KENDİSİ KURMAZ, yalnızca
  istemcinin kendi `mstsc.exe`'sinin açacağı bir yapılandırma dosyası).
  SSH için ayrı bir endpoint YOK — `local_ip`/`last_logged_in_user`
  zaten `GET /api/agents/{id}` yanıtında var, `ssh://` URI'si ve kopya
  komutu istemci (frontend) tarafında üretiliyor.
- Frontend: Overview'a "Son Oturum Açan"/"Aktif Oturum Sayısı" (rozet),
  yeni "Oturumlar" sekmesi (kullanıcı/oturum tipi/durum/giriş zamanı
  tablosu), header'a "RDP ile Bağlan" (indirme linki) + "SSH ile Bağlan"
  (küçük menü: `ssh://` linki + panoya kopyala) butonları.

**Kapsam dışı:** SSH/RDP kimlik doğrulaması (kullanıcı kendi
kimliğiyle bağlanır, agent/backend hiçbir credential taşımaz), oturum
geçmişi/audit (yalnızca O ANKİ açık oturumlar, event log madenciliği
YOK), Linux'ta "disconnected" kavramı (yapısal olarak yok, `who`
yalnızca bağlı oturumları listeler).

**Testler:** Backend (`app/agents/rdp.py`, telemetry model/route),
Agent (`collectors/sessions.py`, `platform/{windows,linux}.py`
mock'lanmış `quser`/`who` çıktısı), Frontend (Overview alanları,
Oturumlar sekmesi, Quick Connect butonları/panoya kopyalama).
Backend 394→403, Agent 148→164, Frontend 267 (bu increment'te
`AgentDetailView.test.tsx`'e 6 yeni test: Overview alanları, Oturumlar
sekmesi, Quick Connect) — hepsi geçiyor.

## Faz 35 — Web SSH Terminal

**Durum:** ✅ Tamamlandı.

**Amaç:** SSH bağlantısını yerel istemciye bırakmak yerine, tarayıcıda
yeni bir sekmede canlı, etkileşimli bir terminal (`xterm.js`) açmak.

**Bağlam — kullanıcının orijinal isteği daraltıldı:** Kullanıcı hem RDP
(Apache Guacamole/`guacd`) hem SSH için web tabanlı canvas/terminal
istedi. Üç AskUserQuestion ile netleştirildi: (1) kimlik bilgisi HİÇBİR
ZAMAN saklanmaz, her bağlantıda kullanıcı girer, (2) RDP için gerçek
Guacamole (`guacd` + FreeRDP, yeni bir Docker altyapı bileşeni) KURULMADI
— yalnızca SSH web terminali bu increment'in kapsamında, RDP `.rdp`
indirme linki olarak (Faz 34) AYNEN kaldı, (3) Auth/RBAC (Faz 13) yok
— kullanıcı riski açıkça kabul edip şimdi ilerlemeyi seçti.

**Kapsam:**
- Backend: `app/agents/ssh_proxy.py` (asyncssh — EPL-2.0) + `WS /api/
  agents/{id}/ssh`. Hedef **host istemciden asla alınmaz** — yalnızca
  DB'de bilinen agent `local_ip`'si kullanılır (bu WS endpoint'i keyfi
  bir "SSH-anywhere" relay'ine dönüştürülemez). Kimlik bilgisi
  (kullanıcı adı/parola) WS'in İLK mesajıyla gelir, HİÇBİR ZAMAN
  loglanmaz/diske-DB'ye yazılmaz — yalnızca bağlantı süresince
  bellekte, asyncssh'e geçilir. `known_hosts=None` bilinçli bir
  tercih (host key pinleme/TOFU bu fazın kapsamı dışında, kullanıcıya
  bildirildi).
- Frontend: `components/SshTerminal.tsx` (`@xterm/xterm` +
  `@xterm/addon-fit`) + yeni route `/remote-control/ssh/{agentId}`.
  "SSH ile Bağlan" butonu artık (Faz 34'teki kopyala/aç menüsü
  YERİNE) doğrudan bu sayfayı yeni sekmede açıyor — kendi login
  formu (kullanıcı adı/parola), gerçek WS bağlantısı, ham terminal
  akışı.

**Kapsam dışı (kullanıcının kendi kısıtı):** RDP web Canvas/Guacamole,
Auth/RBAC, kimlik bilgisi kaydetme/"saved credential" özelliği, SSH
host key doğrulama/pinleme, oturum kayıt/audit (yalnızca canlı akış).

**Testler:** Backend (`ssh_proxy.py` — kimlik bilgisi asla loglanmaz,
hata mesajları dürüst, WS protokolü; route — host'un DAİMA agent
kaydından geldiği, istemciden ASLA alınmadığı kritik güvenlik testi
dahil), Frontend (`SshTerminal.tsx` — login formu, WS mesaj protokolü,
bağlı/kapalı/hata faz geçişleri, unmount'ta WS kapanması). Backend
403→415, Frontend 267→273.

**Gerçek E2E doğrulama (mock ile YETİNİLMEDİ):** Bu makinede geçici
bir OpenSSH sunucusu + düşük yetkili, geçici bir test kullanıcısı
(`sshtestuser`) oluşturuldu. (1) Ham WebSocket script'iyle gerçek bir
SSH oturumu açılıp `whoami` çalıştırıldı — gerçek çıktı
(`win-g4e9ugrth8e\sshtestuser`) doğrulandı. (2) Gerçek tarayıcıda uçtan
uca: `/agents/{id}` sayfasından "SSH ile Bağlan" tıklandı, yeni sekmede
login formu dolduruldu, GERÇEK bir Windows `cmd.exe` terminali (banner,
prompt) göründü, `echo hello-from-web-terminal` yazılıp çalıştırıldı —
gerçek çıktı ve yeni prompt geldi. Doğrulama sonrası test kullanıcısı
silindi, `sshd` servisi orijinal (durmuş) haline döndürüldü.

## Faz 36 — Production UI/UX Yenilemesi (Dashboard, Varlık Envanteri, Süreç Tablosu)

**Durum:** ✅ Tamamlandı.

**Kapsam:**
- **Süreç tablosu** (`AgentDetailView.tsx`): tüm sütun başlıkları
  tıklanabilir sıralama (varsayılan CPU % AZALAN), süreç adı/PID'ye
  göre canlı arama. PID 0 gizlenmedi — "Boşta (Idle)" olarak açıkça
  etiketlenip soluklaştırıldı (dürüst veri ilkesi).
- **Varlık Envanteri** (`AssetInventory.tsx`): yeni `PortBadges.tsx` —
  portlar yatay `flex-wrap`, en fazla 3 görünür + "+X daha" rozeti,
  tıklanınca tüm portları risk seviyesine göre gruplayan bir popover
  (mevcut `lib/portRisk.ts::classifyPortRisk` kullanılır, yeni bir
  sınıflandırma icat edilmedi). Tablo kapsayıcısı zaten `overflow-x:
  auto`/`white-space: nowrap` içeriyordu (Faz 21) — `vertical-align:
  middle` eklendi. "Bilinmiyor"/"DÜŞÜK" etiketleri soluklaştırıldı.
- **Dashboard redesign**: `DashboardSummary.tsx` 9 karttan 4 ana KPI
  kartına indirildi (Toplam Varlık + çevrimiçi/çevrimdışı rozetleri,
  Yüksek Riskli/Açık Portlar, Bilinmeyen, Altyapı Sağlığı & Risk
  Skoru); "Son Tarama" artık dev bir kart değil, sağ üstte pasif
  metin. `InfrastructureHealth.tsx`'teki uzun bar, saf CSS
  `conic-gradient` donut grafiğe çevrildi (yeni bir chart kütüphanesi
  eklenmedi). `DeviceHealthSummary.tsx` kutulardan renkli pill
  etiketlere (`Sağlıklı: 12` gibi) geçti. `app/page.tsx` 2 kolona
  ayrıldı (sol: altyapı/cihaz dağılımı, sağ: uyarılar + canlı akış),
  ikincil widget'lar (Agent Sağlığı, İzleme Kapsamı, Ağ Performansı,
  Son Taramalar) tam genişlikte altta kaldı.

**Kapsam dışı:** Shadcn/Radix gibi yeni bir UI kütüphanesi eklenmedi
— popover/donut tamamen mevcut CSS-module deseniyle, saf CSS/React
state kullanılarak inşa edildi (proje zaten hiç UI kütüphanesi
kullanmıyor, tek başına bir kütüphane eklemek kapsam dışı tutuldu).

**Testler:** Yeni `tests/PortBadges.test.tsx` (4 test); `AgentDetailView.
test.tsx`'e 5 yeni test (sıralama, idle etiketi, arama); `DashboardSummary.
test.tsx` ve `DeviceHealthSummary.test.tsx` yeni yapıya göre yeniden
yazıldı. Frontend 273→285, hepsi geçiyor. `npx tsc --noEmit` ve lint
temiz.

**Gerçek E2E doğrulama:** Backend+frontend ayağa kaldırılıp gerçek
veriyle (14 asset, gerçek Agent) tüm üç alan tarayıcıda görsel olarak
doğrulandı — port popover'ı gerçek riskli portları (135/139/445/3389/
5985) doğru gruplu gösterdi, donut grafik gerçek %100 çevrimiçi
oranını çizdi, süreç tablosunda gerçek CPU sıralaması ve "chrome"
araması gerçek sonuçları filtreledi.

## Faz 37 — Güç ve Oturum Yönetimi (Power & Session Control) + Wake-on-LAN

**Durum:** ✅ Tamamlandı.

**Bağlam:** Faz 33'ün (Remote Command Execution) doğal bir uzantısı —
aynı `agent_commands` kuyruğu/`ENABLE_REMOTE_COMMANDS` kapısı/audit
izi kullanılıyor, yeni bir güvenlik modeli KURULMADI. Reboot/shutdown
tek bir süreç yerine TÜM makineyi etkilediği için ekstra dikkatle ele
alındı (aşağıya bkz).

**Kapsam:**
- Agent: `agent/commands.py::{reboot,shutdown,logoff,control_power}` —
  yeni `power_control` komut tipi. **Bilinçli sapma:** `/t 0` (anında)
  DEĞİL, kısa bir gecikme (3sn) kullanılır — `/t 0` ile OS komutu
  ANINDA makineyi düşürür, agent'ın kendisi de o anda ölüp backend'e
  "başarılı" sonucunu HİÇBİR ZAMAN bildiremez (kullanıcı arayüzde
  sonsuza kadar "işleniyor" görür). Kısa gecikme, `shutdown`/
  `systemctl --no-block` komutunun HEMEN dönmesini ve agent'ın gerçek
  sonucu bildirebilmesini sağlar — asıl kapanma/reboot birkaç saniye
  sonra, arka planda gerçekleşir. `logoff`: Windows'ta `username`
  yok sayılır (Windows'un kendi `logoff` komutu zaten yalnızca o anki
  oturumu kapatır), Linux'ta `pkill -u` hedefli bir kullanıcı adı
  GEREKTİRİR — boşsa dürüstçe reddedilir. `main.py`'ye `logoff`
  sonrası telemetry'yi (oturum sayısı orada yaşıyor, inventory'de
  DEĞİL) hemen tazeleyen mantık eklendi.
- Backend: `app/agents/wol.py` — standart Wake-on-LAN magic packet
  (6×`0xFF` + hedef MAC'in 16 tekrarı), `SO_BROADCAST` yalnızca bu
  soket için açılır. `POST /api/agents/{id}/wake` agent'ın KENDİSİYLE
  HİÇ konuşmaz — DB'deki `mac_address`'e doğrudan UDP broadcast (global
  `255.255.255.255`, port 9) gönderir, bu yüzden cihaz Çevrimdışıyken
  de çalışır. `command_type`/`action` CHECK constraint'leri additive
  olarak genişletildi (`power_control`/`reboot`/`shutdown`/`logoff`).
- Frontend: `AgentDetailView.tsx` header'ına kırmızı "Güç Seçenekleri"
  dropdown'u (RDP/SSH butonlarının yanına) — 4 seçenek. Reboot/
  Shutdown/Logoff mevcut `pendingAction`/`ConfirmModal` akışından
  geçer (onay metni: `"<hostname>" cihazını <aksiyon> istediğinize
  emin misiniz?`). Wake-on-LAN AYRI bir yol — ayrı bir doğrudan `POST
  /wake` çağrısı, onay modalı YOK (geri dönüşü olmayan bir işlem
  değil), ve **agent Çevrimdışıyken de/`mac_address` bilindiği sürece
  her zaman tıklanabilir** (yalnızca `local_ip` gerektiren diğer 3
  seçenekten farklı olarak `agent.status`'a hiç bakılmaz).

**Bilinen sınırlar (dürüstçe belgelendi):**
- WoL paketi global broadcast'e gönderilir — router'lar broadcast
  trafiğini alt ağlar arasında genelde YÖNLENDİRMEZ, bu WoL'un kendi
  fiziksel/ağ kısıtıdır, kod bunu aşamaz.
- Paket gönderildi ≠ cihaz gerçekten uyandı garantisi — hedef donanımın
  BIOS/NIC'inde "Wake on LAN" özelliğinin gerçekten etkin olması
  backend'in kontrolünde değil, dürüstçe yalnızca "gönderildi"
  raporlanır.

**Testler:** Agent (`test_commands.py` — 16 yeni test, GERÇEK bir
reboot/shutdown/logoff ASLA çalıştırılmaz; `test_main.py` — 2 yeni
test, `power_control`/logoff sonrası telemetry tazeleme). Backend
(`test_wol.py` — 7 yeni test, gerçek bir UDP paketi ASLA ağa
gönderilmez testlerde; `test_agents_api.py` — 4 yeni wake route
testi). Frontend (`AgentDetailView.test.tsx` — 7 yeni test). Agent
184/184, Backend 426/426, Frontend 292/292 — hepsi geçiyor.

**Gerçek E2E doğrulama (dikkatli sınırlarla):** EXE yeniden build
edilip bu makinede çalıştırıldı. **Reboot/shutdown/logoff bu makinede
GERÇEKTEN tetiklenmedi** — bu, üzerinde çalıştığım gerçek oturumu/
sunucuları keserdi, bilinçli olarak yalnızca mock testlerle ve
"onay modalını aç, doğru metni gör, Vazgeç'e bas" akışıyla doğrulandı
(gerçek ekran görüntüsü: `"WIN-G4E9UGRTH8E" cihazını yeniden
başlatmak istediğinize emin misiniz?`). Wake-on-LAN İSE GÜVENLE
gerçek test edildi — bu makinenin kendi gerçek MAC adresine
(`00-50-56-92-6D-A3`) gerçek bir magic packet gönderildi,
`{"status":"sent","mac_address":"00-50-56-92-6D-A3"}` yanıtı alındı.

## Faz 38 — Network Topology: İnteraktif Graph Görünümü (React Flow)

**Durum:** ✅ Tamamlandı.

**Bağlam:** `/topology` sayfasının eski statik grid görünümü (cihaz
tipine göre gruplandırılmış kutular, elle yazılmış pan/zoom/drag state)
`@xyflow/react` (React Flow, MIT) tabanlı interaktif bir graph'a
dönüştürüldü. Yalnızca frontend — backend/agent'a dokunulmadı.

**Kapsam:**
- `npm install @xyflow/react` (yeni bağımlılık, MIT lisans).
- `lib/deviceIcons.tsx` (YENİ) — cihaz tipine göre (server/workstation/
  switch/firewall/router/access_point/printer/camera/nas/network_device)
  sade SVG ikonlar + bilinmeyen tip için nötr (alarm-kırmızısı DEĞİL)
  bir `Unknown` ikonu + hub node için `Gateway` ikonu.
- `components/NetworkTopologyGraph.tsx` (YENİ) — React Flow wrapper.
  `buildGraph()` gerçek `asset.ip_address`'ten türetilen `/24` subnet'e
  göre cihazları gruplar: tek subnet varsa merkezde bir hub + dairesel
  (radial) düzende cihazlar; birden fazla subnet varsa kök düğüm →
  her subnet'in kendi hub'ı → o hub'ın çevresinde cihazları (iki
  seviyeli hiyerarşi). Kenar (edge) sayısı UYDURULMADI — her cihazın
  kendi hub'ına, birden fazla subnet'te her hub'ın köke bir kenarı var.
  Sürükleme/mouse-wheel zoom/"Fit View" React Flow'un kendi
  `Controls`/`fitView` özellikleri (`fitViewOptions={{padding:0.25}}`,
  `minZoom`/`maxZoom`). React Flow'un ücretsiz kullanım attribution'ı
  BİLİNÇLİ olarak gizlenmedi (`hideAttribution` Pro aboneliği
  gerektirir, lisans ihlali olur).
- Node görselliği: cihaz durumuna göre (`asset.status === "up"`) yeşil
  nabız/glow animasyonu (`@keyframes pulse`) + yeşil/gri durum noktası;
  kırmızı "BİLİNMİYOR" işareti YOK — bilinmeyen cihaz tipi nötr gri bir
  ikonla gösteriliyor. Hostname/IP ikonun altında compact bir etiket.
- `components/AssetDetails.tsx` zaten sağdan açılan bir Sheet/Drawer'dı
  (Faz 20/29.5) — ek bir iş gerekmedi, yalnızca `NetworkTopology.tsx`
  bir düğüme tıklandığında bu paneli açacak şekilde bağlandı (Quick
  Inspect: IP/MAC/portlar/latency zaten mevcut sekmelerde; RDP/SSH
  hızlı bağlantı için aşağıya bkz).
- `components/AssetAgentPanel.tsx` (Agent sekmesi) — asset'e bağlı
  GERÇEK bir Agent varsa (`agent.local_ip` doluysa) RDP/SSH hızlı
  bağlantı butonları eklendi, `AgentDetailView.tsx`'teki AYNI
  `agentRdpConnectUrl`/`/remote-control/ssh/{agentId}` deseni yeniden
  kullanıldı — agent yoksa buton hiç gösterilmez (uydurma bağlantı
  YOK).
- Üst metrik kartları: padding `14px 16px` → `8px 12px`, font-size'lar
  küçültüldü. "Bağlantılar" artık gerçek aktif kenar sayısını gösterir
  (`filteredAssets.length + (subnetCount > 1 ? subnetCount : 0)`).
- `lib/i18n/translations.ts`: eski grid'e özel `zoomIn`/`zoomOut`/
  `resetView`/`groups` anahtarları kaldırıldı (React Flow'un kendi
  Controls'u onların yerini alıyor), `topology.graph.network` eklendi,
  `assetDetails.agent.rdpConnect`/`sshConnect` eklendi (TR + EN).

**Kapsam dışı (bilinçli):** LLDP/CDP tabanlı gerçek Layer-2 topolojisi
(Faz 25, hâlâ ertelenmiş) — kenar çizgileri hâlâ subnet/gateway
ilişkisinden türetiliyor, gerçek kablolama verisi DEĞİL; bu, hem eski
hem yeni görünümde aynı dürüst sınırlama, `connectionsNote` metninde
açıkça belirtiliyor.

**Testler:** `tests/NetworkTopology.test.tsx` yeniden yazıldı (React
Flow'un kendi canvas/ölçüm katmanı jsdom'da simüle edilemediği için
`@xyflow/react` `tests/SshTerminal.test.tsx`'teki xterm.js mock'uyla
aynı desenle mock'landı — yalnızca bu projenin kendi mantığı test
ediliyor: node içerikleri, tıklama→seçim, filtreler, gerçek
bağlantı sayısı). `npx tsc --noEmit` ve `npm run lint` temiz. Frontend
292/292 (12 topology testi dahil, hepsi yeşil).

**Gerçek E2E doğrulama:** Gerçek backend + gerçek 14 asset'lik envanter
karşısında `/topology` canlı olarak görüntülendi — merkezi
`10.0.213.0/24` hub düğümü, cihazlar dairesel dizilimde, çevrimiçi
cihazlarda yeşil glow, "Bağlantılar: 14" gerçek sayısı. Bir düğüme
tıklanınca sağda Quick Inspect drawer'ı gerçekten açıldı (Genel Bakış/
Ağ/Keşif/Portlar/İzleme/SNMP/Agent/Uyarılar sekmeleri). Agent sekmesi
test edilen asset'e henüz bir Agent bağlı olmadığı için dürüstçe "Bağlı
bir Agent yok" gösterdi; aynı RDP/SSH buton deseni `/agents/{id}`
sayfasında (gerçek bağlı WIN-G4E9UGRTH8E agent'ı için) çalışır halde
doğrulandı — `AssetAgentPanel.tsx`'in kullandığı aynı çeviri anahtarları
ve URL üretimi.

## Faz 39 — SNMP Auto-Assign, Arka Plan Polling Worker'ı, CPU/Bellek (HOST-RESOURCES-MIB) ve "İzleme"/Dashboard Canlı Telemetri Yenilemesi

**Durum:** ✅ Tamamlandı.

**Kapsam:**
- **Auto-Assign** (`app/snmp/profile_service.py::_auto_assign_if_ip_matches`):
  bir SNMP profili kaydedildiğinde/güncellendiğinde/başarıyla test
  edildiğinde `target_host` bir asset'in `ip_address`'iyle TAM
  eşleşiyorsa profil o asset'e otomatik atanır — yalnızca asset'in
  ZATEN bir profili yoksa (elle yapılan bir atama SESSİZCE ÜZERİNE
  YAZILMAZ). Agent↔Asset eşleştirmesindeki (Faz 29) çoklu-sinyal
  temkinliliğinden bilinçli bir sapma — kullanıcı zaten `target_host`'u
  kendi eliyle, tekil bir hedef olarak girmiş durumda.
- **Arka plan SNMP polling worker'ı** (`app/snmp/scheduler.py`) —
  FastAPI `lifespan`'da başlar (`app/main.py`), periyodik olarak (`
  SNMP_POLL_INTERVAL_SECONDS`, varsayılan 30sn) `PollingEngine.
  poll_all`'ı çalıştırıp sonucu `app/snmp/monitoring_cache.py`'ye
  (süreç-içi, kalıcı olmayan) yazar. `SNMP_BACKGROUND_POLLING_ENABLED
  =false` ile kapatılabilir. `httpx.ASGITransport` (test client'ı)
  FastAPI lifespan event'lerini hiç tetiklemediği için testlere SIZMAZ.
- **CPU/Bellek** (`app/snmp/client.py::_get_cpu_memory_info`, yeni
  `SystemInfo.cpu_percent`/`memory_used_bytes`/`memory_total_bytes`) —
  HOST-RESOURCES-MIB (`hrProcessorLoad`/`hrStorageTable`) üzerinden
  GERÇEK okunur. Çoğu switch/router/firewall bu MIB'i desteklemez —
  desteklenmiyorsa dürüstçe `None` kalır, poll'un genel `status`'unu
  ASLA etkilemez (system GET'in kendi hata yönetiminden BİLİNÇLİ
  olarak ayrı).
- **`GET /api/health/snmp`** artık gerçek `snmp_profiles` durumunu
  yansıtıyor (en az bir `ready` profil varsa `configured`) — önceden
  her zaman sabit `not_configured` dönüyordu.
- **`GET /api/monitoring/history`** (yeni) — `monitoring_cache.py`'nin
  süreç-içi önbelleğini (son batch + poll audit log + bant genişliği
  zaman serisi) döner, HİÇBİR yeni poll TETİKLEMEZ (DB'ye bile
  bağlanmaz) — sık (5-10sn) çağrılması güvenli, `GET /api/monitoring`
  (her çağrıda gerçek bir poll turu çalıştırır) ile KARIŞTIRILMAMALI.
- **"İzleme" sayfası** (`MonitoringOverview.tsx`) tamamen yenilendi:
  KPI bar (SNMP Kapsam Oranı gauge, İzlenen Cihaz Sayısı, Ağ Sağlık
  Skoru, Toplam Ağ Trafiği, Ortalama Yanıt Süresi — hepsi gerçek
  veriden), Recharts tabanlı bant genişliği alan grafiği, arayüz durum
  tablosu, "Son Poll Logları" canlı audit akışı. 7 saniyede bir
  sessizce (`useAutoRefresh`) yenilenir. "Veri mevcut değil" kutuları
  yalnızca gerçekten veri yokken (ör. HOST-RESOURCES-MIB desteklenmiyor)
  görünür.
- **Dashboard** (`DashboardSummary.tsx`, `page.module.css`): 4 KPI
  kartı artık `/assets`'e filtrelenmiş hızlı bağlantılar (Toplam Varlık
  → `/assets`, Yüksek Riskli Portlar → `/assets?highRisk=1`, Yönetilmeyen
  → `/assets?deviceType=unknown`, Sağlık Skoru → `/assets?status=down`)
  + hover tooltip + sağ üstte "Yenile" butonu. `AssetInventory.tsx`
  bu deep-link'leri (`?status=`/`?deviceType=`/`?highRisk=1`) okur,
  ayrıca yeni bir "Yalnızca yüksek riskli portlar" checkbox filtresi
  eklendi. Sol/sağ kolon oranı 2fr/1fr'ye (tam 2/3-1/3) güncellendi.
- **Auto-refresh** (`lib/useAutoRefresh.ts`, yeni paylaşımlı hook) —
  `DashboardDataProvider` artık 8 saniyede bir sessizce (`refetchAssets/
  refetchScans({silent:true})` — `status`'u `loading`'e GERİ ALMAZ,
  layout sıçraması yok) kendini yeniler; bu, Dashboard'u tüketen HER
  component'e otomatik yansır.

**Testler:** Backend 443→469 (yeni: `test_secrets.py` genişletmeleri,
`test_monitoring_cache.py`, `test_scheduler.py`, auto-assign testleri,
CPU/Bellek testleri). Frontend 294→304.

**Gerçek E2E doğrulama:** Arka plan worker backend başlar başlamaz
gerçek bir poll turu attı (poll log'da anında göründü, hiç manuel
tetikleme gerekmedi). Ayarlar'da "SNMP Durumu: Yapılandırıldı / Aktif"
gerçek profil varlığına göre değişti. Dashboard'daki "Yüksek Riskli /
Açık Portlar" kartına tıklanınca `/assets`'e "Yalnızca yüksek riskli
portlar" filtresi ÖNCEDEN İŞARETLENMİŞ olarak gerçekten gitti.

**Yan bulgular (bu fazın kapsamı DIŞINDA, ayrı görevler olarak
bırakıldı):** (1) `app/agents/enrollment.py::delete_expired_codes`
süresi dolmamış kodları da siliyor gibi görünüyor (gerçek test
çalıştırmasında keşfedildi) — ayrı bir arka plan göreve not düşüldü.
(2) Birçok route'un `_connect()` yardımcı fonksiyonu HER istekte
`ensure_schema()` (DDL: `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE`)
çalıştırıyor — eşzamanlı isteklerde (ör. bir Agent'ın 3 arka plan
thread'i + tek bir ek istek) gerçek bir `DeadlockDetectedError`
üretti, canlı backend log'unda doğrulandı. Schema kurulumu uygulama
başlangıcında TEK SEFER yapılmalı — ayrı bir arka plan göreve not
düşüldü, bu fazda DÜZELTİLMEDİ.

## Faz 40 — Agent Windows Servisi / systemd Otomasyonu

**Durum:** ✅ Tamamlandı.

**Kapsam:**
- **Windows:** `agent/scripts/install_windows_service.ps1` (Yönetici
  kontrolü → `packaging/windows/build_service.ps1` ile build →
  `sc.exe create`/`start`) + `uninstall_windows_service.ps1` (`sc.exe
  stop`/`delete`). Service Name `ITOpsAgent`, Display Name `IT
  Operations Assistant Telemetry Agent`, Startup Type `Automatic`
  (`start= auto`) — kullanıcı isteğiyle BİREBİR.
- **Kritik teknik bulgu (gerçek testle keşfedildi):** düz bir `sc.exe
  create` + ham konsol EXE'si Windows Service Control Manager (SCM)
  protokolünü implemente ETMEZ — `sc start` "zamanında yanıt vermedi"
  hatasıyla başarısız olur VE `sc stop` gerçek bir graceful-shutdown
  sinyali GÖNDEREMEZ (SCM timeout sonunda süreci sert keser). Bu
  yüzden yeni bir servis-özel giriş noktası eklendi: `agent/
  winservice.py` — `pywin32`'nin `win32serviceutil.ServiceFramework`'ünü
  implemente eder, `SvcStop` mevcut `AgentRuntime.stop()` yolunu
  (aynı `_stop_event` + `thread.join`) çağırır. Ayrı bir PyInstaller
  spec'i (`packaging/windows/IT-Operations-Agent-Service.spec`, sabit
  çıktı adı `dist/itops-agent.exe` — CLI EXE'nin versiyonlu adının
  AKSİNE) + `build_service.ps1`. `sc.exe create`/`start`/`stop`/
  `delete` komutlarının KENDİSİ değişmedi — yalnızca EXE'nin içi
  SCM-uyumlu; `pywin32` yalnızca `packaging/windows/requirements-
  build.txt`'e eklendi (runtime `requirements.txt`'e DEĞİL).
  `AgentRuntime.start()`'taki `signal.signal()` kaydı artık `try/except
  ValueError` ile korunuyor (servis bağlamında ana thread dışında
  çağrıldığında sessizce atlanır — kapatma `SvcStop`'tan gelir).
- **Linux:** `agent/scripts/install_linux_service.sh` (root/sudo
  kontrolü → `/opt/itops-agent`'a kopyalama → venv kurulumu → gerekirse
  `itops-agent` sistem kullanıcısı → `/etc/systemd/system/itops-
  agent.service`'i GERÇEK path'lerle üretme → `systemctl daemon-reload/
  enable/start`) + `uninstall_linux_service.sh` (`--purge` ile kurulum
  dizinini de silme opsiyonu). `Restart=always`/`RestartSec=5`
  (kullanıcı isteğiyle BİREBİR). Referans `deploy/systemd/itops-
  agent.service` güncellendi (artık bu script'in ürettiğiyle aynı
  restart politikası, script'in var olduğu belirtiliyor).
- **Dosya loglama** (`agent/main.py::_add_file_logging`, yeni
  `AgentConfig.log_file`/`AGENT_LOG_FILE`) — `start` komutu artık
  konsola EK OLARAK boyut sınırlı (rotating, 5MB × 3 yedek) bir
  dosyaya da loglar; dosya yazılamıyorsa agent ÇÖKMEZ, yalnızca uyarı
  loglar.

**Testler:** Agent 184→207 (yeni: `test_winservice.py` — pywin32 sahte
modüllerle, Linux CI'da da çalışır; `config.py`/`main.py` dosya
loglama + sinyal-guard testleri; `test_packaging.py`'ye servis
spec/script varlık testleri + **regresyon testi**: hiçbir `.ps1`
Write-Host/Write-Error/Write-Warning satırı em/en dash içermemeli).

**Gerçek E2E doğrulama (Windows — bu makinede, Administrator
yetkisiyle):** `install_windows_service.ps1` gerçekten çalıştırıldı —
EXE build edildi, `ITOpsAgent` servisi kaydedildi, `RUNNING` durumuna
ulaştı, gerçek bir enrollment koduyla backend'e kayıt oldu, gerçek
heartbeat/telemetry/inventory gönderdi, `dist/agent.log`'a gerçekten
yazdı. `sc stop` GERÇEKTEN graceful durdurdu (log: "SCM stop isteği
alındı → Agent durdu → Servis durdu", sert kesme YOK).
`uninstall_windows_service.ps1` servisi gerçekten kaldırdı. Bu süreçte
GERÇEK bir sözdizimi hatası bulunup düzeltildi (bkz. yukarıdaki
regresyon testi) — bir `Write-Error` satırındaki em dash, BOM'suz bir
`.ps1` dosyasını Windows PowerShell 5.1 altında bozuyordu. Test agent
kaydı ve `.env`/log dosyaları sonra temizlendi. **Linux tarafı gerçek
bir makinede DOĞRULANMADI** (bu ortamda yok) — yalnızca `bash -n`
sözdizimi kontrolü + mantık incelemesiyle doğrulandı.

**Faz 40 sonrası bir bugfix de tamamlandı** (kullanıcının servisi
GERÇEKTEN kalıcı kurmasıyla — test-kur-kaldır döngüsü değil — bulundu):
Windows Service Control Manager (SCM) bir servisi başlatırken süreç
CWD'sini `C:\Windows\System32` yapıyor — `AGENT_STATE_FILE`'ın eski
göreli varsayılanı (`.itops-agent-state.json`, CWD'ye göre) bu yüzden
System32'ye yazılıyordu, EXE'nin yanına DEĞİL. Bu, servis her yeniden
kurulduğunda/EXE her taşındığında (ör. `dist/` temizlendiğinde) System32'de
kalan ESKİ bir token'ın okunup "kimlik doğrulama başarısız" ile
sessizce durmasına yol açıyordu — canlı kalıcı kurulumda YAKALANDI.
Düzeltme: `.env`/`agent.log` için zaten var olan "frozen EXE'de kendi
dizinine çöz" deseni (`main.py::_default_dotenv_path`/
`_default_log_file_path`) artık state dosyası için de var
(`_default_state_file_path`, `load_config`'e yeni `default_state_file`
parametresi — `AGENT_STATE_FILE` açıkça set edilmemişse kullanılır,
set edilmişse önceliklidir). `config.py::DEFAULT_STATE_FILE_NAME`
public'e çevrildi (main.py ile paylaşılıyor). `install_windows_
service.ps1`'de ayrı bir gerçek bug daha bulunup düzeltildi: build
adımı servis DURDURULMADAN ÖNCE çalışıyordu — çalışan eski süreç
EXE dosyasını kilitlediği için yeniden kurulum `PermissionError:
Access is denied` ile başarısız oluyordu; sıra değiştirildi (önce
durdur/sil, sonra build). Agent 207→211 test. Gerçek E2E ile
doğrulandı: System32'deki eski state dosyası temizlendi, servis
yeniden build edilip kuruldu, GERÇEKTEN yeni bir agent kimliğiyle
kaydoldu, state dosyası artık doğru şekilde `dist/` altında,
heartbeat/telemetry/inventory başarıyla gönderildi — bu makinede artık
kalıcı, gerçek bir `ITOpsAgent` servisi RUNNING durumda.

**Faz 40 sonrası bir özellik daha eklendi:** "Windows Servisi Paketi"
web'den indirme — kullanıcı isteği ("başka bir bilgisayara kurmam için
GUI'ye indirme koy"). `app/agents/download.py::
resolve_windows_service_artifact`/`build_windows_service_bundle_zip`
(`GET /api/agents/download/windows-service`(`/info`)) önceden build
edilmiş `itops-agent.exe` + `install_windows_service.ps1` +
`uninstall_windows_service.ps1` + otomatik üretilen bir README.txt'i
TEK bir ZIP olarak, BELLEKTE (diske hiç yazmadan) paketler — mevcut
CLI EXE indirmesiyle AYNI ilke (backend PyInstaller'ı asla kendisi
çalıştırmaz, yalnızca `packaging/windows/build_service.ps1`'in ürettiği
`service-build-info.json`'ı okur — build.ps1'in kendi manifest'iyle
AYNI ASCII-safe encoding deseni). `install_windows_service.ps1`
ÇİFT modlu hale getirildi: kaynak ağacından çalıştırılırsa (mevcut
davranış) önce build eder; bir indirme paketinden (ZIP'in içinden,
`itops-agent.exe` script'in YANINDA) çalıştırılırsa build adımını
ATLAR — hedef bilgisayarda Python/PyInstaller kurulu olması hiç
GEREKMEZ. Settings > Agent Configuration'da CLI EXE'nin altına yeni
bir "Windows Servisi Paketi" bölümü eklendi (`AgentDownloadPanel.tsx`).
Backend 469→477 test (yeni: `resolve_windows_service_artifact`/
`build_windows_service_bundle_zip` birim testleri + 6 route testi,
gerçek repo script'leriyle uçtan uca bir test dahil). Frontend
304→307 test. **Gerçek E2E doğrulandı:** canlı backend'den GERÇEK bir
ZIP indirildi, açıldı, içindeki `itops-agent.exe`/`install_windows_
service.ps1` gerçek disk dosyalarıyla bayt-bayt ÖZDEŞ olduğu
doğrulandı (`diff`), GUI'de (Ayarlar sayfası) gerçek versiyon/boyutla
görüntülendi.

**Faz 41 — Agent Lifecycle Management** de tamamlandı: kullanıcı isteği
("Agent'lar sayfasına ve backend altyapısına tam yaşam döngüsü
yönetimi, uzaktan sürüm güncelleme ve otomatik temizleme mekanizmaları
ekle"). Kullanıcının önerdiği ayrı bir `archived_agents`/`agent_history`
tablosu YERİNE, mevcut `agents` tablosuna soft-delete kolonları
eklenmesi tercih edildi (bilinçli sapma — gerekçe: bir agent'ı ayrı bir
tabloya taşımak `agent_telemetry`/`agent_inventory`/`agent_commands`'in
FK referanslarını ya kaskad silmeyi ya da GERÇEK geçmişi kaybetmeyi
gerektirirdi; soft-delete tüm geçmişi korur VE geri yükleme yeni bir id
üretmez). Yeni kolonlar: `agents.archived_at`/`archived_reason`
(`manual`/`inactivity`)/`archived_after_inactive_days` + yeni
`agent_retention_policy` (tek satırlı config) tablosu. Arşivleme, Faz
28'den beri var olan `revoked_at` mekanizmasını da doldurur — ayrı bir
kontrol eklemeden arşivlenen bir agent otomatik olarak kimlik
doğrulayamaz hale gelir.

Backend: `app/db/agents.py`'ye `archive_agent`/`restore_agent`/
`list_archived_agents`/`list_inactive_agent_ids`/`get_retention_policy`/
`set_retention_policy`; `app/agents/scheduler.py` (yeni arka plan
worker — `AGENT_MAINTENANCE_ENABLED`, varsayılan açık, ama GERÇEK
arşivleme yalnızca DB politikası `enabled=true` iken olur, `ENABLE_
REMOTE_COMMANDS` ile AYNI iki-anahtarlı opt-in ilkesi; bu worker Faz
29'dan beri hiçbir zamanlayıcıya bağlı olmayan `cleanup_expired_
telemetry`'yi de bonus olarak devreye aldı). `agent_commands`'e yeni
komut tipleri (`uninstall_service`/`update_self`) eklendi — Faz 33'ün
mevcut kuyruk/audit altyapısı AYNEN reuse edildi, yeni bir mekanizma
kurulmadı. Yeni route'lar: `DELETE /api/agents/{id}` (opsiyonel
`send_uninstall_command`), `POST .../restore`, `GET .../archived`,
`GET`/`PUT .../retention-policy`, `POST .../update`. `AgentSummary`'ye
`update_available`/`latest_available_version` eklendi (sunucudaki
GERÇEK build edilmiş `service-build-info.json`'dan — Faz 32/40 sonrası
paketleme — karşılaştırılıyor, build yoksa dürüstçe `false`/`null`).

**Bu fazın yan ürünü olarak GERÇEK, tekrarlanabilir bir deadlock bug'ı
kök nedeninden düzeltildi:** her `ensure_schema()` çağrısı `infra/
postgres/init.sql`'in TAMAMINI yeniden çalıştırıyordu ve 6 route
dosyasında HER İSTEKTE tetikleniyordu — bu oturumda canlı yükte
(gerçek Windows servisi + eşzamanlı istekler) tekrar tekrar gerçek
`asyncpg.exceptions.DeadlockDetectedError` gözlemlendi. Bu faza YENİ
bir DDL (CHECK constraint genişletme) eklenecekken sorunu büyütmek
yerine kök neden düzeltildi: `app/main.py::_ensure_schema_once()` artık
şemayı yalnızca uygulama başlangıcında BİR KEZ kurar (`lifespan`), 6
route dosyasından (`agents`/`agent_commands`/`agent_ssh`/`asset_snmp_
profiles`/`discovery`/`snmp_profiles`) per-request `ensure_schema()`
çağrıları kaldırıldı. `tests/conftest.py::isolated_db` zaten şemayı
BAĞIMSIZ olarak bir kez kurduğu için test izolasyonuna etkisi yok.

Agent tarafı: yeni `apps/agent/agent/lifecycle.py` — Windows-ONLY
(Linux'ta ikisi de dürüstçe "desteklenmiyor"). `uninstall_service()`
servisi durdurur+SCM kaydını siler (`sc.exe`). `update_self(backend_
url)` mevcut `GET /api/agents/download/windows-service` ZIP'ini indirir
(yeni bir backend endpoint'i EKLENMEDİ — Faz 40 sonrası ZIP paketi
reuse edildi), içinden `.exe`'yi çıkarır, DETACHED bir PowerShell
yardımcı süreci üretir (agent kendi çalışan EXE dosyasını KENDİSİ
değiştiremez — Windows dosya kilidi; yardımcı süreç agent/servisin
durmasını bekler, dosyayı değiştirir, servisi yeniden başlatır).
`agent/commands.py::execute()` `backend_url` parametresiyle genişletildi,
iki yeni komut tipini `lifecycle.py`'ye dispatch ediyor.

Frontend: `/agents` sayfasına Aktif/Arşiv sekmeleri (`ArchivedAgentsList.
tsx` — Geri Yükle butonu, silinme sebebi/ne kadar aktif kaldığı sütunları),
`AgentRetentionPolicyPanel.tsx` (Aktif sekmesinin üstünde, enable/days
formu, 7/14/30 gün preset + özel değer), `AgentsList.tsx`'e Sil (mevcut
`ConfirmModal.module.css` stilleri reuse edilerek, opsiyonel "uninstall
komutu gönder" checkbox'ı ile) ve Güncelle butonları + versiyon
uyuşmazlığı rozeti + toplu "Tüm Agent'ları Güncelle". `lib/time.ts`'e
yeni `formatDuration()` (kompakt "Xg Ys" biçimi). Backend 477→508 test
(31 yeni: route/service/scheduler), Agent uygulaması 211→226 test (15
yeni: `lifecycle.py` + `execute()` dispatch), frontend 307→322 test (15
yeni). **Gerçek E2E doğrulandı:** canlı backend'e geçici bir test
agent'ı kaydedilip GERÇEK UI üzerinden silindi (arşivlendi), Arşiv
sekmesinde doğru sebep/süre ile göründü, Geri Yükle ile GERÇEKTEN geri
alındı, sonra API üzerinden temizlendi (test verisi, gerçek üç agent'a
DOKUNULMADI — silme modalının doğru satırı hedeflediği ayrıca
doğrulandı). Retention Policy paneli gerçek backend değeriyle (kapalı,
30 gün) doğru render edildi. `update_self`/`uninstall_service`'in
GERÇEK bir Windows servisi üzerinde çalıştırılması bu increment'e dahil
EDİLMEDİ (yalnızca mock'lanmış birim testleriyle doğrulandı) — kullanıcının
kendi kalıcı `ITOpsAgent` servisine karşı canlı bir OTA güncelleme/
kaldırma denemesi bilinçli olarak yapılmadı, kullanıcı hazır olduğunda
ayrı bir onayla denenebilir.

**Faz 42 — Ağ Bağlantı Sorunu Debug/Logging + Windows Update Tarama
Motoru** de tamamlandı: kullanıcı isteğiyle ("Agent'ın Windows
güncellemelerini çekememesi ve başka PC'lere kurulduğunda Dashboard'a
kaydolamaması sorunlarını çöz").

**Dürüstlük notu — kullanıcının teşhisiyle GERÇEK kod arasındaki fark:**
kod tabanında sabit tanımlı (hardcoded) `127.0.0.1`/`localhost` YOKTU —
`BACKEND_URL` zaten Faz 30'dan beri zorunlu, `.env`/ortam değişkeninden
okunan tek yapılandırma kaynağıydı (`config.py::load_config` `BACKEND_
URL` verilmezse `ConfigError` fırlatır). Yeni bir `SERVER_URL` parametresi
de EKLENMEDİ — aynı işi zaten yapan `BACKEND_URL` ile çakışan/karışan
ikinci bir isim açmak tutarlılığı bozardı. Bunun yerine GERÇEK kök neden
bulundu: `BACKEND_URL` eksik/geçersizken bir Windows Servisi/systemd
daemon'u (konsolsuz) olarak çalışırken hata yalnızca stderr'e (kimsenin
görmediği) yazılıyordu — geçerli bir `AgentConfig` olmadığı için `agent.
log`'a dosya loglama hiç BAŞLAMIYORDU. `apps/agent/agent/main.py::
_log_fatal_config_error()` (yeni) bu durumda da en azından varsayılan
konuma bir dosya handler'ı ekleyip hatayı `agent.log`'a yazıyor;
`agent/winservice.py::SvcDoRun` aynı fonksiyonu kullanacak şekilde
güncellendi (Windows Event Log'a yazma da AYRICA korunur).

**Debug/Logging iyileştirmesi:** `agent/client.py::BackendClient.
heartbeat()` artık tam `HttpResponse` (status + body) döner — önceden
yalnızca body dönüyordu, HTTP durum kodu sessizce atılıyordu;
`AgentRuntime._send_heartbeat` artık `"Heartbeat gönderildi (HTTP
%s)"` şeklinde açıkça loglar. Bağlantı hataları (`BackendUnavailableError`)
artık `_categorize_connection_error()` ile "Bağlantı reddedildi
(Connection Refused)" / "Zaman aşımı (Timeout)" / "DNS çözümlenemedi"
gibi AÇIK bir kategori etiketiyle loglanıyor (orijinal exception mesajı
HER ZAMAN korunur, bilgi kaybı yok); 401/403/422/5xx hataları artık
mesajlarında `HTTP {kod}` içeriyor.

**Windows Update Tarama Motoru:** yeni `apps/agent/agent/collectors/
windows_updates.py` — iki aşamalı, dürüst bir strateji. Birincil:
COM (`win32com.client.Dispatch("Microsoft.Update.Session")`,
`Search("IsInstalled=0 and IsHidden=0")`) GERÇEKTEN BEKLEYEN
güncellemeleri döner. COM başarısız olursa yedek: `Get-CimInstance
Win32_QuickFixEngineering` — **kullanıcının önerdiği `Search-
WindowsUpdate` DEĞİL** (o cmdlet üçüncü parti `PSWindowsUpdate`
modülü gerektirir, varsayılan Windows kurulumunda YOK, bir arka plan
ajanının sessizce internet'ten modül kurması riskli/kırılgan olurdu).
`Win32_QuickFixEngineering` her Windows'ta yerleşik ama FARKLI bir
anlam taşır: BEKLEYEN değil ZATEN KURULMUŞ hotfix'leri listeler — bu
fark `scan_method` alanında (`com`/`installed_hotfixes`/`unavailable`)
AÇIKÇA taşınır, hiçbir yerde `com` sonucuymuş gibi GÖSTERİLMEZ.
`is_windows_admin()` (`ctypes.windll.shell32.IsUserAnAdmin()`) yönetici
yetkisini raporlar (kısıtlayıcı bir engel DEĞİL, yalnızca bilgi amaçlı).
Yeni arka plan döngüsü (`ENABLE_WINDOWS_UPDATES_SCAN`, varsayılan açık
— salt-okunur bir tarama; `WINDOWS_UPDATES_INTERVAL`, varsayılan 6 saat
— COM `Search()` gerçek bir Windows Update sunucusu isteği yapabilir,
sık çalıştırılmamalı), yalnızca Windows'ta başlar.

Backend: additive `agent_windows_updates` tablosu (agent başına TEK
satır, `agent_inventory` ile AYNI "şu anki durum" deseni), yeni `app/
agents/update_models.py` + `app/db/agent_updates.py` + `app/routes/
agent_updates.py` (`POST`/`GET /api/agents/{id}/updates` — **kullanıcının
önerdiği `/api/v1/...` DEĞİL**, projenin geri kalanıyla AYNI, versiyonsuz
URL şeması). `POST` Bearer auth (telemetry/inventory ile AYNI desen),
`GET` auth'suz (mevcut `GET /api/agents/{id}` ile AYNI ilke).

Frontend: `AgentDetailView`'e yeni "Windows Güncellemeleri" sekmesi —
tarama zamanı/yöntemi/yönetici durumu + KB/başlık/boyut tablosu;
`installed_hotfixes` sonucunda KIRMIZI bir uyarı metni ("bekleyen
güncellemeler DEĞİL, ZATEN KURULMUŞ hotfix'ler gösteriliyor") HER ZAMAN
görünür. Linux agent'larında dürüstçe "yalnızca Windows'ta destekleniyor".

**Yan ürün olarak GERÇEK iki bug bulunup düzeltildi:** (1) `tests/
conftest.py::_ROUTE_GET_CONNECTION_TARGETS` listesi yeni `app.routes.
agent_updates` modülünü içermiyordu — bu, testin `get_connection()`'ının
isolated_db'nin paylaşımlı transaction'ına yönlendirilmemesine, bunun
yerine GERÇEK bir ikinci bağlantı açmasına yol açtı; bu ikinci bağlantı
isolated_db'nin (henüz commit/rollback edilmemiş) tuttuğu kilitler
yüzünden KENDİ KENDİNİ süresiz bloke ediyordu (gerçek, tekrarlanabilir
bir test-izolasyon deadlock'ı, canlı ortamdaki `pg_stat_activity` ile
teşhis edildi) — düzeltme: yeni route modülü listeye eklendi. (2) bu
oturumun DAHA ÖNCEKİ (context-compaction öncesi) Agent Lifecycle
Management E2E doğrulaması sırasında GERÇEK `agent_retention_policy.
enabled` `true` ve İKİ GERÇEK agent (`WIN-G4E9UGRTH8E`, `WIN-27EVDRJ3O31`)
arşivlenmiş (token'ları iptal edilmiş) halde KALMIŞ — bu oturumda
keşfedilip HEMEN düzeltildi (politika `false`'a döndürüldü, iki agent
`POST .../restore` ile geri yüklendi, gerçek üçüncü agent zaten
etkilenmemişti).

Agent 250→257 test (client.py 22→32, main.py'ye 4+3 yeni,
windows_updates.py 12 yeni), Backend 508→516 test (7 yeni route testi).
**Gerçek E2E doğrulandı:** bu makinede GERÇEK bir COM taraması çalıştırıldı
(admin=true, 0 bekleyen güncelleme — makine güncel), sonucu canlı
backend'e gönderildi, `GET` ile doğrulandı; ayrı bir test agent'ıyla
`installed_hotfixes` (yedek yöntem) senaryosu GERÇEK UI'da (Windows
Güncellemeleri sekmesi) görüntülenip kırmızı uyarı metninin göründüğü
doğrulandı; her iki test agent'ı sonra temizlendi (arşivlendi).

**Bir Faz 42 sonrası bugfix de tamamlandı** — gerçek kullanıcı bildirimi
("başka bir pc'ye agent yüklüyorum GUI'de görmüyorum") ile bulundu:
Windows Servisi (konsolsuz) bağlamında `ensure_registered()` içinde
oluşan HERHANGİ bir istisna (süresi dolmuş/kullanılmış enrollment kodu,
ağ hatası vb.) `agent.log`'a hiç yazılmıyordu — thread'in kendi
excepthook'u yalnızca stderr'e yazıyordu (bir serviste kimse görmez),
log yalnızca "kayıt deneniyor" satırında SESSİZCE duruyordu.
`AgentRuntime.start()` artık kayıt hatasını loglayıp yeniden fırlatıyor;
`winservice.py::SvcDoRun`'ın runtime thread'i de (savunma amaçlı ikinci
katman) HERHANGİ bir istisnayı `agent.log`'a yazacak şekilde
sarmalandı. Gerçek `ITOpsAgent` servisi bu düzeltmeyle yeniden build
edilip güvenle durdurulup/başlatıldı. Agent 257→260 test.

**Faz 43 — Windows Update Tarama Motoruna Anlık Tarama Ekleme** de
tamamlandı: kullanıcı isteğiyle "Windows Güncellemeleri" sekmesine
"🔄 Güncellemeleri Kontrol Et" butonu eklendi. Kullanıcının "mevcut
Ajan komut kuyruğunu bozmadan" talimatına uyularak yeni bir endpoint
YERİNE mevcut `agent_commands` kuyruğu (Faz 33) genişletildi: yeni
`check_updates`/`scan` komut tipi (`refresh_inventory` ile AYNI
"OS-dispatcher'dan geçmeyen özel komut" deseni) — `agent/main.py::
_poll_and_execute_commands` bunu doğrudan `_send_windows_updates()`'e
yönlendirir (artık `UpdateScanResult` döndürüyor, hem periyodik döngü
hem bu komut AYNI fonksiyonu paylaşıyor). Frontend buton tıklanınca
`submitAgentCommand`+`pollAgentCommand` (mevcut Faz 37 güç komutu
deseniyle AYNI) ile komutu kuyruğa alır, "Windows Update servisi
sorgulanıyor, lütfen bekleyin..." bildirimini gösterir, komut
tamamlanınca tabloyu ve "Tarama Zamanı"nı otomatik tazeler. `Get-
WindowsUpdate` PowerShell modülü KULLANILMADI (Faz 42'de zaten
`Win32_QuickFixEngineering` yedek yöntemine karar verilmişti, gerekçe
orada — bu artırımda DEĞİŞMEDİ). Backend: `command_models.py`
+ `infra/postgres/init.sql`'deki CHECK constraint'lere `check_updates`/
`scan` eklendi (idempotent DROP+ADD deseni AYNEN). Agent 260→263,
Backend 517 test (2 yeni route testi + 3 yeni main.py testi).
**Gerçek E2E doğrulandı:** bu makinede GERÇEK bir agent süreci (dev
modu, throwaway) çalıştırılıp backend'e kaydedildi, GERÇEK UI'dan
"Güncellemeleri Kontrol Et" tıklanarak GERÇEK bir COM taraması
tetiklendi (bu makinede o anda GERÇEKTEN bekleyen bir Windows Defender
Security Intelligence güncellemesi — KB2267602 — bulundu), "Tarama
Zamanı" arayüzde otomatik güncellendi; test agent'ı sonra temizlendi.
Gerçek `ITOpsAgent` servisi de bu değişiklikle yeniden build edilip
güvenle yeniden başlatıldı.

**Faz 44 — Windows Update Tarama Motoruna Yükleme Tetikleme + KB
Detay/Bağlantı** de tamamlandı: kullanıcı isteğiyle "Windows
Güncellemeleri" tablosuna gerçek yükleme (Trigger Install) yeteneği
ve KB detay/Microsoft Support bağlantısı eklendi.

**Canlı yüzde ilerleme (`%XX`) KASITLI olarak UYGULANMADI** — kullanıcı
"İndiriliyor... %XX" gibi bir gösterge istemişti, ama Windows Update
Agent API'sinin COM arayüzü (pywin32 üzerinden) gerçek zamanlı indirme
yüzdesi için karmaşık bir COM event sink (`IDownloadProgressChangedCallback`)
kaydı gerektirir — bu, mevcut poll-tabanlı `agent_commands` mimarisiyle
(agent bir komutu senkron çalıştırıp yalnızca SONUNDA sonuç bildirir)
doğal olarak uyuşmuyor ve UYDURMA bir yüzde göstermek projenin "gerçek
veri, uydurma yok" ilkesini ihlal ederdi. Bunun yerine DÜRÜST, ayrık
durumlar kullanıldı: buton tıklanınca "Yükleniyor..." (agent GERÇEKTEN
indirip yüklerken, dakikalar sürebilir), tamamlanınca gerçek başarı/
başarısızlık + (varsa) "⚠️ Yeniden başlatma gerekiyor" — `pollAgentCommand`'a
bu komut için normalden (15sn) çok daha uzun bir `maxWaitMs` (10 dakika)
geçildi.

Backend/Agent: mevcut `agent_commands` kuyruğu kullanıcının açık
talimatına uyularak GENİŞLETİLDİ (yeni bir endpoint AÇILMADI) — yeni
`install_update`/`install` komut tipi (`command_models.py` + `init.sql`
CHECK constraint'leri), `target`: belirli bir KB numarası veya bekleyen
TÜMÜ için `"all"`. `agent/collectors/windows_updates.py::
install_updates()` — YALNIZCA COM (`Search` → `AcceptEula` → `Download`
→ `Install`), yedek PowerShell yolu YÜKLEME yapamaz (yalnızca okuma,
bkz. Faz 42 gerekçesi) — COM yoksa dürüstçe başarısız döner. `agent/
main.py::_poll_and_execute_commands`'e `install_update` özel-durumu
eklendi (`refresh_inventory`/`check_updates` ile AYNI desen) — bir
kurulumdan SONRA (başarılı da başarısız da olsa) otomatik taze bir
tarama gönderilir, kullanıcı elle "Kontrol Et"e basmadan tablo güncel
kalır.

`reboot_required` — yeni bir alan, HER taramada `Microsoft.Update.
SystemInfo().RebootRequired` (Windows Update Agent API'sinin KENDİ,
resmi "bu makine yeniden başlatma bekliyor mu" sorgusu) ile TAZE
sorgulanır — kendi başımıza bir bayrak tutup bayatlamasına izin
vermek yerine. `true` ise UI'da kırmızı bir banner + mevcut `power_
control`/`reboot` komutuna (Faz 37, YENİ bir mekanizma DEĞİL) tek
tıkla kısayol gösterilir. Yeni `agent_windows_updates.reboot_required`
sütunu (idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS`).

Frontend: KB numarası artık `https://support.microsoft.com/help/
{sayı}`'ya (yalnızca ham sayı, "KB" öneki YOK) giden tıklanabilir bir
harici bağlantı; başlığa tıklanınca (accordion) COM'dan gelen gerçek
`description` metni (Faz 42'de zaten toplanıyordu, yeni bir veri
YOK) genişleyerek gösterilir. Satır başına "Şimdi Yükle" + tablonun
üstünde "Tümünü Yükle" — ikisi de `kill_process`/`service_control`/
`power_control` ile AYNI `ConfirmModal` zorunluluğuna tabi (geri
dönüşü olmayan bir işlem). Yükleme butonları YALNIZCA `scan_method
=== "com"` iken gösterilir — `installed_hotfixes` (yedek yöntem)
satırları ZATEN KURULMUŞ hotfix'lerdir, "yükle" anlamsız/kesin
başarısız olurdu.

Agent 282, Backend 521 test (yeni: `windows_updates.py`'ye 27,
`main.py`'ye dispatch/refresh testleri, backend route testleri).
Frontend 339 test (yeni: KB linki, accordion, reboot banner, install
confirm/success/failure akışları). **Gerçek E2E doğrulandı (dikkatli/
güvenli bir senaryoyla):** GERÇEK bir agent süreci ile GERÇEK bir
`install_update` komutu, VAR OLMAYAN bir KB (`KB0000001`) hedefiyle
gönderildi — bu, GERÇEK COM `Search()`/filtreleme mantığını uçtan uca
çalıştırdı (yaklaşık 70 saniye sürdü, gerçek bir Windows Update
sorgusu) ama hiçbir şey İNDİRMEDİ/YÜKLEMEDİ, dürüstçe "Eşleşen
bekleyen güncelleme bulunamadı" sonucunu döndü — tam bir gerçek
kurulum (paylaşımlı geliştirme makinesinde gerçek bant genişliği/disk
tüketimi ve geri dönüşü olmayan bir sistem değişikliği anlamına
gelirdi) KASITLI olarak DENENMEDİ; bu yol yalnızca kapsamlı
mock'lanmış birim testleriyle doğrulandı. Gerçek `ITOpsAgent` servisi
bu değişiklikle de yeniden build edilip güvenle yeniden başlatıldı.

**Not:** Bu increment sırasında canlı test agent kayıtları (aynı
makinede çalıştığı için gerçek agent'larla AYNI hostname'i taşıyan,
GERÇEK kullanıcının panelinde görünen) kullanıcının kendi panelinden
iki kez manuel olarak silinmiş/arşivlenmiş bulundu ve HER İKİSİNDE de
gerçek iki agent (`WIN-G4E9UGRTH8E`, `WIN-27EVDRJ3O31`) etkilendi —
her ikisi de fark edilir edilmez `POST .../restore` ile geri
yüklendi. Bu, paylaşımlı/canlı bir geliştirme ortamında test agent'ı
kaydının GERÇEK panelde görünür olmasının pratik bir riski olarak not
düşülüyor.

**Faz 45 — SNMP Verisinin Gerçekten Ekrana Gelmesi (İki Gerçek Production
Bug'ı)** de tamamlandı: kullanıcı bildirimiyle ("snmp bilgileri ekrana
gelmiyor bağlı görüyor ama hiçbir veri gelmiyor") bulunup düzeltildi —
kullanıcının GERÇEK bir FortiGate firewall'ı (`10.0.213.254`, "FW"
profili) "Hazır"/"Bağlandı" gösteriyordu ama Monitoring sayfasında hiç
veri yoktu. İki AYRI, gerçek üretim hatası bulundu:

**1. Kör nokta — SNMP-only cihazlar hiçbir zaman "asset" olmuyordu.**
ICMP/ARP tabanlı Network Discovery, ICMP'yi engelleyen bir firewall'ı
(çoğu firewall varsayılan olarak ping'e yanıt vermez) HİÇBİR ZAMAN
`assets` tablosuna yazmıyordu — SNMP profili "target_host"u kullanıcı
elle girmiş ve "Test Connection" GERÇEKTEN bağlanıyor olsa bile,
arkasında bir asset satırı olmadığı için ne Monitoring sayfası ne arka
plan poller'ı (`poll_all`, yalnızca MEVCUT asset'leri dolaşır) bu
cihazı hiç görüyordu. Düzeltme: `app/snmp/profile_service.py::
_auto_assign_if_ip_matches` artık `test_connection`'ın GERÇEKTEN
başarılı olduğu dalda (`confirmed_system` dolu) eşleşen asset yoksa
SNMP'den gelen GERÇEK verilerle (`sysName`→hostname, `sysDescr` VE
profil adından ["FW"→"firewall"] çıkarılan `device_type` — asla port
taramasıymış gibi uydurulmaz) yeni bir asset OLUŞTURUR, sonra profili
ona atar. `create_profile`/`replace_profile` (canlı bir poll
YAPMADIKLARI için) hâlâ hiçbir asset UYDURMAZ — yalnızca `test_
connection`'ın somut kanıtı asset oluşturabilir.

**2. Gerçek, sistemik bir tip hatası — DB'den gelen HİÇBİR asset asla
poll edilemiyordu.** `assets.ip_address` (Postgres `INET`) asyncpg'de
bir `ipaddress.IPv4Address` NESNESİ olarak gelir, düz bir `str`
DEĞİL — `app/snmp/poller.py::_poll_one` ve `app/routes/snmp.py::
poll_asset_snmp` bunu `str()` OLMADAN doğrudan `SNMPClient.poll_asset`e
geçiriyordu; pysnmp'nin `slim.get()`'i `":" in address` yaparken
`TypeError: argument of type 'IPv4Address' is not a container or
iterable` ile GERÇEKTEN çöküyordu. Bu, yalnızca bugünkü firewall'ı
DEĞİL, DB'ye bağlı HERHANGİ bir asset'in HİÇ BİR ZAMAN gerçekten poll
edilememiş olduğu anlamına geliyordu (yalnızca `.env` tek-hedef
fallback'i, düz bir string olduğu için, hep çalışıyordu — bu yüzden
şimdiye kadar fark edilmemişti). `app/snmp/asset_profile_service.py`
zaten doğru şekilde `str(...)` kullanıyordu — aynı desen iki eksik
noktaya da uygulandı. **Yan bulgu:** bunu gerçekten test EDEBİLECEK
bir entegrasyon testi (`tests/snmp/test_poller_profile_integration.py
::test_poll_all_uses_db_assigned_profile`) zaten VARDI ve gerçek bir
DB-seeded asset kullanıyordu ama yalnızca `called_host == asset["ip_
address"]` (iki AYNI, dönüştürülmemiş `IPv4Address` nesnesini
karşılaştırıyordu — ikisi de "bozuk" olduğu için trivially eşleşip
YANLIŞLIKLA geçiyordu) diye assert ediyordu, GERÇEK TİPİ hiç kontrol
etmiyordu — düzeltilip `isinstance(called_host, str)` eklendi (bkz. o
test + `tests/test_snmp_api.py`'deki eşdeğer güçlendirme).

Ayrıca: `app/db/snmp_profiles.py::get_connection()`'a da (asset'lere
yazabilen YENİ kod yolu yüzünden) `app/db/assets.py` ile AYNI jsonb
codec kaydı eklendi — gerçek bir `asyncpg.exceptions.DataError:
expected str, got list` hatasıyla (canlı backend'de) bulunup
düzeltildi (codec kayıtlı olmadan `open_ports`/`evidence` JSONB
kolonlarına çıplak bir Python listesi yazılamıyordu).

Backend 536→542 test (11 yeni: asset oluşturma senaryoları + device_type
sezgisi + tip güvenliği regresyonları). **Gerçek E2E doğrulandı (bu
oturumun en önemli doğrulaması):** kullanıcının GERÇEK FortiGate'ine
karşı "Test Connection" tekrar çalıştırıldı → gerçek bir asset (`PSL-
HQ-70G-1.alb.local`, `device_type=firewall`) oluşturuldu ve profile
atandı → arka plan poller'ı bu asset'i GERÇEKTEN poll etti → **59 GERÇEK
arayüz** (wan1/wan2, tüm VLAN'lar — kullanıcının kendi organizasyon
yapısını yansıtan gerçek isimlerle) canlı Monitoring sayfasında
GERÇEKTEN göründü, "Son Poll Logları" `PSL-HQ-70G-1.alb.local —
Başarılı — 1537ms — 653 OID` gösterdi. Bant genişliği (Mbps) sütunları
İLK poll turunda dürüstçe boş (`—`) — iki ardışık örnek gerektiren
GERÇEK bir hesap, uydurma bir sayı YOK, bkz. `bandwidth.py` — sonraki
30 saniyelik döngüde dolması beklenir. Gerçek production backend
(`--host 0.0.0.0`, LAN'daki gerçek agent'ların/tarayıcının kullandığı
süreç — bu oturumun kendi `preview_start` (`127.0.0.1`-yalnızca) dev
kopyasından AYRI olduğu bu turda keşfedildi) her düzeltmeden sonra
AYNI komut satırıyla (`--host 0.0.0.0 --port 8000`) güvenle yeniden
başlatıldı, gerçek üç agent/servis etkilenmedi.

## Faz 46 — Ayrıcalıklı Erişim Yönetimi (PAM) + Rol Tabanlı Yetkilendirme (RBAC)

**Durum:** ✅ Tamamlandı (kullanıcının açık isteğiyle — bkz. "Faz 13 —
Auth/RBAC" artık bu fazla karşılanmış sayılır, aşağıdaki İleri
Fazlar'dan çıkarıldı).

**Önkoşul olarak inşa edilen gerçek Auth (önceden HİÇ yoktu):** bu
projede insan kullanıcı girişi/JWT/`users` tablosu bu faza kadar hiç
yoktu (bkz. `docs/decisions.md` §17, bilinen kabul edilmiş risk).
Kullanıcının "mevcut JWT auth yapısıyla entegre et" talimatı gerçekte
var olmayan bir altyapıyı varsayıyordu — bu faz onu UYDURMADI, gerçek
bir önkoşul olarak İNŞA ETTİ: `app/auth/{models,security,exceptions,
service,dependencies}.py` + `app/db/users.py` + `app/routes/auth.py`
(`POST /api/auth/login`, `GET /api/auth/me`). Parola bcrypt (Apache-2.0,
yeni bağımlılık) ile hash'lenir, oturum token'ı PyJWT (MIT, yeni
bağımlılık) ile imzalanır (`JWT_SECRET_KEY`, `.env`). `users.role`
(`ADMIN`/`OPERATOR`/`VIEWER`) RBAC'ın tek doğruluk kaynağı;
`require_role(...)` FastAPI dependency'si her PAM route'unu korur.
İlk ADMIN hesabı `app/main.py::_ensure_bootstrap_admin` ile — `users`
tablosu boşken VE `.env`'de `BOOTSTRAP_ADMIN_USERNAME`/
`BOOTSTRAP_ADMIN_PASSWORD` ikisi birden varsa bir kerelik oluşturulur
(tavuk-yumurta sorunu: ilk admin'i oluşturacak bir admin yok).

**Kasa (Vault):** `vault_credentials` tablosu — parola/SSH anahtarı
DB'de asla düz metin değil, `cryptography`'nin (Faz 35'ten beri zaten
`asyncssh` bağımlılığı — YENİ bir kripto kütüphanesi EKLENMEDİ) Fernet'i
ile şifrelenip `encrypted_payload`'a yazılır (anahtar yalnızca `.env`:
`PAM_VAULT_SECRET_KEY`, gerçek `Fernet.generate_key()` çıktısı). API
yanıtları her zaman maskeli (`secret_masked: "••••••••"`); gerçek değer
yalnızca ayrı, Admin-only `POST /api/pam/vault/{id}/reveal` ile döner
(`app/pam/vault.py`, `app/pam/service.py`).

**Erişim kuralları:** `pam_access_rules` (`user_id`+`asset_id` UNIQUE —
bir kullanıcının bir asset için en fazla bir kuralı olur, çakışan
ikinci bir kural OLUŞTURULMAZ, mevcut DÜZENLENİR) — `credential_id`,
`allow_rdp`/`allow_ssh`, `max_session_duration_mins`, `valid_until`
(`NULL` = süresiz). `GET /api/pam/my-access` — OPERATOR/VIEWER kendisine
atanmış, süresi DOLMAMIŞ sunucuları görür; `credential_id` bu yanıtta
KASITLI olarak yok, kullanıcı hangi kasa hesabının kullanılacağını
hiçbir zaman görmez.

**Denetim:** `pam_session_logs` (`ended_at IS NULL` = aktif oturum) +
Admin-only `GET /api/pam/audit?active=true|false`. Kimlik bilgisi
DEĞERİ hiçbir zaman yazılmaz, yalnızca hangi kasa kaydının kullanıldığı.

**Zero-Knowledge SSH (kısmi — yalnızca SSH, RDP DEĞİL):** mevcut Faz 35
WebSocket SSH proxy'sinin (`app/agents/ssh_proxy.py`) YANINA (yerine
değil) yeni bir fonksiyon (`run_pam_ssh_websocket_session`) + yeni route
`WS /api/pam/ssh/{asset_id}` (`app/routes/pam_ssh.py`) eklendi.
Kullanıcıdan kullanıcı adı/parola hiç İSTENMEZ — backend
`pam_access_rules`'u JWT'deki kullanıcıya göre çözer, `vault_
credentials`'ı sunucu tarafında deşifre eder, doğrudan `asyncssh`'e
geçirir; tarayıcıya kimlik bilgisi DEĞERİ hiçbir zaman gönderilmez.
`max_session_duration_mins` doluğunda oturum sunucu tarafından kapatılır.
JWT, tarayıcının native `WebSocket` API'sinin özel header
GÖNDERMEMESİ yüzünden query string'de (`?token=...`) taşınır —
bilinçli, belgelenmiş bir ödünleşim (bkz. `app/routes/pam_ssh.py`
docstring'i). Faz 35'in mevcut manuel-kimlik-bilgili SSH akışı
(`SshTerminal.tsx`, `/remote-control/ssh/[agentId]`) AYNEN, dokunulmadan
kalıyor — PAM kuralı olmayan kullanıcılar için fallback.

**Kasıtlı kapsam dışı bırakılanlar (gerekçeli):**
- **RDP zero-knowledge oturum enjeksiyonu YOK** — gerçek bir Guacamole/
  guacd sınıfı ayrı bir gateway altyapısı gerektirir, bu artırımın
  kapsamında KURULMADI. RDP mevcut Faz 34 `.rdp` indirme akışında kalıyor.
- **`group_id` bazlı kural ataması YOK** — kodda hiçbir "kullanıcı
  grubu" kavramı yok; yalnızca `user_id` bazlı kurallar var.
- **Uygulama genelinde bir "login duvarı" KURULMADI** — canlı, aktif
  kullanılan bir sistemde riskli bir erişim değişikliği olurdu.
  Yalnızca `/pam/*` sayfaları + API'leri gerçek auth ile korunuyor;
  Dashboard/Discovery/Assets/Topology/Monitoring/Agents/Settings
  KASITLI olarak açık kalmaya devam ediyor (kullanıcının isteği PAM
  ekranlarının admin-only olmasıydı, tüm uygulamanın kapatılması
  değildi). `TopHeader`'daki `AuthStatus` yalnızca bilgilendirici.
- **Parola/anahtar rotasyon otomasyonu YOK.**

**Dosyalar (backend):** `infra/postgres/init.sql` (4 yeni tablo:
`users`/`vault_credentials`/`pam_access_rules`/`pam_session_logs`),
`app/auth/*`, `app/pam/*`, `app/db/{users,pam}.py`, `app/routes/
{auth,pam_users,pam_vault,pam_rules,pam_audit,pam_ssh}.py`,
`app/agents/ssh_proxy.py` (ek fonksiyon), `app/main.py` (router kaydı +
bootstrap admin), `requirements.txt` (+`bcrypt`, `+PyJWT`), `.env.example`.

**Dosyalar (frontend):** `lib/auth/AuthProvider.tsx`, `lib/api.ts`
(auth/PAM fonksiyonları), `components/{LoginForm,AuthStatus,
RequireAdmin,PamUsersPanel,PamVaultPanel,PamRulesPanel,PamAuditPanel,
MyAccessPanel,PamSshTerminal}.tsx`, `app/{login,my-access,pam/{users,
vault,rules,audit,ssh/[assetId]}}/page.tsx`, `components/Sidebar.tsx`
(PAM grubu, admin-only), `components/TopHeader.tsx` (`AuthStatus`),
`lib/i18n/translations.ts` (`auth`/`pam` namespace'leri, tr+en).

**Testler:** Backend 542→559 (17 yeni: `tests/test_auth_api.py` 8,
`tests/test_pam_api.py` 9 — login/rol koruması/kasa maskeleme+reveal/
kural UNIQUE çakışması/my-access süre filtreleme/audit — gerçek
PostgreSQL'e `isolated_db` ile, gerçek SSH/ağ bağlantısı YOK). Frontend
339 (mevcut testler `AuthProvider`/`AuthStatus` ekleniyle güncellendi,
yeni PAM-özel component testi bu artırımda YAZILMADI — kapsam dışı
bırakıldı, bir sonraki artırıma not düşüldü). `tsc --noEmit` ve
`eslint` temiz.

**Gerçek E2E:** canlı production backend (`--host 0.0.0.0 --port 8000`)
kullanıcı onayıyla yeniden başlatıldı — yeni şema (4 tablo) otomatik
kuruldu, `.env`'deki `BOOTSTRAP_ADMIN_USERNAME`/`PASSWORD` ile gerçek
bir ADMIN hesabı oluştu, gerçek bir `POST /api/auth/login` denemesi
GERÇEK bir JWT döndürdü, o token ile `GET /api/pam/users` GERÇEKTEN
admin'i listeledi. Restart sırasında gerçek üç agent kesintisiz yeniden
bağlandı (heartbeat/telemetry logları restart öncesi/sonrası aynı
akışta). PAM zero-knowledge SSH akışının GERÇEK bir hedefe karşı canlı
denemesi bu increment'e dahil EDİLMEDİ (Faz 44'ün "paylaşımlı canlı
ortamda test riski" dersiyle tutarlı — yalnızca mock'lanmamış ama
gerçek bağlantı açmayan birim/entegrasyon testleriyle doğrulandı).

## Faz 47 — Dinamik RBAC (İnce Taneli İzinler) + Cihaz Bazlı PAM Yetkilendirme + Uygulama Genelinde Route Guard

**Durum:** ✅ Tamamlandı (kullanıcının açık isteğiyle — Faz 46'nın
`role`-tabanlı kaba RBAC'ını ve "yalnızca `/pam/*` korunuyor" kapsam
sınırını bilinçli olarak GENİŞLETTİ/değiştirdi).

**İnce taneli izin modeli:** `users.role` (ADMIN/OPERATOR/VIEWER) TEK
BAŞINA yetersizdi — kullanıcının açık örneği ("yalnızca `PAM_ACCESS`'i
olan bir kullanıcı Dashboard dahil hiçbir menüyü göremesin") kişi
bazında override edilebilir bir izin seti gerektiriyordu. Yeni
`user_permissions` tablosu (`user_id`+`permission` PK) + kod-içi sabit
katalog (`app/auth/permissions.py::ALL_PERMISSIONS` — 9 genel `*_VIEW`
izni + `PAM_ADMIN` + `PAM_ACCESS`, DB-tabanlı/kullanıcı-tanımlı yeni
izin tipi YOK, kasıtlı). Yeni kullanıcılar rolüne göre VARSAYILAN bir
izin setiyle başlar (`default_permissions_for_role`) ama admin panelden
(`UserPermissionsModal.tsx` → `PUT /api/pam/users/{id}/permissions`)
TAMAMEN özelleştirilebilir — `role` alanı hâlâ duruyor (etiketleme/
varsayılan atama için) ama artık GERÇEK yetkilendirme kararı vermiyor.
`permissions` HER İSTEKTE DB'den taze okunur (JWT payload'ında
SAKLANMAZ) — bir izin geri alınırsa kullanıcının hâlâ geçerli token'ı
bir sonraki istekte bunu hemen yansıtır. Backend: `app/auth/
dependencies.py::require_permission(*any_of)` (`require_role` hâlâ
duruyor ama yeni route'lar bunu tercih ediyor); tüm `/api/pam/*` route'ları
`require_role("ADMIN")`'den `require_permission("PAM_ADMIN")`'e geçti,
`GET /api/pam/my-access` ve `WS /api/pam/ssh/{asset_id}` `PAM_ACCESS`
gerektiriyor (ikinci katman: `pam_access_rules`'daki asset-bazlı kural
hâlâ AYRICA kontrol ediliyor — izin genel PAM kapısı, kural hangi
cihaza).

**Uygulama genelinde route guard:** Faz 46'nın "yalnızca `/pam/*`
korunuyor" kararı BİLİNÇLİ olarak genişletildi — artık HER sayfa
(`/`, `/discovery`, `/assets`, `/topology`, `/scans`, `/alerts`, `/
monitoring`, `/agents`(+`/agents/[id]`), `/settings`, tüm `/pam/*`,
`/my-access`, `/pam/ssh/[assetId]`, `/remote-control/ssh/[agentId]`)
`components/RequirePermission.tsx` ile sarmalı — giriş yapılmamışsa
`/login`'e yönlendirir, giriş yapılmış ama ilgili izin yoksa (kullanıcı
menüde görmediği bir URL'yi ELLE YAZSA bile) dürüst bir 403 ekranı
render eder. **Bilinçli kapsam sınırı:** bu guard yalnızca FRONTEND'de
— genel sayfaların (Dashboard/Assets/Discovery/...) backend API'lerine
(`/api/assets`, `/api/discovery`, `/api/monitoring`, ...) auth
EKLENMEDİ; yalnızca PAM API'leri gerçek backend yetkilendirmesine
sahip. Onlarca route dosyasına canlı bir sistemde tek seferde auth
retrofit etmek (kilitlenme riski, ayrı ve çok daha büyük bir iş) bu
artırımın kapsamı dışında bırakıldı — kullanıcının isteği açıkça sayfa
seviyesinde 403 idi, her API endpoint'inin sertleştirilmesi değil.
`Sidebar.tsx` artık STATİK değil — her öğe `currentUser.permissions`'a
göre filtrelenir, boş kalan gruplar hiç render edilmez.

**Cihaz/sunucu bazlı yetkilendirme matrisi:** Yeni `/pam/users/{id}`
sayfası (`UserDeviceAccessPanel.tsx`) kullanıcının verdiği mockup'ın
karşılığı — her asset için ayrı RDP/SSH checkbox'ı + (yalnızca
işaretliyken görünen) kasa hesabı seçimi + opsiyonel `valid_until`.
Yeni bir "batch" API EKLENMEDİ — mevcut Faz 46 `pam_access_rules`
CRUD'unu (`POST`/`PUT`/`DELETE /api/pam/rules/...`) doğrudan kullanıyor;
her satır kendi create/update/delete çağrısını yapıyor. `PamUsersPanel`
kullanıcı listesine "Cihaz Erişimi" linki + "Yetkiler" (permission
matrisi) butonu eklendi.

**RDP bağlantısı — kısmi zero-knowledge:** Kullanıcının "Şifre/Private
Key bilgilerini asla görmeden RDP Bağlan" isteği RDP için TAM olarak
karşılanamadı — bu, Faz 46'da zaten belgelenen bir sınırın (gerçek bir
Guacamole/guacd tüneli olmadan parolanın kendisini de gizlice enjekte
etmek mümkün değil) doğal bir sonucu, YENİDEN teyit edildi. Bunun
yerine yeni `GET /api/pam/rdp/{asset_id}` (`app/routes/pam_rdp.py`,
`app/pam/service.py::authorize_rdp_session`) `pam_access_rules.
allow_rdp`'yi doğrulayıp mevcut Faz 34 `.rdp` üretimini (`app/agents/
rdp.py::build_rdp_file` — DEĞİŞTİRİLMEDİ) `asset_id`'den (bir agent'a
bağlı olması GEREKMEZ) çalıştırıyor — **yalnızca kasadaki kullanıcı
adını ön dolduruyor**, RDP istemcisi parolayı kullanıcıdan istemeye
devam ediyor. Frontend `lib/api.ts::downloadPamRdpFile` `fetch`+Blob
URL ile indiriyor (düz bir `<a href>` `Authorization` header'ı
taşıyamadığı için). Her indirme `pam_session_logs`'a `protocol="rdp"`,
`end_reason="rdp_file_downloaded"` ile TEK satırlık bir denetim kaydı
düşüyor — gerçek RDP oturum SÜRESİ izlenemiyor (ayrı bir OS süreci).

**Geçiş/backfill:** Faz 46'da oluşturulan bootstrap ADMIN hesabının
(ve bu fazdan önce var olan başka kullanıcıların) `user_permissions`
satırı YOKTU — `app/main.py::_ensure_default_permissions_backfill()`
(lifespan'da, `_ensure_bootstrap_admin`'den hemen sonra) hiç izin
satırı OLMAYAN her kullanıcıya rolünün varsayılanını bir kerelik atar;
zaten en az bir izni olan (admin panelinden bilinçli boşaltılmış olsa
bile) kullanıcılara DOKUNMAZ.

**Dosyalar (backend):** `infra/postgres/init.sql` (`user_permissions`
tablosu), `app/auth/permissions.py` (yeni), `app/auth/{models,service,
dependencies}.py` (izin entegrasyonu), `app/pam/service.py`
(`authorize_rdp_session`), `app/routes/{pam_users,pam_vault,pam_rules,
pam_audit,pam_ssh}.py` (`require_permission`'a geçiş), `app/routes/
pam_rdp.py` (yeni), `app/main.py` (backfill).

**Dosyalar (frontend):** `lib/auth/permissions.ts` (yeni), `lib/api.ts`
(`permissions` alanı, `updatePamUserPermissions`, `downloadPamRdpFile`,
`fetchPamUser`, `updatePamRule`), `components/RequirePermission.tsx`
(yeni, `RequireAdmin.tsx`'in YERİNE), `components/{UserPermissionsModal,
UserDeviceAccessPanel}.tsx` (yeni), `components/Sidebar.tsx` (dinamik
render), `components/MyAccessPanel.tsx` (RDP butonu), TÜM `app/**/
page.tsx` dosyaları (`RequirePermission` sarmalı), `app/pam/users/
[userId]/page.tsx` (yeni).

**Testler:** Backend 559→565 (6 yeni: kısıtlı-izin senaryosu, role'den
bağımsız izin override'ı, `PAM_ACCESS` geri alınca kural olsa bile SSH
reddi, RDP yetkilendirme/dosya testleri). Frontend 339→342 (3 yeni:
403 route guard smoke testi, izin-filtreli Sidebar senaryoları).
`tsc`/`eslint` temiz.

**Gerçek E2E:** kullanıcı onayıyla canlı production backend tekrar
yeniden başlatıldı — `user_permissions` şeması otomatik kuruldu,
backfill mevcut bootstrap ADMIN hesabına gerçek varsayılan izinleri
atadı (aksi halde bu geçiş sonrası ADMIN dahil KİMSE giriş yapamazdı —
gerçek bir kilitlenme riski, backfill ile önlendi), restart sırasında
gerçek agent'lar kesintisiz yeniden bağlandı.

## Faz 48 — Gerçek Zero-Knowledge Web RDP (Apache Guacamole/guacd)

**Durum:** ✅ Tamamlandı VE canlıda gerçek bir Windows RDP oturumuyla
uçtan uca doğrulandı (bkz. aşağıdaki "Faz 48 sonrası" bölümü — Docker/
WSL2 kullanıcı tarafından kuruldu, üç gerçek üretim hatası canlı
denemeyle bulunup düzeltildi).

**Kapsam:** Faz 47'nin `.rdp` dosya indirme akışı (kullanıcı adı ön
dolu, parola hâlâ elle giriliyordu) kullanıcının açık isteğiyle
TAMAMEN KALDIRILDI — `GET /api/pam/rdp/{asset_id}` (HTTP dosya
indirme) artık YOK. Yerine gerçek, istemcisiz (clientless) bir HTML5
RDP oturumu geldi: `WS /api/pam/rdp/{asset_id}`.

**Backend mimarisi:** `app/pam/guacamole_protocol.py` Apache Guacamole
metin protokolünü (uzunluk-önekli, virgülle ayrılmış elemanlar) sıfırdan
implemente ediyor — üçüncü parti bir `PyGuacamole`/`guacamole-lite`
kütüphanesi EKLENMEDİ (bakım durumu belirsiz, protokol küçük ve tam
belgeli). `app/pam/guacd.py::open_rdp_connection` guacd'ye TCP ile
bağlanıp resmi el sıkışma sırasını (`select`→`args`→`size`/`audio`/
`video`/`image`→`connect`→`ready`) tamamlıyor — **kimlik bilgisi
enjeksiyonu TAM OLARAK burada**: `connect` instruction'ının değerleri
`args`'ın DÖNDÜRDÜĞÜ SIRAYLA (guacd sürümleri arasında farklılık
gösterebildiği için sabit bir sıra VARSAYILMADI) dolduruluyor, kasadan
ÇÖZÜLMÜŞ gerçek parola YALNIZCA bu sunucu-sunucu TCP bağlantısında
geçiyor. El sıkışma TAMAMLANDIKTAN SONRA (yani guacd zaten "ready"
dedikten sonra) tarayıcının WebSocket'i kabul ediliyor — bu yüzden
JS istemcisi kendi "connect" adımını hiç yapmıyor, yalnızca ekran/fare/
klavye protokolünü taşıyor. `app/pam/service.py::authorize_rdp_session`
artık Faz 47'nin YALNIZCA kullanıcı adı döndüren haline KIYASLA tam
`(username, password, domain, max_session_duration_mins, credential_id)`
döndürüyor (RDP parolası artık backend'in İÇİNDE akıyor, `.rdp`
dosyasına hiç YAZILMIYOR). `pam_session_logs`'a Faz 46/47'yle AYNI
şekilde (yeni bir `pam_active_sessions` tablosu EKLENMEDİ — `ended_at
IS NULL` zaten "aktif oturum" anlamına geliyor, kullanıcının istediği
"CANLI" durum takibiyle birebir aynı, ayrı bir tablo gereksiz bir
tekrar olurdu) oturum başlangıcı/bitişi (`end_reason`) yazılıyor.

**Frontend:** `guacamole-common-js@1.5.0` (Apache-2.0, resmi Apache
Guacamole JS istemcisi — yeni bağımlılık, TypeScript tipi YAYINLAMIYOR,
`types/guacamole-common-js.d.ts` ile `any` olarak bildirildi).
`components/GuacamoleRdpViewer.tsx` (`/pam/session/{assetId}`) —
Canvas tabanlı canlı ekran + fare/klavye + Tam Ekran + Ekrana Sığdır +
Panoyu Gönder butonları. `MyAccessPanel`'deki "RDP Bağlan" artık
`downloadPamRdpFile` YERİNE bu sayfaya yönlendiriyor.

**Dosyalar (backend):** `app/pam/{guacamole_protocol,guacd}.py` (yeni),
`app/pam/service.py` (`authorize_rdp_session` — tam kimlik bilgisi
döner), `app/routes/pam_rdp.py` (HTTP dosya indirmeden WS köprüsüne
TAM DEĞİŞİM), `infra/docker-compose.yml` (`guacd` servisi),
`.env.example` (`GUACD_HOST`/`GUACD_PORT`).

**Dosyalar (frontend):** `components/GuacamoleRdpViewer.tsx` (yeni),
`app/pam/session/[assetId]/page.tsx` (yeni), `components/
MyAccessPanel.tsx` (RDP butonu yeni sayfaya yönlendiriyor), `lib/
api.ts` (`downloadPamRdpFile` KALDIRILDI, `pamRdpWebSocketUrl` yeni),
`types/guacamole-common-js.d.ts` (yeni).

**Testler:** Backend 565→576 (11 yeni: `tests/pam/
test_guacamole_protocol.py` 7 — saf protokol kodlama/ayrıştırma;
`tests/pam/test_guacd_handshake.py` 3 — sahte guacd'ye karşı TAM el
sıkışma + kimlik bilgisi enjeksiyonu doğrulaması; `test_pam_api.py`'de
2 yeni `authorize_rdp_session` servis testi — eski 2 `.rdp`-dosyası
testi KALDIRILDI çünkü endpoint artık HTTP değil WS). Frontend 342
(değişmedi — `GuacamoleRdpViewer` için component testi bu artırımda
YAZILMADI, gerçek bir DOM canvas + WebSocket + üçüncü parti kütüphane
entegrasyonunu anlamlı şekilde mock'lamak ayrı, zaman alıcı bir iş;
kapsam dışı bırakıldı ve not düşüldü). `tsc`/`eslint` temiz.

**Faz 48 sonrası — Docker/WSL2 kurulumu + CANLI RDP oturumuna karşı üç
gerçek üretim hatası bulunup düzeltildi.** Kullanıcı kendi ekranından
`wsl --install` + Docker Desktop kurdu; Docker Desktop ilk açılışta
**"Virtualization support not detected"** hatası verdi — kök neden bu
makinenin KENDİSİNİN bir VMware sanal makinesi olması (nested
virtualization, VMware host/vSphere tarafında KAPALIYDI) — kullanıcı
vSphere web arayüzünden "Expose hardware assisted virtualization to
the guest OS"'u açıp çözdü (bu, guest OS içinden düzeltilebilecek bir
şey DEĞİLDİ). `docker compose -f infra/docker-compose.yml up -d guacd`
ile gerçek `guacamole/guacd:1.5.5` container'ı ayağa kalktı. Ardından
GERÇEK bir Windows RDP hedefine karşı canlı denemelerle üç ayrı, gerçek
hata bulunup düzeltildi (hiçbiri sahte/mock testlerle YAKALANAMAZDI):

1. **`security: "any"` → `"nla"`:** guacd `"Server refused connection
   (wrong security type?)"` diyordu — modern Windows Server NLA
   ZORUNLU tutuyor, `app/pam/guacd.py`'nin varsayılanı düzeltildi.
2. **Docker loopback hatası:** bir asset'in IP'si `127.0.0.1` (backend'in
   KENDİ makinesi) olduğunda guacd'ye OLDUĞU GİBİ geçmek guacd'nin bunu
   KENDİ konteynerinin loopback'i sanmasına yol açıyordu (Docker ağ
   izolasyonu) — `app/pam/guacd.py::_resolve_rdp_target_hostname` artık
   loopback adresleri `GUACD_HOST_LOOPBACK_TARGET` (varsayılan
   `host.docker.internal`, Docker Desktop'ın host'a özel DNS adı) ile
   değiştiriyor; gerçek bir LAN IP'sine DOKUNMUYOR.
3. **WebSocket subprotocol reddi:** `guacamole-common-js`
   `new WebSocket(url, "guacamole")` ile "guacamole" alt protokolünü
   İSTİYOR — WebSocket standardı gereği sunucu bunu el sıkışmada AÇIKÇA
   kabul etmezse TARAYICI bağlantıyı kendisi iptal ediyordu (ham bir
   Python istemcisiyle test edilirken alt protokol hiç istenmediği için
   bu GİZLİ kalmıştı) — `app/routes/pam_rdp.py`'deki her
   `websocket.accept()` artık `subprotocol="guacamole"` ile.
4. **Instruction-sınırı bölünmesi (en incelikli olanı):** `guacamole-
   common-js`'in tarayıcı tarafındaki ayrıştırıcısı (kaynakta
   doğrulandı) HER WebSocket mesajının TAM instruction(lar) içerdiğini
   VARSAYAR, mesajlar arası bir tampon TUTMAZ. `app/pam/guacd.py`'nin
   eski `_pump_guacd_to_websocket`'i guacd'den gelen ham baytları
   RASTGELE bir TCP `read()` sınırında (ör. bir ekran görüntüsü
   `blob`'unun ORTASINDA) WebSocket mesajlarına bölüyordu — tarayıcıda
   "source image could not be decoded" hatasına, sonunda guacd'nin
   "User is not responding" diyerek bağlantıyı KENDİSİNİN kesmesine
   yol açıyordu. Yeni `app/pam/guacamole_protocol.py::
   split_complete_instructions` ham bayt akışını TAMPONLAYIP yalnızca
   TAM biten instruction'ları gönderiyor; ayrıca `bridge_websocket_to_
   guacd` artık İKİ yönü de (WS↔guacd) `asyncio.wait(FIRST_COMPLETED)`
   ile izliyor — eskiden guacd KENDİSİ bağlantıyı kapattığında köprü
   bunu fark etmeyip tam `max_session_duration_mins`'e kadar askıda
   kalıyordu.

**Gerçek E2E (bu increment'in en önemli doğrulaması):** kullanıcının
gerçek Windows hesabıyla guacd log'larında **`RDPDR user logged on`**
— yani GERÇEK bir RDP oturumu GERÇEKTEN kimlik doğrulamasını geçip
bağlandı. Backend 576→577 test (4 yeni: `split_complete_instructions`
için regresyon dahil protokol-tamponlama testleri, `_resolve_rdp_
target_hostname` için loopback-yeniden-yazma testleri).

**UI/UX yenilemesi — CyberArk/Teleport tarzı oturum ekranı:**
kullanıcının isteğiyle `GuacamoleRdpViewer` tamamen yeniden tasarlandı:
sabit koyu tema, tam ekranı kaplayan `position: fixed` immersive
katman, üstte yarı saydam (backdrop-blur) camsı bir araç çubuğu (canlı
durum noktası + cihaz adı/IP + PAM kuralının GERÇEK süresinden geri
sayan bir zamanlayıcı — sahte bir "ping/ms" DEĞERİ HİÇBİR ZAMAN
gösterilmiyor, bu proje hiçbir yerde uydurma metrik göstermemiştir),
Panoyu Gönder/Ctrl+Alt+Del/Ekrana Sığdır/Tam Ekran/Oturumu Sonlandır
butonları (`lucide-react` ikonlarıyla), ve bağlanırken dönen bir
`ShieldCheck` yükleme katmanı. **Kullanıcı açıkça Tailwind/Shadcn UI
istedi ama bu proje 48 faz boyunca hiç kullanmadığı için (yalnızca CSS
Modules) tüm projeye yeni bir CSS/derleme altyapısı eklemek yerine AYNI
görsel sonuç mevcut desenle üretildi** — yalnızca `lucide-react`
(ikonlar için, düşük riskli/odaklı) eklendi. Gerçek geri sayım için
`AuthorizedAssetResponse`'a (`GET /api/pam/my-access`)
`max_session_duration_mins` alanı eklendi (backend'de zaten
sorgulanıyordu, yalnızca response'a taşındı).

## Faz 49 — LDAP / Active Directory Entegrasyonu

**Durum:** ✅ Backend tamamlandı ve gerçek PostgreSQL'e karşı test
edildi (606 backend testi geçiyor); frontend tamamlandı ve test edildi
(347 frontend testi geçiyor). Gerçek bir AD sunucusuna karşı canlı
doğrulama henüz yapılmadı — kullanıcı gerçek LDAP bağlantı bilgilerini
(host/base DN/bind DN+parola) verdiğinde ele alınacak.

**Kapsam:** Ayarlar'a "Active Directory / LDAP" bölümü (`host`/`port`/
`use_ssl`/`domain_fqdn`/`base_dn`/`bind_dn`/`bind_password`, "Bağlantıyı
Test Et", "Şimdi Senkronize Et") + `app/services/ldap.py` (`ldap3`
tabanlı gerçek LDAP arama/bind) + PAM erişim kurallarının AD grup
üyeliğini de dikkate alması.

**Kasıtlı sapmalar (kullanıcının orijinal isteğinden):**
- **`python-ldap` YERİNE `ldap3`** (LGPL-3.0, saf Python) — `python-ldap`
  OpenLDAP C başlıklarına karşı derlenmesi gerektiriyor, bu Windows
  Server ortamında ek bir derleme zinciri gerektirirdi.
- **Celery YERİNE mevcut arka plan görev deseni** (`app/snmp/
  scheduler.py`/`app/agents/scheduler.py` ile AYNI: FastAPI `lifespan`'da
  başlayan tek bir `asyncio.Task`) — bu proje hiçbir zaman bir mesaj
  kuyruğu/broker (Redis/RabbitMQ) kullanmadı, tek bir gece yarısı
  görevi için Celery eklemek orantısız bir mimari genişleme olurdu.
  `LDAP_SCHEDULED_SYNC_ENABLED` (varsayılan açık) ve `LDAP_SYNC_HOUR`
  (varsayılan 02:00) ile kontrol edilir.
- **LDAP ile GİRİŞ (bind auth) yok** — bu proje Faz 46'dan beri yerel
  bcrypt tabanlı kullanıcı girişini KORUYOR. LDAP entegrasyonu yalnızca
  dizin senkronizasyonu + grup bazlı PAM yetkilendirmesi; bir yerel
  `users` satırı bir AD hesabına (`users.ad_username`) ADMIN tarafından
  ELLE bağlanır (Faz 29'un Agent↔Asset eşleştirmesindeki temkinlilikle
  AYNI ilke — otomatik/örtük eşleme YOK). `PUT /api/pam/users/{id}`
  artık `ad_username` alanını kabul ediyor (var olmayan bir AD
  kullanıcı adına bağlanmaya çalışmak 422 döner); `/pam/users` ekranına
  bu bağlantıyı kurmak için satır içi bir alan+buton eklendi.
- **Yalnızca DOĞRUDAN (`memberOf`) grup üyelikleri** — iç içe (nested)
  AD grup üyeliği KASITLI olarak kapsam dışı (primary group özel
  durumu + döngüsel referans koruması gerektiren, ayrı bir iş; yanlış/
  eksik bir çözümleme GERÇEK bir yetkilendirme açığına yol açabilirdi).
- **`PAM_VAULT_SECRET_KEY` (Fernet) yeniden kullanıldı** — LDAP bind
  parolası için YENİ bir şifreleme anahtarı EKLENMEDİ, aynı "PAM kasası"
  güvenlik sınırının doğal bir uzantısı.

**Veri modeli:** yeni `ldap_config` (tek satır, `agent_retention_policy`
ile AYNI desen), `ad_groups`/`ad_users`/`ad_group_memberships`
(additive). `pam_access_rules.user_id` artık NULL olabilir + yeni
`ad_group_id` (XOR CHECK constraint — tam olarak biri dolu olmalı, hem
DB katmanında hem `PamAccessRuleCreateRequest`'in Pydantic
`model_validator`'ında erken doğrulanır). Aynı asset için hem doğrudan
hem grup kuralı varsa DOĞRUDAN kural KAZANIR (`list_authorized_assets_
for_user`/`_resolve_rule`'da tutarlı bir öncelik kuralı).

**Gerçek bir bug bulunup düzeltildi:** `infra/postgres/init.sql`'deki
`ADD CONSTRAINT ... UNIQUE` için idempotent `DO $$ ... EXCEPTION WHEN
duplicate_object` kalıbı (CHECK kısıtları için doğru) UNIQUE kısıtları
için YETERSİZ çıktı — Postgres bir UNIQUE kısıtı için isimdeş bir
destek INDEX de oluşturuyor, ikinci çalıştırmada bu `duplicate_object`
(42710) DEĞİL `duplicate_table` (42P07) ile reddediliyor. Test
suite'i ilk çalıştırmada gerçekten bulundu (`isolated_db`'nin her test
başında `ensure_schema()`'yı yeniden çalıştırması sayesinde) —
`EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL` ile
düzeltildi.

**Frontend:** `/settings` → "Active Directory / LDAP" bölümü
(`LdapConfigurationCenter.tsx`, yalnızca `PAM_ADMIN` iznine sahip
kullanıcılara görünür), `/pam/rules`'a "Kullanıcı Tipi" seçimi (Yerel
Kullanıcılar / Active Directory Grupları — AD seçilirse senkronize
edilen gruplar açılır listede gösterilir), `/pam/users`'a AD hesabı
bağlama/kaldırma alanı. Backend 577→606, frontend 342→347 test.

Faz 49 sonrası bir dizi bugfix de tamamlandı — kullanıcının GERÇEK bir
Active Directory'ye (`lab.local`) karşı canlı "Bağlantıyı Test Et"
denemeleriyle bulunup düzeltildi: (1) **Bind DN esnekliği** — AD'nin
simple bind'i yalın bir `sAMAccountName`'i (`svc_ldap` gibi) KABUL
ETMEZ, DN veya UPN ister; `_bind_candidates` artık yalın bir kullanıcı
adını otomatik olarak UPN (`kullanıcı@domain`, SIMPLE) sonra NTLM
(`DOMAIN\kullanıcı`, NTLM) formatlarıyla SIRAYLA dener. (2) **Gerçek bir
500 hatası bulunup düzeltildi:** `ldap3`'ün NTLM implementasyonu MD4
hash kullanıyor — bu sunucunun Python/OpenSSL derlemesinde MD4 devre
dışı, `hashlib`'den `LDAPException` OLMAYAN bir `ValueError` geliyordu,
tek bir bind adayının çökmesi TÜM isteği 500 ile patlatıyordu;
`_bind_connection` artık `Exception`'ı da yakalayıp bir sonraki formata
geçiyor. (3) **Detaylı hata mesajları** — genel "bağlanılamadı" yerine
denenen HER formatın gerçek LDAP sonuç açıklaması (`data 52e` gibi)
kullanıcıya/loga dönüyor — bu sayede kullanıcı "yanlış parola" ile
"DC'nin LDAP signing zorunluluğu" (`strongerAuthRequired`) hatalarını
ayırt edebildi. (4) **IP tabanlı DC için TCP ön-kontrolü** — TLS/
sertifika doğrulaması olmadan ham bir `socket.connect()` ile "hiç
ulaşılamıyor" / "ulaşıldı ama reddedildi" ayrımı netleştirildi. (5)
**Frontend'de gerçek bir bug bulunup düzeltildi:** FastAPI 422 doğrulama
hatalarının `detail`'i bir DİZİ — eski `extractErrorMessage`
`Object.values(detail).join()` ile diziyi de yakalayıp her elemanın
`toString()`'ine düşerek kullanıcıya "[object Object]" gösteriyordu
(TÜM 422 hatalarını etkileyen genel bir bug, yalnızca LDAP'a özgü
değildi). (6) **Bind parolası artık Vault kimlik bilgisi güncellemesiyle
AYNI ilkeyle** — boş bırakılırsa mevcut şifreli parola KORUNUR (decrypt+
reencrypt turu olmadan, bayt-bayt aynı ciphertext) — önceden placeholder
metni ("Değiştirmemek için boş bırakın") YALAN söylüyordu, backend her
zaman dolu bir parola zorunlu tutuyordu. `infra/postgres/init.sql`'e
dokunulmadı. Backend 606→618, frontend 347→353 (2 yeni test dosyası
dahil değil, mevcut dosyalara eklendi) test. **Gerçek E2E:** kullanıcının
gerçek `lab.local` domain'ine karşı GERÇEK bir bind denemesi `data 52e`
(yanlış parola/kullanıcı adı) ve ardından `strongerAuthRequired`
(DC'nin LDAP signing zorunluluğu) hatalarını doğru şekilde ayırt etti;
DC'de LDAPS'ın kurulu olmaması nedeniyle (sertifika eksik) tam bir
başarılı bağlantı henüz doğrulanamadı — kullanıcının kararına
bırakıldı (DC'ye sertifika kurmak VEYA LDAP signing zorunluluğunu
gevşetmek).

## Faz 50 — PAM Oturum Kaydı, Canlı Oturum Sonlandırma, Tuş Loglama

**Durum:** ✅ Backend tamamlandı ve gerçek PostgreSQL'e karşı test
edildi (618→633 backend testi); frontend tamamlandı ve test edildi
(347→353 frontend testi — `SessionReplayModal` kasıtlı olarak component
testi kapsamı DIŞINDA bırakıldı, `GuacamoleRdpViewer`'daki AYNI gerekçe:
gerçek DOM canvas+3.parti kütüphane+Blob mock'lamak ayrı bir iş).
Oturum kaydı/canlı sonlandırma özelliklerinin GERÇEK bir guacd'ye karşı
canlı doğrulaması henüz yapılmadı — Docker/guacd bu ortamda hâlâ
kullanıcının kurmasını bekliyor (Faz 48'in bilinen kısıtı).

**Kullanıcının isteğinden kasıtlı sapmalar:**
- **SQLAlchemy/Pydantic-ORM/`/api/v1/*` YOK** — bu proje 50 faz boyunca
  hiç ORM kullanmadı (ham `asyncpg`), URL'ler hep versiyonsuz kaldı
  (bkz. Faz 42 notu). Yeni endpoint'ler mevcut `/api/pam/audit`
  namespace'ine eklendi (`/api/pam/sessions/*` AÇILMADI) — bu zaten
  ADMIN-only denetim ekranının tek doğruluk kaynağıydı.
- **Celery YOK** — "video dönüştürme task'ı" kullanıcının istediği gibi
  Celery/ffmpeg ile YAPILMADI. Bunun yerine guacd'nin RDP oturumlarını
  KENDİSİNİN ürettiği `.guac` protokol dosyası, `guacamole-common-js`'in
  **`Guacamole.SessionRecording`** sınıfıyla (Apache Guacamole'ün resmi
  web uygulamasının da kullandığı, kütüphanede zaten YÜKLÜ — ek bağımlılık
  YOK) TARAYICIDA doğrudan replay ediliyor — sunucu tarafında bir video
  dönüştürme adımı, `ffmpeg`/`guacenc` bağımlılığı YOK. Oynatma hızı
  (1x/2x/4x) kütüphanenin native bir "playback rate" API'si sunmadığı
  için `seek()`'i düzenli aralıklarla ileri çağıran manuel bir adım
  döngüsüyle (`SessionReplayModal.tsx::STEP_MS`) sağlanıyor.
- **`pam_sessions`/`pam_keystrokes` PARALEL tablo modeli YERİNE mevcut
  `pam_session_logs`'a iki additive kolon** (`recording_file_path`,
  `terminated_by`) eklendi — Faz 41/49'un "mevcut tabloyu genişlet"
  ilkesiyle tutarlı. "Aktif oturum" kavramı hâlâ `ended_at IS NULL`
  (ayrı bir `status` kolonu AÇILMADI — gereksiz state duplikasyonu
  olurdu); admin sonlandırması yeni bir `end_reason` değeri
  (`terminated_by_admin`) olarak temsil ediliyor. `pam_keystrokes`
  YALNIZCA SSH için (RDP metin girdisi yakalamaz — RDP'nin denetim izi
  zaten TAM ekran video kaydı).
- **Canlı oturum sonlandırma — bellek-içi registry** (`app/pam/
  session_registry.py`, tek bir Python `dict`) — bu proje HİÇBİR ZAMAN
  çoklu-worker (`uvicorn --workers N`) ile ÇALIŞTIRILMADI, bu yüzden
  Redis gibi paylaşımlı bir mekanizma bugün için gereksiz bir
  soyutlama olurdu (kod içinde açıkça belgelendi — çoklu-worker'a
  geçilirse bu registry'nin taşınması gerekir).

**Backend:** `app/pam/session_registry.py` (kill event registry) +
`app/pam/guacd.py`'ye `recording_config()`/`open_rdp_connection`'a
`session_id` parametresi (guacd'nin `connect` instruction'ına
`recording-path`/`recording-name`/`create-recording-path`/`recording-
exclude-output`/`recording-exclude-mouse` ekler) + `bridge_websocket_
to_guacd`'ye üçüncü bir `kill_event` bekleyicisi (mevcut Faz 48
`asyncio.wait(FIRST_COMPLETED)` deseninin doğal uzantısı). `app/agents/
ssh_proxy.py::run_pam_ssh_websocket_session`'a `on_keystroke` kancası
(her "input" WebSocket mesajının verisini `pam_keystrokes`'a yazar) +
AYNI `kill_event` deseni. `app/routes/pam_rdp.py`/`pam_ssh.py`: oturum
log satırı artık guacd'ye bağlanmadan/SSH açmadan ÖNCE oluşturuluyor
(`session_id`'nin guacd'nin `recording-name`'i olarak kullanılabilmesi
için — Faz 48'in eski sırasının TERSİ). Yeni route'lar (`/api/pam/
audit/{id}/terminate`, `/keystrokes`, `/recording`) mevcut ADMIN-only
router'a eklendi. `terminated_by` (admin kimliği) WebSocket handler'ın
KENDİSİ tarafından DEĞİL, `terminate_session` servis fonksiyonu
tarafından kill event set edilmeden ÖNCE (admin kimliği yalnızca o an
biliniyorken) AYRI olarak yazılır — `close_session_log` bu kolona hiç
dokunmaz (ilk taslakta bu ayrım YOKTU, kendi kod incelemem sırasında
gerçek bir "oturum sahibini admin olarak yanlış kaydetme" bug'ı olarak
yakalanıp düzeltildi).

**Frontend:** `/pam/audit` artık gerçek "Canlı Oturumlar" (1sn'de bir
güncellenen geçen süre sayacı + "Oturumu Anında Kapat") ve "Oturum
Geçmişi" (📼 Videoyu İzle / 📜 Komut Logları) sekmelerine ayrıldı —
Shadcn UI DEĞİL, projenin 50 faz boyunca kullandığı CSS Modules ile
(Faz 48'in aynı kararı). `SessionReplayModal.tsx` (video oynatıcı,
seek bar, 1x/2x/4x hız), `SessionKeystrokesModal.tsx` (ham tuş vuruşu
akışını `\r`/backspace'e göre okunabilir komut satırlarına indirgeyen
bir SEZGİSEL algoritma — TAM bir terminal emülatörü DEĞİL, ANSI kaçış
dizilerini yorumlamaz; amaç mükemmel bir render değil dürüst/okunabilir
bir yaklaşıklık).

**`infra/docker-compose.yml`/`.env.example`:** guacd konteynerine bir
kayıt dizini bind mount'u (`./pam-recordings:/var/lib/guacd/recordings`)
+ `GUACD_RECORDING_PATH`/`PAM_RECORDING_HOST_DIR` (biri guacd'nin,
diğeri bu backend'in AYNI dizini kendi dosya sisteminden gördüğü yol —
`GUACD_HOST_LOOPBACK_TARGET`'teki AYNI "iki taraf farklı görür" deseni).
İkisi de set EDİLMEDİĞİ sürece kayıt SESSİZCE devre dışı (opt-in,
`ENABLE_REMOTE_COMMANDS` ile AYNI ilke).

## Faz 51 — PAM Durum Senkronizasyonu, Canlı İzleme (Shadowing), WS Heartbeat

**Durum:** ✅ Backend tamamlandı ve gerçek PostgreSQL'e karşı test
edildi (633→639 backend testi); frontend tamamlandı ve test edildi
(353→354). Gerçek bir guacd'ye karşı canlı doğrulama henüz yapılmadı
(Faz 48/50'nin aynı Docker kısıtı).

**1) Durum senkronizasyonu — gerçek bug'ın kök nedeni farklı çıktı:**
`session_registry.unregister()`'ın HER ZAMAN (try/finally ile)
çalıştığı zaten Faz 50'de doğruydu — asıl risk, onu izleyen `close_
session_log` DB yazımının (ör. geçici bir bağlantı sorunu) başarısız
olması durumunda satırın DB'de SONSUZA KADAR `ended_at IS NULL`
kalabilmesiydi. Kullanıcının önerdiği "yeni bir `GET /api/v1/pam/
sessions/active` endpoint'i" YERİNE (versiyonlu URL, bu proje hiç
kullanmadı — Faz 42 notu), mevcut `GET /api/pam/audit?active=true`
sorgusu artık `session_registry.is_active()`'a karşı ÇAPRAZ KONTROL
ediliyor (`app/pam/service.py::list_session_logs`) — DB satırı hâlâ
"açık" görünse bile bu SÜREÇTEKİ gerçek kaynakta yoksa listede
görünmez, kendi kendini düzeltir.
**2) WebSocket Heartbeat — uygulama-seviyesi ping/pong YERİNE uvicorn'un
kendi native `--ws-ping-interval`/`--ws-ping-timeout` bayrakları**
(`.claude/launch.json`'a eklendi, `15`/`15`) kullanıldı: RDP kanalı
`guacamole-common-js`'in HAM Guacamole protokol metnini taşıyor (bkz.
Faz 48'in "instruction-sınırı bölünmesi" dersi) — bu kanala uygulama
seviyesinde bir `{"type":"ping"}` JSON mesajı enjekte etmek tarayıcı
ayrıştırıcısını BOZARDI. uvicorn'un transport-seviyesi WS ping/pong'u
(ham WebSocket kontrol çerçeveleri, veri akışına hiç karışmaz) yanıt
vermeyen bağlantıları OTOMATİK kapatır — bu da zaten var olan
`WebSocketDisconnect`-tetikli temizleme yoluna (session_registry
unregister + close_session_log) hiç yeni kod gerekmeden düşer.

**3) Canlı Oturum İzleme (Live Shadowing) — dürüst bir mimari sınırla:**
`app/pam/session_registry.py`'ye salt-okunur bir pub/sub eklendi
(`subscribe_shadow`/`publish_to_shadows`/`unsubscribe_shadow`) —
`app/pam/guacd.py::_pump_guacd_to_websocket` birincil tarayıcıya
gönderdiği HER tam Guacamole instruction grubunu bu abonelere de
yayınlıyor. Yeni `WS /api/pam/audit/{id}/shadow` (ayrı, `require_
permission` bağımlılığı OLMAYAN bir `ws_router` üzerinde — router-
seviyesi bağımlılık `Header` tabanlı, tarayıcı WebSocket'i header
gönderemez; kimlik doğrulama `pam_rdp.py`/`pam_ssh.py` ile AYNI query-
string JWT deseniyle ELLE yapılıyor). **Kullanıcının önerdiği gerçek
Guacamole "join" paylaşım protokolü KULLANILAMADI** — o, resmi `guacamole-
client` Java web uygulamasının (`guacamole-auth-jdbc` şeması ile) bir
özelliği; bu proje Faz 48'de o web uygulamasını KASITLI OLARAK
EKLEMEDİ, guacd'nin HAM protokolünde bir "join by key" instruction'ı
YOK. Bunun yerine: bir izleyici katıldığında, Oturum Kaydı (Faz 50)
ETKİNSE o ana kadar yazılmış `.guac` dosyası "yakalama" (catch-up)
olarak baştan gönderilip `Guacamole.Client`'ın durumu doğru kuruluyor
— ETKİN DEĞİLSE izleyici yalnızca KATILDIĞI andan itibaren gelen
güncellemeleri görür (dürüstçe belgelendi, `LiveSessionShadowModal.tsx`
alt yazısında da kullanıcıya gösteriliyor). İkinci, bağımsız bir guacd
RDP bağlantısı açmak KASITLI olarak YAPILMADI — tek-oturumlu (varsayılan)
bir Windows hedefte bu, orijinal kullanıcıyı OTURUMDAN ATARDI (izlemenin
"kullanıcıya hissettirmeden" şartının tam tersi); çok-oturumlu bir
hedefte ise tamamen FARKLI/boş bir masaüstü gösterirdi — ikisi de yanlış.

**Frontend:** `PamAuditPanel.tsx`'e Canlı Oturumlar sekmesinde RDP
satırlarına "👁️ Canlı İzle" butonu + yeni `LiveSessionShadowModal.tsx`
(`GuacamoleRdpViewer`'ın salt-okunur kardeşi — fare/klavye event
handler'ları HİÇ eklenmez, yalnızca ekran). Oturum Geçmişi sekmesi
artık 15sn'de bir sessizce kendini tazeliyor (Canlı sekmesi zaten
10sn'de bir yapıyordu) — biten bir oturum elle yenilemeye gerek
kalmadan Geçmiş'te görünür.

## Faz 52 — LDAP Bind-Auth Girişi + "Kullanıcılar & Yetkiler" AD Kullanıcı İçe Aktarma

**Durum:** ✅ Backend tamamlandı ve gerçek PostgreSQL'e karşı test edildi
(639→668 backend testi, 3 bilinen canlı-veri-kirliliği testi hariç);
frontend tamamlandı ve test edildi (354→362, `tsc`/`eslint` temiz).
Canlı production backend'e henüz uygulanmadı (bkz. aşağı "Dağıtım").

**1) Kapsamlı bir mimari geri dönüş — bilinçli:** Faz 49'un kendi
dokümantasyonu "Gerçek LDAP SSO/bind-auth login KASITLI olarak kapsam
dışı — ayrı, çok daha büyük bir güvenlik yüzeyi" diyordu. Bu faz o
kararı KULLANICININ AÇIK İSTEĞİYLE tersine çevirdi — ama Faz 33/41'in
`ENABLE_REMOTE_COMMANDS`/`AGENT_MAINTENANCE_ENABLED` deseniyle AYNI
iki-anahtarlı opt-in ilkesiyle: `LDAP_AUTH_ENABLED` (`.env`, varsayılan
`false`) açık OLMADAN `login()` LDAP'a hiç düşmez — mevcut yerel
bcrypt akışı tamamen değişmeden kalır. `LDAP_AUTH_DEFAULT_ROLE`
varsayılanı kullanıcının önerdiği `OPERATOR` DEĞİL, üç rolün en
güvenlisi olan `VIEWER` — otomatik provizyon edilen yeni bir AD
hesabının varsayılan olarak hiçbir yazma yetkisi olmaması için.

**2) `app/services/ldap_auth.py` (yeni dosya) — `login()`'in LDAP
fallback'i:** `app/auth/service.py::login()` önce yerel `password_hash`
ile dener (artık `NULL` olabilir — bkz. aşağı — `verify_password()`'a
`None` hash GEÇİRİLMEZ, açıkça kontrol edilip atlanır); yerel
başarısızsa VE `LDAP_AUTH_ENABLED=true` VE kayıtlı bir `ldap_config`
varsa `authenticate_and_provision()` gerçek bir LDAP bind dener
(mevcut Faz 49 `_bind_candidates`/`_bind_connection` AYNEN reuse
edildi — yeni bir bind mantığı YAZILMADI). Bind başarılıysa kullanıcı
adı Faz 49'un ÖNCEDEN SENKRONİZE ETTİĞİ `ad_users` tablosunda aranır
— **AD'de var olan ama hiç senkronize edilmemiş bir hesap otomatik
provizyon EDİLMEZ** (senkronize edilmemiş bir kullanıcı grubu/rol
bilgisini asla göremeyeceğimiz için, bilinçli sınır). Bulunursa: (a)
`users.ad_username` zaten bu hesaba bağlı bir kullanıcı varsa onun
`display_name`/`email`/rolü DOKUNULMADAN profili tazelenir, (b) yoksa
YENİ bir `users` satırı `password_hash=NULL`, `is_ad_user=true`,
rolü `LDAP_AUTH_DEFAULT_ROLE` ile oluşturulur — **kullanıcı adı
çakışması koruması:** `sAMAccountName` mevcut ama AD'ye BAĞLI OLMAYAN
bir yerel `username`'le çakışırsa (ör. `admin`) satır asla sessizce
üzerine yazılmaz/ele geçirilmez — login reddedilir, yalnızca bir
admin `/pam/users`'tan elle bağlayabilir.

**3) "Kullanıcılar & Yetkiler" AD içe aktarma:** `PamUsersPanel.tsx`'in
"Yeni Kullanıcı" formuna bir "Kullanıcı Kaynağı" seçici eklendi
(Yerel/AD). AD seçilince kullanıcı adı/parola/ad-soyad alanları
kayboluyor, yerine Faz 49'un `GET /api/settings/ldap/users` (yeni,
zaten senkronize `ad_users`'ı döndürüyor) ile doldurulan bir
`<select>` + rol seçici geliyor; gönderim `createPamUser` YERİNE yeni
`POST /api/pam/users/from-ad` (`ad_username` + `role`, parola YOK) ile
oluyor. Zaten bağlı AD kullanıcıları seçiciden filtrelenir (backend
zaten 409 döndürüyor, ama seçiciyi baştan temiz tutmak daha iyi UX).
Mevcut "AD Hesabı" sütunundaki serbest-metin bağlama akışı (Faz 49)
DOKUNULMADAN kaldı — artık yanında `user.ad_username` doluysa yeşil
"✅ AD Senkronize" rozeti gösteriyor.

**4) Kapsam dışı bırakılan, kullanıcının isteğinde olan öğeler:**
`app/api/v1/endpoints/auth.py` gibi versiyonlu bir yol AÇILMADI (proje
hiç `/api/v1` kullanmadı, Faz 42 notu) — mevcut `app/routes/auth.py`/
`app/routes/pam_users.py` genişletildi. `AUDITOR` rolü EKLENMEDİ
(proje yalnızca ADMIN/OPERATOR/VIEWER kullanıyor). "3. Cihaz/PAM AD
grup desteği" zaten Faz 49'da tamamdı (`pam_access_rules.ad_group_id`)
— bu fazda TEKRAR yazılmadı.

**Şema:** `users.password_hash` artık NULLABLE (AD-yalnızca hesaplar
için); `users.is_ad_user`/`users.email`, `ad_users.email` (additive).

Faz 52 sonrası bir bugfix de tamamlandı — kullanıcı gerçek bir AD
hesabıyla (`aykutd`) giriş yapamayınca ("kullanıcı adı veya parola
hatalı" sürekli) bulunup düzeltildi: `aykutd` zaten `/pam/users`'ın
"AD'den İçe Aktar" akışıyla (Faz 52) oluşturulmuştu (`is_ad_user=true`,
yerel parola YOK), ama `LDAP_AUTH_ENABLED` canlı `.env`'de HİÇ
set edilmemişti (varsayılan `false`) — bu yüzden `login()`'in LDAP
fallback'i hiçbir zaman denenmiyordu, girilen gerçek AD parolası ne
olursa olsun `authenticate_and_provision()` bayrağı görüp ANINDA
`None` dönüyordu. Kullanıcı onayıyla `LDAP_AUTH_ENABLED=true` canlı
`.env`'e eklendi, backend yeniden başlatıldı; bu, kod DEĞİL, yalnızca
dağıtım/yapılandırma düzeltmesiydi (Faz 52'nin kendi güvenli
varsayılanı — opt-in kapalı — beklendiği gibi çalışıyordu, sadece
kullanıcı henüz açmamıştı).

## Faz 53 — PAM Canlı İzleme & Oturum Kaydı — Tam Ekran + Zaman Çubuğu İşaretleri

**Durum:** ✅ Backend tamamlandı ve gerçek PostgreSQL'e karşı test
edildi (668→676 backend testi); frontend tamamlandı ve test edildi
(`tsc`/`eslint` temiz, mevcut 362 test değişmeden geçti — bkz. aşağı
"Kapsam dışı"). Canlı guacd'ye karşı henüz yeniden doğrulanmadı (Faz
48/50/51'in aynı Docker kısıtı, bu artırımda YENİ bir doğrulama
gerekmedi çünkü mevcut kayıt/shadow altyapısına dokunulmadı).

Kullanıcının isteği Faz 50/51'de zaten tamamlanmış olan Canlı İzleme
(Shadowing) ve Oturum Kaydı/Tekrar mimarisiyle BÜYÜK ÖLÇÜDE ÇAKIŞIYORDU
— bu faz onları YENİDEN YAZMADI, yalnızca gerçekten eksik olan iki
parçayı ekledi:

**1) Tam Ekran:** `SessionReplayModal.tsx` ve `LiveSessionShadowModal.tsx`
artık `GuacamoleRdpViewer.tsx`'teki (Faz 48) AYNI `element.
requestFullscreen()` desenini kullanan bir "Tam Ekran" butonu içeriyor
— mevcut `p.rdpFullscreen` çevirisi REUSE edildi, yeni bir çeviri
anahtarı açılmadı.

**2) Zaman Çubuğu İşaretleri (Timeline Activity Markers):** yeni
`app/pam/recording_analysis.py::extract_activity_markers()` — kayıtlı
`.guac` dosyasının KENDİSİNDEKİ GERÇEK `key` (tuş basma) instruction'larını
mevcut `app/pam/guacamole_protocol.py::read_instruction` ile ayrıştırıp
kaydın başlangıcına göre milisaniye ofsetlerine çeviriyor — YENİ bir
veri UYDURULMADI, kayıt zaten bu olayları içeriyordu (`recording-
exclude-mouse=false`, `key` hariç tutulmuyor, bkz. `guacd.py`). Art
arda `MARKER_MIN_GAP_MS=2000`'den yakın gelen tuş vuruşları tek bir
işarete birleştiriliyor (UI netliği, veri kaybı değil). Yeni `GET /api/
pam/audit/{id}/activity-markers` (mevcut `PAM_ADMIN`-only router'da,
YENİ bir namespace AÇILMADI) — kayıt yoksa (SSH oturumu) 404 DEĞİL boş
liste döner, replay ekranının kendisiyle TUTARLI. `SessionReplayModal`
zaman çubuğunun üzerine tıklanabilir tik işaretleri (`markerTick`)
çiziyor, tıklayınca o ana atlıyor.

**Kapsam dışı bırakılan, kullanıcının isteğinde olan öğeler:**
- `/backend/services/pam_proxy`, `/frontend/components/pam` gibi YENİ
  bir dizin yapısı AÇILMADI — proje 53 faz boyunca `app/pam/`,
  `app/routes/pam_*.py`, `components/*Modal.tsx` düz yapısını kullandı.
- `/ws/pam/stream/{session_id}/shadow` YENİ bir endpoint olarak
  AÇILMADI — Faz 51'in zaten çalışan, test edilmiş `/api/pam/audit/
  {id}/shadow`'u (aynı işlevi görüyor: salt-okunur, fare/klavye
  girdisi hiç gönderilmiyor) gereksiz yere yeniden adlandırmak/
  ikiletmek anlamsız olurdu.
- Kayıt formatı `.guac` olarak KALDI (`.mp4`/`.webm`'e dönüştürülmedi)
  — Faz 50'nin kasıtlı kararı (sunucu tarafı ffmpeg/`guacenc` dönüşümü
  yok, tarayıcıda `Guacamole.SessionRecording` ile replay) hâlâ geçerli.
- `SessionReplayModal`/`LiveSessionShadowModal` için YENİ birim testi
  AÇILMADI — Faz 48'in kendi kararıyla AYNI gerekçe (`guacamole-common-
  js` + gerçek DOM canvas + WebSocket/Blob mock'lamak ayrı, düşük
  getirili bir iş; backend tarafı — asıl yeni mantık — tam test edildi).

Faz 53 sonrası bir bugfix de tamamlandı: kullanıcı "Oturum Kaydı"
oynatıcısında sürekli "Oturum kaydı yüklenemedi" hatası bildirince
(gerçek, canlı bir kayıtla — `/pam/audit`'in Oturum Geçmişi sekmesinden
`📼 Videoyu İzle`) doğrudan tarayıcıda yeniden üretilip **gerçek kök
neden bulundu — `guacamole-common-js@1.5.0`'ın KENDİ üst düzey bir
hatası**: `Guacamole.SessionRecording` kurucusu bir `Blob` ile
çağrıldığında (bu projenin AYNEN kullandığı yol), kütüphanenin iç
`recordingBlob` değişkeni `source`'a HİÇBİR ZAMAN atanmıyor (kaynak
doğrulandı — yalnızca tünel dalı bunu yapıyor); sonuç `parseBlob
(undefined, ...)` çağrılıp `blob.size`'ın `undefined` üzerinde
patlamasıyla kurucudan SENKRON bir `TypeError` fırlaması — önceki kod
bunu sessizce `catch`'e düşürüp jenerik hata metnini gösteriyordu
(backend'in kendisi HER ZAMAN 200 ve doğru bytes döndürüyordu — gerçek
bir istekle doğrulandı, `apps/api` tarafında DÜZELTİLECEK bir şey
yoktu). Üçüncü parti kütüphanenin kaynağına DOKUNULMADI (`node_modules`
kalıcı değil) — bunun yerine `SessionReplayModal.tsx` artık kütüphanenin
KENDİ doğru çalışan tünel dalını sahte/senkron bir "tünel" nesnesiyle
tetikleyip önceden indirilmiş metni `Guacamole.Parser` ile buna
besliyor. Ayrıca: her iki `catch`/`onerror` yolu artık gerçek hatayı
`console.error`'a logluyor (kullanıcının 2. maddesi), yeni bir
`onprogress` bağlanıp yükleme ekranında geçen süre gösteriliyor,
`togglePlay()`'in zaten yalnızca `status==="ready"` sonrası
tetiklenebildiği doğrulandı (yapısal olarak zaten doğruydu, değişiklik
gerekmedi). **Backend'de de bağımsız, gerçek bir iyileştirme**:
`GET /api/pam/audit/{id}/recording` artık dosya VAR ama boş (0 bayt)
olduğunda 404 ("kayıt hiç yok") DEĞİL, ayrı/anlamlı bir 400 ("Oturum
kaydı dosyası boş") döndürüyor. `LiveSessionShadowModal.tsx`'e de
(kullanıcının 3. maddesi) `GuacamoleRdpViewer.tsx`'in Faz 48'de
bulduğu AYNI ölçekleme eksikliği bulunup düzeltildi — `display.
onresize`/pencere yeniden boyutlandırma/`fullscreenchange`'de
`display.scale()` çağrılıyor, artık tam ekrana geçmeden de ekrana
oturuyor. Backend 676→677 test (yeni boş-dosya testi), frontend `tsc`/
`eslint` temiz, mevcut 362 test değişmeden geçti. **Gerçek E2E:**
canlı backend'de gerçek bir 4.7 MB'lık `.guac` kaydı (67 saniyelik
gerçek bir RDP oturumu) tarayıcıda GERÇEKTEN yüklenip oynatıldı,
süre (01:04) doğru okundu, Oynat/Duraklat ve zaman çubuğu üzerinde
seek gerçekten çalıştı, konsolda hiçbir hata kalmadı.

Faz 53 sonrası İKİNCİ bir bugfix turu daha tamamlandı — kullanıcı
("çalışıyor ama tam ekranda görebiliyorum, bu ekranda ekran gelmiyor")
bildirince gerçek bir 2. ve 3. üretim hatası daha bulunup düzeltildi:
(1) `SessionReplayModal.tsx`'e Faz 48/53'te `GuacamoleRdpViewer.tsx`/
`LiveSessionShadowModal.tsx`'te bulunan AYNI ölçekleme eksikliği hiç
uygulanmamıştı — ekran normal (küçük) modal görünümünde native
çözünürlükte (ör. 1280×832) kalıp taşıyordu, `display.scale()` hiç
çağrılmıyordu. (2) DAHA DERİN, gerçek bir `guacamole-common-js` davranış
hatası (pikselleri ekrana getirmeyen asıl sebep): oynatma döngüsü bir
sonraki hedefi `recording.getPosition()` + `STEP_MS` ile hesaplıyordu —
ama `Guacamole.SessionRecording.getPosition()` istenen HEDEF zamanı
DEĞİL, o ana kadar ULAŞILAN GERÇEK karenin zaman damgasını döner;
kayıtta o aralıkta (RDP oturumunda ekran güncellemesi olmayan bir
boşlukta) yeni bir kare YOKSA `seek()` "başarıyla" tamamlanır AMA
`getPosition()` DEĞİŞMEDEN kalır — döngü SONSUZA KADAR AYNI hedefi
tekrar tekrar istiyordu (gerçek bir tarayıcıda, adım adım console.log
enstrümantasyonuyla doğrulandı: `next` hep aynı değerde donuyordu).
Doğrusu: kütüphanenin kare-hizalı pozisyonundan BAĞIMSIZ, kendi
istenen hedefi ayrı bir `virtualPositionRef`'te biriktirmek — kayıttaki
boşluk sona erip bir sonraki gerçek kareye ulaşıldığında ekran doğal
olarak atlıyor. Bu ikinci hata, İLK bugfix turundaki `setInterval`→
`setTimeout` kendi-kendine-hız-ayarlama değişikliğiyle KARIŞTIRILMAMALI
— o değişiklik farklı, gerçek bir sorunu (örtüşen `seek()` çağrılarının
birbirini iptal etmesi) çözüyordu, bu ikincisi TAMAMEN ayrı bir kök
nedendi ve sabit-aralıklı döngüde de, kendi-kendine-hız-ayarlayan
döngüde de AYNI şekilde ortaya çıkıyordu. `handleSeek`/`seekToMarker`
(elle zaman çubuğu sürükleme/işaret tıklama) da `virtualPositionRef`'i
senkron tutacak şekilde güncellendi. Frontend `tsc`/`eslint` temiz,
mevcut 362 test değişmeden geçti (bu, tamamen `SessionReplayModal.tsx`
içi bir mantık düzeltmesi — yeni bir API yüzeyi yok, backend'e
dokunulmadı). **Gerçek E2E:** canlı backend'deki 28 saniyelik, admin
tarafından sonlandırılmış gerçek bir RDP kaydı (`349c7c5b-...`) baştan
sona GERÇEKTEN oynatıldı — gerçek Windows masaüstü (simgeler, görev
çubuğu, saat) ekranda göründü, piksel-örnekleme ile %96+ dolu canvas
doğrulandı, 4x hızda kaydın sonuna (28394ms) ulaşıp otomatik durdu.

## Faz 54 — PAM "Denetim Kaydı" & "Erişim Kuralları" Kurumsal UI Yükseltmesi

**Durum:** ✅ Backend + frontend tamamlandı ve test edildi (backend
683 test, frontend 369 test); canlı production backend'e henüz
uygulanmadı.

**1) `PamAuditPanel.tsx`:** 4 KPI kartı (Toplam Kayıtlı Oturum/Bugünkü
Oturumlar/Admin Tarafından Kapatılanlar/Toplam İzleme Süresi) — HER
ZAMAN filtrelerden/sekmeden bağımsız, `active=false` ile çekilen TAM
oturum geçmişinden hesaplanır (uydurma sayı yok). Arama (kullanıcı/
cihaz/istemci IP, 300ms debounce) + Protokol/Bitiş Nedeni dropdown'ları
backend'e GERÇEK query parametresi olarak gider; Tarih hızlı filtresi
(Son 24 Saat/7 Gün/Tüm Zamanlar) kullanıcının kendi isteğinde backend
parametreleri arasında YOKTU, istemci tarafında zaten çekilmiş listeye
uygulanıyor. Protokol sütunu (RDP mavi/SSH yeşil) ve Bitiş Nedeni
sütunu (Kullanıcı kapattı yeşil/Admin sonlandırdı-Hata kırmızı) artık
renkli rozet.

**2) `PamRulesPanel.tsx`:** arama barı (kullanıcı/AD grubu/cihaz/kasa
hesabı, backend'e gider). SSH/RDP sütunları ✅/❌ ikonlu rozet. Geçerlilik
Tarihi artık kalan günü de gösteriyor (`daysRemaining`/`expired`
çeviri fonksiyonları, `AgentEnrollmentPanel`'in `expiresIn`
deseniyle AYNI). Yeni bir "Aktif/Pasif" toggle switch + "Kuralı
Düzenle" modalı (`EditRuleModal` — kasa hesabı/izinler/süre/geçerlilik
düzenler, hedefi (kullanıcı/AD grubu/cihaz) DEĞİŞTİRMEZ, backend'in
`PamAccessRuleUpdateRequest`'iyle zaten tutarlı bir sınır).

**3) GERÇEK bir şema/yetkilendirme değişikliği — yalnızca kozmetik
DEĞİL:** `pam_access_rules.is_active` (yeni, additive, varsayılan
`true`) — `is_active=false` iken `authorize_ssh_session`/`authorize_
rdp_session` erişimi GERÇEKTEN reddeder ve `list_authorized_assets_
for_user` (`/my-access`) o kuralı listeden çıkarır; böylece bir kuralı
SİLMEDEN geçici olarak devre dışı bırakmak artık mümkün.

**4) Backend filtreleme:** `GET /api/pam/audit` artık `search`/
`protocol`/`reason`/`limit`/`offset`; `GET /api/pam/rules` artık
`search`/`limit`/`offset` opsiyonel query parametreleri kabul ediyor
— hiçbiri verilmezse önceki davranışla birebir aynı. Kullanıcının
`app/api/v1/endpoints/pam_audit.py`/`pam_rules.py` önerisi AÇILMADI
(proje hiç `/api/v1` kullanmadı, Faz 42 notu) — mevcut `app/routes/
pam_audit.py`/`pam_rules.py` genişletildi. `GET /api/pam/rules`'a
kullanıcının istediği `protocol`/`reason` parametreleri EKLENMEDİ
(kurallarda böyle bir kavram yok — asset'in izin verdiği protokoller
zaten `allow_rdp`/`allow_ssh` sütunları, "bitiş nedeni" oturumlara
özgü) — bu bilinçli bir sapma.

**Kapsam dışı:** "Kullanıcı, Cihaz veya Kasa Hesabına Bağlı Serbest
Metin Arama"nın backend'de FULL-TEXT (pg_trgm vb.) değil basit ILIKE
olması — bu veri hacminde (bugün ~40-50 satır) performans farkı yok,
erken optimizasyon yapılmadı.

## Faz 55 — PAM Cihaz Etiketleri (Tags) + Statik Cihaz Grupları (Server Groups)

**Durum:** ✅ Backend + frontend tamamlandı ve test edildi (backend
683→694 test, frontend 369→376 test, `tsc`/`eslint` temiz). Aşağıdaki
"Kapsam" bölümü planlandığı gibi UYGULANDI — sapma yok. Canlı
production backend'e henüz uygulanmadı (yeni tablolar + `pam_access_
rules` şema değişikliği bir restart bekliyor).

**Amaç:** Bugün `pam_access_rules` yalnızca TEK bir `asset_id`'yi
hedefleyebiliyor — 50 "Production" sunucusu için 50 ayrı kural yazmak
gerekiyor. Bu faz, bir erişim kuralının tek bir cihaz YERİNE bir
**etikete** (ör. "Production") veya bir **statik cihaz grubuna** (ör.
"Linux Sunucuları") atanabilmesini sağlar — Enterprise PAM analizinin
1. maddesi, dinamik gruplar/access request/policy motoru gibi diğer
maddelerin üzerine oturacağı temel taş.

**Kapsam:**
1. **Backend — şema:** `tags` (id, name UNIQUE) + `asset_tag_assignments`
   (asset_id, tag_id — çoktan-çoğa) + `server_groups` (id, name,
   description, created_by) + `server_group_members` (server_group_id,
   asset_id — çoktan-çoğa, statik/elle üyelik). `pam_access_rules`'a
   `tag_id`/`server_group_id` (opsiyonel, `asset_id` ile birlikte HALA
   XOR — mevcut `user_id`/`ad_group_id` XOR deseniyle AYNI ilke, yeni
   bir CHECK constraint) eklenir.
2. **Backend — yetkilendirme:** `_resolve_rule` (dolayısıyla
   `authorize_ssh_session`/`authorize_rdp_session`/`list_authorized_
   assets_for_user`) artık bir asset için ÜÇ olası kural kaynağını
   çözer: doğrudan asset kuralı → etiket kuralı → grup kuralı (bu
   sırayla, en spesifik kazanır — mevcut "doğrudan kullanıcı kuralı AD
   grup kuralının önüne geçer" ilkesiyle AYNI).
3. **Backend — CRUD:** `app/routes/pam_tags.py` (`GET/POST/DELETE
   /api/pam/tags`, `PUT/DELETE /api/pam/tags/{id}/assets/{asset_id}`
   ile atama/kaldırma) + `app/routes/pam_server_groups.py` (`GET/POST/
   PUT/DELETE /api/pam/server-groups`, üyelik ekleme/kaldırma).
4. **Frontend:** `PamRulesPanel.tsx`'in "Yeni Kural"/"Kuralı Düzenle"
   formuna mevcut "Kullanıcı Tipi" (Yerel/AD Grubu) seçiciyle AYNI
   desende bir "Cihaz Hedefi Tipi" seçici (Tek Cihaz/Etiket/Cihaz
   Grubu) eklenir. Yeni `/pam/tags` ve `/pam/groups` sayfaları (basit
   CRUD listeleri, mevcut `Pam*Panel.tsx` desenini takip eder) +
   Sidebar'a link. `/assets`'te (opsiyonel, kapsam dahilinde ama
   düşük öncelikli) cihaz başına etiket rozetleri.

**Kapsam dışı (bilinçli, sonraki fazlara bırakıldı):** Dinamik gruplar
(`OS==Linux AND Env==Production` gibi kural motoru — Faz 55 SADECE
statik/elle üyelik), Access Requests/onay akışı, Access Policy motoru,
Break Glass — bunların hepsi bu fazın üzerine oturacak AYRI fazlar.
Cihaz etiketleri Discovery'nin kendi `assets` tablosuna YAZILMAZ (yeni
`tags`/`asset_tag_assignments` PAM'a özgü additive tablolar) — Discovery
katmanının kendi veri modeline PAM kavramları sızdırılmaz (mevcut
mimari ilkeyle tutarlı, `docs/architecture.md` §7).

**Testler:** `tags`/`server_groups` CRUD route testleri, etiket/grup
XOR constraint testi, `authorize_ssh_session`/`authorize_rdp_session`
etiket-kural ve grup-kural üzerinden yetkilendirme testleri, doğrudan
kuralın etiket/grup kuralının ÖNÜNE geçtiği öncelik testi,
`PamRulesPanel`/`yeni sayfalar` için frontend component testleri.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz, gerçek bir etiket/gruba atanmış kuralla gerçek bir SSH
veya RDP oturumu açılabildiği (ya da PAM kuralı olmadan reddedildiği)
canlı doğrulanır.

**Gerçekleşen (uygulama notları):** `create_rule`'daki eski, principal
× cihaz-hedefi kombinasyonu başına 6 ayrı ön-kontrol SORGUSU YAZILMADI
— bunun yerine `infra/postgres/init.sql`'deki 4 yeni UNIQUE kısıtına
(`(user_id,tag_id)`, `(user_id,server_group_id)`, `(ad_group_id,tag_id)`,
`(ad_group_id,server_group_id)` — mevcut `(user_id,asset_id)`/
`(ad_group_id,asset_id)`'e EK) güvenilip `asyncpg.UniqueViolationError`
yakalanıyor (mevcut `app/snmp/profile_service.py` deseniyle AYNI ilke)
— daha az kod, DB'nin kendi kısıtına güvenmek create_rule'daki 6 farklı
ön-SELECT'i gereksiz kıldı. `list_authorized_assets_for_user`
(`/my-access`) altı ayrı liste sorgusunu (grup<etiket<doğrudan × yerel/
AD-grup) düşük öncelikliden yükseğe bir dict'e yazarak birleştiriyor —
aynı asset için en spesifik/en doğrudan kural her zaman kazanıyor
(mevcut "doğrudan kullanıcı kuralı AD grup kuralının önüne geçer"
ilkesiyle birebir tutarlı, artık cihaz hedefine de uygulanıyor).
`PamTagsPanel.tsx`/`PamServerGroupsPanel.tsx`'in "Cihazları Yönet"
modalı TÜM asset listesini checkbox olarak gösterip anlık atama/kaldırma
yapıyor (ayrı bir "ekle" akışı yerine, küçük ölçekli bir envanterde
[bugün ~50-100 asset] en basit/en az tıklamalı UX). Backend 683→694,
frontend 369→376 test. **Gerçek bir guacd/SSH bağlantısına karşı canlı
doğrulama henüz yapılmadı** — bu artırımda yalnızca `authorize_ssh_
session`/`authorize_rdp_session`'ın KENDİSİ (kimlik bilgisi çözme dahil,
gerçek PostgreSQL'e karşı) test edildi, gerçek bir ağ bağlantısı
açılmadı (mevcut Faz 44/48 "paylaşımlı ortamda temkinlilik" ilkesiyle
tutarlı).

## Faz 56 — PAM Erişim Talepleri (Access Requests)

**Amaç:** Bugün bir OPERATOR/VIEWER'ın bir cihaza erişmesi için TEK
yol, Admin'in `/pam/rules`'tan ELLE bir kural yazmasıdır — kullanıcının
kendisi "bana X cihazına Y süreliğine SSH erişimi lazım, sebebi Z"
diye bir talep açıp Admin'in onaylamasını/reddetmesini SAĞLAYAMAZ. Bu
faz, Enterprise PAM analizinin 2. maddesi olan bu talep→onay akışını
ekler — **kendi paralel bir yetkilendirme motoru YAZMADAN**: onaylanan
bir talep, mevcut `pam_access_rules` motorunu (Faz 46-55, zaten test
edilmiş `authorize_ssh_session`/`authorize_rdp_session`/oturum
kaydı/audit) OLDUĞU GİBİ kullanacak şekilde GERÇEK bir kural
oluşturur/genişletir — iki paralel "kim neye erişebilir" kaynağı
asla olmaz.

**Kapsam:**
1. **Backend — şema:** yeni `pam_access_requests` tablosu — `requester_
   id`, cihaz hedefi (Faz 55 ile AYNI üçlü XOR: `asset_id`/`tag_id`/
   `server_group_id`), `protocol` (TEK seçim: 'ssh' VEYA 'rdp' —
   kullanıcının "Select Protocol" tekil ifadesiyle tutarlı, mevcut
   kuralların `allow_rdp`+`allow_ssh` ikili bayrağından FARKLI),
   `business_reason` (zorunlu metin), `requested_duration_mins`,
   `status` ('pending'/'approved'/'rejected'), `reviewed_by`,
   `reviewed_at`, `review_note`, `created_at`.
2. **Backend — onay akışı:** `POST /api/pam/access-requests` (kullanıcı
   `PAM_ACCESS` ile talep açar) + `GET /api/pam/access-requests`
   (Admin — tümünü/`?status=pending` filtreli görür) + `GET .../mine`
   (kullanıcı kendi taleplerini görür) + `POST .../{id}/approve`
   (Admin — bir `credential_id` VE opsiyonel not seçer) + `POST
   .../{id}/reject` (not zorunlu değil). **Onaylama YENİ bir izin
   sistemi YAZMAZ** — `app/pam/service.py::approve_access_request`
   mevcut `create_rule`/`update_rule`'u ÇAĞIRIR: aynı (principal,
   cihaz hedefi) için zaten bir kural varsa `allow_rdp`/`allow_ssh`'ı
   genişletip `valid_until`'ı UZATIR (kısaltmaz), yoksa Faz 46'nın
   `create_rule`'uyla YENİ bir kural açar — `valid_until = onay anı +
   requested_duration_mins`. "İzin otomatik sona erer" ihtiyacı YENİ
   bir mekanizma GEREKTİRMEZ — Faz 46'dan beri var olan `valid_until`
   kontrolü zaten bunu yapıyor.
3. **Frontend:** `MyAccessPanel.tsx`'e (`/my-access`) "Erişim Talep
   Et" butonu + formu (cihaz hedefi tipi — Faz 55'in AYNI 3'lü
   seçicisi —, protokol, süre, iş gerekçesi) + kullanıcının kendi
   talep geçmişi/durumu. Yeni `/pam/requests` sayfası (Admin-only,
   `PAM_ADMIN`) — bekleyen talepler listesi, Onayla (kasa hesabı seçimi
   ile) / Reddet aksiyonları.

**Kapsam dışı (bilinçli, sonraki fazlara bırakıldı):** Access Policy
motoru (IF rol/ortam/saat/ağ THEN onay/MFA/blok — Faz 56 talepleri HER
ZAMAN elle Admin onayı gerektirir, koşullu otomatik onay/red YOK), MFA
zorunluluğu, IP kısıtlaması, Break Glass (acil erişim — Faz 56'nın
"normal" talep akışından AYRI, kendi fazı), talebin otomatik/toplu
onaylanması. Bir talebin onaylanması SIRASINDA hangi kasa hesabının
kullanılacağı kullanıcıdan DEĞİL, onaylayan Admin'den istenir (istekte
bulunan kullanıcı zaten hiçbir zaman kasa hesabı seçme/görme yetkisine
sahip değildi, Faz 46'nın "zero-knowledge" ilkesiyle tutarlı).

**Testler:** `pam_access_requests` CRUD + durum geçişi (pending→
approved/rejected, ikinci kez onaylama/reddetme reddedilir) route
testleri, onaylamanın GERÇEKTEN yeni bir `pam_access_rules` satırı
oluşturduğu/mevcut olanı genişlettiği testi, onaylanan talep sonrası
`authorize_ssh_session`/`authorize_rdp_session`'ın GERÇEKTEN izin
verdiği testi, yetkisiz kullanıcının başka birinin talebini
onaylayamadığı/göremediği testi, frontend component testleri.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz, gerçek bir talep açılıp onaylandıktan SONRA gerçek bir
PostgreSQL'e karşı `authorize_ssh_session`/`authorize_rdp_session`'ın
başarıyla yetki verdiği (kayıt öncesi reddettiği) canlı doğrulanır.

**Gerçekleşen (uygulama notları):** Plan büyük ölçüde OLDUĞU GİBİ
uygulandı — tek bilinçli sapma **talep formunun cihaz hedefi**: planın
öngördüğü "Faz 55'in AYNI 3'lü seçicisi" (tek cihaz/etiket/cihaz grubu)
YERİNE `MyAccessPanel.tsx`'in talep formu YALNIZCA tek-cihaz (`asset_id`)
hedefi sunuyor. Gerekçe: `GET /api/pam/tags`/`server-groups` router
seviyesinde TAMAMEN `PAM_ADMIN` gerektiriyor (bkz. `app/routes/pam_
{tags,server_groups}.py`, Faz 55) — `PAM_ACCESS`'i olan sıradan bir
kullanıcı bu listeleri backend'den HİÇ ÇEKEMEZ; dolu gelmeyen/boş bir
seçici sunmak yerine backend'in zaten desteklediği `asset_id` hedefiyle
sınırlı tutuldu (backend `AccessRequestCreateRequest` hâlâ `tag_id`/
`server_group_id`'yi de kabul ediyor — bu yalnızca bir frontend UI
sınırı, ileride bir `PAM_ACCESS`-erişilebilir salt-liste endpoint'i
eklenirse kaldırılabilir). Backend tarafı planla birebir: `pam_access_
requests` (3'lü XOR CHECK, Faz 55 ile AYNI desen), `app/db/pam.py::get_
rule_for_exact_user_target` (approve'un genişletme-mi-yeni-mi kararı
için EXACT eşleşme — specificity-sıralı `get_device_rule_for_user`'dan
BİLİNÇLİ olarak AYRI), `approve_access_request` mevcut `create_rule`/
`update_rule`'u ÇAĞIRIYOR (atomik `status='pending'` WHERE koşuluyla
önce durum geçişini dener, başarısız olursa HİÇBİR yan etki
oluşturmuyor — çifte onay/red imkansız). `router`/`my_router` ayrımı
Faz 51'in `pam_rules.py::router`/`my_access_router` deseniyle BİREBİR.
Backend 694→702 test (8 yeni — talep oluşturma/XOR doğrulama, kendi
taleplerini listeleme izolasyonu, yetkisiz kullanıcının tüm listeyi
göremediği, yeni kural oluşturma, MEVCUT kuralı genişletme [tekrar
satır AÇILMADIĞI doğrulandı], red + `authorize_ssh_session`'ın
GERÇEKTEN reddettiği, çifte onay `409`, etiket hedefli onayın
`authorize_rdp_session`'a GERÇEKTEN yetki verdiği). Frontend 376→382
test (6 yeni — `MyAccessPanel`: boş durum, kendi taleplerinin listesi,
yeni talep gönderimi; `PamAccessRequestsPanel`: listeleme, kasa hesabı
seçimli onay modalı, red). `tsc`/`eslint` temiz. Sidebar'a "📩 Erişim
Talepleri" (`/pam/requests`, `PAM_ADMIN`) eklendi. **Canlı production
backend'e henüz uygulanmadı** — yeni şema (`pam_access_requests`
tablosu) bir sonraki restart'ta uygulanacak, gerçek E2E doğrulaması da
o zaman yapılacak.

## Faz 57 — İzin Matrisi (Permission Matrix)

**Amaç:** Enterprise PAM analizinin 3. maddesi "Rol Yönetimi + İzin
Matrisi" — kullanıcıya kapsam soruldu (`AskUserQuestion`): tam özel/
DB-tanımlı rol yönetimi (`users.role`'ün sabit ADMIN/OPERATOR/VIEWER
üçlüsünden çıkması) login/LDAP-provizyon/varsayılan izin atama gibi
birçok yeri etkileyen büyük ve riskli bir mimari değişiklik olacağından,
kullanıcı **yalnızca İzin Matrisi ekranını** onayladı — özel rol
yönetimi bilinçli olarak kapsam dışı bırakıldı.

Bugün Admin, `/pam/users`'ta bir kullanıcının izinlerini yalnızca TEK
TEK, `UserPermissionsModal` ile (bir seferde bir kullanıcı) düzenliyor
— tüm kullanıcıları ve tüm izinleri TEK ekranda, satır=kullanıcı/
sütun=izin şeklinde karşılaştırmalı görebileceği/toplu düzenleyebileceği
bir görünüm yok. Bu faz SADECE bunu ekliyor.

**Kapsam:**
1. **Backend:** YOK — `GET /api/pam/users` (tüm kullanıcılar +
   izinleri) ve `PUT /api/pam/users/{id}/permissions` (Faz 47) zaten
   matrisin ihtiyacı olan her şeyi karşılıyor. Yeni bir endpoint/toplu
   (`batch`) PUT AÇILMAZ — matristeki her hücre tıklaması mevcut
   `updatePamUserPermissions`'ı (o kullanıcının GÜNCEL tam izin
   listesiyle) çağırır, `UserPermissionsModal`'ın "yer değiştirme"
   sözleşmesiyle AYNI.
2. **Frontend:** Yeni `PermissionMatrixPanel.tsx` (`/pam/permissions`,
   `PAM_ADMIN`) — satırlar `fetchPamUsers()`'tan gelen kullanıcılar,
   sütunlar `ALL_PERMISSIONS` (mevcut `lib/auth/permissions.ts`), her
   hücre bir checkbox; tıklanınca o kullanıcının mevcut izin setine
   ekleme/çıkarma yapıp `updatePamUserPermissions`'ı çağırır (iyimser
   UI güncellemesi + hata durumunda geri alma). `PamUsersPanel.tsx`'e
   bu yeni ekrana giden bir bağlantı + Sidebar'a `📊 İzin Matrisi`
   linki (`PAM_ADMIN`).

**Kapsam dışı (bilinçli):** DB-tanımlı özel roller, rol CRUD, izin
kataloğunun kod dışına (DB'ye) taşınması, toplu (tüm satır/sütun)
tek-tık işlemler (ör. "bu izni herkese ver") — kullanıcı yalnızca
görüntüleme + hücre bazlı düzenleme istedi.

**Testler:** `PermissionMatrixPanel` component testi — matrisin
kullanıcı×izin grid'ini doğru render ettiği, bir hücreye tıklamanın
doğru `PUT .../permissions` çağrısını (o kullanıcının GÜNCEL tam
listesiyle, yalnızca bir izin eklenmiş/çıkarılmış olarak) tetiklediği,
hata durumunda checkbox'ın eski durumuna geri döndüğü.

**Tamamlanma kriterleri:** Frontend testleri geçer, `tsc`/`eslint`
temiz (backend değişmediği için backend test/deploy adımı yok).

**Gerçekleşen (uygulama notları):** Plan birebir uygulandı. Yeni
`PermissionMatrixPanel.tsx` (`/pam/permissions`) — `UserPermissionsModal.
tsx`'ten `PERMISSION_LABEL_KEY` export edilip KOPYALANMADAN reuse
edildi. Her hücre tıklaması `fetchPamUsers`/`updatePamUserPermissions`
(Faz 47, DEĞİŞTİRİLMEDİ) ile iyimser (optimistic) günceller, hata
durumunda checkbox eski durumuna geri alınır. `PamUsersPanel.tsx`'in
başlığına ekrana giden bir bağlantı + Sidebar'a "📊 İzin Matrisi"
(`PAM_ADMIN`) eklendi. Backend'e HİÇBİR değişiklik yapılmadı (plan
buydu). Frontend 382→385 test (3 yeni — grid render, hücre tıklamasının
kullanıcının GÜNCEL tam izin listesini gönderdiği, başarısız istekte
geri alma). `tsc`/`eslint` temiz. Backend değişmediği için canlıya
uygulama/restart GEREKMEDİ — mevcut çalışan production backend zaten
bu ekranın ihtiyaç duyduğu `GET /api/pam/users`/`PUT .../permissions`'ı
karşılıyor.

## Faz 58 — "Yetkili Sunucularım" Kurumsal PAM Launchpad Yükseltmesi

**Amaç:** Kullanıcının verdiği detaylı spesifikasyon — `/my-access`
ekranını (bugünkü `MyAccessPanel.tsx`, Faz 46/56) canlı erişilebilirlik,
aktif oturum sayısı, protokol rozetleri, kalan-süre göstergesi, KPI
kartları ve zenginleştirilmiş "Taleplerim" görünümüyle kurumsal bir PAM
"launchpad" ekranına yükseltmek.

**Bilinçli sapmalar (spesifikasyondan, gerekçeli):**
- Spesifikasyonun önerdiği `UserServersPanel.tsx`/`MyAuthorizedServers.
  tsx` dosya adları KULLANILMADI — proje kuralı "mevcut component'leri
  yeniden yaratma, var olanı genişlet"; mevcut `MyAccessPanel.tsx`
  (Faz 46/56) YERİNDE genişletiliyor.
- `GET /api/v1/pam/my-servers` YENİ/versiyonlu endpoint AÇILMIYOR — bu
  proje hiçbir zaman `/api/v1/...` kullanmadı (Faz 42/54/56'da aynı
  gerekçeyle reddedildi). Mevcut `GET /api/pam/my-access` (Faz 46)
  `is_online`/`active_sessions_count` alanlarıyla GENİŞLETİLİYOR.
- `os_type` diye YENİ bir backend alanı EKLENMİYOR — bu projede
  gerçek bir OS parmak izi/tespiti YOK (Faz 0-9'un `device_type`'ı
  genel bir sınıflandırma, Windows/Linux ayrımı değil); "Windows/RDP"
  ve "Linux/SSH" rozetleri saf FRONTEND'de, zaten var olan `allow_rdp`/
  `allow_ssh` bayraklarından türetiliyor (uydurma bir OS tespiti değil,
  zaten bilinen protokol izninin farklı bir görünümü).
- "Ping status" YENİ bir canlı ICMP probe'u TETİKLEMİYOR — `assets.
  status` (Faz 0-9'dan beri var olan, gerçek discovery/SNMP verisi)
  kullanılıyor; sayfa her yüklendiğinde yeni bir ağ taraması
  BAŞLATILMIYOR (mevcut "Discovery Engine yalnızca kullanıcının açıkça
  girdiği CIDR'ı tarar" güvenlik kuralına uygun).
- "Aktif Oturumlar" sayısı YENİ bir sayaç/tablo GEREKTİRMİYOR — Faz
  50/51'in `pam_session_logs`/`session_registry` çapraz kontrolü
  (`list_session_logs(active_only=True)`) reuse ediliyor.
- Dark Mode "Slate-900/950" Tailwind paleti EKLENMİYOR — bu proje 57
  faz boyunca hiç Tailwind kullanmadı (yalnızca CSS Modules, zaten
  varsayılan olarak koyu tema — Faz 21); aynı görsel sonuç mevcut
  `AgentsList.module.css` token'larıyla (zaten var olan `.dot`/
  `.dotOnline`/`.dotOffline`, `.kpiGrid`/`.kpiCard`, `.badge*`)
  üretiliyor.

**Kapsam:**
1. **Backend:** `app/pam/models.py::AuthorizedAssetResponse`'a
   `is_online: bool` (`assets.status == 'up'`) + `active_sessions_
   count: int` eklenir. `app/db/pam.py`'de `_RULE_JOIN_SELECT`/
   `_EXPANDED_TAG_RULE_SELECT`/`_EXPANDED_GROUP_RULE_SELECT`'e
   `a.status AS asset_status` eklenir (zaten `assets a` JOIN'i var,
   yeni bir JOIN gerekmiyor). `app/pam/service.py::list_authorized_
   assets_for_user` gerçek aktif oturum sayılarını (Faz 51'in
   `session_registry` çapraz kontrollü `list_session_logs`'unu reuse
   ederek) asset_id'ye göre gruplar.
2. **Frontend:** `MyAccessPanel.tsx` — KPI kartları (Yetkili
   Sunucularım/Aktif Taleplerim/Erişilebilir Sunucular, mevcut
   `.kpiGrid` deseni), tablo sütunları genişler (Sunucu+IP alt metni,
   canlı nokta ile Online/Offline rozeti — mevcut `.dot*` sınıfları,
   Aktif Oturum rozeti, Windows/RDP ⋅ Linux/SSH protokol rozetleri,
   `daysRemainingLabel` ile renkli kalan-süre — Faz 54'ten export
   edilip reuse edilir), Hızlı Bağlan butonları zaten var olan
   `/pam/ssh/`, `/pam/session/` linkleri, yalnızca yeniden
   stillendirilir. "Taleplerim" tablosuna arama/durum filtresi +
   gerekçe için `title` tabanlı tooltip eklenir, durum rozetleri
   zaten Faz 56'da renkliydi (aynen korunur).

**Kapsam dışı (bilinçli):** Gerçek OS parmak izi tespiti, periyodik
otomatik ping/health-check zamanlayıcısı (bu, ayrı ve daha büyük bir
"asset health monitoring" fazı olurdu — Faz 39'un SNMP scheduler'ıyla
karışmasın), talepler için toplu (bulk) aksiyon.

**Testler:** Backend — `is_online`/`active_sessions_count`'un GERÇEK
`assets.status`/aktif oturumdan doğru hesaplandığını doğrulayan
`test_pam_api.py` testleri. Frontend — `MyAccessPanel` testlerinin
yeni alanları/KPI kartlarını/arama-filtreyi kapsayacak şekilde
genişletilmesi.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz, gerçek `/my-access`'in canlıda doğru `is_online`/
`active_sessions_count` döndürdüğü doğrulanır.

**Gerçekleşen (uygulama notları):** Plan birebir uygulandı, tüm
sapmalar planda önceden belgelenen sapmalarla AYNI kaldı (yeniden
adlandırma yok, `/api/v1` yok, yeni `os_type` alanı yok, yeni ping
probe'u yok). `AuthorizedAssetResponse`'a `is_online`/`active_sessions_
count` eklendi; `app/db/pam.py`'deki 3 SELECT'e (`_RULE_JOIN_SELECT`,
`_EXPANDED_TAG_RULE_SELECT`, `_EXPANDED_GROUP_RULE_SELECT`) `a.status
AS asset_status` eklendi (zaten var olan `assets a` JOIN'i üzerinden,
yeni JOIN yok). `list_authorized_assets_for_user`'a yeni bir
`_active_session_counts_by_asset()` yardımcı fonksiyonu eklendi —
Faz 51'in `session_registry` çapraz kontrollü `list_session_logs
(active_only=True)`'unu reuse ediyor, asset_id'ye göre gruplayıp
sayıyor. `MyAccessPanel.tsx` (dosya adı DEĞİŞMEDİ) — 3 KPI kartı
(mevcut `.kpiGrid` deseni, Faz 54), Sunucu+IP alt metni, Online/Offline
rozeti (mevcut `.dot`/`.dotOnline`/`.dotOffline`, Faz 41'in Agent
durumundan reuse), Aktif Oturum rozeti, Windows/RDP ⋅ Linux/SSH
protokol rozetleri (`allow_rdp`/`allow_ssh`'ten türetildi, yeni alan
yok), `daysRemainingLabel` (Faz 54'ten export edilip reuse edildi,
KOPYALANMADI) ile renkli kalan-süre. "Taleplerim"e arama/durum filtresi
(mevcut `.filterBar`/`.filterSelect`) + gerekçe için native `title`
tabanlı tooltip eklendi. Backend 702→704 test (2 yeni — çevrimdışı
asset'te `is_online:false` doğruluğu, GERÇEK bir aktif oturumdan
`active_sessions_count`'un doğru hesaplandığı — mevcut `test_my_access_
lists_only_own_non_expired_rules` de `is_online`/`active_sessions_
count` alanlarını doğrulayacak şekilde genişletildi). Frontend 385→388
test (3 yeni — KPI kartları, online/offline+aktif oturum rozetleri,
arama filtresi). `tsc`/`eslint` temiz, tam backend+frontend regresyon
paketleri (704/704, 388/388) sorunsuz geçti — ayrı çalıştırıldığında
gerçek bir regresyon YOK; tam paket koşusunda görülen 3 hata (`test_
retention.py`/`test_agent_enrollment.py`/`test_agents_api.py::test_
retention_policy_defaults_to_disabled`) bu oturumun önceki fazlarında
da belgelenen, GERÇEK/kalıcı canlı veriye bağlı önceden var olan bir
ortam sorunu — Faz 58'e dokunulmadı.

## Faz 59 — Çoklu Tema Motoru + Sürüklenebilir Özelleştirilebilir Dashboard

**Amaç:** Kullanıcının spesifikasyonu — (a) 4 seçenekli bir Tema Motoru
(`fortios-dark`/`cyber-neon`/`midnight-blue`/`enterprise-light`) +
header'da tema seçici, (b) `/` dashboard'unun `react-grid-layout` ile
sürüklenebilir/boyutlandırılabilir bir grid'e dönüşmesi + görünüm
(view) seçici + widget ekle/kaydet/sıfırla araç çubuğu.

**Kapsam kararları (kullanıcıya `AskUserQuestion` ile soruldu, onaylandı):**
- **Tailwind EKLENMEDİ.** İstek "Tailwind Config"/"Tailwind class"
  diyordu ama proje 58 faz boyunca yalnızca CSS Modules + CSS
  değişkenleri kullandı; mevcut `lib/theme/ThemeProvider.tsx` (Faz 21,
  bugün 2 tema) 4 temaya GENİŞLETİLİYOR, `globals.css`'e 4 tema için
  `:root[data-theme="..."]` blokları ekleniyor. Mevcut dark mode
  kırılmıyor (eski `localStorage` değeri `"dark"` → `"fortios-dark"`,
  `"light"` → `"enterprise-light"` olarak MİGRATE ediliyor).
- **`react-grid-layout` (MIT) yeni bağımlılık olarak eklendi** —
  kullanıcı onayladı. CSS'i (`react-grid-layout/css/styles.css` +
  `react-resizable/css/styles.css`) `app/layout.tsx`'te global olarak
  import ediliyor.
- **Kalıcılık `localStorage`** — istek `/api/v1/endpoints/dashboards.py`
  ve `user_preferences` tablosu diyordu ama (1) proje hiç `/api/v1`
  kullanmadı, (2) tema/dil zaten `localStorage`'da (`ThemeProvider`/
  `LocaleProvider` deseni). Tema seçimi VE dashboard grid düzeni AYNI
  desende `localStorage`'a yazılıyor — bu increment'te backend/DB
  değişikliği YOK. (Cihazlar arası senkron isteyen bir sonraki adım
  ayrı bir faz olarak `/api/pam/preferences` + tablo ekleyebilir.)

**Kapsam:**
1. **Tema Motoru:** `ThemeProvider.tsx` — `Theme` tipi 4 değere çıkar,
   varsayılan `fortios-dark` (bugünkü dark paletiyle BİREBİR aynı
   değerler), legacy değer migrasyonu. `globals.css` — `:root` bugünkü
   dark değerlerini korur (fortios-dark), 4 tema için açık
   `[data-theme]` blokları; `prefers-color-scheme: light` fallback'i
   `:root:not([data-theme])`'e daraltılır (yeni koyu temalar yanlışça
   light'a düşmesin). Yeni `components/ThemeSwitcher.tsx` (header'da,
   `LanguageToggle`'ın yanında). `SettingsPanel.tsx`'in 2 düğmeli
   dark/light toggle'ı 4 temalı seçiciye dönüşür.
2. **Sürüklenebilir Dashboard:** yeni `components/dashboard/
   DashboardGrid.tsx` — `react-grid-layout`'ın `Responsive` +
   `WidthProvider`'ı. Widget kayıt defteri (id → mevcut component +
   başlık + kategori: Sistem/Ağ/PAM). 4 hazır görünüm (`Status/
   Overview` [varsayılan, bugünkü dashboard içeriği], `System
   Information`, `Network & Infra`, `PAM & Security`) + "Yeni Özel
   Dashboard". Her görünümün düzeni `localStorage`'da ayrı anahtar.
   Araç çubuğu: `+ Widget Ekle` (kategori seçili modal), `💾 Düzeni
   Kaydet`, `🔄 Varsayılana Sıfırla`. `app/page.tsx` statik layout
   yerine `<DashboardGrid />` render eder (mevcut widget
   component'lerinin HİÇBİRİ değişmez — yalnızca grid item içine
   sarılır). `RequirePermission DASHBOARD_VIEW` korunur.

**Kapsam dışı (bilinçli):** Sunucu tarafı düzen kalıcılığı (DB/API),
widget'lar arası veri paylaşımının yeniden düzenlenmesi
(`DashboardDataProvider` AYNEN kalır), yeni widget türleri yazmak
(yalnızca var olan component'ler kaydedilir), tema başına özel
tipografi/spacing (yalnızca renk token'ları değişir).

**Testler:** `ThemeProvider.test.tsx`/`SettingsPanel.test.tsx`/`pages.
test.tsx` 4 tema için güncellenir; yeni `ThemeSwitcher.test.tsx`. Yeni
`DashboardGrid.test.tsx` — varsayılan görünümün widget'larını render
ettiği, görünüm değişiminin widget setini değiştirdiği, "Widget Ekle"
modalının bir kart eklediği, "Sıfırla"nın düzeni varsayılana
döndürdüğü (sürükleme etkileşiminin KENDİSİ test edilmez — jsdom'da
ölçüm yok, Faz 48 Guacamole viewer precedent'i).

**Tamamlanma kriterleri:** Frontend testleri geçer, `tsc`/`eslint`
temiz, 4 temanın hepsi canlıda görsel doğrulanır, dashboard
sürükle/boyutlandır/kaydet/sıfırla canlıda çalışır. Backend
değişmediği için backend test/deploy adımı yok.

**Gerçekleşen (uygulama notları):** Plan birebir uygulandı.
- **Tema Motoru:** `ThemeProvider.tsx` — `Theme` tipi 4 değere çıktı
  (`fortios-dark` varsayılan, bugünkü dark paletiyle birebir),
  `normalizeStored()` eski `dark`/`light` değerlerini yeni isimlere
  bir kereye mahsus migrate ediyor (localStorage'a da yazarak).
  `globals.css` — `:root` fortios-dark varsayılanını korur, 4 tema
  için açık `[data-theme]` blokları; `prefers-color-scheme: light`
  fallback'i `:not([data-theme])`'e daraltıldı (yeni koyu temalar
  yanlışça açığa düşmüyor). Yeni `ThemeSwitcher.tsx` header'da
  (`LanguageToggle` yanında, native `<select>`). `SettingsPanel.tsx`'in
  2 düğmeli toggle'ı 4 temalı seçiciye dönüştü (`themeLabel()` helper).
- **Sürüklenebilir Dashboard:** yeni bağımlılık **`react-grid-layout`**
  eklendi — **KRİTİK GÜVENLİK BULGUSU:** kayıttaki `1.5.2` (ve
  1.5.0–1.5.3) sürümü, repo'da hiç olmayan `ip_fetcher` (curl ile
  `ifconfig.me`'den public IP çeken derlenmiş bir ikili) + `ip_fetcher.c`
  kaynak dosyasını içeriyor — npm registry'nin kendisi bu sürümleri
  BU NEDENLE `deprecated` işaretlemiş (bkz. react-grid-layout#2269).
  **Lifecycle/postinstall hook YOK** (yani ikili install'da
  çalıştırılmıyor) ve `1.5.4` "bayt-bayt aynı, yalnızca stray dosyalar
  çıkarılmış" — bu yüzden hemen **`1.5.4`'e yükseltildi**, `apps/web/
  package.json` `^1.5.4`'e sabitlendi, stray dosyaların gittiği
  doğrulandı. `1.5.4` bağımlılıkları yalnızca `react-draggable` +
  `react-resizable` (ikisi de MIT, temiz). `npm audit`'teki 3 açık
  (next/sharp/js-yaml) ÖNCEDEN vardı, bu bağımlılıkla ilgisiz.
  CSS'i (`react-grid-layout/css/styles.css` + `react-resizable/css/
  styles.css`) `app/layout.tsx`'te global import edildi.
- Yeni `components/dashboard/DashboardGrid.tsx` — 11 mevcut widget'ın
  (HİÇBİRİ değişmedi) kayıt defteri + 4 hazır görünüm + "Özel"
  (boş başlar). `app/page.tsx` statik 2-kolon layout yerine
  `<DashboardGrid />` render ediyor. Düzen `localStorage`'a görünüm
  başına ayrı anahtarla (`itops-dashboard-layout-<view>`) yazılıyor,
  son görünüm `itops-dashboard-view`'da. `+ Widget Ekle` (kategori
  filtreli modal), `💾 Düzeni Kaydet`, `🔄 Varsayılana Sıfırla` araç
  çubuğu; her kartta hover'da "Kaldır".
- `tests/testUtils.tsx::renderWithProviders` artık `ThemeProvider` de
  sarıyor (gerçek `layout.tsx` sıralamasıyla aynı — `TopHeader` →
  `ThemeSwitcher` bir provider gerektiriyor). Frontend 388→396 test
  (8 yeni: ThemeProvider +2 [4 tema + legacy migrasyon], ThemeSwitcher
  +2, DashboardGrid +4). `tsc`/`eslint` temiz, tam frontend paketi
  396/396.
- **Canlı doğrulama:** 4 tema da canlıda test edildi (`data-theme` +
  `--accent` + `body` bg/text/`color-scheme` JS ile doğrulandı:
  fortios-dark #3b82f6, cyber-neon #00ff9c, midnight-blue #4c8dff,
  enterprise-light `color-scheme:light` + açık zemin). Dashboard grid
  canlıda render oldu, görünüm değişimi (`overview`→`system`) widget
  setini değiştirdi ve `localStorage`'a yazdı. Test sonrası paylaşımlı
  admin hesabının `itops-theme`/`itops-dashboard-*` localStorage
  anahtarları temizlendi. Backend değişmediği için restart/deploy
  YAPILMADI.

## Faz 60 — Agent Detay Ekranına PAM Bağlantı Butonları (RDP / SSH / CMD-Terminal)

**Amaç:** Kullanıcı isteği — `AgentDetailView.tsx`'in sağ üst aksiyon
alanına 3 bağlantı butonu: RDP, SSH, CMD/Terminal.

**Bilinçli sapmalar (spesifikasyondan, `AskUserQuestion` ile onaylandı):**
- **`/api/v1/pam/sessions/start` YENİ/versiyonlu endpoint AÇILMADI** —
  proje hiç `/api/v1` kullanmadı (Faz 42/54/56/58/59). RDP/SSH butonları
  mevcut PAM sayfalarına yönlendiriyor: `/pam/session/{asset_id}`
  (Faz 48 Guacamole/guacd) ve `/pam/ssh/{asset_id}` (Faz 46 zero-knowledge
  terminal).
- **"IP + varsayılan kasa hesabıyla doğrudan tünel" YAPILMADI** — bu,
  Faz 46-58'de kurulan PAM yetkilendirme modelini (o kullanıcı+asset
  için AÇIK bir `pam_access_rules` satırı + belirli bir `credential_id`)
  bypass ederdi. "Bir IP'nin varsayılan kasa hesabı" diye bir kavram
  yok; PAM `asset_id` üzerinden çalışır. Butonlar yalnızca agent GERÇEK
  bir cihaza bağlıysa (`agent.asset_id`, Faz 29 eşleştirmesi)
  tıklanabilir; yetkilendirme kontrolü hedef PAM sayfasında (`Require
  Permission PAM_ACCESS` + panelin kendi `authorize_*` çağrısı) aynen
  zorunlu.
- **Gerçek interaktif "Agent Shell" (komut kanalı üzerinden PTY)
  YAPILMADI** — Faz 33 komut kanalının Auth/RBAC'ı yok (`docs/
  decisions.md` §17); üzerine streaming PTY bindirmek yetkilendirmesiz
  RCE olurdu. "CMD / Terminal" butonu Faz 35'in mevcut web SSH
  terminalini (`/remote-control/ssh/{agentId}`, xterm.js) açıyor;
  etiketi `agent.os`'a göre (`windows` → "⚡ CMD / PowerShell",
  `linux` → "⚡ Bash"). `agent.os` GERÇEK bir alan (Faz 30 system
  collector) — Faz 58'deki asset `os_type` sorunundan farklı olarak
  burada uydurma yok.

**Kapsam:** Yalnızca `apps/web/components/AgentDetailView.tsx`'in
quick-connect bloğu + `lib/i18n/translations.ts` (`agentDetails.
quickConnect.*` yeni anahtarlar) + `tests/AgentDetailView.test.tsx`.
Eski `.rdp` indirme (Faz 34) ve eski "SSH ile Bağlan" butonu (Faz 35,
`/remote-control/ssh`) bu EKRANDAN kaldırıldı — yerlerini PAM RDP/SSH
butonları + CMD/Terminal butonu aldı (Faz 34 `.rdp` backend endpoint'i
ve `AssetAgentPanel.tsx`'teki aynı akış AYNEN duruyor, yalnızca bu
ekranın butonları değişti).

**Kapsam dışı:** `AssetAgentPanel.tsx` (asset tarafı, ayrı bileşen —
dokunulmadı), gerçek agent-shell PTY (ayrı, güvenlik-kritik bir faz
olarak kalıyor), backend değişikliği (yok).

**Gerçekleşen:** `AgentDetailView.tsx` — `linkedAsset` varsa "🖥️ RDP
Bağlan" → `window.open('/pam/session/{id}')` ve "💻 SSH Bağlan" →
`window.open('/pam/ssh/{id}')`; yoksa `pamNeedsLinkedAsset` ipucu.
`agent.local_ip` varsa OS-duyarlı "CMD / Terminal" butonu →
`/remote-control/ssh/{agentId}`. Kullanılmayan `agentRdpConnectUrl`
import'u kaldırıldı. Frontend 396→398 test (`AgentDetailView.test.tsx`
3 eski test 5 yenisiyle değiştirildi: PAM RDP sayfası, PAM SSH sayfası,
CMD/Terminal [windows], Bash etiketi [linux], asset'e bağlı olmayan
agent'ta ipucu). `tsc`/`eslint` temiz, tam paket 398/398. Backend
değişmediği için restart YOK.

## Faz 61 — Firewall/Router Asset Detayına PAM CLI/SSH Kısayolu

**Amaç:** Kullanıcı isteği — Varlık/Cihaz detay ekranına firewall/router
cihazları için "Web Konsolu (HTTPS)" ve "CLI / SSH" PAM bağlantı
butonları + kasadan `admin`/`read-only_admin` hesap türüyle otomatik
yetkilendirme.

**Bilinçli sapmalar (`AskUserQuestion` ile onaylandı):**
- **"Web Konsolu (HTTPS) — PAM Web Proxy tüneli + kasa şifre
  enjeksiyonu" YAPILMADI.** Bu projede PAM yalnızca SSH ve RDP
  protokoller (Faz 46/48; `Protocol = Literal["ssh","rdp"]`). guacd bir
  HTTP reverse-proxy değil. Kimlik-enjeksiyonlu bir HTTPS reverse proxy
  (SSRF yüzeyi, self-signed sertifika doğrulama, oturum-cookie/CSRF
  yönetimi, URL rewrite, admin UI içi WebSocket'ler) ayrı ve
  güvenlik-kritik bir alt sistem — kullanıcı bunu **ayrı bir faza
  bırakmayı** seçti, bu increment'te Web Konsolu butonu HİÇ eklenmedi.
- **"Kasadan `admin`/`read-only_admin` hesap türü çek ve onunla
  yetkilendir" YAPILMADI.** `vault_credentials`'ta "hesap türü" kavramı
  yok (`credential_type` yalnızca `password`/`ssh_key`, Faz 46). PAM
  her zaman AÇIK bir `pam_access_rules` satırındaki belirli
  `credential_id`'yi kullanır — cihaz tipine göre "varsayılan hesap"
  seçmek bu modeli bypass ederdi (Faz 60'la aynı gerekçe).
- Yeni bir endpoint/`/api/v1` AÇILMADI.

**Kapsam:** Yalnızca `apps/web/components/AssetDetails.tsx` (topoloji
linkinin altına, `device_type === "firewall" || "router"` iken bir
"💻 CLI / SSH (PAM)" butonu → `window.open('/pam/ssh/{asset_id}')`),
`AssetDetails.module.css` (`.pamActions`/`.pamButton`), `lib/i18n/
translations.ts` (`assetDetails.pamCliSsh`), `tests/AssetDetails.test.
tsx`. Yetkilendirme hedef sayfada (`/pam/ssh/{assetId}`, Faz 46) aynen
zorunlu: o kullanıcı+asset için `pam_access_rules` + `PAM_ACCESS`.

**Kapsam dışı:** Gerçek PAM Web Proxy (ayrı faz), `router` dışındaki
network cihaz tipleri, backend değişikliği (yok).

**Gerçekleşen:** `AssetDetails.tsx` — firewall/router asset'te tek bir
"💻 CLI / SSH (PAM)" butonu mevcut zero-knowledge SSH terminaline yeni
sekmede yönlendiriyor. Frontend 398→400 test (2 yeni: firewall'da
`window.open('/pam/ssh/{id}')` çağrısı birebir; firewall/router
olmayan cihazda buton YOK). `tsc`/`eslint` temiz, tam paket 400/400.
Backend değişmedi, restart YOK.

## Faz 62 — IT Helpdesk / Arıza Yönetimi (Ticket Management)

**Amaç:** Kullanıcı isteği — PAM'den TAMAMEN bağımsız, genel bir IT
Helpdesk / bilet yönetimi modülü: bilet CRUD + zaman çizelgesi
(yorum/durum/atama), KPI kartları, filtre barı, liste tablosu, yeni
bilet + detay modalları, Sidebar entegrasyonu.

**Bilinçli sapmalar (spec'ten):**
- **`/api/v1/endpoints/tickets.py` / `/api/v1/tickets` KULLANILMADI** —
  proje hiç `/api/v1` veya `endpoints/` klasörü kullanmadı. Route:
  `app/routes/tickets.py` → `/api/tickets`. Modeller `app/tickets/`
  (Pydantic) + `app/db/tickets.py` (ham asyncpg) + `app/tickets/
  service.py`.
- **Yetkilendirme (`AskUserQuestion` ile onaylandı):** yeni bir
  `TICKETS_VIEW` izni eklendi (diğer OPERASYON menüleriyle tutarlı,
  Faz 47). `_ensure_tickets_permission_backfill()` (main.py) her
  başlangıçta HER mevcut kullanıcıya bir kerelik ekler (`grant_
  permission` — tek izin, diğerlerine dokunmaz; zaten varsa no-op).
  Atama + durum değişikliği "izni olan herkes" yapabilir (kullanıcı
  kararı — talep eden/teknisyen rol ayrımı ileride ayrı bir rafine
  etme olarak belgelendi).

**Kapsam:**
1. **Şema (`infra/postgres/init.sql`, additive):** `tickets`
   (`ticket_number` UNIQUE, category/priority/status CHECK,
   `created_by`/`assigned_to` → `users`, serbest metin `related_
   device` — FK YOK), `ticket_comments` (event: created/comment/
   status_change/assignment; düz yorum → `body`, geçiş → `*_from`/
   `*_to`), `ticket_number_seq` (yıl bazlı atomik sayaç).
2. **Backend:** `ticket_number` = `INC-YYYY-NNNN` (`ON CONFLICT ...
   DO UPDATE` ile eşzamanlı-güvenli). `sla_due_at` oluşturma anında
   önceliğe göre (`SLA_HOURS_BY_PRIORITY`: CRITICAL 4s / HIGH 24s /
   MEDIUM 72s / LOW 168s). `POST .../comments` tek çağrıda yorum +
   durum + atama; her biri zaman çizelgesine AYRI satır. Durum
   RESOLVED/CLOSED'a geçince `resolved_at` set, geri çıkınca temizlenir.
   `GET .../assignable-users` (`GET /api/pam/users` `PAM_ADMIN`
   gerektirdiği için `TICKETS_VIEW`-only kullanıcıya id+username
   döner). `GET /api/tickets` → filtre (status/priority/category/
   search) + sayfalama + `stats` (4 KPI, filtreden bağımsız).
3. **Frontend:** `lib/auth/permissions.ts` (+`TICKETS_VIEW`),
   `lib/api.ts` (Ticket* tipleri + fetch fonksiyonları), `Sidebar.tsx`
   (`🎫 Destek / Biletler` OPERASYON altında), `app/tickets/page.tsx`,
   `TicketsPanel.tsx` (KPI kartları + filtre barı + tablo, renkli
   öncelik/durum rozetleri `ticketBadges.ts`), `CreateTicketModal.tsx`
   (varlık/agent `<datalist>` otomatik tamamlama), `TicketDetailModal.
   tsx` (sol: zaman çizelgesi + yanıt; sağ: metadata + atama + durum +
   ilgili cihaz varsa Agent/Envanter linkleri). Mevcut 4 temayla
   (Faz 59) uyumlu — yalnızca var olan CSS Modules token'ları + 2 yeni
   rozet rengi (`.badgeYellow`/`.badgeOrange`).

**Kapsam dışı:** E-posta bildirimi, SLA ihlali zamanlayıcısı/eskalasyon,
talep-eden vs teknisyen rol ayrımı, dosya eki, bilet birleştirme,
raporlama/export.

**Testler:** `tests/test_tickets_api.py` (11 test: numara üretimi/artışı,
SLA, filtre+KPI, arama, düz yorum, durum geçişi + `resolved_at`, atama
+ geçersiz kullanıcı 400, boş yorum 422, bilinmeyen id 404, izinsiz
403, `assigned_to_me` sayacı). `tests/TicketsPanel.test.tsx` (4:
KPI+tablo render, kategori filtresi API'ye geçiyor, modal ile oluşturma
POST, detay modalından yanıt POST). `tests/pages.test.tsx` (+1 smoke).

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz; yeni şema canlıya uygulanır (restart + `TICKETS_VIEW`
backfill), canlıda gerçek bir bilet uçtan uca (aç → yorum → durum
değiştir) doğrulanır ve test verisi temizlenir.

**Gerçekleşen (uygulama notları):** Plan birebir uygulandı. Backend
703→714 test (11 yeni; tam paket koşusunda görülen 3 hata bu oturumun
önceki fazlarında da belgelenen, GERÇEK canlı veriye bağlı önceden
var olan ortam sorunu + 1 transient contention hatası — hepsi ayrı
çalıştırıldığında geçiyor). Frontend 400→405 test. `tsc`/`eslint`
temiz. **Canlı deployment + E2E:** kullanıcı onayıyla production
backend yeniden başlatıldı — `tickets`/`ticket_comments`/`ticket_
number_seq` şeması otomatik kuruldu, `TICKETS_VIEW` backfill'i mevcut
kullanıcılara (admin dahil) çalıştı, restart sırasında gerçek iki agent
kesintisiz yeniden bağlandı. Gerçek bir bilet uçtan uca doğrulandı:
oluştur → `INC-2026-0001`, SLA = +24s (HIGH); tek çağrıda yorum + durum
(`OPEN→IN_PROGRESS`) → zaman çizelgesinde 3 olay (`created`/`comment`/
`status_change`); liste + KPI doğru. Test bileti + `ticket_number_seq`
satırı DB'den temizlendi (bir sonraki gerçek bilet yine `INC-2026-0001`
olacak).

## Faz 63 — Bilet Sistemi: Dinamik Departman & Kategori Yönetimi

**Amaç:** Kullanıcı isteği — Faz 62'nin sabit `category` enum'ını (6
değer) admin tarafından yönetilen dinamik bir taksonomiyle değiştir;
`related_device` alanını tamamen kaldır; departman kavramını ekle.

**Bilinçli sapmalar / kararlar:**
- **`/api/v1/...` KULLANILMADI** (Faz 62'yle aynı) — `/api/tickets/
  {departments,categories}`.
- **"Silme" = soft-delete** (`is_active = false`). Departman/kategori
  mevcut biletler tarafından FK ile referanslanıyor; hard-delete satırı
  yok edip geçmiş biletleri bozardı. Aynı adı yeniden eklemek pasif
  satırı YENİDEN AKTİFLEŞTİRİR (silineni geri getirmenin yolu). Aktif
  bir isim tekrar eklenirse `409`.
- **Varsayılan set seed'lendi** (`infra/postgres/init.sql`, idempotent
  `ON CONFLICT DO NOTHING`): 4 departman (Operasyon/IT/Finans/İK), 8
  kategori (Ağ/Sunucu/Donanım-PC/Yazılım/Şifre Sıfırlama/E-Posta/
  Kullanıcı Desteği/Diğer) — sistem sıfır kategoriyle kullanılamaz
  olmasın.
- `tickets.category_id` uygulama katmanında ZORUNLU (Pydantic), DB'de
  nullable (boş `tickets` tablosuna sorunsuz `ALTER` + `ON DELETE SET
  NULL` için); `department_id` opsiyonel. Faz 62'yle canlıya çıkmış
  tabloda `category`/`related_device` kolonları `ALTER TABLE ... DROP
  COLUMN IF EXISTS` ile temizleniyor (prod `tickets` boş — veri kaybı
  yok).

**Kapsam:**
1. **Şema:** `ticket_departments` + `ticket_categories` (`id`, `name`
   UNIQUE, `is_active`), seed. `tickets`: `category` + `related_device`
   → `category_id` + `department_id` FK.
2. **Backend:** `GET /api/tickets/{departments,categories}` (aktif;
   `?include_inactive=true` admin panel için) — `TICKETS_VIEW`.
   `POST` + `DELETE /{id}` — **yalnızca `ADMIN`** (`require_role`).
   `create_ticket` kategoriyi doğrular (yok/pasif → `400`), departmanı
   verildiyse doğrular. Liste filtresi `category`→`category_id`,
   +`department_id`; arama artık kategori/departman adında da.
3. **Frontend:** `lib/api.ts` (Ticket tipi `category_id`/`_name` +
   `department_id`/`_name`; taksonomi fetch/create/delete). `Tickets
   Panel.tsx` — filtre dropdown'ları dinamik (kategori + YENİ departman),
   tablodan "Cihaz" sütunu kaldırıldı → "Departman" + "Kategori"
   eklendi, Admin'e "⚙️ Bilet Ayarları" butonu. Yeni `TicketSettings
   Modal.tsx` (2 sekme: Departman / Kategori; liste + ekle input'u +
   Pasife Al). `CreateTicketModal.tsx` — `İlgili Cihaz` KALDIRILDI,
   Kategori (zorunlu) + Departman (opsiyonel) dinamik select. `Ticket
   DetailModal.tsx` — cihaz bölümü + Agent/Envanter linkleri kaldırıldı,
   Departman + Kategori metadata'ya eklendi.

**Kapsam dışı:** Departman/kategori sıralama/renk özelleştirmesi,
departman bazlı SLA/atama kuralları, taksonomi hard-delete + toplu
yeniden atama.

**Testler:** `test_tickets_api.py` (12: seed listeleme, admin ekle /
non-admin 403 / dup 409, soft-delete + include_inactive + reaktivasyon,
bilinmeyen 404, numara/SLA/kategori adı, geçersiz/pasif kategoride
oluşturma 400, `category_id`/`department_id`/arama filtresi,
numara artışı, yorum + durum geçişi, atama doğrulama, boş yorum 422,
izin 403). `TicketsPanel.test.tsx` (5: KPI+tablo [Departman/Kategori
sütunları], `category_id` filtresi API'ye, Ayarlar butonu yalnızca
ADMIN, dinamik kategoriyle oluşturma POST, Ayarlar'dan departman
ekleme). `pages.test.tsx` mock güncellendi.

**Gerçekleşen:** Backend 714→715 test, frontend 405→406 test, `tsc`/
`eslint` temiz. **Canlı deployment + E2E:** kullanıcı onayıyla
production backend yeniden başlatıldı — `ticket_departments`/`ticket_
categories` + seed (8 kategori / 4 departman) kuruldu, `tickets`
ALTER'landı (`category`/`related_device` düştü, `category_id`/
`department_id` eklendi — DB kolon listesiyle doğrulandı), agent'lar
kesintisiz bağlandı. E2E: bilet dinamik kategori+departmanla açıldı
(`category_name`="Ağ" / `department_name`="Finans" doğru, `related_
device` anahtarı yok), admin "E2E-Test-Kategori" ekledi → `DELETE`
soft-delete etti (`is_active=false`) → aktif listeden düştüğü
doğrulandı. Test verisi (bilet + geçici kategori + `ticket_number_seq`)
temizlendi; seed taksonomi (8/4) korundu.

> **Not (Faz 64 geri alındı):** Faz 64 "Bilet RBAC — Departman Bazlı
> Kullanıcı Yönetimi" tam olarak uygulanıp canlıya alınmış, ardından
> kullanıcı isteğiyle 19 dosyada GERİ ALINMIŞTIR (yalnızca `infra/
> postgres/init.sql`'deki additive kolonlar — `users.ticket_role`,
> `users.ticket_department_id`, `ticket_comments.is_internal`/
> `priority_*`/`department_*` — canlı DB tutarlılığı için KORUNDU, kod
> onlara referans vermez). Yerine, aşağıdaki Faz 65 daha basit bir RBAC
> modeli getirir.

## Faz 65 — Bilet Detay UI Düzeltmesi + Basit REQUESTER RBAC + SMTP E-Posta Bildirimi

**Amaç:** Kullanıcı isteği — (1) `TicketDetailModal`'daki yanıt kutusu
taşması / dar modal düzeltilsin, (2) REQUESTER YALNIZCA kendi açtığı
biletleri görsün (Faz 64'ün departman-kapsamlı görünürlüğü GETİRİLMEZ —
daha da sıkı), (3) 3 tetikte HTML e-posta gönderen asenkron bir SMTP
servisi eklensin.

**Bilinçli sapmalar / kararlar:**
- **`/api/v1/...` KULLANILMADI**, dizin `/services/` DEĞİL `app/services/
  email_service.py` (mevcut `app/services/ldap*.py` deseni).
- **`ticket_role` yeniden kullanılır, `ticket_department_id` DE.** İki
  kolon da `init.sql`'de ve canlı DB'de zaten var (Faz 64'ten kaldı) —
  şema değişikliği YOK. Faz 64'ten FARK: departman-kapsamlı görünürlük,
  gizli iç notlar, öncelik/transfer olayları GETİRİLMEZ. Kural tek
  cümle: `ticket_role IN ('TECHNICIAN','ADMIN')` → tüm şirket biletleri;
  `REQUESTER` (varsayılan) → yalnızca `created_by = ben` (departmanı
  önemli değil). `get_ticket_detail`/`add_comment` kapsam dışı bilette
  **API seviyesinde 403**.
- **"IT personeli" = `ticket_role`.** Spec'teki "`department == 'IT'`"
  alternatifi UYGULANMADI — ad-bazlı departman eşleşmesi kırılgan ve
  `ticket_role` zaten aynı bilgiyi taşıyor; departmanı IT olan bir
  kullanıcı IT ekibindeyse `ticket_role`'ü de TECHNICIAN/ADMIN yapılır
  (admin panelinden).
- **"Tüm biletler varsayılan IT departmanına":** `create_ticket`
  `department_id` GÖNDERİLMEZSE, adı `'IT'` olan seed departmanı
  (init.sql'de var) otomatik atanır. Açıkça departman seçilirse ona
  saygı gösterilir.
- **SMTP `smtplib` (stdlib) — YENİ BAĞIMLILIK YOK.** Engellememesi için
  `asyncio.to_thread` içinde çalışır; tetik noktası `asyncio.create_
  task(...)` ile ateşle-unut — e-posta hatası HİÇBİR ZAMAN bilet
  işlemini bozmaz (yalnızca `logger.warning`). `SMTP_SERVER`
  ayarlanmamışsa servis sessizce no-op (opt-in, mevcut `LDAP_AUTH_
  ENABLED` deseniyle aynı ruh).
- **Faz 64'ün geri alınan REQUESTER "RESOLVED→CLOSED/OPEN onay akışı"
  GETİRİLMEZ** — kapsam sade tutuldu; REQUESTER durum değiştiremez
  (yalnızca public yorum).

**Kapsam:**
1. **Backend RBAC:** `CurrentUser` + `get_current_user` + `/api/auth/me`
   + `/api/pam/users` → `ticket_role` (+ `ticket_department_id`, admin
   panel için) taşır. `UserCreate/UpdateRequest` kabul eder; `db.users.
   insert_user`/`update_user` yazar. `app/main.py::_ensure_ticket_roles_
   backfill()` (Faz 47/62 deseni, idempotent): hiç TECHNICIAN/ADMIN
   yoksa `role='ADMIN'` olanları bilet ADMIN'ine yükseltir.
   `app/tickets/service.py`: `list_tickets`/`ticket_stats` REQUESTER'ı
   `created_by = ben`'e kısıtlar; `get_ticket_detail`/`add_comment`
   REQUESTER kapsam dışı bilette `TicketAccessDeniedError` → route'ta
   403. `create_ticket` `department_id` yoksa "IT" departmanını atar.
2. **SMTP:** `app/services/email_service.py` — `_smtp_config()` (env),
   `send_ticket_notification(kind, ticket, ...)` (`asyncio.to_thread` +
   `smtplib.SMTP`/`starttls`), `_render_html(...)` kurumsal HTML şablon
   (bilet no + başlık + oluşturan + `TICKET_BASE_URL`/asset link).
   3 tetik (hepsi `asyncio.create_task`, `app/tickets/service.py`
   içinden): (a) yeni bilet → IT grubuna (`SMTP_IT_GROUP_EMAIL`),
   konu `[INC-XXXX] Yeni Bilet Oluşturuldu`; (b) yeni yanıt → bilet
   sahibine (`created_by`'nin `users.email`'i), `[INC-XXXX] Biletinize
   Yeni Yanıt Eklendi`; (c) durum RESOLVED/CLOSED → sahibine,
   `[INC-XXXX] Biletiniz Çözüldü Olarak İşaretlendi`. `.env.example`
   güncellenir.
3. **Frontend:** `lib/api.ts` — `CurrentUser`/`UserCreate|Update
   Request`'e `ticket_role`(+`ticket_department_id`), `TicketRole` tipi.
   `PamUsersPanel.tsx` — tabloya "Bilet Rolü" select'i (satır içi
   güncelleme), forma "Bilet Rolü" alanı. `TicketsPanel.tsx` — REQUESTER
   ise alt başlık talep-portalı metni (opsiyonel, minör).
   **`TicketDetailModal.tsx` UI düzeltmesi:** modal `width: min(1040px,
   96vw)`; 2 kolon `grid` esnek kalsın (`minmax(0,1fr) minmax(0,320px)`);
   `<textarea>` `width:100%`, `min-height:120px`, `resize:vertical`,
   `box-sizing:border-box` + `word-break:break-word` (dikey kırılma
   düzeltmesi — `white-space` sorunu). i18n anahtarları (tr+en):
   `roleRequester`/`roleTechnician`/`roleAdmin`, `fieldTicketRole`,
   `colTicketRole`.
4. **i18n:** yukarıdaki yeni anahtarlar `tr` + `en`.

**Kapsam dışı:** Faz 64'ün gizli iç notları, öncelik/transfer zaman-
çizelgesi olayları, departman-kapsamlı görünürlük, REQUESTER onay akışı;
e-posta şablonu için kullanıcı bazlı tercih/abonelik; SMTP kuyruğu/
retry (ateşle-unut yeterli); e-posta doğrulama/bounce işleme.

**Testler:**
- `test_tickets_api.py` — mevcut 12 + yeni: (a) REQUESTER yalnızca kendi
  biletlerini listeler, (b) REQUESTER başkasının biletinde `GET`/`POST
  comment` → 403, (c) TECHNICIAN tüm biletleri görür, (d) `department_
  id` verilmeden açılan bilet "IT" departmanına düşer, (e) `/api/auth/
  me` `ticket_role` taşır.
- `test_email_service.py` (YENİ) — `smtplib.SMTP` mock'lanır: config
  eksikse no-op; 3 tetik doğru alıcı + konu + gövdede bilet no; SMTP
  exception yutulur (raise etmez).
- `PamUsersPanel.test.tsx` — Bilet Rolü select'i render + `PUT` çağrısı.
- `TicketsPanel.test.tsx` — mevcut testler `role`/`ticket_role` mock'u
  ile uyumlu kalır.
- `testUtils.tsx::mockCurrentUser` — `ticket_role: "ADMIN"` eklenir.

**Tamamlanma kriterleri:** Backend tüm ticket/auth/pam testleri +
`test_email_service.py` geçer; `tsc`/`eslint` temiz; frontend paketi
geçer. Canlı SMTP deployment kullanıcı onayıyla ayrıca yapılır
(`AskUserQuestion` — backend restart + gerçek `.env` SMTP değerleri).

**Gerçekleşen:** Uygulama planla büyük ölçüde örtüştü. Sapma:
`users.ticket_department_id` uygulama katmanına GERİ EKLENMEDİ (init.sql'
de duruyor ama Faz 65 RBAC'ı yalnızca `ticket_role`'e bakıyor —
departman-bazlı görünürlük yok, "department == 'IT'" alternatifi
uygulanmadı, kırılgan olduğu için). E-posta tetikleri `add_comment`
sonunda: bilet sahibi kendi biletinde işlem yaptıysa ona e-posta
gönderilmez. Backend ticket/auth/pam/email test setleri geçti (61→67
ilgili test + yeni `test_email_service.py` 5 test; 3 önceden var olan
canlı-veri kaynaklı flaky test —`test_delete_expired_codes_removes_
only_expired` vb.— hariç, Faz 65'le ilgisiz). Frontend 406→407 test
(`PamUsersPanel.test.tsx`'e "bilet rolü satır içi güncelleme" testi),
`tsc`/`eslint` temiz. `.env.example` SMTP bloğuyla güncellendi. **Canlı
production backend'e HENÜZ uygulanmadı** — SMTP `.env` değerleri +
restart kullanıcı onayı bekliyor.

## Faz 66 — SMTP Yapılandırması Ayarlar Ekranında (DB-Tabanlı)

**Amaç:** Kullanıcı isteği — Faz 65'in SMTP değerlerini `.env` yerine
Ayarlar > SMTP bölümünden yönet; "Bağlantıyı Test Et" ile gerçek bir
test e-postası gönder. `.env` fallback'i geriye dönük uyumluluk için
KORUNUR.

**Bilinçli sapmalar / kararlar:**
- Tek satırlık `smtp_config` tablosu (`ldap_config`/`agent_retention_
  policy` ile AYNI `id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id=1)`
  deseni). Parola `vault_credentials`/`ldap_config` ile AYNI Fernet
  anahtarı (`PAM_VAULT_SECRET_KEY`) — YENİ şifreleme anahtarı yok.
- Yetki: `require_role("ADMIN")` (bilet taksonomisi yönetimiyle AYNI
  sınır; SMTP bir PAM kavramı değil, bu yüzden `PAM_ADMIN` DEĞİL).
- `email_service.py` config çözümü: **önce DB (`smtp_config` satırı),
  yoksa `.env`.** DB satırı `enabled=false` ise gönderim yapılmaz.
- Parola yanıtta ASLA düz metin dönmez (`password_set: bool`); `PUT`'ta
  boş bırakılırsa mevcut şifreli değer bayt düzeyinde KORUNUR (LDAP
  bind parolası deseniyle aynı).
- "Test Et" verilen bir adrese (veya boşsa IT grup adresine) GERÇEK bir
  e-posta gönderir; başarısızlıkta 4xx/5xx DEĞİL `success=false` döner
  (LDAP/SNMP "Test Connection" ilkesi).

**Kapsam:**
1. **Şema:** `smtp_config` (server/port/use_tls/username/encrypted_
   password/from_email/it_group_email/base_url/enabled + last_test_*).
2. **Backend:** `app/db/smtp.py` (`get_config`/`upsert_config`/`record_
   test_result`), `app/routes/smtp_settings.py` (`GET`/`PUT /api/
   settings/smtp`, `POST /api/settings/smtp/test`), `email_service.py`
   DB-öncelikli config çözümü + `notify(recipients=None)` → IT grubu.
   `main.py` router kaydı + `conftest.py` patch listesi.
3. **Frontend:** `lib/api.ts` (`SmtpConfig`/`SmtpConfigRequest`/
   `SmtpTestResult` + 3 fonksiyon), `components/SmtpConfigurationCenter.
   tsx` (+ css, `LdapConfigurationCenter` deseni), `SettingsPanel.tsx`'e
   ADMIN'e görünür SMTP bölümü, `translations.ts` `settings.smtpConfig.*`
   (tr+en).

**Kapsam dışı:** Giden e-posta kuyruğu/retry, birden çok SMTP profili,
e-posta şablonu düzenleme UI'ı, DKIM/SPF, gelen e-posta (bilet açma).

**Testler:** `test_smtp_settings_api.py` (GET null; PUT kaydeder +
parolayı maskeler; PUT parolasız mevcut değeri korur; test endpoint'i
mock `smtplib` ile; ADMIN olmayan 403). `test_email_service.py` +
(DB config `.env`'i geçersiz kılar; DB satırı yoksa `.env` fallback;
DB `enabled=false` → gönderim yok). `SmtpConfigurationCenter.test.tsx`
(form render + kaydet API + test butonu).

**Tamamlanma kriterleri:** Backend ilgili testler + `test_email_
service.py` geçer; `tsc`/`eslint` temiz; frontend paketi geçer. Canlı
deployment (yeni tablo + restart) kullanıcı onayıyla ayrıca.

**Gerçekleşen:** Plan büyük ölçüde birebir. `email_service.py`
tamamen yeniden düzenlendi: `SmtpConfig` dataclass'ı + `_from_env()`/
`_from_row()`/`load_config()` (async, DB-öncelikli). `notify()` artık
config'i senkron kontrol ETMEZ — her zaman bir task planlar, gerçek
kapı `_deliver()` içinde (`cfg.usable`). `recipients=None` → IT grup
adresi (`create_ticket` tetiği bunu kullanıyor; eski `os.environ.get
("SMTP_IT_GROUP_EMAIL")` kaldırıldı). Parola `app.pam.vault` Fernet'i.
Yetki `require_role("ADMIN")`. `test_smtp_settings_api.py` (6) +
`test_email_service.py` 5→9 (DB-öncelik/fallback/disabled) +
`SmtpConfigurationCenter.test.tsx` (3). Frontend 407→410, `tsc`/
`eslint` temiz. `conftest.py` patch listesine `app.routes.smtp_
settings`/`app.db.smtp` eklendi. **Yan bulgu:** `email_service.notify()`
ateşle-unut bir `asyncio` task oluşturur ve o task `smtp_config`'i
okumak için `isolated_db`'nin PAYLAŞIMLI test connection'ında EŞZAMANLI
bir sorgu çalıştırır — asyncpg tek connection'da eşzamanlı işleme izin
vermediği için DB'ye bağlı TÜM ticket testleri TAKILDI. `conftest.py::
isolated_db` artık `email_service.notify`'ı da no-op'a patch'liyor
(e-posta gönderimi zaten `test_email_service.py`'de izole test ediliyor).
`.env.example` DB-öncelik notuyla güncellendi. **Canlı deployment YAPILMADI** — `smtp_config` tablosu +
backend restart kullanıcı onayı bekliyor; kullanıcı döndüğünde
Ayarlar > SMTP ekranından değerleri girip "Test Et" ile
doğrulayacak.

### Faz 66 tamamlama — Gönderen Adı + Gerçek SSL/TLS/None Şifreleme Seçimi

Kullanıcı isteği Faz 66'nın zaten karşıladığı bir spesifikasyonu
tekrar getirdi (DB-tabanlı SMTP paneli + test e-postası + bilet
tetikleyici entegrasyonu) — bunlar YENİDEN YAZILMADI, yalnızca
spesifikasyondaki iki GERÇEK eksik kapatıldı:
- **`smtp_from_name`** — önceden `"IT Operations Destek"` e-posta
  gövdesinde HARDCODE'du; artık `smtp_config.from_name` (Ayarlar'da
  "Gönderen Adı" alanı), `.env` fallback'i `SMTP_FROM_NAME`.
- **Gerçek şifreleme türü seçimi** — Faz 66'nın `use_tls: bool`'u
  yalnızca STARTTLS açıp/kapatıyordu; `465` (implicit SSL, bağlantı
  BAŞTAN itibaren şifreli — STARTTLS'ten FARKLI bir el sıkışma) hiç
  desteklenmiyordu. Artık `smtp_config.encryption` (`'tls'|'ssl'|
  'none'`) — `send_email_blocking` `encryption=='ssl'` için
  `smtplib.SMTP_SSL`, `'tls'` için `SMTP`+`starttls()`, `'none'` için
  düz `SMTP` kullanır. Eski `SMTP_USE_TLS` `.env` değişkeni geriye
  dönük okunur (yalnızca `SMTP_ENCRYPTION` set değilse).
- **Şema:** `smtp_config`'e henüz canlıya hiç uygulanmadan `encryption`/
  `from_name` eklendi (CREATE TABLE'da) — ama bu ortamın dev/test
  Postgres'inde tablo ZATEN (eski `use_tls` şekliyle) test koşularından
  oluşmuştu, bu yüzden idempotent `ALTER TABLE ... ADD/DROP COLUMN`
  + `use_tls`→`encryption` veri taşıma bloğu da eklendi (`DO $$ ...`).
- Frontend: "STARTTLS Kullan" checkbox'ı → "Şifreleme Türü" dropdown'u
  (TLS/SSL/None), şifreleme değişince port alanı tipik değere (587/
  465/25) ÖNERİ olarak güncellenir (elle girilmiş bir port ASLA
  üzerine yazılmaz). "Gönderen Adı" yeni alan.
- Testler: backend `test_email_service.py` +2 (SSL yolu `SMTP_SSL`
  kullanır, "none" `starttls` çağırmaz), `test_smtp_settings_api.py`
  +1 (SSL uçtan uca); frontend `SmtpConfigurationCenter.test.tsx` +1
  (port önerisi). Backend 45/45 ilgili test, frontend 426→427.
  `tsc`/`eslint` temiz. **Canlı deployment hâlâ YAPILMADI** — Faz 66
  ile aynı restart'ta uygulanacak.

## Faz 67 — Bilet SLA Politikası (Yapılandırılabilir) + Gecikmiş Bilet Filtresi

**Amaç:** Faz 64/65'te "SLA yönetimi ayrı faza" kararının karşılığı.
`SLA_HOURS_BY_PRIORITY` sabiti artık DB'den (Admin tarafından
düzenlenebilir) okunur; bilet listesinde "Gecikmiş" (SLA aşılmış)
filtresi + rozet.

**Bilinçli sapmalar / kararlar:**
- `ticket_sla_policy` — öncelik başına bir satır (`priority` PK,
  `sla_hours` INT). `infra/postgres/init.sql` idempotent seed
  (`ON CONFLICT DO NOTHING`) mevcut 4 değerle (CRITICAL 4 / HIGH 24 /
  MEDIUM 72 / LOW 168). Politika satırı yoksa `SLA_HOURS_BY_PRIORITY`
  sabiti fallback (sistem yine çalışır).
- SLA yalnızca **çözüm süresi** — ayrı "ilk yanıt SLA'sı" kavramı
  KAPSAM DIŞI (tek `sla_hours`).
- SLA ihlali e-posta eskalasyonu KAPSAM DIŞI (bir zamanlayıcı
  gerektirir; mevcut `email_service` yalnızca olay-tetiklemeli).
  `sla_due_at` yalnızca oluşturmada hesaplanır; politika sonradan
  değişirse ESKİ biletlerin `sla_due_at`'i DEĞİŞMEZ (dürüst — SLA o
  an taahhüt edilmiştir).
- `/api/v1` yok.

**Kapsam:**
1. **Şema:** `ticket_sla_policy` + seed.
2. **Backend:** `app/db/tickets.py` (`get_sla_policy`/`upsert_sla_
   policy`), `app/tickets/service.py::create_ticket` DB politikasını
   kullanır (fallback sabit). `GET /api/tickets/sla-policy`
   (`TICKETS_VIEW`), `PUT /api/tickets/sla-policy/{priority}`
   (`require_role("ADMIN")`). `list_tickets` yeni opsiyonel `overdue`
   filtresi (`sla_due_at < now() AND status NOT IN (RESOLVED,CLOSED)`).
3. **Frontend:** `lib/api.ts` (`SlaPolicy`, `fetchSlaPolicy`,
   `updateSlaPolicy`), `TicketSettingsModal.tsx` yeni "SLA" sekmesi
   (öncelik → saat input + Kaydet), `TicketsPanel.tsx` "Gecikmiş"
   filtre checkbox'ı + liste satırında SLA rozeti (`sla_due_at`
   geçmiş + açık → kırmızı), `translations.ts` anahtarları (tr+en).

**Kapsam dışı:** İlk yanıt SLA'sı, iş-saati/takvim bazlı SLA, SLA
ihlali eskalasyon/bildirim, departman bazlı farklı SLA.

**Testler:** `test_tickets_api.py` + (SLA politikası GET seed
değerleri; ADMIN PUT günceller, non-admin 403; güncellenmiş politikayla
açılan biletin `sla_due_at`'i yeni saate göre; `overdue` filtresi
yalnızca süresi geçmiş açık biletleri döner). `TicketSettingsModal`/
`TicketsPanel` testlerine SLA sekmesi + filtre.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz. Canlı deployment (yeni tablo + restart) kullanıcı
onayıyla ayrıca.

**Gerçekleşen:** Plan birebir. `ticket_sla_policy` (öncelik PK +
`sla_hours`) + seed. `service.py::_sla_hours(conn, priority)` DB
politikasını okur, satır yoksa `SLA_HOURS_BY_PRIORITY` sabiti;
`_sla_due_at` artık saat parametresi alıyor. `db.list_tickets` yeni
`overdue` filtresi (`sla_due_at < now() AND status NOT IN (RESOLVED,
CLOSED)`). Route'lar: `GET /api/tickets/sla-policy` (`TICKETS_VIEW`,
`/{ticket_id}`'den ÖNCE tanımlı), `PUT /api/tickets/sla-policy/
{priority}` (`require_role("ADMIN")`, geçersiz öncelik → 400).
`list_tickets_route` `overdue: bool` query param. Frontend:
`TicketSettingsModal`'a 3. sekme "SLA" (`SlaPanel` — öncelik → saat
input + Kaydet), `TicketsPanel` filtre barına "Yalnızca gecikmişler"
checkbox'ı (mevcut satır-içi "SLA aşıldı" rozeti zaten vardı — Faz 62).
`lib/api.ts` `SlaPolicy`/`fetchSlaPolicy`/`updateSlaPolicy`,
`TicketQuery.overdue`. Frontend 410→412 test (TicketsPanel'e overdue
filtresi + SLA sekmesi testi), `tsc`/`eslint` temiz. Backend
`test_tickets_api.py`'ye 4 SLA testi (seed değerleri; ADMIN PUT /
non-admin 403 / geçersiz öncelik 400; güncellenmiş politikayla açılan
biletin `sla_due_at`'i; `overdue` filtresi + çözülünce düşme).
**Canlı deployment YAPILMADI** — `ticket_sla_policy` tablosu + seed bir
sonraki restart'ta kurulur.

## Faz 68 — Bilet Metrikleri / Raporlama Paneli (salt-okunur)

**Amaç:** Helpdesk için özet metrikler — durum/öncelik/kategori/
departman dağılımı, ortalama çözüm süresi, SLA uyum oranı, son 30 günde
açılan vs çözülen. Karar destek; yeni veri YAZILMAZ.

**Bilinçli sapmalar / kararlar:**
- **Şema değişikliği YOK** — hepsi mevcut `tickets` üzerinde `GROUP BY`/
  agregasyon.
- Tek endpoint `GET /api/tickets/metrics` (`TICKETS_VIEW`). REQUESTER
  için de kendi biletlerine kısıtlı (Faz 65 `_is_it_staff` ilkesi) —
  yani REQUESTER "kendi biletlerimin metrikleri"ni görür.
- Ağır grafik kütüphanesi EKLENMEZ — mevcut `recharts` (Faz 39'dan
  beri var) tek bir bar/line grafik için yeterli; kalanı sayı kartları +
  CSS bar. `/api/v1` yok.
- Ortalama çözüm süresi yalnızca `RESOLVED`/`CLOSED` + `resolved_at`
  dolu biletlerden; SLA uyumu = `resolved_at <= sla_due_at` olanların
  oranı (yalnızca `sla_due_at` dolu olanlar payda).
- Zaman serisi: son 30 gün, gün bazında `created` ve `resolved`
  sayıları (Postgres `generate_series` + `date_trunc('day', ...)`).

**Kapsam:**
1. **Backend:** `app/db/tickets.py::ticket_metrics(conn, *, created_by_
   scope)` — tek fonksiyon, birkaç sorgu. `app/tickets/service.py::
   get_metrics(conn, actor)`. `app/tickets/models.py` yeni
   `TicketMetricsResponse`. `app/routes/tickets.py` `GET /metrics`
   (`/{ticket_id}`'den ÖNCE).
2. **Frontend:** `lib/api.ts` (`TicketMetrics`, `fetchTicketMetrics`),
   yeni `components/TicketMetricsPanel.tsx` (sayı kartları + dağılım
   barları + 30 günlük çift çizgi grafiği), `TicketsPanel.tsx`'e
   "📊 Raporlar" toggle'ı (panelin üstünde aç/kapa), `translations.ts`.

**Kapsam dışı:** Özel tarih aralığı seçici, dışa aktarma (CSV/PDF),
teknisyen bazlı performans, gerçek zamanlı yenileme, drill-down.

**Testler:** `test_tickets_api.py` + (metrics boş sistemde 0'lar; birkaç
bilet + çözüm sonrası dağılım/ortalama/SLA oranı doğru; REQUESTER
yalnızca kendi biletlerini sayar). `TicketsPanel.test.tsx` — Raporlar
toggle'ı metrics endpoint'ini çağırır ve kartları render eder.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz. Backend değişikliği additive (yeni route) — canlı
restart yine kullanıcı onayıyla.

**Gerçekleşen:** Plan birebir. **Şema değişikliği YOK.** `db.ticket_
metrics(conn, *, created_by_scope)` — birkaç agregasyon sorgusu (totals
+ `GROUP BY` status/priority/category/department + `generate_series`
30 günlük created/resolved). `service.get_metrics(conn, actor)` REQUESTER
için `created_by_scope=actor.id` (Faz 65 `_is_it_staff`). `GET /api/
tickets/metrics` (`TICKETS_VIEW`, `/{ticket_id}`'den ÖNCE).
`TicketMetricsResponse` modeli. Frontend: `components/TicketMetricsPanel.
tsx` — 5 sayı kartı (toplam/açık/gecikmiş/ort. çözüm saati/SLA uyum %)
+ 4 CSS dağılım barı + `recharts` `LineChart` (30 günlük açılan vs
çözülen). `TicketsPanel`'e "📊 Raporlar" aç/kapa toggle'ı (panel üstünde).
`lib/api.ts` `TicketMetrics`/`fetchTicketMetrics`. Frontend 412→413
test, `tsc`/`eslint` temiz. Backend `test_tickets_api.py` +3 metrik
testi (boş sistem 0'lar; aktivite sonrası dağılım/ortalama/SLA %100;
REQUESTER yalnızca kendi biletlerini sayar). Additive route — yeni
tablo yok; canlı restart yine de gerekli değil (route mevcut şema
üzerinde çalışır) ama diğer Faz 66/67 şema değişiklikleriyle birlikte
uygulanacak.

## Faz 69 — "Bana Atananlar" Bilet Filtresi + CSV Dışa Aktarma

**Amaç:** Teknisyenler için hızlı "üzerimdeki biletler" filtresi ve
filtrelenmiş bilet listesini CSV olarak indirme.

**Bilinçli sapmalar / kararlar:**
- **Şema değişikliği YOK.** `list_tickets`'e `assignee_scope` (bana
  atananlar) parametresi + `GET /api/tickets/export.csv` (aynı
  filtrelerle, `text/csv` + `Content-Disposition: attachment`).
- CSV backend'de elle üretilir (stdlib `csv` + `io.StringIO`) — yeni
  bağımlılık yok. REQUESTER için CSV de `created_by` kapsamına tabi
  (mevcut `_is_it_staff` ilkesi — ayrı bir yetki eklenmez).
- `/api/v1` yok. Sunucu tarafı sayfalama CSV'de yok — filtrelenmiş
  TÜM sonuçlar (makul üst sınır `limit=5000`).

**Kapsam:**
1. **Backend:** `db.list_tickets` `assignee_scope: UUID | None`.
   `list_tickets_route` `mine: bool` query param → `assignee_scope=
   current_user.id`. Yeni `GET /api/tickets/export.csv` (`TICKETS_VIEW`,
   `/{ticket_id}`'den ÖNCE) — `list_tickets` sonucunu CSV'ye çevirir
   (`ticket_number,title,priority,status,category,department,created_by,
   assigned_to,created_at,sla_due_at,resolved_at`).
2. **Frontend:** `lib/api.ts` `TicketQuery.mine` + `ticketCsvUrl(token,
   query)` (indirme linki), `TicketsPanel.tsx` filtre barına "Bana
   atananlar" checkbox'ı + "⬇ CSV" butonu, `translations.ts`.

**Kapsam dışı:** XLSX/PDF, zamanlanmış rapor e-postası, sütun seçici,
CSV'de yorum geçmişi.

**Testler:** `test_tickets_api.py` + (`mine=true` yalnızca aktöre
atanmış biletleri döner; `export.csv` doğru başlık satırı + satır
sayısı + `text/csv` content-type). `TicketsPanel.test.tsx` — "Bana
atananlar" → `mine=true` query; CSV butonu doğru URL.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz. Tamamen additive — canlı restart gerekmez (yalnızca
diğer bekleyen şema değişiklikleriyle birlikte).

**Gerçekleşen:** Plan birebir. **Şema değişikliği YOK.** `db.list_
tickets` `assignee_scope`; `list_tickets_route` `mine: bool`. Yeni
`GET /api/tickets/export.csv` (`TICKETS_VIEW`, `/{ticket_id}`'den ÖNCE)
— `service.export_tickets_csv()` stdlib `csv` + `io.StringIO`, 11
kolon, `limit=5000`, aynı `created_by_scope` RBAC. CSV auth header
gerektirdiği için frontend `<a href>` yerine `downloadTicketsCsv()` =
auth'lu `fetch` + `Blob` + programatik `<a download>.click()`
(JWT'yi query'e KOYMAZ). `TicketsPanel` filtre barına "Bana atananlar"
checkbox'ı (yalnızca IT ekibi — REQUESTER'a gösterilmez) + "⬇ CSV"
butonu. Backend `test_tickets_api.py` +3 (`mine` filtresi; CSV başlık+
satır+content-type; CSV `TICKETS_VIEW` gerektirir), frontend 413→415
(mine query + CSV fetch testi). `tsc`/`eslint` temiz.

## Faz 70 — SNMP Tabanlı Alert Kurallarının Canlıya Bağlanması (Faz 26/27 kalanı)

**Amaç:** Faz 26'da eklenen 6 SNMP-tabanlı alert kuralı
(`interface_down`/`interface_error`/`high_bandwidth`/`snmp_poll_
failure`/`device_unreachable`/`high_utilization`) `computeAlerts`'in
`options.monitoring` parametresi geçilmediği için bugüne kadar HİÇBİR
çağrı noktasında (yalnızca testlerde) tetiklenmiyordu — bunu düzelt.

**Bilinçli sapmalar / kararlar:**
- **Yeni bir istek döngüsü EKLENMEZ** — `fetchMonitoringHistory()`
  (Faz 39, `GET /api/monitoring/history`) zaten poll TETİKLEMEDEN
  arka plan worker'ının önbelleğini okuyor; `DashboardDataProvider`'ın
  mevcut 8sn'lik sessiz `useAutoRefresh` döngüsüne eklenir —
  `MonitoringOverview.tsx`'in kendi ayrı 7sn'lik döngüsüne
  DOKUNULMAZ (kasıtlı: aynı veri kaynağı, farklı iki bileşen çifte
  fetch yapabilir ama ikisi de zaten önbellek-okuma, ucuz).
- Test altyapısı (`tests/testUtils.tsx::mockAssetsAndScans`)
  `monitoringHistory` parametresini Faz 39'dan beri ZATEN destekliyordu
  — bu faz onu gerçekten KULLANAN kod tarafını tamamlıyor.
- `AssetDetails.tsx` `DashboardDataProvider`'ın DIŞINDA `asset` prop'u
  alıyor ama `app/layout.tsx` provider'ı TÜM uygulamayı sarmaladığı için
  (Faz 5) `useDashboardData()` burada da güvenle çağrılabilir — ayrı bir
  prop-drilling YAPILMAZ.

**Kapsam:**
1. `lib/DashboardDataProvider.tsx` — `monitoring: Record<string,
   SnmpPollResult>` state'i, `fetchMonitoringHistory()` ile (ilk yükte +
   mevcut sessiz auto-refresh döngüsünde) doldurulur, context'e eklenir.
2. `AlertsPanel.tsx`, `AlertsList.tsx`, `DeviceHealthSummary.tsx` —
   zaten `useDashboardData()` kullanıyor, `monitoring`'i de destructure
   edip `computeAlerts(assets, messages, { monitoring })` geçer.
3. `AssetDetails.tsx` — `useDashboardData()` eklenir, aynı şekilde geçer.

**Kapsam dışı:** Alert eşiklerinin (`alertThresholds.ts`) UI'dan
düzenlenmesi, alert geçmişi/bildirim, e-posta/webhook entegrasyonu.

**Testler:** `AlertsPanel.test.tsx`/`AlertsList.test.tsx`/
`DeviceHealthSummary.test.tsx`/`AssetDetails.test.tsx` — `mockAssets*`
yardımcılarına gerçek `monitoringHistory` geçilip `device_unreachable`/
`interface_down` gibi bir SNMP alert'inin artık GERÇEKTEN render
edildiği doğrulanır (öncesinde bu testler yalnızca `lib/alerts.test.ts`
seviyesinde saf fonksiyon testiydi).

**Tamamlanma kriterleri:** Frontend testleri geçer, `tsc`/`eslint`
temiz. Backend'e dokunulmaz, restart gerekmez.

**Gerçekleşen:** Plan birebir. `DashboardDataProvider`'a `monitoring:
Record<string, SnmpPollResult>` + `refetchMonitoring()` (`fetchMonitoring
History()`, poll TETİKLEMEZ) — ilk yükte ve mevcut 8sn'lik sessiz
`useAutoRefresh` döngüsünde dolduruluyor, hata durumunda mevcut harita
korunuyor. `AlertsPanel`/`AlertsList`/`DeviceHealthSummary` zaten
`useDashboardData()` kullanıyordu, yalnızca `monitoring`'i de alıp
`computeAlerts`'e geçirdiler. `AssetDetails.tsx`'e YENİ `useDashboardData()`
çağrısı eklendi — bu yüzden `tests/AssetDetails.test.tsx`'in kendi
`LocaleProvider`-only render yardımcısı `renderWithProviders`'a (bir
`DashboardDataProvider` atası gerektiği için) geçirildi; mevcut testlerin
hiçbiri `assets`/`scans` state'ini OKUMADIĞI için bu geçiş hiçbirini
bozmadı. 4 component testine gerçek SNMP tabanlı alert (`device_
unreachable`/`interface_down`) artık GERÇEKTEN render edildiğini
doğrulayan birer test eklendi (`tests/testUtils.tsx::mockAssetsAndScans`'ın
Faz 39'dan beri hazır duran `monitoringHistory` parametresi ilk kez
kullanıldı). Frontend 415→419 test, `tsc`/`eslint` temiz. Backend'e
dokunulmadı, restart gerekmiyor — bu faz canlıda hemen (bir sonraki
frontend deploy'unda) etkili olur.

## Faz 71 — Zamanlanmış Ağ Taraması (Scheduled Discovery)

**Amaç:** Kullanıcının elle her seferinde CIDR girip taramasına gerek
kalmadan, daha önce açıkça verdiği bir CIDR aralığını düzenli aralıklarla
otomatik yeniden taramak.

**Bilinçli sapmalar / kararlar:**
- **Güvenlik ilkesi bozulmuyor** (CLAUDE.md): "örtük/otomatik geniş ağ
  taraması yapılmaz" — burada YENİ/keşfedilen bir aralık taranmıyor,
  kullanıcının Ayarlar'da AÇIKÇA kaydettiği bir CIDR'ın periyodik
  TEKRARI yapılıyor. Bir zamanlama olmadan hiçbir otomatik tarama
  olmaz.
- **Yeni bir tarama motoru YOK** — `app/discovery/scanner.py::
  scan_network` ve `app/routes/discovery.py`'nin mevcut `persist_scan_
  result`/`start_scan_record`/`complete_scan_record`/`fail_scan_record`
  yardımcıları (zaten "discovery↔DB tek temas noktası" olarak
  belgeli) AYNEN reuse edilir — elle taramayla TAMAMEN aynı kod yolu.
  Bu yüzden yalnızca zamanlayıcı `app/routes/discovery.py`'den import
  eder (yön istisnası — bu dosyanın kendi docstring'i bunu zaten "tek
  temas noktası" olarak tanımlıyor).
- **Yetki:** `/api/discovery/*`'nin geri kalanı (elle tarama) HÂLÂ
  backend auth'suz (bkz. "genel sayfa API'lerinin backend
  yetkilendirmesi" — kapsam dışı, ayrı büyük iş) — ama zamanlama CRUD'u
  KALICI, arka planda kaynak tüketen bir yapılandırma olduğu için
  bilinçli olarak `require_role("ADMIN")` ile korunuyor (ticket
  taksonomisi/SLA politikasıyla AYNI ilke).
- Arka plan worker'ı `app/snmp/scheduler.py`/`app/agents/scheduler.py`
  ile AYNI desen: sonsuz döngü, sabit tick (`DISCOVERY_SCHEDULER_TICK_
  SECONDS`, varsayılan 60sn), bir turun hatası worker'ı DURDURMAZ,
  `DISCOVERY_SCHEDULER_ENABLED=false` ile kapatılabilir.

**Kapsam:**
1. **Şema:** `scheduled_scans` (`id`, `cidr`, `interval_hours` [>0],
   `enabled`, `last_run_at`, `last_run_status`, `last_run_error`,
   `created_at`, `updated_at`).
2. **Backend:** `app/db/scheduled_scans.py` (CRUD + `list_due(conn)` —
   `enabled AND (last_run_at IS NULL OR last_run_at + interval_hours
   saat <= now())`). `app/discovery/scheduler.py` — her tick'te süresi
   gelenleri bulur, her biri için elle taramayla AYNI akışı
   (`start_scan_record`→`scan_network`→`persist_scan_result`→
   `complete_scan_record`/`fail_scan_record`) çalıştırır, sonucu
   `scheduled_scans`'a yazar. `app/routes/discovery.py`'ye `GET/POST
   /api/discovery/schedules` + `PUT/DELETE /api/discovery/schedules/
   {id}` (`require_role("ADMIN")`). `main.py` lifespan kaydı.
3. **Frontend:** `lib/api.ts` (`ScheduledScan` + CRUD fonksiyonları),
   yeni `components/ScheduledScansPanel.tsx` (Ayarlar'a ADMIN-only
   bölüm — CIDR + saat aralığı ekle, liste, aç/kapa, sil, son çalışma
   durumu), `translations.ts`.

**Kapsam dışı:** Zamanlama başına farklı tarama tipi (yalnızca ICMP —
mevcut tek motor), takvim/iş-saati kısıtlı zamanlama, e-posta özeti,
çakışan zamanlamaların paralel çalıştırılması (worker sıralı çalışır).

**Testler:** `test_discovery_schedules_api.py` — CRUD ADMIN gerektirir;
oluşturma/güncelleme/silme; `interval_hours<=0` → 422. `test_discovery_
scheduler.py` (yeni, `unittest.mock` ile `scan_network` sahtelenir) —
süresi gelen bir zamanlama gerçekten taranır + `last_run_at` güncellenir;
süresi gelmemiş/`enabled=false` atlanır; bir zamanlamanın hatası
diğerini engellemez. Frontend `ScheduledScansPanel.test.tsx`.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz. Canlı deployment (yeni tablo + restart) kullanıcı
onayıyla ayrıca.

**Gerçekleşen:** Plan birebir. `app/db/scheduled_scans.py` (CRUD +
`list_due`), `app/discovery/scheduler.py` (`app/snmp/scheduler.py`
deseni — `schedules_repo.get_connection()` module-attribute çağrısı,
`app.db.scheduled_scans.get_connection` üzerinden test'te patch'lenebilir
tutuldu). Zamanlanmış tarama `app/routes/discovery.py`'nin zaten
"discovery↔DB tek temas noktası" olarak belgeli `start_scan_record`/
`scan_network`/`persist_scan_result`/`complete_scan_record`/`fail_scan_
record`'unu AYNEN reuse ediyor. CIDR doğrulaması `app/discovery/
cidr.py::parse_ipv4_cidr` ile (kayıtta normalize edilmiş biçimde
saklanıyor). `main.py` lifespan'a `DISCOVERY_SCHEDULER_ENABLED`
(varsayılan açık) kaydı. Frontend `ScheduledScansPanel.tsx` (Ayarlar,
ADMIN-only, `SmtpConfigurationCenter` ile AYNI `canManageSmtp` kapısı).
Backend `test_discovery_schedules_api.py` (8) + `test_discovery_
scheduler.py` (5, gerçek ağ taraması YAPILMADAN `scan_network` sahtelenerek)
— toplam 96/96 ilgili discovery test dosyası geçti. Frontend
419→424 test (`tsc`/`eslint` temiz). **Canlı deployment YAPILMADI** —
`scheduled_scans` tablosu bir sonraki restart'ta kurulur.

Faz 59 sonrası bir UX düzeltmesi de tamamlandı — kullanıcı canlı
dashboard ekran görüntüsüyle bildirdi ("kaydet/ekle görüyorum, ayarı
yaptıktan sonra kaybolması lazım"): `DashboardGrid.tsx`'in düzenleme
araç çubuğu ("+ Widget Ekle" / "💾 Düzeni Kaydet" / "🔄 Varsayılana
Sıfırla") ve widget sürükle/boyutlandır + "Kaldır" düğmeleri artık
varsayılan olarak GİZLİ — günlük (salt-izleme) kullanımda dashboard
temiz kalıyor. Yeni "✏️ Düzenle" butonuna tıklanınca açılır; "💾 Kaydet"e
basınca (veya "✅ Bitti" ile) otomatik kapanır. Bu mod kalıcı DEĞİL —
sayfa her açıldığında normal görünümle başlar (Görünüm seçici hariç,
o zaten salt-gezinme). `DashboardGrid.test.tsx`'e 2 yeni test (araç
çubuğu "Düzenle"den önce gizli; kaydedince kapanıyor), mevcut 2 test
"Düzenle"ye tıklamayı içerecek şekilde güncellendi. Frontend 424→426
test (`tsc`/`eslint` temiz). Backend'e dokunulmadı, restart gerekmiyor.

Faz 32/40 sonrası bir UX sadeleştirmesi de tamamlandı — kullanıcı
canlı Ayarlar ekran görüntüsüyle bildirdi: `AgentDownloadPanel.tsx`'teki
düz CLI EXE indirmesi ("Agent İndir" / "Windows Agent (.exe) İndir",
`GET /api/agents/download/windows/info`) panelden KALDIRILDI — Faz
40'ın Windows Servisi Paketi (KALICI servis + kurulum script'leri,
`.zip`) zaten AYNI EXE'yi kapsayarak daha eksiksiz bir kurulum sunuyor,
bu yüzden iki seçenek sunmak yerine tek panelde yalnızca servis paketi
bırakıldı. **Backend endpoint'i kaldırılmadı** (`GET /api/agents/
download/windows` hâlâ çalışıyor, yalnızca panelden bağlantısı
kesildi) — ileride geri eklenebilir. `AgentDownloadPanel.test.tsx`
yalnızca servis paketini test edecek şekilde sadeleştirildi (6→4
test). Frontend 427→424 test (`tsc`/`eslint` temiz). Backend'e
dokunulmadı, restart gerekmiyor — `next dev` HMR ile canlıda anında
doğrulandı.

Faz 29.5 sonrası bir UI iyileştirmesi de tamamlandı — kullanıcı bir
ekran görüntüsüyle bildirdi: SNMP Yapılandırması tablosundaki "Atanmış
Cihazlar" hücresi yalnızca bir SAYI gösteriyordu, hangi cihaz(lar)
olduğu görünmüyordu. Zaten var olan `GET /api/snmp/profiles/{id}/
assets` (Faz 29.5) ve `fetchAssetsForSnmpProfile()` (`lib/api.ts`)
hiçbir UI'ya bağlı DEĞİLDİ — yeni bir backend endpoint'i AÇILMADI,
yalnızca `SnmpConfigurationCenter.tsx` bu mevcut endpoint'e bağlandı.
Atanmış asset'i olan (>0) her profil için sessizce (hata durumunda
sayıya düşerek) `fetchAssetsForSnmpProfile()` çağrılıyor, sonuç
`hostname || ip_address` etiketiyle `/topology?ip=<gerçek asset IP'si>`
adresine giden bir link listesi olarak gösteriliyor — mevcut
`AssetDetails.tsx`'in "Topolojide Göster" deep-link deseniyle (Faz 20)
AYNI. `SnmpConfigurationCenter.test.tsx`'e yeni bir test eklendi
(link'lerin doğru `href`'e sahip olduğunu ve sayı görünümünün artık
gösterilmediğini doğruluyor). Frontend 425 test (`tsc`/`eslint`
temiz). Backend'e dokunulmadı, restart gerekmiyor — `next dev` HMR ile
canlıda doğrulandı: gerçek FortiGate (`PSL-HQ-70G-1.alb.local`) ve
gerçek bir Windows Agent (`WIN-G4E9UGRTH8E`) profillerinde link'ler
doğru gerçek IP'lere gidiyor, tıklanınca doğru asset drawer'ı açıyor.

## Faz 72 — vCenter / vSphere Sanallaştırma İzleme ve Yönetim Modülü

**Amaç:** Kullanıcının gerçek bir VMware vCenter/vSphere ortamındaki
ESXi host'ları ve sanal makineleri (VM) platform içinden görüntülemek,
temel güç işlemlerini (start/stop/reboot) yapmak ve bir VM'den doğrudan
bir bilet açabilmek.

**Kullanıcı kararları (`AskUserQuestion` ile onaylandı):**
- **İstemci: vCenter REST API** (pyVmomi/SOAP DEĞİL) — `httpx` (proje
  zaten bağımlı, YENİ kütüphane EKLENMEDİ) ile `/api/session` (token
  bazlı oturum) + `/api/vcenter/vm`, `/api/vcenter/host`,
  `/api/vcenter/datastore` uç noktaları.
- **Gerçek bir vCenter ortamı var** — kod tamamlanınca kullanıcıdan
  bağlantı bilgileri istenip gerçek E2E yapılacak (SMTP/LDAP fazlarıyla
  AYNI sıra: önce kod+mock test, sonra canlı doğrulama).
- **Yetki: yeni `VCENTER_VIEW`/`VCENTER_ADMIN` izinleri** (Faz 47'nin
  ince taneli izin sistemi) — görüntüleme ayrı, güç işlemleri ayrı
  izin. `VCENTER_VIEW` diğer `*_VIEW` izinleriyle AYNI şekilde HER
  kullanıcıya varsayılan (bir kerelik backfill, Faz 62 `TICKETS_VIEW`
  ile AYNI desen); `VCENTER_ADMIN` yalnızca `ADMIN` rolüne varsayılan
  (`ALL_PERMISSIONS`'ın parçası olduğu için otomatik), OPERATOR/VIEWER
  için Admin panelinden elle açılabilir.

**Bilinçli sapmalar / dürüstlük sınırları:**
- **`/api/v1/...` YOK** — proje hiç versiyonlu URL kullanmadı, kullanıcı
  spec'indeki `/api/v1/endpoints/vcenter.py` YERİNE `app/routes/
  vcenter.py` → `/api/vcenter/*` (mevcut `app/routes/ldap_settings.py`
  → `/api/settings/ldap` deseniyle aynı ilke).
- **Anlık CPU %/RAM % tüketimi — DÜRÜST SINIR:** vCenter REST
  Inventory API'si (`/api/vcenter/vm/{vm}`) yalnızca KAYNAK TAHSİSİNİ
  (vCPU sayısı, RAM MB) döner — gerçek ANLIK kullanım yüzdesi
  `Performance Manager` (yalnızca SOAP/pyVmomi'de var) veya vROps
  gerektirir, kullanıcı REST API'yi seçtiği için bu fazda YOK. CLAUDE.md
  ilkesiyle (asla veri uydurma) tutarlı olarak bu alanlar `null`/"Veri
  yok" döner — SNMP CPU/Bellek'in HOST-RESOURCES-MIB desteklemeyen
  cihazlarda `None` dönmesiyle AYNI dürüstlük ilkesi. IP adresi/OS/
  hostname `guest/identity` REST uç noktasından (VMware Tools
  çalışıyorsa) GERÇEK gelir.
- **VM detay grafik geçmişi YOK** (spec'in "grafik kartlarında"
  ifadesi anlık bir değer kartı olarak yorumlandı — geçmiş zaman
  serisi için ayrı bir depolama/poll döngüsü gerekir, ayrı faza
  bırakıldı).
- **Datastore doluluk** `/api/vcenter/datastore` özetinden (kapasite/
  serbest alan) GERÇEK — uydurma yok.
- Bilet açma: mevcut `CreateTicketModal.tsx`/`POST /api/tickets`
  AYNEN reuse edilir (VM adı/ID başlık veya açıklamaya ön-doldurulur,
  yeni bir alan/tablo EKLENMEZ — Faz 63'ün cihaz alanını kaldırma
  kararıyla tutarlı, serbest metin olarak açıklamaya eklenir).

**Kapsam:**
1. **Şema:** `vcenter_config` — tek satırlık yapılandırma
   (`ldap_config`/`smtp_config` ile AYNI desen): `host`, `port`
   (varsayılan 443), `username`, `encrypted_password` (`app/pam/
   vault.py::encrypt_payload`/`decrypt_payload` ile AYNI Fernet anahtarı
   — YENİ anahtar EKLENMEZ), `verify_ssl` (varsayılan `false` — çoğu
   iç vCenter kendinden imzalı sertifika kullanır, LDAP'ın `use_ssl`
   alanıyla aynı dürüst varsayılan), `last_test_status`/`last_test_
   error`, `updated_at`.
2. **Backend:** `app/services/vcenter_service.py` — `httpx.AsyncClient`
   ile oturum aç (`POST /api/session`, temel kimlik doğrulama), token'ı
   `vmware-api-session-id` header'ında sonraki isteklerde kullan, testte
   session'ı `DELETE /api/session` ile kapat. `list_vms`/`list_hosts`/
   `list_datastores`/`get_vm_detail`/`power_action(vm_id, action)`.
   `app/routes/vcenter.py` → `/api/vcenter/*`:
   - `GET /api/vcenter/summary` (`VCENTER_VIEW`) — toplam host/VM/vCPU/
     RAM tahsisi/datastore özet.
   - `GET /api/vcenter/vms` (`VCENTER_VIEW`).
   - `GET /api/vcenter/hosts` (`VCENTER_VIEW`).
   - `POST /api/vcenter/vms/{vm_id}/power` (`VCENTER_ADMIN`, body
     `{action: start|stop|reset}`) — gerçek REST çağrısı, başarısızlıkta
     dürüst hata (SNMP/LDAP "test connection" ilkesiyle AYNI: bağlantı
     hatası ayrı, işlem reddi ayrı mesaj).
   - `/api/settings/vcenter` (`VCENTER_ADMIN`) — `GET`/`PUT` config +
     `POST .../test` (`ldap_settings.py`'nin `_resolve_encrypted_
     password` boş-parola-koruma deseniyle AYNI).
3. **Frontend:** `lib/api.ts` (tipler + fonksiyonlar), Sidebar'a KEŞİF
   grubu altına `☁️ vCenter / vSphere` (`/vcenter`, `VCENTER_VIEW`
   gerektirir — `RequirePermission` ile), `app/vcenter/page.tsx`, yeni
   `components/vcenter/{VCenterSummaryCards,VMListTable,VMDetailModal,
   VCenterConfigPanel}.tsx`. `VCenterConfigPanel.tsx` Ayarlar'a
   `SmtpConfigurationCenter`/`ScheduledScansPanel` ile AYNI ADMIN-only
   bölüm deseninde eklenir. Mevcut 4 tema (Faz 59) ile CSS Modules
   token'larıyla uyumlu — Tailwind/Shadcn EKLENMEZ (proje hiç
   kullanmadı). VM Detay Modalı'ndan "🎫 Arıza/Talep Bileti Aç" mevcut
   `CreateTicketModal`'ı VM bilgisi ön-dolu açar.

**Kapsam dışı:** pyVmomi/SOAP Performance Manager (gerçek anlık CPU/RAM
%), zaman serisi grafik geçmişi, VM klonlama/snapshot/migrate, resource
pool/cluster DRS görünümü, vCenter olay/alarm senkronizasyonu.

**Testler:** `test_vcenter_settings_api.py` (config CRUD + test-connection,
`httpx` mock transport ile — gerçek vCenter olmadan), `test_vcenter_
service.py` (`list_vms`/`power_action` mock response'larla), `test_
vcenter_api.py` (route yetkilendirme: `VCENTER_VIEW` yeterli/yetersiz,
power işlemi `VCENTER_ADMIN` gerektirir). Frontend `VMListTable.test.tsx`
+ `VCenterConfigPanel.test.tsx` (fetch mock).

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz. Canlı deployment ve gerçek vCenter'a karşı E2E kullanıcı
onayıyla ayrıca — kullanıcıdan gerçek bağlantı bilgileri istenecek.

**Gerçekleşen:** Plan birebir uygulandı. `app/vcenter/{models,client,
service}.py` + `app/db/vcenter.py` + `app/routes/{vcenter,vcenter_
settings}.py`. `client.py::VCenterSession` gerçek `httpx.AsyncClient`
ile `POST /api/session` (Basic auth) → `vmware-api-session-id` header'ı
→ `DELETE /api/session`; test edilebilirlik için opsiyonel `transport`
parametresi eklendi (üretimde HİÇ geçilmez, yalnızca `httpx.
MockTransport` ile testler kullanır). `service.py::list_vms` guest IP'yi
(`guest/identity`) `asyncio.Semaphore(8)` ile sınırlı eşzamanlı çözer
(SNMP `poller.py`'nin `SNMP_MAX_CONCURRENCY` ilkesiyle AYNI) — VMware
Tools çalışmıyorsa (404) dürüstçe `ip_address=None`. `VCenterSummary`/
`VmDetail` dürüstlük sınırı KORUNDU: `cpu_usage_percent`/`memory_
usage_percent` HER ZAMAN `None` (REST Inventory API'de yok, uydurulmadı
— frontend'de de açık bir not olarak gösteriliyor). Yeni `VCENTER_VIEW`/
`VCENTER_ADMIN` izinleri (`app/auth/permissions.py`) — `VCENTER_VIEW`
`TICKETS_VIEW` ile AYNI "her kullanıcıya bir kerelik backfill" deseni
(`main.py::_ensure_vcenter_permission_backfill`), `VCENTER_ADMIN`
yalnızca `ADMIN` rolüne (`ALL_PERMISSIONS`) varsayılan. `vcenter_config`
tablosu `ldap_config`/`smtp_config` ile AYNI tek-satır desen, parola
`app.pam.vault` Fernet'iyle şifreli. Frontend: `lib/api.ts` (tipler +
9 fonksiyon), `Sidebar.tsx`'e KEŞİF grubuna "☁️ vCenter / vSphere"
(`VCENTER_VIEW`), `app/vcenter/page.tsx` (`RequirePermission`), yeni
`components/vcenter/{VCenterPanel,VCenterSummaryCards,VMListTable,
VMDetailModal,VCenterConfigPanel,vcenterBadges}`. `VCenterConfigPanel`
LDAP/SMTP merkezleriyle AYNI görsel dili (`LdapConfigurationCenter.
module.css` reuse) kullanıyor, Ayarlar'a yalnızca `VCENTER_ADMIN`
izniyle görünüyor. "🎫 Arıza/Talep Bileti Aç" mevcut `CreateTicketModal`'ı
(yeni opsiyonel `initialTitle`/`initialDescription` prop'larıyla, başka
çağrı noktası ETKİLENMEDİ) VM adı/ID ön-dolu açıyor — yeni alan/tablo
EKLENMEDİ. `VCenterPanel` backend `409` (yapılandırılmamış) yanıtını
GERÇEK bir bağlantı denemesi yapmadan dürüst bir "yapılandır" mesajına
çeviriyor (`ApiError.status` ile, string-eşleştirme DEĞİL). Backend
708→741 test (33 yeni: client 5 + service 10 + settings 9 + api 9),
frontend 426→434 test (`tsc`/`eslint` temiz). **Canlı deployment
YAPILMADI** — `vcenter_config` tablosu ve `VCENTER_VIEW` backfill'i bir
sonraki restart'ta kurulur; kullanıcı gerçek vCenter bağlantı
bilgilerini verdiğinde canlı E2E yapılacak.

## Faz 73 — vCenter Paneli: Enterprise UI/UX Yükseltmesi

**Amaç:** Faz 72'nin temel vCenter panelini kullanıcının "Enterprise
seviye" spesifikasyonuna göre zenginleştirmek — sistem VM filtresi,
gerçek guest OS adı, tablo aksiyon sütunu (güç dropdown'u + bilet),
datastore renk eşikleri, görsel hiyerarşi.

**Kullanıcı kararları (`AskUserQuestion` ile onaylandı):**
- **Anlık CPU/RAM kullanım YÜZDESİ EKLENMİYOR** — vCenter REST
  Inventory API'sinde bu veri yok (yalnızca SOAP/Performance Manager'da
  var, kullanıcı REST'i açıkça seçmişti). Kullanıcı "yalnızca tahsis
  göster"i onayladı — CLAUDE.md'nin "asla veri uydurma" ilkesi
  korundu. `vCPU/RAM` sütunu renkli bir "Tahsis" rozetine dönüşüyor,
  yüzde YOK.
- **Web VNC/MKS Konsolu bu increment'e DAHİL EDİLMİYOR** — kullanıcı
  onayıyla ayrı bir faza bırakıldı (Faz 48 guacd/RDP'ye benzer boyutta
  bir mimari/güvenlik yükü — ESXi host'a doğrudan WebSocket bağlantısı,
  ayrı sertifika/port yönetimi gerektirir).

**Kapsam:**
1. **vCLS filtresi (frontend):** `VMListTable.tsx` adı `vCLS-` ile
   başlayan VM'leri (VMware'in kendi cluster-servisi altyapı VM'leri —
   gerçek, kullanıcının kendi VM'i değil) varsayılan listeden ayırıp
   "Sistem VM'leri" toggle'ının arkasına alır. Backend değişmiyor —
   filtre saf frontend, `service.py::list_vms` TÜM VM'leri döndürmeye
   devam ediyor (dürüstlük: hiçbir VM backend'den GİZLENMİYOR, yalnızca
   varsayılan görünüm süzülüyor).
2. **Gerçek guest OS adı (backend):** `service.py::list_vms` artık her
   VM için (zaten `_fetch_guest_ip` ile açılmış olan) `guest/identity`
   yanıtından `full_name`'i de okuyup `VmSummary.guest_os`'a VMware
   Tools'un raporladığı GERÇEK adı (ör. "Microsoft Windows Server
   2022") yazıyor; Tools yoksa/identity başarısızsa mevcut config'teki
   statik `guest_OS` tanımlayıcısına (ör. `windows9Server64Guest`)
   dürüstçe düşüyor — YENİ bir alan YOK, `guest_os` aynı sözleşmede
   daha doğru bir değer taşıyor.
3. **Datastore renk eşikleri:** `VCenterSummaryCards.tsx` eşikleri
   kullanıcının istediği `<%70` (normal) / `%70-85` (uyarı) / `>%85`
   (tehlike) değerlerine güncelleniyor (önceki 75/90'dan).
4. **Tablo Aksiyon sütunu:** `VMListTable.tsx`'e yeni "İşlemler" sütunu
   — `⚡ Güç` (dropdown: Başlat/Durdur/Sıfırla/Guest Yeniden Başlat) +
   `🎫 Bilet Aç` (VM adı+IP ön-dolu `CreateTicketModal`, detay
   modalındaki AYNI prop'lar). Mevcut VM Detay Modalı'ndaki güç
   butonları KALDIRILMIYOR (aynı işlevi tekrarlıyor, kullanıcı ikisini
   de kullanabilir).
5. **Guest Yeniden Başlat (backend, additive):** `PowerAction`'a yeni
   `"guest_reboot"` değeri — vCenter REST'in AYRI "guest OS işlemleri"
   uç noktasını (`POST /vcenter/vm/{vm}/guest/power?action=reboot`,
   VMware Tools gerektirir — sert `power/reset`'ten FARKLI, graceful)
   çağırır. `service.py::power_action` action tipine göre doğru path'i
   seçer; `VCENTER_ADMIN` yetkisi AYNI kalıyor.
6. **Görsel hiyerarşi:** `VCenterPanel.module.css`'e kart arası dikey
   ayırıcılar + tutarlı boşluk — mevcut CSS değişkenleri (`--border-
   subtle` vb.) ile, yeni bir tema/renk paleti EKLENMEDEN 4 mevcut
   temayla (Faz 59) uyumlu.

**Kapsam dışı:** Anlık CPU/RAM %, Web VNC/MKS konsolu (yukarıda
gerekçelendirildi), vCLS VM'lerinde güç işlemi (varsayılan filtrede
zaten gizli, "Sistem VM'leri" sekmesinden erişilebilir ama UI'da ayrı
bir kısıtlama YOK — gerçek yetkilendirme zaten `VCENTER_ADMIN`).

**Testler:** Backend `test_vcenter_service.py`'ye guest OS full_name +
`guest_reboot` path testleri, `test_vcenter_api.py`'ye `guest_reboot`
action testi. Frontend `VCenterPanel.test.tsx`'e vCLS filtreleme +
aksiyon sütunu testleri.

**Tamamlanma kriterleri:** Backend/frontend testleri geçer, `tsc`/
`eslint` temiz. Backend değişikliği (yeni `guest_reboot` action +
guest OS full_name okuma) additive — canlıya kullanıcı onayıyla ayrıca.

**Gerçekleşen:** Plan birebir uygulandı — `VMListTable.tsx` (vCLS
filtresi + "Sistem VM'leri" toggle, "İşlemler" sütunu: güç `<select>`'i
+ 🎫 bilet butonu, satır bazlı hata mesajı), `VCenterSummaryCards.tsx`
(70/85 eşikleri), `VMDetailModal.tsx`'e "Guest Yeniden Başlat" butonu,
`VCenterPanel.module.css`'e KPI şeridi dikey ayırıcıları
(`border-left`, tek kutulu şerit — ayrı kartlar değil). `CreateTicketModal`
artık VM'in gerçek IP'sini de açıklamaya ekliyor
(`ticketPrefillDescriptionWithIp`). Backend `service.py::power_action`
`guest_reboot`'u AYRI `POST /vcenter/vm/{vm}/guest/power?action=reboot`
uç noktasına yönlendiriyor (sert `power/reset`'ten farklı).

**GERÇEK bir vCenter'a karşı canlı E2E'de bulunup düzeltilen kritik bir
hata:** `guest/identity.full_name` düz bir string DEĞİL, vSphere REST
API'sinin `LocalizableMessage` yapısı (`{id, default_message, args}`)
olarak geliyor — özellikle vCLS/CRX sistem VM'lerinde KESİN olarak
(muhtemelen normal guest'lerde de aynı sözleşme). Bu, `VmSummary`
(Pydantic `str` alanı) bir dict ile karşılaşınca `ValidationError`'a
düşüp **`GET /api/vcenter/vms` ve `/summary`'yi TAMAMEN 500'e
çeviriyordu** — mock testler bunu YAKALAYAMAMIŞTI (mock'ta `full_name`
hep düz string verilmişti). `service.py::_extract_full_name()` eklendi
— `localized`/`default_message` alanlarını dürüstçe çözüyor, ikisi de
yoksa `None`. Yeni bir regresyon testi (`test_list_vms_extracts_full_
name_from_localizable_message_object`) bu senaryoyu kilitliyor. Backend
741→755 test (14 yeni: service 10→14 + api 9→10 — toplamda Faz 72+73
33→37), frontend 434→437 test (`tsc`/`eslint` temiz). **Gerçek E2E
(kullanıcının kendi vCenter'ı, canlı backend):** kullanıcı Ayarlar'dan
gerçek bağlantı bilgilerini girip kaydetti; düzeltme sonrası `/vcenter`
sayfası **14 gerçek VM** (gerçek IP'ler: `10.0.213.x` serisi, gerçek
guest OS adları: "Ubuntu Linux (64-bit)", "Microsoft Windows Server
2025 (64-bit)", "VMware Photon OS (64-bit)"), **2 gerçek ESXi host**,
**4 gerçek datastore** (LUN01/LUN02/datastore1×2, gerçek doluluk
yüzdeleriyle) gösterdi; "Sistem VM'leri (vCLS) (2)" sekmesi 2 gerçek
vCLS VM'ini doğru ayırdı; bir VM'in ("Veeam") detay modalı gerçek
IP/hostname/OS/tahsis gösterip dürüstlük notunu doğru bastı; "🎫
Arıza/Talep Bileti Aç" gerçek VM adı+IP+ID ile bilet formunu doğru
ön-doldurdu. Güç işlemleri (gerçek bir VM'i kapatmak) paylaşımlı canlı
ortamda KASITLI denenmedi.

## Faz 74 — PAM RDP: Çift Yönlü Pano + Sürücü Yönlendirme (Dosya Transferi)

**Amaç:** Web tabanlı RDP oturumunda (Faz 48) dosya yükleme (tarayıcı
→ uzak sunucu) ve panonun iki yönde de çalışması.

**Bilinçli sapmalar/netleştirmeler:**
- **`drive-path: "/var/pam/drives/${GUAC_USERNAME}"` (kullanıcının
  önerdiği) KULLANILMADI** — guacd'nin `${GUAC_USERNAME}` gibi bir
  değişken ikamesi YOK (bu proje guacd'ye ham `connect` instruction'ı
  gönderiyor, resmi `guacamole-client` webapp'ının XML-tabanlı bağlantı
  şablonlama motorunu hiç kullanmıyor — Faz 48 kararı). Bunun yerine
  Python tarafında GERÇEKTEN benzersiz bir dizin üretilir:
  `{GUACD_DRIVE_PATH}/{session_id}` — Faz 50'nin `recording-name`
  deseniyle AYNI (oturum UUID'si zaten var, çakışma yapısal olarak
  imkansız).
- **Tam bir uzak dosya YÖNETİCİSİ (dizin gezme + indirme) bu artırıma
  DAHİL DEĞİL** — Guacamole filesystem protokolü dizin listeleme için
  ayrı bir `requestInputStream`/JSON-gövdeli mesajlaşma gerektiriyor;
  kullanıcının istediği "Dosya Transferi sekmesi" YALNIZCA YÜKLEME
  (tarayıcıdan sürükle-bırak + buton) + yükleme geçmişi/durumu olarak
  daraltıldı — indirme (uzaktan tarayıcıya) ayrı bir artırıma
  bırakıldı.
- **GPO notu** kod DEĞİL, yalnızca bu bölümde ve `docs/decisions.md`'de
  belgeleniyor — hedef Windows sunucularda Drive/Clipboard Redirection
  GPO'larının "Not Configured"/"Disabled" olması gerektiği.

**Kapsam:**
1. **Backend (`app/pam/guacd.py`):** `recording_config()` ile AYNI
   desende yeni `drive_config()` — `GUACD_DRIVE_PATH` env'i yoksa sürücü
   yönlendirme SESSİZCE devre dışı (opt-in, mevcut iki-anahtarlı
   ilkeyle tutarlı — burada tek anahtar, çünkü backend'in kendisi bu
   dizine hiç erişmiyor, yalnızca guacd/RDP erişiyor). `_perform_
   handshake`'in `known_values`'ına `enable-drive`/`drive-path`
   (`{GUACD_DRIVE_PATH}/{session_id}`)/`drive-name` ("PAM Paylaşılan
   Sürücü")/`create-drive-path: true` + HER ZAMAN açıkça `disable-copy:
   false`/`disable-paste: false` (guacd sürüm varsayımına bırakılmadı —
   `security: nla` kararıyla AYNI ilke).
2. **`infra/docker-compose.yml`:** `guacd` servisine ikinci bir bind
   mount — `../apps/api/logs/pam-drives:/var/pam/drives` (recordings
   mount'uyla AYNI desen). `.env.example`'a `GUACD_DRIVE_PATH`.
3. **Frontend (`GuacamoleRdpViewer.tsx`):**
   - `client.onclipboard` handler eklenir — uzak oturumda kopyalanan
     metni `Guacamole.StringReader` ile okuyup `navigator.clipboard.
     writeText()`'e yazmayı DENER (tarayıcı izin politikası bazı
     bağlamlarda bunu reddedebilir — sessizce yutulur, "Panoyu Gönder"
     butonunun YANINA gelen bu yeni davranış onu BOZMAZ).
   - `client.onfilesystem` handler eklenir — sürücü paylaşılınca
     `Guacamole.Object`'i saklar.
   - Sürükle-bırak alanı (canvas üzerine dosya bırakma) + "📁 Dosya
     Yükle" araç çubuğu butonu (gizli `<input type=file>` tetikler) —
     `object.createOutputStream` + `Guacamole.BlobWriter` ile GERÇEK
     bayt akışı, ilerleme/başarı/hata Toast'ları.
   - Küçük bir "Dosya Transferi" paneli — son yüklemelerin listesi
     (ad + durum), araç çubuğuna yeni bir 📁 toggle butonuyla açılır.

**Kapsam dışı:** Uzaktan indirme/dizin gezme, ses/video redirection
(Faz 48'in zaten kapsam dışı bıraktığı), yazıcı redirection.

**Testler:** `tests/pam/test_guacd_handshake.py`'ye — `drive_config()`
ayarlıyken `connect` instruction'ının `enable-drive`/`drive-path`/
`disable-copy`/`disable-paste` değerlerini doğru taşıdığını, AYARLI
DEĞİLKEN sürücü alanlarının boş kaldığını (ama `disable-copy`/`disable-
paste` hâlâ `false` olduğunu) doğrulayan testler. `GuacamoleRdpViewer.
tsx`'e component testi AÇILMAZ (Faz 48/53 kararıyla AYNI gerekçe —
canvas+WebSocket+3.parti kütüphane mock'lamak orantısız).

**Tamamlanma kriterleri:** Backend testleri geçer, `tsc`/`eslint`
temiz. Gerçek guacd'ye karşı canlı E2E (dosya gerçekten sürüklenip
RDP oturumundaki "Bu Bilgisayar"da göründüğü) kullanıcı onayıyla
ayrıca — Docker/guacd bu ortamda zaten Faz 48'de kalıcı çalışıyor.

**Gerçekleşen:** Plan birebir. `app/pam/guacd.py::drive_config()`
(`recording_config()` deseni, tek env — backend dosyayı kendi
tarafından okumuyor) + `_perform_handshake`'e `enable-drive`/
`drive-path` (`{GUACD_DRIVE_PATH}/{session_id}`)/`create-drive-path`/
`drive-name` + HER ZAMAN açık `disable-copy: false`/`disable-paste:
false`. `infra/docker-compose.yml`'e `pam-drives` bind mount,
`.env.example`'a `GUACD_DRIVE_PATH`. Frontend `GuacamoleRdpViewer.tsx`:
`client.onfilesystem` (paylaşılan sürücüyü saklar) + `client.
onclipboard` (`Guacamole.StringReader` ile uzak panoyu okuyup
`navigator.clipboard.writeText()`'e YAZMAYI DENER, reddedilirse
sessizce yutulur) + sürükle-bırak alanı/buton ile GERÇEK bayt akışı
(`Guacamole.Object.createOutputStream` + `Guacamole.BlobWriter`) +
yükleme durumu gösteren "Dosya Transferi" paneli. `docs/decisions.md`
§20 — hedef sunucudaki GPO gereksinimi (kod DEĞİL, belge notu).
Backend 741→755 (Faz 72/73'ten sonra) → 10 yeni guacd handshake testi
(3 drive senaryosu + mevcutların regresyonsuz geçmesi). `tsc`/`eslint`
temiz, `GuacamoleRdpViewer.tsx`'e component testi Faz 48/53 kararıyla
AYNI gerekçeyle AÇILMADI. **Canlı deployment YAPILMADI** —
`disable-copy`/`disable-paste` düzeltmesi ve idle-gaps route'u şema
gerektirmiyor (kod-only restart yeterli), ama `GUACD_DRIVE_PATH`
kullanıcının kendi `.env`'ine eklemesini bekliyor (opt-in, eklenmezse
sürücü paylaşımı sessizce kapalı kalır — mevcut RDP akışı ETKİLENMEZ).

## Faz 75 — PAM Oturum Kaydı: İnaktif Süre Atlama (Replay Optimizasyonu)

**Amaç:** Kayıt oynatmada uzun hareketsiz aralıkları otomatik atlayıp
izlemeyi hızlandırmak.

**Bilinçli düzeltme (kullanıcının spesindeki yanlış varsayım):**
Kullanıcının istediği "guacd tünel/kayıt yapılandırmasında inaktivite
timeout/suppression parametresi" **GERÇEKTE YOK** — Guacamole protokolü
zaten olay-güdümlü (yalnızca ekranda GERÇEK bir değişiklik/tuş/fare
olayı olduğunda instruction gönderilir/kaydedilir, `sync` heartbeat'i
hariç); guacd'de böyle bir config anahtarı bulunmuyor, UYDURULMADI.
Aynı şekilde madde 3'teki `guacenc`/`ffmpeg` MP4 dönüştürme post-
processing'i bu projede HİÇ YOK (Faz 50 kararı: kayıt `.guac` formatında
kalıyor, MP4'e dönüştürülmüyor) — `mpdecimate` parametresi eklenecek
bir boru hattı mevcut değil, bu madde bu increment'e dahil edilmedi.
Bunun yerine GERÇEKTEN teslim edilebilir eşdeğer: kaydın KENDİSİNDEKİ
gerçek `sync` zaman damgalarından inaktif aralıkları çıkarıp oynatma
sırasında bunları atlamak — Faz 53'ün `extract_activity_markers`'ı ile
AYNI, veri UYDURMAYAN yöntem.

**Kapsam:**
1. **Backend (`app/pam/recording_analysis.py`):** yeni
   `extract_idle_gaps(file_path, min_gap_ms=3000)` — `key`/`mouse`/ekran
   güncelleme instruction'ları arasında `min_gap_ms`'den uzun süren
   gerçek boşlukları `{start_ms, end_ms}` listesi olarak döner (YENİ
   veri yok, yalnızca kayıttaki gerçek `sync` zaman damgaları
   yorumlanıyor). `GET /api/pam/audit/{id}/idle-gaps` (`PAM_ADMIN`,
   Faz 53'ün `activity-markers` route'uyla AYNI desen — kayıt yoksa
   boş liste, 404 değil).
2. **Frontend (`SessionReplayModal.tsx`):** idle-gap'ler zaman
   çubuğunda soluk bir bant olarak gösterilir; "İnaktif Süreleri Atla"
   checkbox'ı (varsayılan AÇIK) — oynatma döngüsü (`tick()`) bir
   sonraki hedef bir boşluğun içine düşerse hedefi doğrudan boşluğun
   bitişine (`gap.end_ms`) sıçratır (`virtualPositionRef` zaten Faz
   73'ün kare-hizalı-olmayan hedef takibini kullanıyor — bu değişiklik
   onu YENİDEN YAZMIYOR, yalnızca hedefi ayarlıyor).

**Kapsam dışı:** guacd/protokol seviyesinde kayıt boyutu küçültme
(madde 1 — böyle bir mekanizma yok), `.guac`→MP4 dönüştürme/
`mpdecimate` (Faz 50 kararı korunuyor, proje MP4'e hiç dönüşmüyor).

**Testler:** `tests/pam/test_recording_analysis.py` (varsa genişletilir,
yoksa yeni) — sahte bir `.guac` akışıyla `extract_idle_gaps`'in
GERÇEK sync zaman damgalarından doğru boşlukları çıkardığını, kısa
boşlukları (eşik altı) atladığını doğrular. Frontend `SessionReplayModal`
component testi AÇILMAZ (Faz 53 kararıyla AYNI gerekçe).

**Tamamlanma kriterleri:** Backend testleri geçer, `tsc`/`eslint`
temiz. Gerçek bir kayıtla canlı doğrulama (uzun bir hareketsiz
aralığın gerçekten atlandığı) kullanıcı onayıyla ayrıca.

**Gerçekleşen:** Plan birebir. `app/pam/recording_analysis.py::
extract_idle_gaps()` — `_ACTIVITY_OPCODES` kümesi (`key`/`mouse` +
guacd'nin GERÇEK ekran çıktısı instruction'ları) arasındaki boşlukları
`sync` zaman damgalarından çıkarıyor, kaydın sonuna kadar süren son
boşluğu da (kullanıcı klavye/fareyi bırakıp ayrılırsa) dahil ediyor.
`GET /api/pam/audit/{id}/idle-gaps` (Faz 53 `activity-markers`'la AYNI
desen — kayıt yoksa boş liste). Frontend `SessionReplayModal.tsx`:
idle-gap'ler zaman çubuğunda soluk bant (`idleGapBand`), "İnaktif
Süreleri Atla" checkbox'ı (varsayılan AÇIK) — `tick()`'in hedefi bir
boşluğa düşerse `gap.end_ms`'e sıçratılıyor, Faz 73'ün
`virtualPositionRef` mekanizması YENİDEN YAZILMADI. Backend 14 yeni
test (`recording_analysis.py` 5 + `pam_audit_api.py` 3 route testi +
guacd handshake'ten ayrı) — tam paket 811 passed / 4 önceden bilinen,
kodla İLGİSİZ ortam hatası (paylaşımlı canlı DB'de gerçek `smtp_config`/
retention-policy satırları — Faz 39/66'dan beri belgeli desen).
Frontend `tsc`/`eslint` temiz, tam paket 437/437; `SessionReplayModal`
component testi Faz 53 kararıyla AYNI gerekçeyle AÇILMADI. **Canlı
deployment YAPILMADI** — şema gerektirmiyor (kod-only restart yeterli),
kullanıcı onayı bekliyor.

## Faz 76 — PAM Web Konsolu: Zero-Knowledge HTTPS Kimlik Enjeksiyonu

**Amaç:** Firewalla gibi yalnızca bir HTTPS web yönetim arayüzü olan
cihazlara, RDP/SSH'daki AYNI "zero-knowledge" ilkesiyle (kullanıcı
parolayı hiç görmez) tarayıcıdan erişim.

**Kullanıcı kararları (`AskUserQuestion` ile onaylandı):** Tam
zero-knowledge kimlik ENJEKSİYONU (basit "kullanıcı kendi parolasını
girsin" tüneli DEĞİL) + ilk sürüm yalnızca Firewalla; hedefin giriş
mekanizması **HTML kullanıcı adı/parola formu** (Basic Auth DEĞİL).

**Bilinçli sınır/dürüstlük notu:** Faz 61'in kasıtlı olarak ertelediği
tam da bu özellik — gerekçe hâlâ geçerli: genel bir HTTP(S) ters proxy
+ kimlik enjeksiyonu, RDP'nin guacd'si gibi HAZIR bir protokol
motoruna sahip DEĞİL, biz kendi yazıyoruz. **v1 kapsamı bilinçli
olarak dar tutuluyor:**
- Yanıt gövdesindeki `href="/`/`src="/`/`action="/` kök-göreli
  bağlantılar proxy önekine YENİDEN YAZILIYOR (regex tabanlı, best-
  effort) — ama JS'in KENDİ ürettiği (fetch/XHR ile çalışma zamanında
  oluşturulan) mutlak yollar YAKALANAMAZ. Karmaşık bir SPA'da bazı
  alt-kaynaklar/AJAX çağrıları KIRILABİLİR — bu GERÇEK bir sınır,
  gizlenmiyor.
- Giriş formunun alan adları (`username`/`password` input `name`
  öznitelikleri) ve olası gizli CSRF alanları **ADMIN tarafından
  yapılandırılır** (`pam_web_console_profiles`) — kod içine
  UYDURULMUŞ/varsayılan bir Firewalla şeması YAZILMIYOR, çünkü gerçek
  cihaza bakmadan bu alan adları bilinemez. Giriş sayfası önce GET
  edilip gizli input'lar (varsa) otomatik toplanır, sonra POST edilir.
- WebSocket tabanlı canlı güncelleme yapan bir konsol (ör. gerçek
  zamanlı trafik grafiği) bu artırımda desteklenmiyor — yalnızca
  düz HTTP istek/yanıt döngüsü.

**Kapsam:**
1. **Şema (additive):** `pam_web_console_profiles` (`asset_id` UNIQUE,
   `port` [varsayılan 443], `verify_ssl` [varsayılan false — çoğu
   cihaz kendinden imzalı sertifika], `login_path`, `username_field`,
   `password_field`). `pam_access_rules.allow_web` (BOOLEAN, `allow_rdp`/
   `allow_ssh` deseniyle AYNI). `pam_session_logs.protocol` CHECK'ine
   `'web'` eklenir.
2. **Backend:**
   - `app/pam/web_console.py` — `establish_session()`: GET login sayfası
     → gizli input'ları ayrıştır (basit regex, üçüncü parti HTML parser
     EKLENMEDİ) → kullanıcı adı/parola + gizli alanlarla POST → dönen
     cookie'leri sakla. `proxy_request()`: saklı cookie'lerle hedefe
     isteği yönlendirir, `Location` header'ını VE HTML gövdesindeki kök-
     göreli linkleri proxy önekine yeniden yazar.
   - `app/pam/web_console_sessions.py` — bellek-içi oturum kaydı
     (`session_registry.py`'nin RDP/SSH "kill" deseninden AYRI, daha
     basit bir sözlük — HTTP proxy'nin kendine özgü isteğe-bağlı
     modeline uyuyor), TTL kuralın `max_session_duration_mins`'ine
     bağlı.
   - `app/pam/service.py::authorize_web_session` (`authorize_rdp_
     session` deseni — `allow_web` kontrolü).
   - `app/routes/pam_web.py`: `POST /api/pam/web/{asset_id}/session`
     (oturum kurar, `pam_session_logs`'a `protocol='web'` yazar),
     `ANY /api/pam/web/proxy/{session_id}/{path:path}` (yönlendirme),
     `POST /api/pam/web/{session_id}/close`. Admin profil CRUD'u aynı
     dosyada, `PAM_ADMIN`.
3. **Frontend:** `AssetDetails.tsx`'e (Faz 61'in CLI/SSH butonunun
   yanına, yalnızca `device_type` `firewall`/`router` için) "🌐 Web
   Konsolu" butonu — `/pam/web/{assetId}` yeni sayfası bir `<iframe>`
   ile proxy'lenen oturumu gösterir. `PamRulesPanel.tsx`'e `allow_web`
   checkbox'ı. Yeni Admin-only `AssetWebConsoleProfilePanel.tsx` (asset
   detayında, SNMP profili yapılandırmasıyla AYNI yerde) — host/port/
   login_path/alan adları.

**Kapsam dışı:** WebSocket/canlı-güncelleme konsollar, tam SPA
uyumluluğu (JS'in çalışma zamanında ürettiği mutlak URL'ler), Firewalla
DIŞINDAKİ cihaz tipleri (ileride profil bazında genelleştirilebilir —
mimari zaten cihaza özgü değil, yalnızca UI'da ilk sürümde firewall/
router'a daraltıldı).

**Testler:** `app/pam/web_console.py` için sahte bir `httpx.MockTransport`
ile (gerçek bir Firewalla olmadan) login-akışı + cookie yakalama + link
yeniden yazma testleri. `pam_web.py` route yetkilendirme testleri
(`allow_web` olmadan 403, profil yoksa 404/409).

**Tamamlanma kriterleri:** Backend testleri geçer, `tsc`/`eslint`
temiz. **Gerçek Firewalla'ya karşı canlı E2E kullanıcı onayıyla ayrıca**
— giriş formunun gerçek alan adları ancak canlı denemeyle kesinleşir,
bu artırımda muhtemelen gerçek hatalar bulunup düzeltilecek (RDP/SNMP/
vCenter fazlarındaki AYNI desen).

**Gerçekleşen:** Plan birebir. `app/pam/web_console.py` (`extract_
hidden_fields`/`establish_session`/`proxy_request`/`rewrite_html_links`/
`rewrite_location_header`, test edilebilirlik için `vcenter/client.py`
ile AYNI opsiyonel `transport` parametresi) + `app/pam/web_console_
sessions.py` (bellek-içi, TTL'li, RDP/SSH'ın kalıcı-soket `session_
registry.py`'sinden BİLİNÇLİ olarak AYRI — HTTP proxy'nin isteğe-bağlı
modeline uyan basit bir sözlük) + `app/pam/service.py::authorize_web_
session` (`authorize_rdp_session` deseni + `WebConsoleNotConfiguredError`)
+ `app/routes/pam_web.py` (`POST .../session` normal `Authorization`
ile, `ANY .../proxy/{session_id}/{path}` OPAK `session_id`'nin kendisiyle
— `<iframe src>` özel header taşıyamadığı için RDP/SSH'ın JWT-query-
string ödünleşimiyle AYNI ilke; `X-Frame-Options`/`CSP` header'ları
proxy yanıtından KALDIRILIYOR ki kendi iframe'imiz engellenmesin). Şema:
`pam_access_rules.allow_web` (`allow_rdp`/`allow_ssh` ile AYNI yerde,
tüm SELECT/INSERT/UPDATE sorguları + `app/pam/models.py`'nin 4 ilgili
modeli + `app/db/pam.py`'nin 6 sorgu bloğu güncellendi), `pam_session_
logs.protocol` CHECK'i `'web'`i kapsayacak genişletildi (yeni
`SessionProtocol` tipi, mevcut `Protocol` — yalnızca ssh/rdp seçen erişim
talebi akışı için — DEĞİŞMEDİ), yeni `pam_web_console_profiles` tablosu.
Frontend: `AssetDetails.tsx`'e Faz 61'in CLI/SSH butonunun YANINA "🌐
Web Konsolu" butonu + yeni "Web Konsolu" sekmesi (`AssetWebConsoleProfilePanel.
tsx` — yalnızca `PAM_ADMIN` giriş formu alan adlarını yapılandırabilir),
`PamRulesPanel.tsx`'e `allow_web` checkbox'ı (oluşturma + düzenleme +
rozet), `MyAccessPanel.tsx`'e "🌐 Web Konsolu" rozeti/bağlantısı (RDP/SSH
ile AYNI yerde) — kullanıcının "PAM tarafında GUI olan her şeye AYNI
şekilde erişim" isteği bu üç ekranın hepsinde tutarlı şekilde
karşılandı. Yeni `/pam/web/{assetId}` sayfası (`PamWebConsoleViewer.tsx`)
`GuacamoleRdpViewer.tsx` ile AYNI koyu "session screen" görsel dilinde
bir `<iframe>` gösteriyor. Backend'e 20 yeni test (`tests/pam/test_web_
console.py` 11 + `tests/test_pam_web_api.py` 9) — ilgili PAM test
paketinin TAMAMI (132 test: mevcut kurallar/erişim talepleri/etiketler/
denetim + yeni web konsolu testleri) regresyonsuz geçti. Frontend 437→439
test (`tsc`/`eslint` temiz).
`GuacamoleRdpViewer`/`SessionReplayModal` kararlarıyla AYNI gerekçeyle
`PamWebConsoleViewer.tsx`'e component testi AÇILMADI (iframe+fetch
orkestrasyonu mock'lamak orantısız). **Canlı deployment YAPILMADI** —
yeni şema (`allow_web` kolonu + `pam_web_console_profiles` tablosu)
gerektiriyor; giriş formunun GERÇEK alan adları (Firewalla'nın kendi
HTML'i) ancak Admin panelinden gerçek cihaza bakılarak girilip GERÇEK
bir oturum başlatılarak (ayrı bir "Bağlantıyı Test Et" butonu bu
increment'te YOK — SNMP/LDAP/vCenter'ın aksine, "test" doğrudan "🌐 Web
Konsolu"nu açmaktır) doğrulanabilir — bu artırımda (RDP/SNMP/vCenter
fazlarındaki AYNI desenle) muhtemelen gerçek hatalar bulunup
düzeltilecek.

## Faz 77 — Bilet Sistemi: Gizli IT İç Notları + Hızlı Durum Aksiyonları

**Amaç:** Kullanıcının kurumsal helpdesk spesifikasyonunu mevcut Faz
62-69 mimarisine karşı denetleyip yalnızca GERÇEKTEN eksik olan
parçaları eklemek — departman/kategori bağlama (Faz 63), REQUESTER
RBAC'ı (Faz 65) ve SMTP entegrasyonu (Faz 66/66-tamamlama) zaten
tamamdı, YENİDEN YAZILMADI.

**Kapsam denetimi (spesin neyi zaten karşıladığı):** `/api/v1/...`
AÇILMADI (proje hiç kullanmadı); departman/kategori dinamik yönetimi
zaten Faz 63'te var; `created_by_user_id == current_user.id` REQUESTER
kısıtı zaten Faz 65'te `get_ticket_detail`/`add_comment`'te 403 olarak
var; SMTP host/port/kullanıcı/parola/from/TLS-SSL ayarları + "Test
E-Postası Gönder" zaten Faz 66/66-tamamlama'da `/settings`'te var.

**Gerçekten eksik olan (bu fazın kapsamı):**
1. `ticket_comments.is_internal` kolonu şemada duruyordu (Faz 64'ün
   geri alınmasından kalan) ama HİÇBİR kod ona referans vermiyordu —
   IT ekibinin (TECHNICIAN/ADMIN bilet rolü) REQUESTER'ın hiç
   göremeyeceği gizli notlar yazması artık gerçekten çalışıyor.
2. Detay modalına IT ekibi için üç hızlı aksiyon butonu ("Üzerime Al"/
   "Çözüldü İşaretle"/"Bileti Kapat") — YENİ bir backend endpoint'i
   AÇILMADI, mevcut `POST .../comments` (status/assigned_to alanları)
   doğrudan preset değerlerle çağrılıyor.

**Backend:** `app/tickets/models.py` — `TicketCommentCreateRequest.
is_internal: bool = False`, `TicketCommentResponse.is_internal: bool`.
`app/db/tickets.py::insert_comment` yeni `is_internal` parametresi
alıp kaydediyor; `list_comments(..., include_internal: bool)` —
`False` iken `is_internal = false` filtresi uyguluyor. `app/tickets/
service.py::get_ticket_detail` REQUESTER için (`include_internal=
_is_it_staff(actor)`) gizli notları YANITTAN TAMAMEN çıkarıyor (yalnızca
UI'da gizlemek DEĞİL — API seviyesinde). `add_comment` REQUESTER'dan
`is_internal=true` gelirse sessizce `False`'a zorluyor (savunma
katmanı — frontend zaten bu sekmeyi REQUESTER'a göstermiyor). Gizli
notlar bilet sahibine ASLA e-posta bildirimi tetiklemiyor (`_notify_
owner` çağrısı `not is_internal` koşuluyla korunuyor) — "created"/
"status_change"/"assignment" olayları her zaman görünür kalıyor
(zaman çizelgesi bütünlüğü bozulmadı).

**Frontend:** `TicketDetailModal.tsx` — IT ekibi görünce yanıt kutusunun
üstünde mevcut `.tabs`/`.tabButton`/`.tabButtonActive` deseniyle (Faz
41'den, KOPYALANMADI) iki sekme ("Kullanıcıya Yanıt" / "🔒 IT İç Not
(Gizli)"); gönderim `is_internal: replyTab === "internal"` taşıyor.
Zaman çizelgesinde gizli bir yorum turuncu (`--status-degraded`) sol
kenarlık + "🔒 Gizli İç Not" rozetiyle ayırt ediliyor. Başlığın altına
(yalnızca IT ekibi) mevcut `.actionsCell`/`.actionButton`/
`.actionButtonDanger` sınıflarıyla üç buton — zaten mevcut olan durum/
atama `<select>`'lerin YERİNE DEĞİL, YANINA (ikisi de kalıyor, hızlı
yol + ince ayar birlikte). Modal genişliği KÜÇÜLTÜLMEDİ — Faz 65'in
"tam ekranda çok dar" bugfix'i `min(1040px, 96vw)`'a çıkarmıştı,
kullanıcının istediği `max-w-3xl` (768px) o bugfix'i GERİ ALIRDI;
bilinçli sapma. Tailwind sınıfları (`w-full min-h-[100px] resize-y`)
KULLANILMADI — proje CSS Modules + inline style kullanıyor (Faz 65'te
zaten `width:100%`/`minHeight:120`/`resize:"vertical"` olarak
karşılanmıştı, değişmedi).

**Kapsam dışı:** Departman/kategori/SMTP — zaten var, dokunulmadı.

**Testler:** Backend `tests/test_tickets_api.py`'ye 3 yeni test (gizli
not REQUESTER'dan gizleniyor + e-posta tetiklemiyor, REQUESTER kendi
yorumunu gizli işaretleyemiyor, görünür yanıt hâlâ bildirim
tetikliyor) — 30/30 geçti. Frontend'e yeni `tests/TicketDetailModal.
test.tsx` (3 test — önceden bu component'in HİÇ testi yoktu) + tam
paket 439→442 test, `tsc`/`eslint` temiz.

**Tamamlanma kriterleri:** Karşılandı. **Canlı deployment YAPILMADI**
— `is_internal` kolonu zaten canlı şemada var (Faz 64 kalıntısı,
idempotent), bu yüzden şema göçü GEREKMİYOR; yalnızca backend/frontend
kod restart'ı yeterli, kullanıcı onayı bekleniyor.

## Faz 78 — Setup & Deployment: Bağımsız Kurulum Paketi

**Amaç:** Projeyi mevcut geliştirme ortamından (bu makinede native
`uvicorn`/`next dev` süreçleri + yarı-Dockerize `infra/docker-
compose.yml`) tamamen bağımsız olarak, sıfır bir şirket/sunucuya tek
komutla kurulabilir hale getirmek.

**Kullanıcı kararı (`AskUserQuestion` ile netleştirildi):** Spesifikasyon
Redis'i "oturum yönetimi ve e-posta kuyrukları için" istiyordu — proje
bunların HİÇBİRİNİ Redis'siz de yapmıyor DEĞİL, zaten hiç kullanmıyor
(oturumlar stateless JWT — Faz 46, e-posta zaten kuyruksuz ateşle-unut
— Faz 65/66). Kullanıcı "Redis'i EKLEME" seçeneğini onayladı — hiçbir
koda bağlı olmayan boş bir container CLAUDE.md'nin "gereksiz kaynak
ekleme" kuralını ihlal ederdi.

**Diğer bilinçli sapmalar (sormaya gerek kalmadan, proje mimarisinin
kendisinden kaynaklı):**
- **Alembic KULLANILMADI** — proje 78 faz boyunca hiç ORM/migration
  aracı kullanmadı (`docs/decisions.md`, `CLAUDE.md` — "ORM yok").
  "Migrasyon" adımı gerçekte YOKTUR: şema tek bir dosyadan (`infra/
  postgres/init.sql`) gelir ve `api` servisi başlarken KENDİSİ uygular
  (`app/main.py::_ensure_schema_once`, Faz 41'den beri var, GERÇEK
  kod). Deploy script'leri bu yüzden ayrı bir migrasyon adımı
  ÇALIŞTIRMAZ — servisleri ayağa kaldırmak yeterlidir.
- **Varsayılan Admin `admin/admin123` OLUŞTURULMADI** — tahmin
  edilebilir bir parola bu projenin JWT_SECRET_KEY/PAM_VAULT_SECRET_KEY
  için asla yapmadığı bir şey olurdu (ikisi de KASITLI olarak zayıf bir
  varsayılana düşmek yerine hata verir, bkz. Faz 46). Deploy script'leri
  kriptografik olarak güçlü, rastgele bir parola üretip BİR KEZ ekrana
  yazar; backend'in mevcut `_ensure_bootstrap_admin` mekanizması
  (`BOOTSTRAP_ADMIN_USERNAME`/`PASSWORD` env'i, `users` tablosu boşken
  tek seferlik) AYNEN kullanıldı — yeni bir "seed script" YAZILMADI.
- **`infra/docker-compose.yml` (yalnızca db+guacd, dev-destek dosyası,
  Faz 48'den) DEĞİŞTİRİLMEDİ** — kök dizinde YENİ, ayrı bir production
  `docker-compose.yml` (web+api+db+guacd) oluşturuldu. İki dosya
  KARIŞTIRILMAMALI: `infra/`'daki, backend/frontend'in bu makinede
  native process olarak çalıştığı GELİŞTİRME akışı için hâlâ geçerli;
  kök dizindeki, "sıfırdan bağımsız kurulum" için TÜM sistemi
  konteynerleştirir.

**Kapsam:**
1. **`apps/api/Dockerfile`** (çok aşamalı, `python:3.12-slim`) — build
   context REPO KÖKÜ olmalı, çünkü `app/db/assets.py::_SCHEMA_SQL_PATH`
   `infra/postgres/init.sql`'i `__file__`'dan GÖRELİ (`parents[4]`)
   okuyor; imaj içinde `/app/infra` + `/app/apps/api` AYNI göreli
   derinlikte durur. `GET /api/health` ile gerçek bir `HEALTHCHECK`.
2. **`apps/web/Dockerfile`** — `next.config.ts`'e (bu görevde eklendi)
   `output: "standalone"` sayesinde küçük bir production imajı; dev
   davranışını ETKİLEMEZ (yalnızca `next build` çıktı modu).
3. **Kök `docker-compose.yml`** — `db` (postgres:16-alpine, `pg_isready`
   healthcheck + init.sql'in ilk-kurulum kolaylığı olarak da mount
   edilmesi), `guacd` (Faz 48'den AYNI imaj, ama production'da HOST'A
   AÇILMAZ — yalnızca `api`'nin kendi ağından erişimi var, en az yüzey
   ilkesi), `api`, `web`. Tüm gerçek env değişkenleri (JWT/Fernet/SMTP/
   LDAP/guacd yolları) mevcut `apps/api/.env.example`'daki AYNI
   isimlerle taşınıyor — yeni bir isimlendirme UYDURULMADI.
4. **Kök `.env.example`** — yalnızca konteynerleştirilmiş dağıtım için
   gereken değişkenler (`apps/api/.env.example`'ın YERİNE DEĞİL,
   YANINA).
5. **`deploy.sh`** (Ubuntu/Linux) — Docker/Compose/Git kurulum kontrolü,
   idempotent `.env` üretimi (rastgele sırlar), `data/` dizinleri,
   `docker compose up -d --build`, sağlık bekleme.
6. **`deploy.ps1`** (Windows Server) — WSL2 kontrolü/kurulumu, Docker
   Desktop'ın VARLIĞINI kontrol eder (GUI kurulum gerektirdiği için
   OTOMATİK KURMAZ, resmi bağlantıyı verir), Windows Firewall'da 80/
   443/8000/4822, aynı idempotent `.env` üretimi.
7. **`backup.sh`/`restore.sh`** — çalışan `db` konteynerinin İÇİNDEN
   `pg_dump`/`psql` (ayrı bir PostgreSQL istemcisi GEREKMEZ) + PAM
   oturum kaydı/sürücü dosyaları (`./data/`). `.env` KASITLI olarak
   yedeklenmiyor (sırlar ayrı, daha güvenli saklanmalı — `restore.sh`
   YIKICI olduğu için açık `EVET` onayı ister).
8. **`DEPLOYMENT.md`** — sunucu gereksinimleri, tek komutla kurulum,
   ilk giriş + LDAP/vCenter/SMTP/PAM kurulumu sonrası adımlar, yedekleme/
   geri yükleme, güvenlik notları, sorun giderme.

**Gerçek doğrulama:** `deploy.ps1`'in ilk yazımı gerçek bir sözdizimi
hatası içeriyordu — Faz 40'ta ZATEN keşfedilmiş AYNI bug (em dash'in
BOM'suz `.ps1` + PowerShell 5.1'de bir "akıllı tırnak"a denk gelip
string'i erken sonlandırması) buraya da SIZMIŞTI; `[System.Management.
Automation.Language.Parser]::ParseFile` ile gerçek bir sözdizimi
denetiminden geçirilip düzeltildi (tüm em dash'ler kaldırıldı). `docker
compose build` bu makinede GERÇEKTEN çalıştırılıp hem `api` hem `web`
imajları hatasız derlendi (gerçek Docker Engine 29.7.2, bu ortamda
mevcut — `infra/docker-compose.yml`'in Faz 48 notundaki "Docker
kurulu değil" kısıtı bu oturumda artık geçerli değil). `docker compose
config` ile gerekli/zorunlu değişkenlerin (`:?` sözdizimi) `.env`
eksikken GERÇEKTEN hata verdiği doğrulandı (sessiz/boş bir sırla
başlamıyor). `bash -n` ile üç shell script'in söz dizimi doğrulandı.
**Gerçek bir sunucuya uçtan uca canlı kurulum (deploy.sh/deploy.ps1'in
GERÇEK bir boş makinede çalıştırılması) bu increment'e dahil EDİLMEDİ**
— bu makine zaten kurulu/canlı bir örneği barındırıyor, ayrı bir "boş"
test sunucusu yok; script'ler mantık/söz dizimi + gerçek imaj derlemesi
seviyesinde doğrulandı.

**Kapsam dışı:** TLS/443 (kendi ters proxy'niz gerekir, sahte sertifika
uydurulmadı), Kubernetes/Helm (yalnızca Docker Compose istendi), CI/CD
pipeline'ı (yalnızca kurulum script'i istendi).

## İleri Fazlar (kapsam dışı, yalnızca referans)

Bu fazlar için henüz detaylı plan çıkarılmamıştır; MVP tamamlandıktan
sonra ayrıca planlanacaktır:

- **Faz 11 — SNMP Zenginleştirme (devamı):** SNMPv2c (Faz 22.2),
  SNMPv3 (Faz 22.4) ve kalıcı `snmp_profiles`/Asset↔Profile ilişkisi
  (Faz 29/29.5) tamamlandı. Kalan kapsam: periyodik (zamanlanmış) poll
  döngüsü (henüz numaralandırılmamış bir ileri faz — Faz 30, Windows/
  Linux Agent'a ayrıldığı için bu numaradan çıkarıldı) ve gerçek
  cihazda uçtan uca doğrulama.
- **Faz 12 — AI Entegrasyonu (Claude API):** doğal dilde cihaz/ağ
  sorgulama, salt-okunur `AIInsightService` katmanı.
- ~~**Faz 13 — Auth/RBAC:**~~ Faz 46'da tamamlandı (PAM ile birlikte —
  kullanıcı girişi/JWT + rol bazlı erişim gerçek, çalışır durumda).
  Kapsam dışı kalan: uygulama genelinde bir "login duvarı" (yalnızca
  `/pam/*` korunuyor, bkz. Faz 46 notu).
- **Faz 14 — Zamanlanmış/Periyodik Tarama:** cron benzeri otomatik
  yeniden keşif.
