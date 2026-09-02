# IT Operations Assistant — Mimari

## 1. Amaç

Kurumsal ağdaki cihazları (firewall, router, switch, server, Windows/Linux
host, access point, printer, NAS, IP kamera, IoT, diğer network cihazları)
otomatik olarak keşfedip merkezi bir veritabanında tutan, web dashboard
üzerinden gösteren ve ilerleyen fazlarda AI ile sorgulanabilir hale getiren
bir platform.

MVP akışı:

```
CIDR gir → Network Discovery → IP keşfi → MAC adresi → Hostname → Vendor
→ Open ports → Device type → Database → Web Dashboard
```

## 2. Sistem Bileşenleri

```
┌─────────────┐      HTTP/REST      ┌──────────────┐      SQL      ┌────────────┐
│  Next.js Web │ ───────────────────▶│  FastAPI API  │──────────────▶│ PostgreSQL │
│  (Dashboard) │◀─────────────────── │   (Backend)   │◀───────────────│  (Storage) │
└─────────────┘                     └──────┬───────┘               └────────────┘
                                            │
                                            │ ICMP / ARP / TCP / DNS
                                            ▼
                                     ┌───────────────┐
                                     │ Discovery      │
                                     │ Engine (Python)│
                                     └───────────────┘
                                            │
                                            ▼
                                     Kurumsal Ağ (LAN)
```

- **Web (Next.js/React/TypeScript):** CIDR girişi, tarama tetikleme,
  cihaz listesi/detay dashboard'u. Backend'e yalnızca REST API üzerinden
  konuşur.
- **API (FastAPI/Python):** İş mantığı, discovery orkestrasyonu, CRUD
  endpoint'leri, gelecekte AI sorgu endpoint'i.
- **Discovery Engine (Python, API içinde bir modül):** CIDR aralığını
  tarar, canlı host'ları bulur, cihaz bilgilerini toplar.
- **Database (PostgreSQL):** Keşfedilen cihazlar, tarama geçmişi, portlar.

## 3. Veri Akışı (Gerçekleşen)

1. Kullanıcı ana sayfadaki **Network Discovery** bölümünden bir CIDR
   girer (örn. `192.168.1.0/24`).
2. Web, API'ye `POST /api/discovery/icmp` isteği gönderir.
3. Discovery Engine (`app/discovery/scanner.py`) sırayla:
   - **ICMP** ping sweep → canlı IP'leri bulur.
   - **ARP** → aynı L2 segmentindeki host'lar için MAC adresi çözer.
   - **Vendor (OUI) lookup** → MAC OUI önekinden üretici bilgisini
     çıkarır.
   - **Reverse DNS** → hostname çözer.
   - **TCP port tarama** → önceden tanımlı yaygın port listesini tarar.
   - **Device type sınıflandırma** → açık portlar + vendor + hostname
     kalıplarından basit bir sezgisel (heuristic) ile cihaz tipini tahmin
     eder.
4. API, `ScanResult`'ı senkron olarak Web'e döner; dönmeden hemen önce
   sonuçtaki **UP** host'ları `app/db/assets.py::upsert_asset` üzerinden
   PostgreSQL'deki tek `assets` tablosuna yazar (bkz. §7). Bu yazma
   adımı `app/routes/discovery.py::persist_scan_result` içinde
   orkestre edilir; discovery katmanı (`app/discovery/*`) veritabanını
   hiçbir zaman doğrudan tanımaz (bkz. §5, §8). DOWN host'lar
   veritabanına yazılmaz — henüz görülmemiş bir cihaz için "yok"
   anlamına gelen bir satır oluşturmak asset envanterini anlamsızca
   doldurur. Bilinen bir cihaz artık yanıt vermiyorsa mevcut kaydı
   `down` olarak otomatik güncellenmez (ayrı bir reconciliation kararı
   gerektirir, henüz planlanmadı).
5. Web, ayrı bir **Asset Inventory** bölümünden `GET /api/assets` ile
   kalıcı listeyi çeker (sayfa yüklendiğinde otomatik, ayrıca Refresh
   butonuyla).

Tek bir cihaz için detay endpoint'i (`GET /api/assets/{id}` benzeri)
henüz yoktur. SNMP tabanlı zenginleştirme, AI destekli sorgulama
(Claude API) ve authentication ileri fazlarda bu akışa eklenecek;
mevcut kapsamda değildir.

## 4. Mevcut Dizin Yapısı

Docker fazı (bkz. `roadmap.md` Faz 10) henüz uygulanmadı; geri kalanı
gerçekleşmiş durumdadır.

