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
    command_type TEXT NOT NULL CHECK (command_type IN ('kill_process', 'service_control', 'refresh_inventory', 'power_control')),
    action TEXT NOT NULL CHECK (action IN ('kill', 'start', 'stop', 'restart', 'collect', 'reboot', 'shutdown', 'logoff')),
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
