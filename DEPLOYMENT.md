# Kurulum & Dağıtım Kılavuzu (DEPLOYMENT.md)

Bu belge, **IT Operations Assistant**'ı sıfır bir sunucuya, mevcut
geliştirme ortamından tamamen bağımsız olarak kurmak içindir. Tüm
sistem (Frontend + Backend + PostgreSQL + Guacamole Daemon) Docker
Compose ile konteynerleştirilmiş şekilde çalışır.

> **Not — bu proje ORM/migration aracı (Alembic vb.) veya Redis
> KULLANMAZ.** Şema tek bir dosyadan (`infra/postgres/init.sql`) gelir
> ve backend başlarken kendisi uygular; oturumlar stateless JWT'dir,
> e-posta bildirimi kuyruksuz bir arka plan görevidir. Aşağıdaki
> adımlarda bu araçlara YER VERİLMEMİŞTİR — bu kasıtlıdır, bkz.
> `docker-compose.yml`'in başındaki not.

---

## 1. Sunucu Gereksinimleri

| Bileşen | Minimum | Önerilen |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Disk | 50 GB SSD | 100 GB SSD (PAM oturum kayıtları zamanla büyür) |
| OS | Ubuntu 22.04 LTS veya Windows Server 2022 | aynı |
| Ağ | 80/443 (Web), 8000 (API), 4822 (guacd — yalnızca ihtiyaç halinde dışa açın) | aynı |

Docker/Docker Compose dışında hiçbir bağımlılık (Python, Node.js,
PostgreSQL istemcisi vb.) sunucuya elle kurulmasına GEREK YOKTUR —
hepsi konteyner imajlarının içindedir.

---

## 2. Tek Komutla Kurulum

### Linux / Ubuntu

```bash
git clone <bu-repo-url> it-operations-assistant
cd it-operations-assistant
bash deploy.sh
```

`deploy.sh` sırasıyla:
1. Docker Engine + Compose plugin + Git eksikse kurar (`apt`).
2. Kök `.env.example`'dan gerçek bir `.env` üretir — `POSTGRES_PASSWORD`/
   `JWT_SECRET_KEY`/`PAM_VAULT_SECRET_KEY` kriptografik olarak güçlü,
   rastgele üretilir (`.env` zaten varsa DOKUNULMAZ — script'i ikinci
   kez çalıştırmak güvenlidir).
3. İlk ADMIN hesabının parolasını rastgele üretip **bir kez** ekrana
   yazar (bkz. §5 — "admin/admin123" gibi tahmin edilebilir bir
   varsayılan KULLANILMAZ).
4. `docker compose up -d --build` ile tüm sistemi ayağa kaldırır.
5. Backend'in şemayı kurup sağlıklı olmasını bekler, erişim adreslerini
   yazdırır.

### Windows Server

PowerShell'i **Yönetici olarak** açıp:

```powershell
git clone <bu-repo-url> it-operations-assistant
cd it-operations-assistant
.\deploy.ps1
```

`deploy.ps1` aynı adımları izler; farklar:
- WSL2 kurulu değilse `wsl --install` ile kurar (yeniden başlatma
  gerekebilir — script bunu algılayıp sizi bilgilendirir, ikinci
  çalıştırmada kaldığı yerden devam eder).
- **Docker Desktop'ı otomatik kurmaz** — Windows Server'da sessiz/GUI'siz
  kurulum güvenilir değildir; script resmi indirme bağlantısını verip
  durur, siz kurup script'i tekrar çalıştırırsınız.
- 80/443/8000/4822 portlarını Windows Firewall'da açar
  (`New-NetFirewallRule`).

**Sanal makinede (vSphere/Hyper-V) kuruyorsanız:** bu projenin kendi
geçmişinde gerçek bir engelle karşılaşıldı — Docker Desktop, host
tarafında "nested virtualization" AÇIK olmadan "Virtualization support
not detected" hatası verir. Bu, **guest içinden düzeltilemez** —
vSphere/Hyper-V host'undan sanal makinenin ayarlarında "Expose
hardware assisted virtualization" (veya eşdeğeri) açılmalıdır.