```
it-operations-assistant/
├── apps/
│   ├── web/
│   │   ├── app/               # layout.tsx (sidebar+header+Provider shell),
│   │   │                      # page.tsx (dashboard, /), discovery/,
│   │   │                      # assets/, topology/, scans/, alerts/,
│   │   │                      # monitoring/, settings/ — her biri gerçek
│   │   │                      # bir route (bkz. §6.3), shared.module.css
│   │   ├── components/        # BackendStatus, Sidebar, TopHeader,
│   │   │                      # GlobalSearch, LanguageToggle,
│   │   │                      # NetworkDiscovery, DashboardSummary,
│   │   │                      # InfrastructureHealth, DeviceDistribution,
│   │   │                      # DeviceHealthSummary, MonitoringCoverage,
│   │   │                      # OpenPortsOverview, AlertsPanel, AlertsList,
│   │   │                      # NetworkPerformance, MonitoringOverview,
│   │   │                      # SettingsPanel, RecentScans, ScanDetails,
│   │   │                      # RecentActivity, AssetInventory,
│   │   │                      # AssetDetails (sekmeli), NetworkTopology
│   │   │                      # (arama/filtre)
│   │   └── lib/                # api.ts (REST client), health.ts,
│   │                            # portRisk.ts, time.ts, activity.ts,
│   │                            # deviceHealth.ts, monitoringCoverage.ts,
│   │                            # alerts.ts — her biri saf, test edilebilir
│   │                            # hesaplama fonksiyonları (bkz. §6.1);
│   │                            # DashboardDataProvider.tsx — paylaşımlı
│   │                            # assets/scans context (bkz. §6.2);
│   │                            # i18n/ (translations.ts, LocaleProvider.tsx),
│   │                            # theme/ThemeProvider.tsx (bkz. §6.3)
│   └── api/
│       └── app/
│           ├── discovery/     # icmp, arp, dns_lookup, vendor, port_scan,
│           │                  # device_classifier, cidr, schemas, scanner
│           │                  # (orkestrasyon), data/ (OUI veri seti)
│           ├── db/            # connection.py, assets.py, scans.py
│           │                  # (şema + repository, tek tabloya bir dosya)
│           ├── snmp/          # models.py, oid_map.py, bandwidth.py —
│           │                  # gerçek ajan olmadan mimari (bkz. §7.1)
│           └── routes/        # health.py, discovery.py, assets.py, scans.py,
│                               # snmp.py (endpoint başına bir dosya)
│   └── agent/                 # Faz 30 — BAĞIMSIZ Windows/Linux Agent
│       ├── agent/             # main.py (CLI+ana döngü), config.py,
│       │                      # client.py (urllib), authentication.py,
│       │                      # heartbeat.py, telemetry.py, inventory.py,
│       │                      # collectors/ (system/cpu/memory/disk/
│       │                      # network/processes/services), platform/
│       │                      # (windows.py/linux.py) — bkz. §7.2
│       ├── tests/
│       ├── deploy/systemd/    # yalnızca referans unit dosyası
│       └── requirements.txt   # tek runtime bağımlılığı: psutil
├── infra/
│   ├── docker-compose.yml     # yalnızca PostgreSQL (Faz 10'a kadar)
│   └── postgres/init.sql      # `assets`+`scans` şeması — tek doğruluk kaynağı
├── docs/
│   ├── architecture.md
│   ├── roadmap.md
│   └── decisions.md
└── CLAUDE.md
```

ORM veya migration aracı (Alembic vb.) kullanılmıyor — `db/assets.py`,
şemayı `infra/postgres/init.sql`'den okuyup idempotent şekilde
(`CREATE TABLE/INDEX IF NOT EXISTS`) uygular (bkz. §7, `decisions.md`
§3).

## 5. Discovery Engine Tasarımı

Her keşif adımı bağımsız, test edilebilir bir fonksiyon/modül olarak
tasarlanır; bir adımın başarısız olması sonraki adımları durdurmaz
(örn. ARP çözülemeyen bir host için hostname/port taraması yine de
denenir).

| Adım | Yöntem | Girdi | Çıktı |
|---|---|---|---|
| Host keşfi | ICMP echo (ping sweep) | CIDR | canlı IP listesi |
| MAC çözümleme | ARP (yerel segment) | IP | MAC adresi (varsa) |
| Hostname | DNS reverse lookup (PTR) | IP | hostname (varsa) |
| Vendor | MAC OUI veritabanı | MAC | üretici adı (varsa) |
| Açık portlar | TCP connect scan (sınırlı port listesi) | IP | port listesi |
| Cihaz tipi | Heuristic (port + vendor + hostname kalıpları) | yukarıdakiler | tahmini tip |

SNMP tabanlı zenginleştirme (sysDescr, interface listesi vb.) ileri fazda
aynı arayüze eklenecek bir adım olarak tasarlanır; MVP'nin akışını bozmaz.

## 6. Backend API (Gerçekleşen)

Endpoint başına bir router dosyası (`app/routes/`) prensibiyle:

- `GET /api/health` — API'nin ayakta olduğunu doğrular (`{"status": "ok"}`).
- `GET /api/health/db` — PostgreSQL bağlantısını doğrular; erişilemezse
  `503 {"database": "unreachable"}`.
- `POST /api/discovery/icmp` — CIDR alır, `ScanResult`'ı senkron döner
  (bkz. §3); yanıt dönmeden önce UP host'ları `assets` tablosuna yazar.
  Geçersiz CIDR → `400`.
- `GET /api/assets` — `assets` tablosundaki tüm kayıtları `last_seen
  DESC` sırayla döner (filtreleme/arama frontend'de yapılır, backend'de
  yok). DB erişilemezse `503 {"database": "unreachable"}`; diğer
  beklenmeyen hatalarda ham PostgreSQL hatası kullanıcıya sızdırılmadan
  `500` döner.
- `GET /api/scans` — `scans` tablosundaki tüm tarama kayıtlarını
  `started_at DESC` sırayla döner ("son N" kısıtı frontend'de). Aynı
  hata davranışı (`503`/`500`) `GET /api/assets` ile birebir aynı.
- `POST /api/snmp/poll/{asset_id}` — asset var mı diye `assets`
  tablosunda kontrol eder (`404` yoksa). Profil `resolve_profile_for_
  asset` ile çözülür (Faz 29.5) — önce `asset_snmp_profiles` DB
  ataması, yoksa `.env` (`SNMP_TARGET_*`) tek-hedef fallback'i (bkz.
  §7.1). Hiçbiri çözülmezse `status: "not_configured"` döner. Profil
  çözülürse gerçek bir SNMP (v2c veya v3) poll yapılır ve `status`
  gerçek sonucu (`success`/`partial`/`timeout`/`unreachable`/
  `authentication_failed`) yansıtır — hiçbir durumda `system`/
  `interfaces` uydurulmaz.
