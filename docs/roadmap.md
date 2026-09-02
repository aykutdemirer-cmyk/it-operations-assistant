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
- **Faz 13 — Auth/RBAC:** kullanıcı girişi, rol bazlı erişim.
- **Faz 14 — Zamanlanmış/Periyodik Tarama:** cron benzeri otomatik
  yeniden keşif.