---

## 3. Kurulumdan Sonra

### 3.1 İlk Giriş

1. Tarayıcıda `http://<sunucu-ip>` (veya `.env`'deki `WEB_HTTP_PORT`)
   adresine gidin.
2. Kurulum sırasında ekrana yazdırılan `admin` kullanıcı adı + rastgele
   parolayla giriş yapın.
3. **Girişten hemen sonra:** Ayarlar > Kullanıcılar'dan kendi kalıcı
   hesabınızı oluşturun (veya bu admin'in parolasını değiştirin), ardından
   `.env` dosyasındaki `BOOTSTRAP_ADMIN_PASSWORD` satırını SİLİN —
   bu değişken varken backend her yeniden başlatıldığında (yalnızca
   `users` tablosu BOMBOŞSA etkili olsa da) düz metin olarak diskte
   durur.

### 3.2 Active Directory / LDAP

Bağlantı bilgileri (host, base DN, bind DN/parola) `.env`'e DEĞİL —
**Ayarlar > Active Directory / LDAP** ekranından girilir; parola
veritabanında şifreli (`PAM_VAULT_SECRET_KEY` ile) saklanır.

1. Host/port/SSL/domain FQDN/base DN/bind DN/bind parolasını girin.
2. "Bağlantıyı Test Et" ile doğrulayın.
3. "Şimdi Senkronize Et" ile grupları/kullanıcıları içe aktarın.
4. (Opsiyonel, dikkatli kullanın) `.env`'de `LDAP_AUTH_ENABLED=true`
   yaparsanız senkronize edilmiş AD hesapları kendi AD parolalarıyla
   doğrudan giriş yapabilir — varsayılan KAPALIDIR.

### 3.3 vCenter / vSphere

**Ayarlar > vCenter / vSphere** ekranından host/kullanıcı adı/parola
girip "Bağlantıyı Test Et" ile doğrulayın. Not: vCenter REST API'si
anlık CPU/RAM kullanım YÜZDESİ sunmaz — bu proje bu veriyi hiçbir
zaman uydurmaz, yalnızca tahsis (allocation) gösterilir.

### 3.4 SMTP (Bilet E-Posta Bildirimleri)

**Ayarlar > E-Posta Bildirimi (SMTP)** ekranından sunucu/port/kullanıcı/
parola/gönderen adresi/şifreleme türünü (TLS/SSL/Yok) girip
**"Test E-Postası Gönder"** ile doğrulayın. Girilmezse bilet
bildirimleri sessizce devre dışı kalır (opt-in) — hiçbir hata akışı
bozmaz.

### 3.5 PAM (RDP/SSH/Web Konsolu) — Kasa Anahtarları

`PAM_VAULT_SECRET_KEY` (`.env`'de, kurulum sırasında otomatik üretildi)
kasadaki (`vault_credentials`) TÜM şifreli parolaların/SSH anahtarlarının
TEK şifre çözme anahtarıdır. **Bu anahtarı kaybederseniz kasadaki
kimlik bilgileri KALICI OLARAK okunamaz hale gelir** — `.env`'in tamamını
(yalnızca `POSTGRES_PASSWORD`/`JWT_SECRET_KEY` değil) düzenli olarak,
veritabanı yedeğinden AYRI, güvenli bir konumda (parola yöneticisi/kasa)
saklayın (bkz. §4).

---

## 4. Yedekleme & Geri Yükleme

```bash
# Yedek al (varsayılan hedef: ./backups)
bash backup.sh

# Belirli bir dizine yedek al
bash backup.sh /mnt/yedekler

# Geri yükle (YIKICI — mevcut veriyi siler, onay ister)
bash restore.sh backups/itops-db-20260916-140000.sql.gz backups/itops-data-20260916-140000.tar.gz
```

- `backup.sh`: çalışan `db` konteynerinin İÇİNDEN `pg_dump` çalıştırır
  (ayrıca bir PostgreSQL istemcisi kurulu olması GEREKMEZ) + PAM oturum
  kaydı/sürücü dosyalarını (`./data/`) `tar.gz` olarak arşivler.
  **`.env`'i yedeklemez** (kasıtlı — sırları ayrı, daha güvenli bir
  konumda saklayın, bkz. §3.5).
- `restore.sh`: hedef veritabanını SİLİP yedekteki içerikle değiştirir
  (`EVET` yazarak onaylamanız gerekir), restore sırasında `api`/`web`
  servislerini durdurup sonra tekrar başlatır.

Windows Server'da bu script'leri **Git Bash / WSL** üzerinden çalıştırın
(ikisi de saf bash + `docker compose exec`/`tar`/`gzip` kullanır, ayrı
bir PowerShell sürümü YAZILMADI — Docker CLI zaten her iki ortamda da
aynı şekilde çalışır).

**Öneri:** `backup.sh`'ı bir cron/Görev Zamanlayıcısı işiyle günlük
çalıştırıp `backups/` dizinini sunucu dışına (ör. bir NAS/obje
depolama) senkronize edin — bu script'ler bunu OTOMATİK yapmaz, yalnızca
yerel bir yedek dosyası üretir.

---

## 5. Güvenlik Notları

- Kurulum script'leri **hiçbir zaman** "admin/admin123" gibi tahmin
  edilebilir bir varsayılan parola OLUŞTURMAZ — her kurulumda
  kriptografik olarak güçlü, rastgele bir parola üretilip yalnızca BİR
  KEZ ekrana yazılır.
- `.env` içindeki `JWT_SECRET_KEY`/`PAM_VAULT_SECRET_KEY`/
  `POSTGRES_PASSWORD` gerçek sırlardır — commit'lenmemeli, yalnızca bu
  sunucuda, dosya izinleri kısıtlı (ör. `chmod 600 .env`) tutulmalıdır.
- `guacd` servisi production compose'da HOST'A AÇILMAZ (yalnızca `api`
  konteynerinin kendi ağı üzerinden erişimi vardır) — en az yüzey
  ilkesi. `deploy.sh`/`deploy.ps1`'in açtığı 4822 firewall kuralı,
  guacd'nin ayrı bir host'ta/Docker dışında çalıştırılması gibi
  alternatif kurulumlar için bir seçenektir, varsayılan mimaride
  gerekmez.
- TLS/443 bu artırımda dahil DEĞİL — `web` konteyneri düz HTTP (3000)
  sunar, `WEB_HTTP_PORT` ile host'ta istediğiniz porta (varsayılan 80)
  bağlanır. Gerçek bir TLS sertifikası (Let's Encrypt vb.) için
  önünüze kendi ters proxy'nizi (nginx/Caddy/Traefik) eklemeniz
  gerekir — bu kasıtlı bir sınırdır, sahte bir sertifika UYDURULMADI.

---

## 6. Sorun Giderme

```bash
docker compose logs -f api      # backend logları
docker compose logs -f web      # frontend logları
docker compose ps               # servis durumları
curl http://localhost:8000/api/health/db   # DB bağlantısını doğrudan sına
```

- **`api` sürekli yeniden başlıyorsa:** genelde `.env`'de
  `JWT_SECRET_KEY`/`PAM_VAULT_SECRET_KEY` eksiktir (backend bu ikisi
  olmadan KASITLI olarak hata verir, zayıf bir varsayılanla sessizce
  imzalamaz) — `docker compose logs api` ile kesin nedeni görün.
- **Web arayüzü açılıyor ama giriş/PAM ekranları 502/boş dönüyorsa:**
  `api` henüz `/api/health` üzerinden sağlıklı değildir — `depends_on:
  condition: service_healthy` bunu genelde önler, ama ilk build'de
  birkaç dakika sürebilir.
- **RDP/SSH oturumları bağlanmıyorsa:** `docker compose logs guacd` +
  `api` loglarını birlikte kontrol edin; `guacd` container'ı `healthy`
  görünmesine rağmen hedef Windows sunucusunun NLA/RDP ayarları da
  gerçek bir engel olabilir (bu projenin kendi geçmişinde karşılaşılan
  gerçek hatalardan biri, kod tarafında zaten ele alındı).