- `GET /api/monitoring` (Faz 24) — tüm asset'leri okur, `PollingEngine.
  poll_all` ile tek bir turda gerçek poll dener (bkz. §7.1), aynı
  `SNMPPollResult` listesini `PollBatchResult` içinde sarıp döner.
  `POST /api/snmp/poll/{asset_id}`'in YERİNE geçmez — o tek-asset/anlık,
  bu tüm-filo/tek-tur içindir; ikisi de aynı `SNMPClient`'ı kullanır.
- `POST /api/agents/register` (Faz 28, Faz 31'de `enrollment_code`
  ZORUNLU hale geldi) — Windows/Linux Agent kendi metadata'sını
  (hostname/OS/version/capabilities) + geçerli/süresi dolmamış/
  kullanılmamış bir enrollment kodu verir, `{agent_id, token}` döner —
  `token` PLAINTEXT olarak YALNIZCA burada görünür. Kod eksikse `422`,
  geçersiz/süresi dolmuş/kullanılmışsa `401` (bkz. `app/agents/
  enrollment.py`, `docs/decisions.md` §14).
- `POST /api/agents/enrollment-codes` (Faz 31) — yeni, tek kullanımlık,
  10dk geçerli bir enrollment kodu üretir (`{code, expires_at}`, 201).
  `GET /api/agents/enrollment-codes` — süresi dolmamış VE henüz
  kullanılmamış kodları listeler. Kod bir credential DEĞİLDİR (tek
  başına hiçbir kaynağa erişim vermez), bu yüzden plaintext dönmesi
  güvenlik ilkesini ihlal etmez.
- `GET /api/agents/download/windows/info` (Faz 32) — gerçek build
  metadata'sı (`{available, version, filename, size_bytes, built_at}`,
  `apps/agent/dist/build-info.json`'dan okunur). `GET /api/agents/
  download/windows` — önceden build edilmiş (`packaging/windows/
  build.ps1`) Windows Agent EXE'sini indirir (`Content-Disposition:
  attachment`). Backend PyInstaller'ı ASLA çalıştırmaz (build/download
  ayrı); dosya adı/yol kullanıcıdan hiç alınmaz — path traversal
  yapısal olarak imkansız (bkz. `app/agents/download.py`, `docs/
  decisions.md` §15). Artifact yoksa dürüst `404`.
- `POST /api/agents/heartbeat` — Bearer auth; `last_heartbeat_at`'i
  günceller, güncel `AgentSummary`'yi (türetilmiş `status` dahil) döner.
- `POST /api/agents/{agent_id}/telemetry` / `POST /api/agents/{agent_id}
  /inventory` — Bearer auth + path'teki `{agent_id}`'nin token'ın
  sahibiyle eşleştiği doğrulanır (eşleşmezse `403`) — path parametresi
  tek başına güvenilir kimlik olarak kabul edilmez.
- `GET /api/agents` / `GET /api/agents/{agent_id}` — agent listesi/
  detayı; `token`/`token_hash` hiçbir response'ta yer almaz.
- `GET /api/agents/{agent_id}/asset-match` (Faz 29) — mevcut `assets`
  listesine karşı bir eşleştirme DEĞERLENDİRMESİ döner, hiçbir şey
  YAZMAZ (bkz. `app/agents/matching.py`). `POST` (aynı path, body:
  `{asset_id}`) bir eşleşmeyi AÇIKÇA onaylayıp `agents.asset_id`'yi
  yazar — yalnızca bu iki endpoint bu sütuna dokunur.
- `GET/POST /api/snmp/profiles`, `GET/PUT/DELETE /api/snmp/profiles/
  {id}`, `POST /api/snmp/profiles/{id}/test` (Faz 29 — SNMP
  Configuration Center) — kalıcı, `target_host`-tabanlı SNMP profil
  CRUD'ı. Hiçbir response secret DEĞERİ taşımaz (`credential_
  configured`/`status` türetilmiş alanlar, `*_ref` yalnızca isim).
  `/test`, mevcut `SNMPClient`'ı (değiştirilmeden) kullanarak profilin
  `target_host`'una GERÇEK bir poll dener — yalnızca kullanıcının
  kaydettiği, kullanıcının test butonuna tıkladığı bir hedefe karşı.
  `DELETE`, atanmış asset'i olan bir profili `409 Conflict` ile reddeder
  (Faz 29.5, bkz. §10.5).
- `GET /api/assets/{asset_id}/snmp-profile`, `PUT /api/assets/
  {asset_id}/snmp-profile/{profile_id}`, `DELETE /api/assets/
  {asset_id}/snmp-profile`, `GET /api/snmp/profiles/{profile_id}/assets`
  (Faz 29.5) — Asset ↔ SNMP Profile ilişki CRUD'ı (`asset_snmp_
  profiles`). `GET`, `target_host_matches_asset` (profilin kendi
  hedefi asset'in IP'sinden farklıysa `false` — bloklayıcı değil,
  yalnızca UI'da bilgilendirici bir uyarı) alanını da döner. Hiçbir
  response secret DEĞERİ taşımaz.

Tek bir asset'in ayrı bir GET detay endpoint'i yok — `AssetDetails`
paneli `GET /api/assets`'in döndürdüğü tam veriyi kullanır (SNMP poll
endpoint'i asset var mı kontrolü için dahili olarak `get_asset_by_id`
kullanır). Genel bir kullanıcı authentication'ı (login/session) henüz
yoktur (bkz. Faz 31 sonrası, ileri faz); yalnızca `app/agents/*`
endpoint'leri (heartbeat/telemetry/inventory) kendi bearer-token
authentication'ını kullanır — bu, insan kullanıcı auth'undan (Faz 41)
bağımsız, ayrı bir mekanizmadır.

### 6.1 Frontend hesaplama katmanı (`apps/web/lib/`)

Backend'den gelen ham `assets`/`scans` verisini component'lere
sunulmadan önce işleyen, DB/network'ten bağımsız, saf (pure) fonksiyon
modülleri — hepsi girdi olarak yalnızca zaten fetch edilmiş veri alır,
kendi başına hiçbir API çağrısı yapmaz:

| Modül | Sorumluluk |
|---|---|
| `health.ts` | `assets`'ten online/offline/unknown yüzdeleri |
| `portRisk.ts` | port → risk sınıflandırması (tek doğruluk kaynağı) |
| `time.ts` | `timeAgo` — göreli zaman formatlama |
| `activity.ts` | `assets`+`scans`'ten olay akışı (discovered/updated/scan) |
| `alerts.ts` | `assets` (+ opsiyonel gerçek SNMP `monitoring`, bkz. §7.1 ve Faz 26) alert üretimi |
| `alertThresholds.ts` | `alerts.ts`'in kullandığı tüm sayısal eşikler (Faz 26) — hiçbiri hardcode değil |

Bu ayrım, her hesaplamanın component render'ından bağımsız `vitest`
testleriyle doğrulanabilmesini sağlar (bkz. `apps/web/tests/`).

### 6.2 Paylaşımlı veri katmanı (`DashboardDataProvider`)

`apps/web/lib/DashboardDataProvider.tsx` — kök `app/layout.tsx`'e
bağlı, React `Context` tabanlı tek bir `assets`/`scans` kaynağı (Faz 5).
Dashboard component'lerinin her biri kendi `GET /api/assets`/
`GET /api/scans` çağrısını yapmak yerine `useDashboardData()` hook'unu
tüketir; `network-scan-completed` event'i de burada, tek noktada
dinlenir. Yeni bir dependency (SWR/React Query) eklenmedi — mevcut
React primitive'leri yeterli görüldü (gerekçe/ölçüm: `docs/decisions.md`
§9). `NetworkTopology` (`/topology` sayfası) da aynı provider'ı
tüketir — sayfa geçişlerinde ek istek atılmaz.

### 6.3 Sayfa (route) mimarisi, i18n ve tema (Faz 21)

**Route'lar:** Her ana menü öğesi gerçek bir Next.js App Router
route'udur — `/` (Dashboard, yalnızca özet/analitik widget'ları),
`/discovery`, `/assets`, `/topology`, `/scans`, `/alerts`,
`/monitoring`, `/settings`. Basit sayfalar (`discovery`/`assets`/
`scans`/`alerts`/`monitoring`/`settings`) ortak `app/shared.module.css`
`.page` sarmalayıcısını kullanır; Dashboard kendi `page.module.css`'ini
korur (kart grid'i farklı).

**i18n (`apps/web/lib/i18n/`):** `translations.ts` — `tr` (varsayılan)
ve `en` iki tam sözlük nesnesi (dize literal tipi ZORLANMAZ — `tr`'ye
`as const` uygulanmıyor, aksi halde `en`'in aynı literal string'leri
taşıması gerekirdi). `LocaleProvider.tsx` bir React `Context`; `t`
(aktif dilin tam sözlüğü), `locale`, `setLocale` sağlar. Kalıcı seçim
`localStorage`'da (`itops-locale`), yalnızca mount sonrası bir
`useEffect`'te okunur — sunucu ve ilk client render'ı her zaman `tr`
olduğundan hydration mismatch oluşmaz (bkz. dosya içi yorum, kabul
edilen ödünleşim: kalıcı "en" seçimi olan bir kullanıcı her ziyarette
çok kısa bir "tr" karesi görebilir).

Teknik gerçek veriler (IP, MAC, hostname, vendor, OID, port numarası,
CIDR, SNMP version) **hiçbir zaman çevrilmez** — yalnızca sabit UI
metinleri (`translations.ts` sözlüğündeki anahtarlar) çevrilir.

Saf hesaplama katmanındaki (`lib/alerts.ts`, `lib/time.ts`) metin
üretimi dile bağımlı olduğu için, bu iki fonksiyon artık ilgili çeviri
alt-sözlüğünü (`t.alertMessages`, `t.timeAgo`) bir parametre olarak
alır — modül kendisi `useLocale()`'a bağımlı değildir, çağıran
component enjekte eder.

**Tema (`apps/web/lib/theme/ThemeProvider.tsx`):** Aynı desen —
varsayılan `dark`, `localStorage`'da (`itops-theme`) kalıcı,
`document.documentElement.dataset.theme` ile uygulanır. `globals.css`
`:root[data-theme="light"]` / `:root[data-theme="dark"]` açık
seçicilerini, var olan `@media (prefers-color-scheme: light)` sorgusunu
(`:not([data-theme="dark"])` ile korunmuş) **geçersiz kılacak** şekilde
tanımlar.

**GlobalSearch davranışı korundu:** bir sonuca tıklanınca `AssetDetails`
paneli doğrudan açılır (bir `/assets?search=...` yönlendirmesi değil)
— bu, Faz 20'de zaten doğrulanmış bir davranıştı ve bozulmadı.
`TopHeader`'da her sayfada görünür (kök layout'ta).

## 7. Veritabanı (Gerçekleşen)

Ana tablo — `assets` (`infra/postgres/init.sql`, `app/db/assets.py`);
`scans`/`agents`/`agent_telemetry`/`agent_inventory` aynı `init.sql`
dosyasında additive olarak eklendi (bkz. altta).
Bir "cihaz" ile bir "tarama kaydı" ayrı satırlar/tablolar olarak değil,
**IP başına tek, sürekli güncellenen bir satır** olarak modellenir:

| Kolon | Tip | Not |
|---|---|---|
| `id` | `UUID` (PK) | `gen_random_uuid()` |
| `ip_address` | `INET` | **UNIQUE** — cihazın ana kimliği |
| `hostname` | `TEXT` (null olabilir) | |
| `mac_address` | `TEXT` (null olabilir) | bilinçli olarak `MACADDR` değil — uygulamanın kendi biçimini (`AA-BB-CC-DD-EE-FF`) korur |
| `vendor` | `TEXT` (null olabilir) | |
| `device_type` | `TEXT`, `DEFAULT 'unknown'` | |
| `confidence` | `TEXT`, `DEFAULT 'low'` | |
| `status` | `TEXT` | `"up"` / `"down"` |
| `latency_ms` | `DOUBLE PRECISION` (null olabilir) | |
| `open_ports` | `JSONB`, `DEFAULT '[]'` | `[{port, status, latency_ms}, ...]` |
| `evidence` | `JSONB`, `DEFAULT '[]'` | sınıflandırma gerekçesi (string listesi) |
| `last_seen` | `TIMESTAMPTZ` | son başarılı discovery zamanı |
| `created_at` | `TIMESTAMPTZ`, `DEFAULT now()` | yalnızca ilk eklemede set edilir |
| `updated_at` | `TIMESTAMPTZ` | her upsert'te `clock_timestamp()` ile güncellenir (`now()` DEĞİL — bkz. `app/db/assets.py` docstring'i: `now()` bir transaction boyunca sabit kalır) |

Index'ler: `assets_ip_address_key` (UNIQUE), `idx_assets_mac_address`,
`idx_assets_device_type`, `idx_assets_status`, `idx_assets_last_seen`.

**Upsert davranışı** (`INSERT ... ON CONFLICT (ip_address) DO UPDATE`):
kimlik alanları (`hostname`/`mac_address`/`vendor`) yeni tarama `NULL`
bulduysa eski değeri korur (`COALESCE`); gözlem alanları (`status`,
`latency_ms`, `open_ports`, `evidence`, `device_type`, `confidence`,
`last_seen`) her taramada `NULL` olsa bile yeni değerle değiştirilir —
detaylı gerekçe `app/db/assets.py::upsert_asset` docstring'indedir.

Roadmap'in ilk taslağındaki ayrı `devices`/`device_ports` tabloları
**uygulanmadı**; tek-tablo upsert modeli tercih edildi (basitlik, MVP
kapsamının IP başına "güncel durum" göstermesi yeterli olduğu için).

**`scans` tablosu** (`infra/postgres/init.sql`, `app/db/scans.py`) —
ayrı bir tarama geçmişi ihtiyacı ortaya çıktığında (bkz.
`roadmap.md` Faz 10.1) eklendi. `assets`'ten bağımsız, kendi
`ensure_schema`'sı olan ayrı bir repository modülü; aynı `init.sql`
dosyasını okur (tek doğruluk kaynağı korunur — iki modülün
`ensure_schema`'sı da idempotent olduğu için hangisi çağrılırsa
çağrılsın tüm şema garanti altındadır):

| Kolon | Tip | Not |
|---|---|---|
| `id` | `UUID` (PK) | `gen_random_uuid()` |
| `cidr` | `TEXT` | |
| `started_at` | `TIMESTAMPTZ` | |
| `completed_at` | `TIMESTAMPTZ` (null olabilir) | `running` iken null |
| `duration_ms` | `DOUBLE PRECISION` (null olabilir) | |
| `hosts_scanned` | `INTEGER`, `DEFAULT 0` | `ScanResult.total_hosts` |
| `hosts_discovered` | `INTEGER`, `DEFAULT 0` | `ScanResult.alive_hosts` |
| `open_ports` | `INTEGER`, `DEFAULT 0` | taramada bulunan toplam açık port **sayısı** (assets'teki gibi JSONB liste değil — aynı veri iki kez tutulmasın diye) |
| `status` | `TEXT` | `"running"` / `"completed"` / `"failed"` |

Index'ler: `idx_scans_started_at`, `idx_scans_status`. `created_at`/
`updated_at` bilinçli olarak yok (gereksiz alan — `started_at`/
`completed_at` zaten yeterli).

Scan history yazımı, discovery'nin ana işlevini (tarama + asset
persistence) **hiçbir zaman bloke etmez**: `app/routes/discovery.py`
taramadan önce best-effort bir `running` kaydı açar, sonuçta
`completed`/`failed` olarak günceller; DB erişilemezse veya yazım
başarısız olursa yalnızca loglanır, HTTP response'u etkilenmez (aynı
felsefe `persist_scan_result` ile — bkz. §3).

**`agents` / `agent_telemetry` / `agent_inventory`** (`infra/postgres/
init.sql`, `app/db/agents.py`, Faz 28) — Windows/Linux Agent alt
sistemi, `assets`/`scans`'a dokunmadan additive olarak eklendi:
- `agents`: kimlik + `token_hash` (SHA-256, plaintext asla) +
  `asset_id` (nullable FK → `assets.id` ON DELETE SET NULL — Faz 29'da
  yalnızca `app/agents/matching.py`'nin AÇIKÇA onaylanmış eşleşmesi
  yazabiliyor, otomatik doldurulmuyor) + `last_heartbeat_at`
  (`AgentStatus` buradan TÜRETİLİR, ayrı bir "status" sütunu yok —
  bkz. §12 karar dokümanı). `agent_telemetry` için Faz 29'da bir
  retention politikası eklendi (`AGENT_TELEMETRY_RETENTION_DAYS`,
  varsayılan 30 gün, `app/db/agents.py::delete_expired_telemetry`) —
  henüz hiçbir zamanlayıcı tarafından otomatik çağrılmıyor.
- `agent_telemetry`: yüksek frekanslı CPU/RAM/disk/network örnekleri;
  `disks`/`network_interfaces` JSONB (normalize edilmedi, MVP). Faz
  29'daki retention politikası henüz hiçbir zamanlayıcı tarafından
  OTOMATİK çağrılmıyor — bu hâlâ üretim öncesi kapatılması gereken bir
  boşluk (bkz. Faz 38).
- `agent_inventory`: agent başına TEK satır (`agent_id` PK) — seyrek
  değişen envanter (hardware/os/network/software/services, hepsi
  JSONB), tarihçe tutulmaz.

Index'ler: `idx_agents_hostname`, `idx_agents_asset_id`,
`idx_agents_last_heartbeat_at`, `idx_agent_telemetry_agent_id_
collected_at`.

**`snmp_profiles`** (`infra/postgres/init.sql`, `app/db/snmp_profiles.py`,
Faz 29) — kullanıcının Settings > SNMP Configuration Center üzerinden
yönettiği kalıcı SNMP hedef profilleri; `assets`'e KASITLI olarak bağlı
DEĞİL (`target_host` ile doğrudan tanımlanır, `name` UNIQUE — bkz.
`docs/decisions.md` §10.4, §10.3'ün asset-tabanlı planından bilinçli
sapma). Hiçbir sütun gerçek secret DEĞERİ taşımaz — yalnızca
`community_ref`/`auth_credential_ref`/`priv_credential_ref` (birer
İSİM). Index'ler: `idx_snmp_profiles_target_host`, `idx_snmp_profiles_
enabled`.

**`asset_snmp_profiles`** (`infra/postgres/init.sql`, `app/db/
asset_snmp_profiles.py`, Faz 29.5) — Asset ↔ SNMP Profile ilişki
tablosu. `asset_id UUID PRIMARY KEY REFERENCES assets(id) ON DELETE
CASCADE` (bir asset'in en fazla bir aktif profili olabileceğini DB
seviyesinde garanti eder), `snmp_profile_id UUID NOT NULL REFERENCES
snmp_profiles(id) ON DELETE CASCADE` (bir profil birden fazla asset'e
atanabilir — 1:N, profil→asset). Karar gerekçesi ve kullanıcının kendi
mimari ifadesi: `docs/decisions.md` §10.5. Index: `idx_asset_snmp_
profiles_profile` (`GET /api/snmp/profiles/{id}/assets` için).

### 7.1 SNMP mimarisi — gerçek SNMPv2c client (Faz 22.2)

`apps/api/app/snmp/`:

- `oid_map.py` — MIB-II/IF-MIB standart OID'lerinin isim → OID
  eşlemesi (`sysName`/`sysDescr`/`sysObjectID`/`sysUpTime`,
  `ifName`/`ifDescr`/`ifOperStatus`/`ifAdminStatus`/`ifSpeed`/
  `ifInOctets`/`ifOutOctets`/`ifHCInOctets`/`ifHCOutOctets`). Hiçbir
  yerde ham OID string'i başka bir dosyada hardcode edilmez.
- `models.py` — `SystemInfo`, `InterfaceInfo`, `SNMPPollResult`
  (Pydantic). `SNMPPollResult.status` altı değerden birini yansıtır:
  `not_configured`/`unreachable`/`timeout`/`authentication_failed`/
  `success`/`partial`; veri yoksa `system`/`interfaces` `None`/`[]`
  kalır, asla varsayılan/uydurma değerle doldurulmaz.
  `InterfaceInfo.if_in_bps`/`if_out_bps` (hesaplanan bant genişliği,
  ilk poll'da her zaman `None`) ve `if_counters_64bit` (32/64-bit
  sayaç ayrımı) Faz 22.2'de eklendi. `if_in_errors`/`if_out_errors`
  (Faz 26) — `ifInErrors`/`ifOutErrors`, KÜMÜLATİF sayaç (bir ORAN
  değil), frontend `interface_error` alert kuralının veri kaynağı.
- `bandwidth.py` — iki ardışık octet örneğinden bps hesabı. Negatif
  delta (counter rollover veya ajan yeniden başlaması) ayırt
  edilemediği için tahmini bir değer üretmek yerine `None` döner.
  Değişmedi — `client.py` bunu aynen, süreç-içi (in-memory) bir
  `asset_id+ifIndex+yön` örnek önbelleğiyle çağırıyor.
- `credentials.py` — `SNMPProfile` (Faz 7): v2c/v3 yapılandırma
  modeli. **Hiçbir gerçek secret değeri taşımaz** — yalnızca
  `community_ref`/`auth_credential_ref`/`priv_credential_ref` gibi
  referans alanları var; v2c/v3'e göre zorunlu alanlar
  `model_validator` ile doğrulanır. v1 kasıtlı olarak desteklenmez.
- `secrets.py` — `resolve_secret(ref)`: tek, merkezi secret çözümleme
  noktası; `ref` (bir ortam değişkeni ADI) alır, gerçek değeri yalnızca
  poll anında ortamdan okur. Hiçbir yerde saklamaz/loglamaz.
- `profile_store.py` — `resolve_profile_for_asset(conn, asset)` (Faz
  29.5, tercih edilen giriş noktası): önce `asset_snmp_profiles` DB
  atamasını dener (`enabled=False` ise doğrudan `None`, env fallback'e
  DÜŞMEZ); atama yoksa (veya `conn` verilmezse) `get_profile_for_
  asset(asset_id)` — `.env`'deki `SNMP_TARGET_*` değişkenleriyle
  tanımlı tek bir kullanıcı-onaylı hedefi çözen ESKİ (ama hâlâ
  YAŞAYAN, dokümante edilmiş bir geriye dönük uyumluluk yolu olarak)
  fallback'e düşülür. İkisi de eşleşme yoksa `None` (→
  `not_configured`). Karar: `docs/decisions.md` §10.5.
- `client.py` — `SNMPClient.poll_asset(profile, host, asset_id)`:
  hem **SNMPv2c** (`pysnmp.hlapi.v1arch.asyncio.Slim`) hem **SNMPv3**
  (`pysnmp.hlapi.v3arch.asyncio` — `SnmpEngine`/`UsmUserData`/
  `get_cmd`/`bulk_cmd`; v3'te `Slim` benzeri bir sarmalayıcı yok)
  destekler. System MIB GET + Interface MIB keşif (GETBULK ile
  `ifDescr` subtree'si) + kolon başına GET akışı, küçük bir
  `_Transport` protokolü (`_V2cTransport`/`_V3Transport`) arkasında
  **tek bir** ortak parsing koduyla yapılır — iki versiyon arasında
  MIB parsing asla tekrarlanmaz. `exceptions.py`'deki hiyerarşiye
  (`SNMPError` ve alt sınıfları) çevrilmeyen hiçbir pysnmp-özel tip
  veya credential DEĞERİ dışarı sızmaz. v3 güvenlik seviyeleri:
  `noAuthNoPriv`/`authNoPriv`/`authPriv` (bkz. `credentials.py`); auth
  SHA-1 + SHA-2 ailesi, priv AES (128/192/256-bit) — `_build_usm_user_
  data` `authKey`/`authProtocol` ve `privKey`/`privProtocol`'ü HER ZAMAN
  birlikte geçirir, pysnmp'nin sessiz MD5/DES varsayılanına asla
  düşülmez (bkz. `docs/decisions.md` §10.2).
- `exceptions.py` — `SNMPError` / `SNMPTimeoutError` /
  `SNMPAuthenticationError` / `SNMPUnavailableError` /
  `SNMPProtocolError`.
- `poller.py` (Faz 23, Faz 29.5'te DB-tabanlı profil çözümüne bağlandı)
  — `PollingEngine.poll_all(assets, conn=None)`: profil çözümü ÖNCE,
  SIRAYLA yapılır (tek bir `asyncpg.Connection` aynı anda yalnızca bir
  sorguyu destekler — eşzamanlı denenirse `InterfaceError` fırlatır,
  bkz. `docs/decisions.md` §10.5), yalnızca gerçek SNMP ağ poll'ları
  `asyncio.Semaphore` ile sınırlı eşzamanlı (varsayılan `SNMP_MAX_
  CONCURRENCY=5`) çalışır. Bir asset'in hatası diğerlerini durdurmaz,
  `asyncio.CancelledError` hiç yutulmaz (graceful shutdown).
  `PollBatchResult` yalnızca `SNMPPollResult` listesini zamanlama/sayım
  bilgisiyle sarar — tekil sözleşmeye yeni bir `status` değeri eklemez.
  `GET /api/monitoring`'e bağlı (Faz 24, bkz. §6/§9).

`POST /api/snmp/poll/{asset_id}` (`app/routes/snmp.py`): profil
çözülmezse `not_configured` (değişmedi); çözülürse gerçek
`SNMPClient.poll_asset` çağrılır — hiçbir hata sahte bir HTTP 200
"success" olarak gizlenmez.

**Bilinçli olarak yok:** SNMP community string/credential DEĞERİ için
kalıcı bir DB sütunu (yalnızca `*_ref` İSİMLERİ saklanır, gerçek değer
her zaman `.env`'den `resolve_secret()` ile poll anında okunur — bkz.
`docs/decisions.md` §10.1/§10.2); periyodik/zamanlanmış poll döngüsü;
gerçek cihazda (v2c veya v3) canlı doğrulama (kullanıcı henüz bir hedef
vermedi). (Asset↔Profil İLİŞKİSİNİN kendisi artık kalıcı — bkz.
`asset_snmp_profiles`, §7/§10.5 — bu madde yalnızca credential
DEĞERİNİN saklanmadığını belirtir.)

**Agent (Faz 28-30):** API + veri modeli (Faz 28), Asset↔Agent
eşleştirme değerlendirme/onay akışı ve telemetry retention politikası
(Faz 29), gerçek bağımsız Windows/Linux Agent uygulaması + `/agents` ve
`/agents/[id]` frontend sayfaları + `AssetDetails`'in Agent sekmesi +
Dashboard'ın Agent Health widget'ı (Faz 30) tamamlandı (bkz. §6, §7,
§7.2, §12/§13/§10.4 karar dokümanları — `docs/decisions.md`). Kalan iş:
token sertleştirme/enrollment-secret/revocation (Faz 31), retention'ın
gerçek bir zamanlayıcıya bağlanması (Faz 38), Windows Service/systemd
gerçek kurulumu ve installer (bkz. §13).

**SNMP Configuration Center (Faz 29) + Asset↔Profile İlişkisi (Faz
29.5):** `snmp_profiles` CRUD + gerçek "Test Connection" (Faz 29),
`asset_snmp_profiles` ilişki tablosu + `resolve_profile_for_asset` ile
gerçek asset polling'in Configuration Center profillerini kullanması
(Faz 29.5) tamamlandı (bkz. §6, §7, §7.1, §10.4/§10.5 karar
dokümanları). Kalan iş: periyodik/zamanlanmış poll döngüsü, gerçek
cihazda canlı doğrulama (kullanıcı henüz bir hedef vermedi).

### 7.2 Agent mimarisi — bağımsız Windows/Linux uygulaması (Faz 30)

`apps/agent/` (backend'e gömülü DEĞİL, ayrı dağıtılabilen bir Python
uygulaması, bkz. §4, `docs/decisions.md` §13):

- `main.py` — CLI (`start`/`status`/`inventory`/`test-connection`/
  `version`) + `AgentRuntime`: heartbeat/telemetry/inventory için ÜÇ
  bağımsız arka plan thread'i, `_Loop` sınıfı ile kontrollü retry/
  exponential backoff (`2,5,10,30,60`s, sonsuz agresif retry YOK) ve
  `BackendAuthenticationError`'da tam durma.
- `config.py` — `.env`/ortam değişkenlerinden (`BACKEND_URL`,
  `AGENT_ID`/`AGENT_TOKEN`, `HEARTBEAT_INTERVAL`/`TELEMETRY_INTERVAL`/
  `INVENTORY_INTERVAL`, `VERIFY_TLS`, `MAX_PROCESSES_REPORTED`)
  yapılandırma; stdlib-only minik bir `.env` loader (`python-dotenv`
  bağımlılığı eklenmedi).
- `client.py` — `BackendClient`, stdlib `urllib.request` üzerinden
  (bkz. `docs/decisions.md` §13 — bilinçli olarak `requests`/`httpx`
  kullanmıyor) `register`/`heartbeat`/`send_telemetry`/`send_inventory`
  /`test_connection`; `VERIFY_TLS=false` yalnızca bu client'a özgü bir
  `ssl.SSLContext` ile (global bir sertifika doğrulama değişikliği
  YAPILMAZ).
- `authentication.py` — kayıt sonrası `{agent_id, token}`'ı yerel bir
  dosyaya (`AGENT_STATE_FILE`) kalıcı yazar (her başlatmada yeniden
  kayıt OLMASIN diye), `redact_token()` token'ı hiçbir log/debug
  çıktısında tam göstermez.
- `collectors/` — `system.py` (hostname/FQDN/machine id/boot time/OS),
  `cpu.py`, `memory.py`, `disk.py`, `network.py` (interface tipini
  ethernet/wifi/loopback/docker/virtual/vpn/other olarak sınıflandırır,
  bkz. `docs/decisions.md` §13), `processes.py` (yalnızca PID/isim/
  CPU%/memory%/kullanıcı/durum — command-line KASITLI olarak YOK),
  `services.py` (Windows/Linux'a `platform/` üzerinden devreder).
  Hepsi `psutil` (tek runtime bağımlılığı) üzerine kurulu; her collector
  kendi hatasını yutar (`try/except` + boş/`None` dönüş) — bir
  collector'ın başarısızlığı diğerlerini veya agent'ın kendisini
  ÇÖKERTMEZ.
- `platform/{windows,linux}.py` — yalnızca GERÇEKTEN platforma özgü
  kod (Windows: registry `MachineGuid`, `psutil.win_service_iter()`;
  Linux: `/etc/machine-id`, `systemctl list-units`, `/sys/class/dmi/id/
  *` donanım bilgisi). `agent/platform/__init__.py::resolve()` çağıran
  tarafın `sys.platform`'a göre doğru modülü seçmesini sağlar.
- `telemetry.py`/`inventory.py`/`heartbeat.py` — collector çıktılarını
  backend'in `AgentTelemetryRequest`/`AgentInventoryRequest`/
  `AgentHeartbeatRequest` şemasına birebir uyan bir payload'a
  toplar (Telemetry ≠ Inventory ayrımı, bkz. §7 `agent_telemetry`/
  `agent_inventory` tabloları).

**Backend tarafında YENİ bir route eklenmedi** — Faz 30, Faz 28'de
oluşturulan `POST /api/agents/{register,heartbeat,telemetry,
inventory}` sözleşmesini AYNEN kullanır. Yalnızca payload'lar
zenginleşti (additive Pydantic alanları — `AgentInventoryRequest.
processes`, `AgentRegistrationRequest.fqdn`, `NetworkInterfaceSample.
addresses`/`.interface_type`, `AgentSummary.local_ip` — hiçbiri
`network_interfaces`/`processes` gibi JSONB sütunlar için migration
GEREKTİRMEDİ; `agents.fqdn` ve `agent_inventory.processes` additive
`ADD COLUMN IF NOT EXISTS` ile eklendi, bkz. `docs/decisions.md` §13).

**Frontend:** `/agents` (`AgentsList.tsx` — durum/hostname/OS/IP/
versiyon/son heartbeat/bağlı asset), `/agents/[id]`
(`AgentDetailView.tsx` — Genel Bakış/Sistem/CPU/Bellek/Disk/Ağ/
Süreçler/Servisler sekmeleri, hiçbir veri yoksa dürüst "veri mevcut
değil" mesajları), `AssetDetails`'e yeni Agent sekmesi
(`AssetAgentPanel.tsx` — bu asset'e `agents.asset_id` ile bağlı bir
agent var mı gösterir, `GET /api/agents` client-side filtrelenir, ayrı
bir "asset_id'ye göre agent" endpoint'i YOK), Dashboard'a Agent Health
widget'ı (`AgentHealthSummary.tsx` + `lib/agentHealth.ts` — gerçek
online/offline/unknown sayıları).

## 8. Güvenlik Sınırları

- Discovery Engine yalnızca kullanıcının açıkça girdiği CIDR aralığını
  tarar; otomatik/örtük geniş ağ taraması yapılmaz.
- Ham socket (ICMP/ARP) gerektiren işlemler için gereken yetkiler backend
  process'inde izole edilir; frontend'in bu yetkilere hiçbir zaman
  erişimi olmaz.
- Web, backend'e yalnızca REST API üzerinden bağlanır; veritabanına veya
  discovery katmanına doğrudan erişimi yoktur.
- SNMP community string'leri, gelecekteki kimlik bilgileri ve Claude API
  key'i yalnızca backend `.env` dosyasında tutulur; koda, frontend'e veya
  loglara yazılmaz.
- Cihaz/tarama verisi loglanırken kimlik bilgisi (SNMP community, API key
  vb.) asla log'a yazılmaz.
- Agent bearer token'ı (Faz 28) DB'de yalnızca SHA-256 hash'i olarak
  tutulur; Agent süreci tarafında da (Faz 30) token hiçbir log/debug
  çıktısında tam olarak gösterilmez (`agent/authentication.py::
  redact_token`). Process collector command-line argümanlarını hiç
  toplamaz (credential/token içerebilir).

## 9. İleri Faz Mimari Notları (kapsam dışı, referans amaçlı)

- **SNMP:** SNMPv2c (Faz 22.2), SNMPv3 (Faz 22.4), polling engine (Faz
  23), `GET /api/monitoring` (Faz 24), SNMP-tabanlı alert kuralları
  (Faz 26, `lib/alerts.ts`), `/monitoring` sayfasının gerçek veriye
  bağlanması (Faz 27 kısmi), `snmp_profiles` Configuration Center (Faz
  29) ve Asset↔Profile ilişkisi + gerçek asset polling entegrasyonu
  (Faz 29.5, `asset_snmp_profiles`) tamamlandı (bkz. §7, §7.1, §6.1,
  §10.4/§10.5). Kalan iş: Dashboard (`/`) widget'larını ve `AlertsList`/
  `AlertsPanel`'i (Faz 26'nın `monitoring` parametresi) gerçek veriye
  bağlamak (Faz 27'nin geri kalanı), periyodik/zamanlanmış poll döngüsü
  (Faz 30+), gerçek cihazda (v2c veya v3) canlı doğrulama (kullanıcı
  henüz bir hedef vermedi).
- **AI (Claude API):** backend'de ayrı bir sorgu endpoint'i; veritabanı
  içeriğini doğal dille sorgulamaya izin verir. Discovery Engine'den
  bağımsız, salt-okunur bir tüketicidir.
- **Auth/RBAC:** MVP'de yoktur; ileri fazda API katmanına eklenecektir.
