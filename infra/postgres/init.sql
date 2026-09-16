-- assets tablosu — discovery tarafından keşfedilen cihazların kalıcı
-- kaydı (bkz. FAZ 3.1). Bu dosya `app/db/assets.py` tarafından runtime'da
-- okunup çalıştırılır (`ensure_schema`) — tek doğruluk kaynağıdır, ayrıca
-- Docker init script'i olarak da kullanılabilir. Tekrar çalıştırmak
-- güvenlidir (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_address INET NOT NULL,
    hostname TEXT,
    mac_address TEXT,
    vendor TEXT,
    device_type TEXT NOT NULL DEFAULT 'unknown',
    confidence TEXT NOT NULL DEFAULT 'low',
    status TEXT NOT NULL,
    latency_ms DOUBLE PRECISION,
    open_ports JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_seen TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT assets_ip_address_key UNIQUE (ip_address)
);

CREATE INDEX IF NOT EXISTS idx_assets_mac_address ON assets (mac_address);
CREATE INDEX IF NOT EXISTS idx_assets_device_type ON assets (device_type);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets (status);
CREATE INDEX IF NOT EXISTS idx_assets_last_seen ON assets (last_seen);

-- scans tablosu — NetworkDiscovery ile yapılan tarama çalıştırmalarının
-- geçmişi (bkz. FAZ 4.3). `app/db/scans.py` tarafından okunur/uygulanır;
-- assets şemasıyla aynı dosyada tutulur (tek doğruluk kaynağı).
CREATE TABLE IF NOT EXISTS scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cidr TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION,
    hosts_scanned INTEGER NOT NULL DEFAULT 0,
    hosts_discovered INTEGER NOT NULL DEFAULT 0,
    open_ports INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scans_started_at ON scans (started_at);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans (status);

-- agents tablosu — Windows/Linux host'larda çalışan Agent'ların kaydı
-- (bkz. Faz 28). `token_hash`: agent'ın bearer token'ının SHA-256
-- hash'i — PLAINTEXT token asla saklanmaz, yalnızca kayıt anında bir
-- kez döndürülür (bkz. app/agents/authentication.py). `asset_id`:
-- nullable, `agents` ile mevcut `assets` tablosu arasında GÜVENİLİR bir
-- eşleştirme (hostname/IP/MAC) yapılmadan asla otomatik doldurulmaz
-- (bkz. Faz 29) — MVP'de her zaman NULL.
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname TEXT NOT NULL,
    fqdn TEXT,
    os TEXT NOT NULL,
    os_version TEXT,
    architecture TEXT,
    agent_version TEXT NOT NULL,
    local_ip TEXT,
    mac_address TEXT,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    token_hash TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat_at TIMESTAMPTZ,
    last_heartbeat_uptime_seconds DOUBLE PRECISION,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT agents_token_hash_key UNIQUE (token_hash)
);

-- `fqdn` Faz 30'da eklendi — Faz 28'de oluşturulan `agents` tablosuna
-- (zaten var olan gerçek/geliştirme veritabanları için) additive kolon.
ALTER TABLE agents ADD COLUMN IF NOT EXISTS fqdn TEXT;

CREATE INDEX IF NOT EXISTS idx_agents_hostname ON agents (hostname);
CREATE INDEX IF NOT EXISTS idx_agents_asset_id ON agents (asset_id);
CREATE INDEX IF NOT EXISTS idx_agents_last_heartbeat_at ON agents (last_heartbeat_at);

-- agent_telemetry — yüksek frekanslı (CPU/RAM/disk/network) örnekler.
-- Bilinçli olarak normalize edilmedi (disk/network listeleri JSONB) —
-- MVP'de retention/aggregation POLİTİKASI henüz yok (bkz.
-- docs/decisions.md §12); bu, gerçek periyodik toplama (Faz 38
-- Scheduler) devreye girmeden önce netleştirilmesi gereken ayrı bir
-- karar olarak işaretlendi.
CREATE TABLE IF NOT EXISTS agent_telemetry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    collected_at TIMESTAMPTZ NOT NULL,
    cpu_percent DOUBLE PRECISION,
    memory_total_bytes BIGINT,
    memory_used_bytes BIGINT,
    memory_percent DOUBLE PRECISION,
    disks JSONB NOT NULL DEFAULT '[]'::jsonb,
    network_interfaces JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Faz 34 — User Sessions Tracking. `sessions_json`: açık oturumların
    -- ham listesi (username/session_name/status/logon_time, bkz.
    -- `apps/agent/agent/collectors/sessions.py`). `last_logged_in_user`/
    -- `active_sessions_count` agent tarafında `sessions_json`'dan
    -- TÜRETİLİR (backend burada ayrıca hesaplama YAPMAZ) — yalnızca
    -- hızlı okuma için ayrı sütunlarda da tutulur.
    sessions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_logged_in_user TEXT,
    active_sessions_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_telemetry_agent_id_collected_at
    ON agent_telemetry (agent_id, collected_at DESC);

-- Zaten var olan gerçek/geliştirme veritabanları için idempotent ekleme
-- (bkz. `agent_inventory.processes`'daki aynı gerekçe/desen).
ALTER TABLE agent_telemetry ADD COLUMN IF NOT EXISTS sessions_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE agent_telemetry ADD COLUMN IF NOT EXISTS last_logged_in_user TEXT;
ALTER TABLE agent_telemetry ADD COLUMN IF NOT EXISTS active_sessions_count INTEGER;

-- agent_inventory — seyrek değişen envanter (donanım/OS/network/
-- software/services). Bilinçli olarak agent başına TEK satır (tarihçe
-- tutulmuyor, her yeni inventory eskisinin üzerine yazar) — envanter
-- zaman serisi değil, "şu anki durum" anlamına gelir.
CREATE TABLE IF NOT EXISTS agent_inventory (
    agent_id UUID PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    hardware JSONB,
    os JSONB,
    network_interfaces JSONB NOT NULL DEFAULT '[]'::jsonb,
    software JSONB NOT NULL DEFAULT '[]'::jsonb,
    services JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- processes — Faz 30, additive. Command-line argümanları KASITLI
    -- olarak burada YOK (credential/token içerebilir, bkz.
    -- docs/decisions.md). Tarihçe tutulmaz — `agent_inventory`'nin
    -- geri kalanı gibi "şu anki durum".
    processes JSONB NOT NULL DEFAULT '[]'::jsonb,
    collected_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- `agent_inventory` Faz 28'de oluşturuldu — `processes` sütunu Faz
-- 30'da eklendi. `CREATE TABLE IF NOT EXISTS` zaten var olan bir
-- tabloya yeni sütun eklemez; bu yüzden zaten uygulanmış (Faz 28-29.5)
-- gerçek/geliştirme veritabanları için ayrı, idempotent bir
-- `ALTER TABLE` gerekiyor. Mevcut satırlara (varsa) dokunmaz, yalnızca
-- eksikse sütunu ekler.
ALTER TABLE agent_inventory ADD COLUMN IF NOT EXISTS processes JSONB NOT NULL DEFAULT '[]'::jsonb;

-- agent_windows_updates — Windows Update Tarama Motoru (agent
-- lifecycle/updates increment). `agent_inventory` ile AYNI desen —
-- agent başına TEK satır, tarihçe TUTULMAZ ("şu anki tarama sonucu").
-- Yalnızca Windows agent'ları bu satırı yazar (`scan_method`, agent'ın
-- birincil COM taramasını mı yoksa yedek PowerShell yöntemini mi
-- kullandığını AÇIKÇA taşır — ikisi FARKLI anlam taşır, bkz. `apps/
-- agent/agent/collectors/windows_updates.py` docstring'i: COM
-- BEKLEYEN güncellemeleri, yedek yöntem ZATEN KURULMUŞ hotfix'leri
-- döner. Frontend/kullanıcı bu ikisini ASLA karıştırmamalı).
CREATE TABLE IF NOT EXISTS agent_windows_updates (
    agent_id UUID PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    collected_at TIMESTAMPTZ NOT NULL,
    scan_method TEXT NOT NULL CHECK (scan_method IN ('com', 'installed_hotfixes', 'unavailable')),
    is_admin BOOLEAN NOT NULL,
    updates JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Bir taramanın kısmen/tamamen başarısız olduğu durumları dürüstçe
    -- taşır (ör. COM başarısız oldu, yedek yönteme düşüldü) — `NULL`
    -- ise tarama tamamen başarılı.
    error TEXT,
    -- `Microsoft.Update.SystemInfo().RebootRequired` — makinenin GENEL
    -- bekleyen yeniden başlatma durumu, HER taramada TAZE sorgulanır
    -- (bkz. `apps/agent/agent/collectors/windows_updates.py::
    -- _query_reboot_required`). Kendi başımıza elle bir bayrak tutup
    -- bayatlamasına izin vermek yerine agent HER seferinde gerçek
    -- durumu sorar.
    reboot_required BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Zaten var olan gerçek/geliştirme veritabanları için idempotent ekleme
-- (bkz. `agent_inventory.processes`'daki aynı gerekçe/desen).
ALTER TABLE agent_windows_updates ADD COLUMN IF NOT EXISTS reboot_required BOOLEAN NOT NULL DEFAULT false;

-- agent_enrollment_codes — Faz 31. Self-service registration'ın
-- sertleştirilmesi: `POST /api/agents/register` artık geçerli, süresi
-- dolmamış, daha önce kullanılmamış bir kod ister (bkz.
-- docs/decisions.md). Kod insan-okur, kısa ömürlü (varsayılan 10dk) ve
-- TEK KULLANIMLIKTIR — `used_at` dolduktan sonra bir daha tüketilemez.
-- Bir credential/secret DEĞİLDİR (tek başına hiçbir kaynağa erişim
-- vermez, yalnızca "bu kayıt insan tarafından başlatıldı" iddiasını
-- doğrular) — bu yüzden plaintext saklanması güvenlik ilkesini ihlal
-- etmez (bkz. `secrets.py`/token modeliyle KARIŞTIRILMAMALI).
CREATE TABLE IF NOT EXISTS agent_enrollment_codes (
    code TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by_agent_id UUID REFERENCES agents(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_enrollment_codes_expires_at
    ON agent_enrollment_codes (expires_at);

-- snmp_profiles — kullanıcının Settings > SNMP Configuration Center
-- üzerinden yönettiği kalıcı SNMP hedef profilleri (bkz. Faz 29,
-- docs/decisions.md §10.3). `assets` tablosuna KASITLI olarak bağlı
-- DEĞİL — `target_host` (IP/hostname) ile doğrudan tanımlanır; bir
-- asset ile ilişkilendirme (varsa) ayrı, açık bir eşleştirme adımı
-- gerektirir (bkz. `docs/decisions.md`, otomatik/belirsiz eşleştirme
-- yapılmaz). Hiçbir sütun gerçek secret DEĞERİ taşımaz — yalnızca
-- `*_ref` (bir `.env` değişken adı) alanları var; gerçek değer
-- `app/snmp/secrets.py::resolve_secret()` ile yalnızca poll/test anında
-- okunur.
CREATE TABLE IF NOT EXISTS snmp_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    target_host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 161,
    version TEXT NOT NULL,
    timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 2.0,
    retries INTEGER NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT true,
    -- v2c
    community_ref TEXT,
    -- v3
    username TEXT,
    auth_protocol TEXT,
    auth_credential_ref TEXT,
    priv_protocol TEXT,
    priv_credential_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT snmp_profiles_name_key UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_snmp_profiles_target_host ON snmp_profiles (target_host);
CREATE INDEX IF NOT EXISTS idx_snmp_profiles_enabled ON snmp_profiles (enabled);

-- asset_snmp_profiles — Asset ↔ SNMP Profile ilişki tablosu (Faz 29.5,
-- bkz. docs/decisions.md §10.5). Bir profil BİRDEN FAZLA asset'e
-- atanabilir (community/credential paylaşımı — ör. aynı "Core Switches
-- v2c" profili 10 switch'e atanabilir); bir asset'in aynı anda en
-- fazla BİR aktif profili olabilir (`asset_id PRIMARY KEY` bunu
-- garanti eder — ikinci bir atama INSERT değil güncelleme/hata olur).
-- Gerçek poll HER ZAMAN `assets.ip_address`'i hedef alır — bu tablo
-- yalnızca HANGİ credential/config'in kullanılacağını belirler,
-- `snmp_profiles.target_host` asset-bağlı poll'da hiç okunmaz (yalnızca
-- profilin kendi bağımsız "Test Connection"ı için kullanılır).
CREATE TABLE IF NOT EXISTS asset_snmp_profiles (
    asset_id UUID PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    snmp_profile_id UUID NOT NULL REFERENCES snmp_profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_asset_snmp_profiles_profile
    ON asset_snmp_profiles (snmp_profile_id);

-- agent_commands — Faz 33: uzaktan process kill / service control.
-- Hem KUYRUK (agent henüz almadığı komutlar `status='pending'` olarak
-- burada bekler, agent'ın command-poll döngüsü çeker) HEM DE minimal
-- AUDIT İZİ (kim/ne zaman/hangi hedefe/ne sonuçla) olarak tek tabloda
-- tutuluyor — ayrı bir audit-log tablosu YARATILMADI (kullanıcının
-- "minimal audit log" tercihiyle tutarlı, bkz. docs/decisions.md §17).
-- Kritik süreç/servis KORUMASI burada değil, agent tarafında
-- uygulanır (`apps/agent/agent/commands.py`) — backend hedef
-- makinenin gerçek süreç/servis isimlerini BİLEMEZ.
CREATE TABLE IF NOT EXISTS agent_commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    -- `refresh_inventory` (Faz 33.1) — hedef bir süreç/servis DEĞİL,
    -- agent'a "envanterini HEMEN gönder" der. UI'nin "Yenile" butonu
    -- (kullanıcı bildirimi: yeni açılan bir process/durdurulan bir
    -- servis normal 5 dakikalık envanter turu dolana kadar ekranda
    -- görünmüyordu) bunu kullanır — `target` bu komut tipi için
    -- anlamsız, sabit `'inventory'` yazılır.
    -- `power_control` (Faz 37) — Güç ve Oturum Yönetimi (reboot/shutdown/
    -- logoff). Aynı kuyruk/audit mekanizması, yeni bir tablo/model YOK.
    -- `uninstall_service`/`update_self` — Agent Yaşam Döngüsü Yönetimi.
    -- `uninstall_service`: agent kendi Windows Servisini durdurup siler
    -- (Linux'ta desteklenmez — sistemdeki servis hesabının kendi
    -- servisini `systemctl`le durdurma/kaldırma yetkisi olmaz, bkz.
    -- `apps/agent/agent/lifecycle.py`). `update_self`: agent backend'den
    -- güncel `itops-agent.exe`'yi indirip kendi servisini değiştirir.
    -- İkisinde de `target` anlamsızdır, sabit `'self'` gönderilir.
    -- `check_updates` — Windows Update Tarama Motoru "Güncellemeleri
    -- Kontrol Et" butonu (`refresh_inventory` ile AYNI desen, `target`
    -- anlamsız, sabit `'self'`).
    -- `install_update` — Windows Update Yükleme. `target`: belirli bir
    -- KB numarası (ör. `'KB5001234'`) veya bekleyen TÜM güncellemeler
    -- için `'all'`. GERİ DÖNÜŞÜ OLMAYAN, GERÇEK bir sistem değişikliği
    -- — `kill_process`/`service_control`/`power_control` ile AYNI
    -- onay-modalı zorunluluğu frontend'de uygulanır.
    command_type TEXT NOT NULL CHECK (command_type IN ('kill_process', 'service_control', 'refresh_inventory', 'power_control', 'uninstall_service', 'update_self', 'check_updates', 'install_update')),
    action TEXT NOT NULL CHECK (action IN ('kill', 'start', 'stop', 'restart', 'collect', 'reboot', 'shutdown', 'logoff', 'uninstall', 'update', 'scan', 'install')),
    target TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'succeeded', 'failed', 'rejected')),
    result_detail TEXT,
    requested_by TEXT,
    -- `clock_timestamp()` (`now()` DEĞİL) — aynı transaction içinde ardışık
    -- INSERT'lerin GERÇEKTEN farklı zaman damgası alması için (bkz.
    -- `asset_snmp_profiles`'daki aynı gerekçe, test izolasyonu tek bir
    -- transaction'da çalışıyor, `now()` transaction başlangıcında SABİTLENİR).
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    sent_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_commands_agent_status ON agent_commands (agent_id, status);

-- Zaten var olan gerçek/geliştirme veritabanları için: `CREATE TABLE
-- IF NOT EXISTS` yeni CHECK değerlerini eklemez — `uninstall_service`/
-- `update_self`/`uninstall`/`update` eklenmeden önce oluşturulmuş bir
-- tabloda bu INSERT'ler reddedilirdi. İdempotent DROP+ADD (aynı isim
-- her zaman `<tablo>_<kolon>_check` — Postgres'in varsayılan otomatik
-- adlandırması, elle bir isim VERİLMEDİĞİ için).
ALTER TABLE agent_commands DROP CONSTRAINT IF EXISTS agent_commands_command_type_check;
ALTER TABLE agent_commands ADD CONSTRAINT agent_commands_command_type_check
    CHECK (command_type IN ('kill_process', 'service_control', 'refresh_inventory', 'power_control', 'uninstall_service', 'update_self', 'check_updates', 'install_update'));
ALTER TABLE agent_commands DROP CONSTRAINT IF EXISTS agent_commands_action_check;
ALTER TABLE agent_commands ADD CONSTRAINT agent_commands_action_check
    CHECK (action IN ('kill', 'start', 'stop', 'restart', 'collect', 'reboot', 'shutdown', 'logoff', 'uninstall', 'update', 'scan', 'install'));

-- Agent Yaşam Döngüsü Yönetimi — arşivleme (soft-delete). Mevcut
-- `revoked_at` (Faz 28, token iptali) alanıyla BİRLİKTE kullanılır:
-- bir agent arşivlendiğinde (elle veya inaktiflik yüzünden otomatik)
-- `revoked_at` de doldurulur — arşivlenmiş bir agent artık kimlik
-- doğrulayıp heartbeat/telemetry gönderemez. Geri yükleme (`restore`)
-- HEPSİNİ birlikte temizler. Ayrı bir `archived_agents`/`agent_history`
-- tablosu YERİNE bilinçli olarak AYNI `agents` satırında soft-delete
-- tercih edildi — ayrı bir tabloya kopyalama hem restore'u kırılgan
-- hale getirirdi (agent'ın gerçek `id`'si/token'ı ve tüm telemetry/
-- inventory geçmişi FK CASCADE ile silinirdi) hem de veri
-- tekrarına yol açardı; gereken tüm bilgi (hostname/IP/OS, ilk kayıt,
-- son heartbeat, arşivlenme zamanı/sebebi) zaten aynı satırda mevcut.
ALTER TABLE agents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS archived_reason TEXT
    CHECK (archived_reason IN ('manual', 'inactivity'));
-- Yalnızca `archived_reason = 'inactivity'` için anlamlı — hangi
-- politika eşiğiyle (kaç gün) arşivlendiğini kayıt altına alır (UI
-- "X gündür inaktiflik sebebiyle" cümlesini BUNDAN türetir, sabit bir
-- Türkçe metin veritabanında SAKLANMAZ).
ALTER TABLE agents ADD COLUMN IF NOT EXISTS archived_after_inactive_days INTEGER;

CREATE INDEX IF NOT EXISTS idx_agents_archived_at ON agents (archived_at);

-- agent_retention_policy — Ayarlar'daki "İnaktif Agent Otomatik
-- Temizleme" politikası. Tek satırlık bir yapılandırma tablosu (`id
-- = 1` CHECK ile zorlanır) — `snmp_profiles`/`asset_snmp_profiles`
-- gibi çok satırlı bir tablo DEĞİL, global tek bir ayar. Varsayılan
-- `enabled = false` — `ENABLE_REMOTE_COMMANDS` ile AYNI opt-in ilkesi,
-- kullanıcı açıkça etkinleştirmeden hiçbir agent otomatik
-- arşivlenmez/silinmez.
CREATE TABLE IF NOT EXISTS agent_retention_policy (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT false,
    retention_days INTEGER NOT NULL DEFAULT 30 CHECK (retention_days > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- Faz 46 — Ayrıcalıklı Erişim Yönetimi (PAM) + Rol Tabanlı
-- Yetkilendirme (RBAC).
--
-- Bu proje şimdiye kadar HİÇBİR kullanıcı girişi/kimlik doğrulaması
-- olmadan çalışıyordu (bkz. docs/decisions.md §17 — bilinen, kabul
-- edilmiş bir risk). PAM/RBAC bunun ÖNKOŞULU olan gerçek bir kullanıcı
-- sistemi olmadan var olamaz — bu yüzden `users` tablosu ve JWT tabanlı
-- girişin KENDİSİ de bu fazın parçası (kullanıcının "mevcut JWT auth
-- yapısıyla entegre et" talimatı, GERÇEKTE var olmayan bir altyapıyı
-- varsayıyordu — bu faz onu da inşa ediyor, uydurmuyor).
--
-- Kasıtlı kapsam dışı (gerekçeler docs/roadmap.md Faz 46 notunda):
-- - RDP için "zero-knowledge" tarayıcı-içi oturum enjeksiyonu
--   (Guacamole/guacd sınıfı ayrı bir altyapı gerektirir, bu artırımda
--   KURULMADI) — RDP mevcut Faz 34 `.rdp` indirme akışında KALIYOR.
-- - `group_id` bazlı kural ataması (kullanıcı grupları KAVRAMI hiç
--   yok) — yalnızca `user_id` bazlı kurallar.
-- - Parola/anahtar rotasyonu otomasyonu.
-- ============================================================

-- users — Faz 46. Parola HER ZAMAN bcrypt hash'i olarak saklanır, asla
-- düz metin. `role`, RBAC'ın tek doğruluk kaynağı: ADMIN (PAM
-- yönetim ekranlarına erişir) / OPERATOR (kendisine PAM ile atanmış
-- sunuculara bağlanabilir) / VIEWER (yalnızca okuma, PAM bağlantısı
-- yok).
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'VIEWER' CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER')),
    full_name TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- vault_credentials — PAM kimlik bilgisi kasası. `encrypted_payload`
-- Fernet (AES-128-CBC + HMAC-SHA256, `cryptography` kütüphanesi —
-- zaten `asyncssh`'in bağımlılığı, YENİ bir kriptografi kütüphanesi
-- EKLENMEDİ) ile şifrelenir; anahtar YALNIZCA `.env`'de
-- (`PAM_VAULT_SECRET_KEY`) — asla DB'de/kodda/loglarda. `credential_
-- type='password'` için payload `{"password": "..."}`, `'ssh_key'`
-- için `{"private_key": "...", "passphrase": "..."}` (JSON, şifreleme
-- ÖNCESİ). Düz metin şifre/anahtar bu tablonun HİÇBİR sütununda
-- SAKLANMAZ.
CREATE TABLE IF NOT EXISTS vault_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    credential_type TEXT NOT NULL CHECK (credential_type IN ('password', 'ssh_key')),
    username TEXT NOT NULL,
    domain TEXT,
    encrypted_payload TEXT NOT NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- pam_access_rules — kullanıcı ↔ asset ↔ kasa hesabı ilişkisi + süreli/
-- kapsamlı erişim izni. Bir kullanıcının bir asset için EN FAZLA bir
-- kuralı olabilir (UNIQUE) — güncellemek isteyen Admin mevcut kuralı
-- DÜZENLER, çakışan ikinci bir kural OLUŞTURULMAZ.
CREATE TABLE IF NOT EXISTS pam_access_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    credential_id UUID NOT NULL REFERENCES vault_credentials(id) ON DELETE CASCADE,
    allow_rdp BOOLEAN NOT NULL DEFAULT false,
    allow_ssh BOOLEAN NOT NULL DEFAULT false,
    -- Faz 76 — PAM Web Konsolu (zero-knowledge HTTPS kimlik enjeksiyonu).
    allow_web BOOLEAN NOT NULL DEFAULT false,
    max_session_duration_mins INTEGER NOT NULL DEFAULT 60 CHECK (max_session_duration_mins > 0),
    -- `NULL` = süresiz (Admin bilinçli olarak süre sınırı KOYMADI).
    valid_until TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_pam_access_rules_user ON pam_access_rules (user_id);
CREATE INDEX IF NOT EXISTS idx_pam_access_rules_asset ON pam_access_rules (asset_id);

-- pam_session_logs — denetim izi (Session Audit Log). Kimlik bilgisi
-- DEĞERİ ASLA yazılmaz — yalnızca HANGİ kasa kaydının (`credential_id`)
-- kullanıldığı. `ended_at`/`end_reason` NULL iken oturum "aktif" sayılır
-- (`/pam/audit`'in "Aktif Oturumlar" filtresi bunu kullanır).
CREATE TABLE IF NOT EXISTS pam_session_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    credential_id UUID REFERENCES vault_credentials(id) ON DELETE SET NULL,
    -- Faz 76 — 'web' (PAM Web Konsolu, zero-knowledge HTTPS proxy).
    protocol TEXT NOT NULL CHECK (protocol IN ('ssh', 'rdp', 'web')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    ended_at TIMESTAMPTZ,
    -- 'user_closed' | 'timeout' | 'error' | 'revoked' — asla serbest
    -- metin Türkçe (frontend i18n'den çevirir, bkz. proje konvansiyonu).
    end_reason TEXT,
    client_ip TEXT
);

CREATE INDEX IF NOT EXISTS idx_pam_session_logs_user_started ON pam_session_logs (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pam_session_logs_active ON pam_session_logs (ended_at) WHERE ended_at IS NULL;

-- ============================================================
-- Faz 47 — İnce taneli izin (permission) modeli. `users.role` (ADMIN/
-- OPERATOR/VIEWER) TEK BAŞINA yeterli değil — kullanıcının isteği açıkça
-- kişi bazında override edilebilir bir yetki seti (ör. yalnızca
-- `PAM_ACCESS` olan, Dashboard dahil hiçbir genel menüyü göremeyen
-- kısıtlı bir kullanıcı). İzin KATALOĞU kod içinde sabit (`app/auth/
-- permissions.py::ALL_PERMISSIONS`) — bu tablo yalnızca HANGİ
-- kullanıcının HANGİ izne sahip olduğunu tutar, yeni izin TİPİ
-- tanımlamaz.
-- ============================================================

CREATE TABLE IF NOT EXISTS user_permissions (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    PRIMARY KEY (user_id, permission)
);

-- ============================================================
-- Faz 49 — LDAP / Active Directory Entegrasyonu.
--
-- Bu proje LDAP-tabanlı GİRİŞ (bind auth) UYGULAMAMAKTADIR — kullanıcı
-- girişi Faz 46'dan beri hâlâ yerel bcrypt (`users.password_hash`).
-- Buradaki entegrasyon YALNIZCA: (1) AD kullanıcı/grup DİZİNİNİ
-- periyodik olarak senkronize edip PAM'in "Kullanıcı/Grup Seçimi"
-- ekranında göstermek, (2) bir yerel `users` satırını (`ad_username`
-- ile) bir AD hesabına BAĞLAMAK, (3) o bağlı kullanıcının AD grup
-- üyeliklerinden gelen `pam_access_rules` satırlarını da yetkilendirme
-- sırasında dikkate almak. Gerçek LDAP SSO/bind-auth login KASITLI
-- olarak kapsam dışı — ayrı, çok daha büyük bir güvenlik yüzeyi
-- (kullanıcı kimlik doğrulamasının kendisini AD'ye devretmek).
-- ============================================================

-- ldap_config — tek satırlık yapılandırma (agent_retention_policy ile
-- AYNI desen). `encrypted_bind_password` `vault_credentials` ile AYNI
-- Fernet anahtarını (`PAM_VAULT_SECRET_KEY`) kullanır — YENİ bir
-- şifreleme anahtarı EKLENMEDİ, aynı "PAM kasası" güvenlik sınırının
-- doğal bir uzantısı (bkz. app/services/ldap.py).
CREATE TABLE IF NOT EXISTS ldap_config (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 389 CHECK (port > 0 AND port <= 65535),
    use_ssl BOOLEAN NOT NULL DEFAULT false,
    domain_fqdn TEXT NOT NULL,
    base_dn TEXT NOT NULL,
    bind_dn TEXT NOT NULL,
    encrypted_bind_password TEXT NOT NULL,
    -- 'success' | 'error' | NULL (hiç senkronize edilmedi) — ham hata
    -- metni `last_sync_error`'da, asla kimlik bilgisi İÇERMEZ.
    last_sync_status TEXT,
    last_sync_error TEXT,
    last_sync_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ad_groups / ad_users / ad_group_memberships — AD dizininin salt-okunur
-- bir YANSIMASI (cache). Her senkronizasyonda mevcut kayıtlar
-- GÜNCELLENİR, AD'de artık bulunmayanlar SİLİNİR (`app/services/
-- ldap.py::sync_directory` — tam, idempotent bir senkronizasyon).
CREATE TABLE IF NOT EXISTS ad_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distinguished_name TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ad_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distinguished_name TEXT NOT NULL UNIQUE,
    -- sAMAccountName — `users.ad_username` bununla eşleşir.
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Yalnızca DOĞRUDAN (`memberOf`) üyelikler — iç içe (nested) AD grup
-- çözümlemesi KASITLI olarak kapsam dışı (bkz. app/services/ldap.py
-- docstring'i).
CREATE TABLE IF NOT EXISTS ad_group_memberships (
    ad_user_id UUID NOT NULL REFERENCES ad_users(id) ON DELETE CASCADE,
    ad_group_id UUID NOT NULL REFERENCES ad_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (ad_user_id, ad_group_id)
);

-- Bir yerel `users` satırını bir AD hesabına BAĞLAMAK için — admin
-- panelinden ELLE yapılan bir eşleme, otomatik/örtük DEĞİL (Faz 46'nın
-- Agent↔Asset eşleştirmesindeki "en az 2 sinyal olmadan otomatik
-- eşleştirme yok" temkinliliğiyle AYNI ilke).
ALTER TABLE users ADD COLUMN IF NOT EXISTS ad_username TEXT REFERENCES ad_users(username) ON DELETE SET NULL;

-- pam_access_rules artık bir AD GRUBUNU da hedefleyebilir — `user_id`
-- NULLABLE'a çevrildi, yeni `ad_group_id` eklendi; TAM OLARAK biri
-- dolu olmalı (CHECK). Mevcut UNIQUE(user_id, asset_id) NULL'ları
-- ayrı satırlar saydığı için (Postgres UNIQUE semantiği) grup bazlı
-- satırları ETKİLEMEZ — onlar için ayrı bir UNIQUE(ad_group_id,
-- asset_id) ekleniyor.
ALTER TABLE pam_access_rules ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE pam_access_rules ADD COLUMN IF NOT EXISTS ad_group_id UUID REFERENCES ad_groups(id) ON DELETE CASCADE;

DO $$ BEGIN
    ALTER TABLE pam_access_rules
        ADD CONSTRAINT pam_access_rules_user_xor_group
        CHECK ((user_id IS NOT NULL) <> (ad_group_id IS NOT NULL));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- `ADD CONSTRAINT ... UNIQUE` bir isimdeş destek INDEX de oluşturur —
-- ikinci çalıştırmada Postgres bunu `duplicate_object` (42710, CHECK
-- kısıtları için beklenen) DEĞİL, `duplicate_table` (42P07, isimdeş
-- INDEX/relation çakışması) ile reddeder; gerçekten çalıştırılıp
-- bulunan bir hata — CHECK kısıtıyla AYNI idempotent kalıp burada her
-- iki hata sınıfını da yakalamalı.
DO $$ BEGIN
    ALTER TABLE pam_access_rules ADD CONSTRAINT pam_access_rules_ad_group_asset_unique UNIQUE (ad_group_id, asset_id);
EXCEPTION
    WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_pam_access_rules_ad_group ON pam_access_rules (ad_group_id);
CREATE INDEX IF NOT EXISTS idx_ad_group_memberships_group ON ad_group_memberships (ad_group_id);

-- ============================================================
-- Faz 50 — Oturum Kaydı (Session Recording), Canlı Oturum Sonlandırma,
-- Tuş Loglama (SSH). `pam_session_logs`'a PARALEL bir tablo AÇILMADI
-- (Faz 41/49 hâlihazırdaki "mevcut tabloyu genişlet" ilkesiyle tutarlı)
-- — yalnızca iki additive kolon eklendi. "Aktif oturum" kavramı hâlâ
-- `ended_at IS NULL` — ayrı bir `status` kolonu EKLENMEDİ (gereksiz
-- state duplikasyonu olurdu); `end_reason`'a yeni bir değer
-- ('terminated_by_admin') eklenmesi yeterli.
-- ============================================================

ALTER TABLE pam_session_logs ADD COLUMN IF NOT EXISTS recording_file_path TEXT;
ALTER TABLE pam_session_logs ADD COLUMN IF NOT EXISTS terminated_by UUID REFERENCES users(id) ON DELETE SET NULL;

-- pam_keystrokes — YALNIZCA SSH. RDP metin girdisi yakalamaz (ham
-- grafik/klavye-olay protokolü) — RDP'nin kendi denetim izi zaten
-- `recording_file_path`'teki TAM ekran kaydı (guacd `.guac` dosyası,
-- bkz. app/pam/guacd.py). Her satır, tarayıcıdan gelen TEK bir
-- WebSocket "input" mesajının (xterm.js'in ürettiği ham klavye girdisi
-- — pratikte neredeyse her tuş vuruşu kendi mesajı) zaman damgalı bir
-- kopyası.
CREATE TABLE IF NOT EXISTS pam_keystrokes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES pam_session_logs(id) ON DELETE CASCADE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pam_keystrokes_session ON pam_keystrokes (session_id, recorded_at);

-- ============================================================
-- Faz 52 — LDAP Bind-Auth Girişi (opt-in) + Otomatik AD Kullanıcı
-- Provisioning. Faz 49'un YORUMU ("LDAP-tabanlı GİRİŞ KASITLI olarak
-- kapsam dışı") burada BİLİNÇLİ olarak GENİŞLETİLDİ — kullanıcının açık
-- isteğiyle. `LDAP_AUTH_ENABLED` (varsayılan false, `.env`) olmadan bu
-- yol HİÇ tetiklenmez — yerel bcrypt girişi TEK BAŞINA yeterliyken bunu
-- sessizce açmak gerçek bir yetki genişletme riski taşır.
-- ============================================================

-- `password_hash` artık NULL olabilir — bir AD hesabından otomatik
-- provision edilen kullanıcının YEREL bir parolası HİÇ yoktur (yalnızca
-- LDAP bind ile giriş yapabilir); `app/auth/service.py::login` NULL
-- hash'i asla `verify_password`'a geçirmez.
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_ad_user BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE ad_users ADD COLUMN IF NOT EXISTS email TEXT;

-- ============================================================
-- Faz 54 — PAM "Denetim Kaydı" ve "Erişim Kuralları" ekranlarının
-- kurumsal (Enterprise PAM) UI yükseltmesi. `pam_access_rules`'a bir
-- "Aktif/Pasif" anahtarı eklendi — önceden bir kuralı geçici olarak
-- devre dışı bırakmanın TEK yolu silmekti (geri dönüşü olmayan, kredi
-- bilgisi/asset/süre eşleşmesini de silen bir işlem). `is_active=false`
-- iken `app/pam/service.py::authorize_ssh_session`/`authorize_rdp_
-- session` erişimi REDDEDER — yalnızca kozmetik bir bayrak değil,
-- gerçek bir yetkilendirme kontrolü.
ALTER TABLE pam_access_rules ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

-- ============================================================
-- Faz 55 — PAM Cihaz Etiketleri (Tags) + Statik Cihaz Grupları (Server
-- Groups). Bir erişim kuralı artık TEK bir `asset_id` YERİNE bir
-- etikete veya statik bir cihaz grubuna atanabilir — 50 "Production"
-- sunucusu için 50 ayrı kural yazma zorunluluğunu kaldırır. Etiketler/
-- gruplar Discovery'nin KENDİ `assets` tablosuna YAZILMAZ (PAM'a özgü,
-- additive tablolar) — Discovery katmanının veri modeline PAM
-- kavramları sızdırılmaz (mevcut mimari ilke, docs/architecture.md §7).
-- ============================================================

CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS asset_tag_assignments (
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_tag_assignments_tag ON asset_tag_assignments (tag_id);

CREATE TABLE IF NOT EXISTS server_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Statik/elle üyelik — Faz 55'te KASITLI olarak DEĞİL: dinamik
-- (kural-tabanlı, ör. "OS == Linux AND Environment == Production")
-- gruplar ayrı, sonraki bir fazın kapsamı.
CREATE TABLE IF NOT EXISTS server_group_members (
    server_group_id UUID NOT NULL REFERENCES server_groups(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (server_group_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_server_group_members_asset ON server_group_members (asset_id);

-- `pam_access_rules.asset_id` artık NULLABLE — bir kural TEK bir
-- cihazı DEĞİL bir etiketi/cihaz grubunu hedefleyebilir. `principal`
-- (user_id/ad_group_id) XOR'u Faz 49'dan beri ZATEN var; burada "cihaz
-- hedefi" için AYNI desende yeni bir üçlü-XOR CHECK ekleniyor.
ALTER TABLE pam_access_rules ALTER COLUMN asset_id DROP NOT NULL;
ALTER TABLE pam_access_rules ADD COLUMN IF NOT EXISTS tag_id UUID REFERENCES tags(id) ON DELETE CASCADE;
ALTER TABLE pam_access_rules ADD COLUMN IF NOT EXISTS server_group_id UUID REFERENCES server_groups(id) ON DELETE CASCADE;

DO $$ BEGIN
    ALTER TABLE pam_access_rules
        ADD CONSTRAINT pam_access_rules_device_target_xor
        CHECK (
            (CASE WHEN asset_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN tag_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN server_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Faz 46/49'un `UNIQUE (user_id, asset_id)` / `(ad_group_id, asset_id)`
-- kısıtları `asset_id IS NULL` olan (etiket/grup hedefli) satırlar için
-- ETKİSİZ kalır (Postgres NULL'ları UNIQUE'te birbirinden FARKLI
-- sayar) — bu yüzden etiket/grup hedefleri için AYRI, eş-değer
-- kısıtlar gerekiyor.
DO $$ BEGIN
    ALTER TABLE pam_access_rules ADD CONSTRAINT pam_access_rules_user_tag_unique UNIQUE (user_id, tag_id);
EXCEPTION
    WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE pam_access_rules ADD CONSTRAINT pam_access_rules_user_group_unique UNIQUE (user_id, server_group_id);
EXCEPTION
    WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE pam_access_rules ADD CONSTRAINT pam_access_rules_ad_group_tag_unique UNIQUE (ad_group_id, tag_id);
EXCEPTION
    WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE pam_access_rules ADD CONSTRAINT pam_access_rules_ad_group_group_unique UNIQUE (ad_group_id, server_group_id);
EXCEPTION
    WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_pam_access_rules_tag ON pam_access_rules (tag_id);
CREATE INDEX IF NOT EXISTS idx_pam_access_rules_server_group ON pam_access_rules (server_group_id);

-- ============================================================
-- Faz 56 — PAM Erişim Talepleri (Access Requests). Onaylanan bir
-- talep KENDİ bir yetkilendirme mekanizması OLUŞTURMAZ — mevcut
-- `pam_access_rules`'u (Faz 46-55) GENİŞLETİR/OLUŞTURUR (bkz.
-- app/pam/service.py::approve_access_request) — iki paralel "kim
-- neye erişebilir" kaynağı asla olmaz.
-- ============================================================

CREATE TABLE IF NOT EXISTS pam_access_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Faz 55'in cihaz-hedefi XOR'uyla AYNI desen — TAM OLARAK biri dolu.
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    server_group_id UUID REFERENCES server_groups(id) ON DELETE CASCADE,
    -- Erişim kurallarının aksine (allow_rdp + allow_ssh ikili bayrak)
    -- bir talep TEK bir protokol ister — kullanıcının "Select Protocol"
    -- tekil akışıyla tutarlı.
    protocol TEXT NOT NULL CHECK (protocol IN ('ssh', 'rdp')),
    business_reason TEXT NOT NULL,
    requested_duration_mins INTEGER NOT NULL DEFAULT 60 CHECK (requested_duration_mins > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

DO $$ BEGIN
    ALTER TABLE pam_access_requests
        ADD CONSTRAINT pam_access_requests_device_target_xor
        CHECK (
            (CASE WHEN asset_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN tag_id IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN server_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_pam_access_requests_requester ON pam_access_requests (requester_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pam_access_requests_status ON pam_access_requests (status);

-- ============================================================
-- Faz 62 — IT Helpdesk / Arıza Yönetimi (Ticket Management).
-- PAM'den TAMAMEN BAĞIMSIZ, additive bir modül — mevcut hiçbir
-- tabloya dokunmaz. `created_by`/`assigned_to` `users`'a bağlıdır
-- (Faz 46 auth); erişim `TICKETS_VIEW` iznine tabidir (Faz 47).
-- `ticket_number` (`INC-YYYY-NNNN`) yıl bazlı atomik bir sayaçtan
-- (`ticket_number_seq`) üretilir; `sla_due_at` oluşturma anında
-- önceliğe göre hesaplanır (bkz. app/tickets/service.py).
-- ============================================================

CREATE TABLE IF NOT EXISTS ticket_number_seq (
    year INTEGER PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0
);

-- Faz 63 — dinamik Departman + Kategori taksonomisi. Faz 62'nin sabit
-- `category` enum'ı (6 değer) kaldırıldı; kategori/departman artık admin
-- panelinden yönetilen satırlar. "Silme" = soft-delete (`is_active =
-- false`) çünkü mevcut biletler bunları FK ile referanslıyor; aynı adı
-- yeniden eklemek pasif satırı yeniden aktifleştirir (bkz. app/tickets/
-- service.py).
CREATE TABLE IF NOT EXISTS ticket_departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS ticket_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Sistemin sıfır kategoriyle kullanılamaz olmaması için makul bir
-- varsayılan set (idempotent). Admin bunları pasife alabilir / yenisini
-- ekleyebilir.
INSERT INTO ticket_departments (name) VALUES
    ('Operasyon'), ('IT'), ('Finans'), ('İK')
ON CONFLICT (name) DO NOTHING;

INSERT INTO ticket_categories (name) VALUES
    ('Ağ'), ('Sunucu'), ('Donanım / PC'), ('Yazılım'),
    ('Şifre Sıfırlama'), ('E-Posta'), ('Kullanıcı Desteği'), ('Diğer')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    -- Faz 63 — dinamik taksonomi. `category_id` uygulama katmanında
    -- ZORUNLU (Pydantic), DB'de nullable tutuldu (boş `tickets`
    -- tablosuna sorunsuz ALTER için); `department_id` opsiyonel.
    department_id UUID REFERENCES ticket_departments(id) ON DELETE SET NULL,
    category_id UUID REFERENCES ticket_categories(id) ON DELETE SET NULL,
    priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_PROGRESS', 'WAITING_USER', 'RESOLVED', 'CLOSED')),
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    resolved_at TIMESTAMPTZ,
    sla_due_at TIMESTAMPTZ
);

-- Faz 63 geçişi — Faz 62'yle canlıya çıkmış `tickets` tablosundaki eski
-- kolonları temizle / yenilerini ekle (idempotent).
ALTER TABLE tickets DROP COLUMN IF EXISTS category;
ALTER TABLE tickets DROP COLUMN IF EXISTS related_device;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES ticket_departments(id) ON DELETE SET NULL;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES ticket_categories(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned_to ON tickets (assigned_to) WHERE assigned_to IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON tickets (created_by, created_at DESC);

CREATE TABLE IF NOT EXISTS ticket_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    -- Düz yorum: `body` dolu, geçiş alanları NULL. Durum/atama
    -- değişikliği: ilgili `*_from`/`*_to` dolu, `body` opsiyonel not.
    -- İlk oluşturma: `event = 'created'`.
    event TEXT NOT NULL DEFAULT 'comment' CHECK (event IN ('created', 'comment', 'status_change', 'assignment')),
    body TEXT,
    status_from TEXT,
    status_to TEXT,
    assigned_from UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_ticket_comments_ticket ON ticket_comments (ticket_id, created_at ASC);

-- ============================================================
-- Faz 64 — Bilet RBAC: Departman Bazlı Kullanıcı Yönetimi + Rol
-- Tabanlı Yetkilendirme. `users`'a bilet-modülüne-özel bir rol ekseni
-- (`ticket_role`) + helpdesk departmanı (`ticket_department_id`)
-- eklenir — mevcut `users.role` (Faz 46) ve `TICKETS_VIEW` izni
-- (Faz 62) DEĞİŞTİRİLMEZ. `ticket_comments.is_internal` = yalnızca
-- TECHNICIAN/ADMIN'in görebileceği gizli IT-içi not.
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS ticket_role TEXT NOT NULL DEFAULT 'REQUESTER'
    CHECK (ticket_role IN ('REQUESTER', 'TECHNICIAN', 'ADMIN'));
ALTER TABLE users ADD COLUMN IF NOT EXISTS ticket_department_id UUID
    REFERENCES ticket_departments(id) ON DELETE SET NULL;

ALTER TABLE ticket_comments ADD COLUMN IF NOT EXISTS is_internal BOOLEAN NOT NULL DEFAULT false;

-- `event` CHECK'ini `priority_change` + `transfer` (departman değişimi)
-- için genişlet — mevcut tabloda eski kısıt olduğu için önce düşür.
ALTER TABLE ticket_comments DROP CONSTRAINT IF EXISTS ticket_comments_event_check;
ALTER TABLE ticket_comments ADD CONSTRAINT ticket_comments_event_check
    CHECK (event IN ('created', 'comment', 'status_change', 'assignment', 'priority_change', 'transfer'));

ALTER TABLE ticket_comments ADD COLUMN IF NOT EXISTS priority_from TEXT;
ALTER TABLE ticket_comments ADD COLUMN IF NOT EXISTS priority_to TEXT;
ALTER TABLE ticket_comments ADD COLUMN IF NOT EXISTS department_from UUID REFERENCES ticket_departments(id) ON DELETE SET NULL;
ALTER TABLE ticket_comments ADD COLUMN IF NOT EXISTS department_to UUID REFERENCES ticket_departments(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_users_ticket_department ON users (ticket_department_id) WHERE ticket_department_id IS NOT NULL;

-- ============================================================
-- Faz 66 — SMTP Yapılandırması (DB-tabanlı, Ayarlar ekranından
-- yönetilir). Faz 65'in `.env` tabanlı SMTP değerleri artık burada
-- da tutulabilir; `email_service.py` ÖNCE bu satırı, yoksa `.env`'i
-- kullanır. `encrypted_password` `vault_credentials`/`ldap_config`
-- ile AYNI Fernet anahtarını (`PAM_VAULT_SECRET_KEY`) kullanır —
-- YENİ bir şifreleme anahtarı EKLENMEDİ.
-- ============================================================
CREATE TABLE IF NOT EXISTS smtp_config (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT true,
    server TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 587 CHECK (port > 0 AND port <= 65535),
    -- 'tls' (STARTTLS, tipik 587) | 'ssl' (baştan itibaren şifreli,
    -- tipik 465) | 'none' (düz metin). Faz 65'in `use_tls` boolean'ının
    -- yerini aldı.
    encryption TEXT NOT NULL DEFAULT 'tls' CHECK (encryption IN ('tls', 'ssl', 'none')),
    username TEXT NOT NULL DEFAULT '',
    -- Boş string = parola ayarlanmadı (kimlik doğrulamasız relay).
    encrypted_password TEXT NOT NULL DEFAULT '',
    from_email TEXT NOT NULL,
    from_name TEXT NOT NULL DEFAULT 'IT Operations Helpdesk',
    it_group_email TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    -- 'success' | 'error' | NULL (hiç test edilmedi). Ham hata metni
    -- `last_test_error`'da, kimlik bilgisi İÇERMEZ.
    last_test_status TEXT,
    last_test_error TEXT,
    last_test_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Faz 66 tamamlama — `encryption`/`from_name` CREATE TABLE'a canlıya
-- hiç uygulanmadan EKLENDİ, ama bu ortamın test/dev Postgres'inde tablo
-- zaten (eski `use_tls` şekliyle) test koşularından oluşmuştu — bu
-- yüzden idempotent `ALTER` de gerekiyor (yalnızca `CREATE TABLE IF NOT
-- EXISTS` bunu YAKALAMAZ). Gerçek canlıda tablo hiç yoksa bu ALTER'lar
-- no-op'tur.
ALTER TABLE smtp_config ADD COLUMN IF NOT EXISTS encryption TEXT NOT NULL DEFAULT 'tls';
ALTER TABLE smtp_config DROP CONSTRAINT IF EXISTS smtp_config_encryption_check;
ALTER TABLE smtp_config ADD CONSTRAINT smtp_config_encryption_check CHECK (encryption IN ('tls', 'ssl', 'none'));
ALTER TABLE smtp_config ADD COLUMN IF NOT EXISTS from_name TEXT NOT NULL DEFAULT 'IT Operations Helpdesk';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'smtp_config' AND column_name = 'use_tls') THEN
        UPDATE smtp_config SET encryption = CASE WHEN use_tls THEN 'tls' ELSE 'none' END;
        ALTER TABLE smtp_config DROP COLUMN use_tls;
    END IF;
END $$;

-- ============================================================
-- Faz 67 — Bilet SLA Politikası. `SLA_HOURS_BY_PRIORITY` sabiti
-- (app/tickets/models.py) artık buradan (Admin tarafından
-- düzenlenebilir) okunur. Satır yoksa kod sabiti fallback'tir —
-- sistem SLA politikası olmadan da çalışır. `sla_due_at` yalnızca
-- bilet OLUŞTURULURKEN hesaplanır; politika sonradan değişirse eski
-- biletlerin taahhüt edilmiş `sla_due_at`'i DEĞİŞMEZ.
-- ============================================================
CREATE TABLE IF NOT EXISTS ticket_sla_policy (
    priority TEXT PRIMARY KEY CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    sla_hours INTEGER NOT NULL CHECK (sla_hours > 0 AND sla_hours <= 8760),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO ticket_sla_policy (priority, sla_hours) VALUES
    ('CRITICAL', 4), ('HIGH', 24), ('MEDIUM', 72), ('LOW', 168)
ON CONFLICT (priority) DO NOTHING;

-- ============================================================
-- Faz 71 — Zamanlanmış Ağ Taraması (Scheduled Discovery). Kullanıcının
-- Ayarlar'da AÇIKÇA kaydettiği bir CIDR'ın periyodik TEKRARI — yeni/
-- keşfedilen bir aralık taranmaz (bkz. CLAUDE.md güvenlik kuralları).
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduled_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cidr TEXT NOT NULL,
    interval_hours INTEGER NOT NULL CHECK (interval_hours > 0 AND interval_hours <= 8760),
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_run_at TIMESTAMPTZ,
    -- 'success' | 'error' | NULL (hiç çalışmadı).
    last_run_status TEXT,
    last_run_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_scans_enabled ON scheduled_scans (enabled) WHERE enabled = true;

-- ============================================================
-- Faz 72 — vCenter/vSphere yapılandırması (tek satırlık, `ldap_config`/
-- `smtp_config` ile AYNI desen). `encrypted_password` `vault_
-- credentials`/`ldap_config`/`smtp_config` ile AYNI Fernet anahtarını
-- (`PAM_VAULT_SECRET_KEY`) kullanır — YENİ bir şifreleme anahtarı
-- EKLENMEDİ.
-- ============================================================
CREATE TABLE IF NOT EXISTS vcenter_config (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 443 CHECK (port > 0 AND port <= 65535),
    username TEXT NOT NULL,
    encrypted_password TEXT NOT NULL,
    -- Çoğu iç vCenter kendinden imzalı sertifika kullanır — LDAP'ın
    -- `use_ssl` alanıyla aynı ilkeyle dürüst bir varsayılan: false.
    verify_ssl BOOLEAN NOT NULL DEFAULT false,
    -- 'success' | 'error' | NULL (hiç test edilmedi). Ham hata metni
    -- `last_test_error`'da, kimlik bilgisi İÇERMEZ.
    last_test_status TEXT,
    last_test_error TEXT,
    last_test_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- Faz 76 — PAM Web Konsolu (zero-knowledge HTTPS kimlik enjeksiyonu).
-- `pam_access_rules.allow_web`/`pam_session_logs.protocol='web'` bu
-- tablonun tanımından SONRA (yukarıda, satır içi) eklendi — bu
-- ortamın dev/test Postgres'inde o tablolar test koşularından ZATEN
-- eski şekliyle oluşmuş olabilir, bu yüzden idempotent ALTER'lar da
-- gerekiyor (Faz 49/66'dan beri kurulu desen).
-- ============================================================
ALTER TABLE pam_access_rules ADD COLUMN IF NOT EXISTS allow_web BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE pam_session_logs DROP CONSTRAINT IF EXISTS pam_session_logs_protocol_check;
ALTER TABLE pam_session_logs ADD CONSTRAINT pam_session_logs_protocol_check CHECK (protocol IN ('ssh', 'rdp', 'web'));

-- Bir asset için EN FAZLA bir web konsolu profili — SNMP profilinin
-- `asset_snmp_profiles` (Faz 29.5) ilişkisiyle AYNI 1-1 ilke. Giriş
-- formunun alan adları/gizli CSRF alanları cihaza göre DEĞİŞTİĞİ için
-- kod içine sabit bir şema YAZILMADI — Admin gerçek cihaza bakıp
-- yapılandırır (bkz. docs/roadmap.md Faz 76).
CREATE TABLE IF NOT EXISTS pam_web_console_profiles (
    asset_id UUID PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    port INTEGER NOT NULL DEFAULT 443 CHECK (port > 0 AND port <= 65535),
    -- Çoğu cihaz kendinden imzalı sertifika kullanır — LDAP/vCenter'ın
    -- `use_ssl`/`verify_ssl` alanlarıyla AYNI dürüst varsayılan: false.
    verify_ssl BOOLEAN NOT NULL DEFAULT false,
    login_path TEXT NOT NULL DEFAULT '/login',
    username_field TEXT NOT NULL DEFAULT 'username',
    password_field TEXT NOT NULL DEFAULT 'password',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
