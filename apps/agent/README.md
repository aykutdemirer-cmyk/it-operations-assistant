# IT Operations Assistant — Agent

Windows/Linux üzerinde çalışan, backend'e (`apps/api`) kendi kendine
kayıt olan, düzenli **heartbeat**, **telemetry** (CPU/RAM/disk/network —
sık değişen) ve **inventory** (donanım/OS/network/servis/process —
seyrek değişen) gönderen bağımsız bir Python agent'ı (Faz 30).

Backend'e GÖMÜLÜ değildir — ayrı, bağımsız olarak dağıtılabilen bir
uygulamadır. SNMP'nin yerini almaz: **SNMP fiziksel ağ cihazları içindir
(switch/router/firewall), Agent ise Windows/Linux işletim sistemi çalışan
makineler içindir.** İkisi aynı Asset üzerinde birleşebilir ama veri
kaynakları ayrıdır (bkz. `docs/architecture.md`).

## Hızlı Başlangıç

```bash
cd apps/agent
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux:   source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env içinde BACKEND_URL'i gerçek backend adresinize göre düzenleyin

python -m agent test-connection   # backend erişilebilir mi, kayıt/auth çalışıyor mu
python -m agent start             # sürekli çalışan modda başlat (foreground, Ctrl+C ile durur)
```

## CLI Komutları

| Komut             | Açıklama                                                                 |
|--------------------|---------------------------------------------------------------------------|
| `start`            | Agent'ı sürekli çalışan modda başlatır (heartbeat/telemetry/inventory üç ayrı döngü). |
| `status`           | Bilinen agent kimliğini gösterir (kayıtlı değilse bunu söyler).           |
| `inventory`        | Yerel envanteri JSON olarak stdout'a yazar — **backend'e göndermez**, yalnızca doğrulama/debug içindir. |
| `test-connection`  | Backend erişilebilir mi + kayıt/kimlik doğrulama gerçekten çalışıyor mu kontrol eder. |
| `version`          | Agent sürümünü yazdırır.                                                   |

## Mimari

```
agent/
├── main.py            CLI + ana döngü (AgentRuntime, üç bağımsız thread)
├── config.py           .env / ortam değişkenlerinden yapılandırma
├── client.py            Backend HTTP istemcisi (stdlib urllib, yeni bağımlılık yok)
├── authentication.py    Yerel kimlik (agent_id/token) saklama, token'ı ASLA loglamama
├── heartbeat.py          Heartbeat payload'ı
├── telemetry.py          Telemetry payload'ı (SIK değişen veri)
├── inventory.py          Inventory payload'ı (SEYREK değişen veri)
├── collectors/           Platform-bağımsız toplama mantığı (psutil üzerinden)
│   ├── system.py    hostname/FQDN/machine id/boot time/OS bilgisi
│   ├── cpu.py       model/çekirdek sayısı/kullanım %/load average
│   ├── memory.py    toplam/kullanılan/%
│   ├── disk.py      mount başına toplam/kullanılan/boş/%
│   ├── network.py   interface listesi + tip sınıflandırması (ethernet/wifi/loopback/docker/vpn/…)
│   ├── processes.py en yoğun N process (PID/isim/CPU%/mem%/kullanıcı/durum — CMDLINE YOK)
│   └── services.py  platform'a devreder (aşağıya bkz.)
└── platform/              Yalnızca gerçekten platforma özgü kod
    ├── windows.py    MachineGuid, Windows Service listesi (psutil.win_service_iter)
    └── linux.py      /etc/machine-id, systemctl servis listesi, DMI donanım bilgisi
```

**Telemetry ≠ Inventory** (bkz. `docs/decisions.md`): telemetry sık
değişen sayısal değerleri taşır (`agent_telemetry` tablosu, zaman
serisi); inventory seyrek değişen "şu anki durum" bilgisini taşır
(`agent_inventory`, agent başına tek satır, üzerine yazılır).

## Kimlik ve Kayıt

Agent ilk çalıştığında `.env`'de `AGENT_ID`/`AGENT_TOKEN` yoksa
`POST /api/agents/register` ile kendi kendine kayıt olur ve aldığı
kimliği `AGENT_STATE_FILE`'a (varsayılan `.itops-agent-state.json`)
yazar. Bir sonraki çalıştırmalarda bu dosyadan okunur — **her
başlatmada yeniden kayıt OLMAZ** (aksi halde backend'de "ghost" agent
kayıtları birikirdi).

**Enrollment kodu (Faz 31) — İLK kayıt için ZORUNLU:** Backend artık
self-service registration'ı geçerli, süresi dolmamış, tek kullanımlık
bir kodla sınırlıyor. Backend'in `/settings` sayfasındaki "Agent
Configuration" bölümünden "Kod Üret" ile 10 dakika geçerli bir kod
alın, `.env`'de `ENROLLMENT_CODE=XXX-XXX-XXX` olarak ayarlayın. Zaten
kayıtlı bir agent (yukarıdaki `AGENT_ID`/`AGENT_TOKEN` veya yerel state
dosyası) için kod HİÇ gerekmez — yalnızca yeni bir kayıt anında
kullanılır ve tüketilir. Kod bir credential DEĞİLDİR (tek başına
hiçbir kaynağa erişim vermez, yalnızca "bu kaydı bir insan başlattı"
onayıdır) — gerçek yetkilendirme hâlâ kayıt sonrası alınan bearer
token'da yaşar.

## Windows EXE Build & Download (Faz 32)

Son kullanıcı artık bu klasörü/Python'u kurmak ZORUNDA değil — Windows
için tek dosya, **Python runtime gerektirmeyen** bir `.exe` web
arayüzünden indirilebilir.

**Build etmek (yalnızca geliştirici/sunucu tarafında, bir kez):**

```bash
cd apps/agent
python -m venv .venv          # zaten yoksa
.venv\Scripts\pip install -r requirements.txt -r packaging\windows\requirements-build.txt
powershell -File packaging\windows\build.ps1
```

Çıktı:
- `apps/agent/dist/IT-Operations-Agent-<version>.exe` — tek dosya,
  bağımsız çalıştırılabilir (PyInstaller onefile).
- `apps/agent/dist/build-info.json` — backend'in `GET /api/agents/
  download/windows` endpoint'inin okuduğu manifest (`{version,
  filename, size_bytes, built_at}`).

**Build ve download BİLİNÇLİ olarak ayrı** — backend `dist/`'i
yalnızca OKUR, kendisi asla PyInstaller çalıştırmaz. `dist/` git'e
commit EDİLMEZ (`.gitignore`) — her ortamda ayrıca build edilmeli.

**Versiyon** tek doğruluk kaynağından gelir: `agent/__init__.py::
__version__`. Değiştirmek için yalnızca BU dosyayı güncelleyin —
`.spec`/`build.ps1`/backend hiçbiri versiyonu elle tekrar yazmaz,
hepsi zincirleme olarak buradan (veya build.ps1'in ürettiği
`build-info.json`'dan) okur.

**Web'den indirme:** Backend çalışırken `/settings` sayfasının Agent
Configuration bölümünde "Agent İndir" altında gerçek versiyon/dosya
boyutuyla bir indirme butonu görünür (`GET /api/agents/download/
windows`). Henüz build edilmemişse buton yerine dürüst bir "henüz
build edilmemiş" mesajı gösterilir — sahte bir link YOK.

**Kullanıcı akışı (`.exe`'yi çalıştıran kişi için):** `.exe`'yi
çalıştırmak `python -m agent`'la AYNI CLI'ı açar (`start`/`status`/
`inventory`/`test-connection`/`version`) — mevcut `.env`/ortam
değişkeni yapılandırma mimarisi HİÇ değişmedi. **Explorer'dan çift
tıklama** (argümansız çalıştırma) artık doğrudan `start`'a düşer: hiç
yapılandırma yoksa Backend URL + Enrollment Code (Settings'ten üretilen)
konsolda DOĞRUDAN sorulur ve `.exe`'nin kendi dizinindeki `.env`'e
yazılır — elle dosya oluşturmaya gerek yok (ama `.env`'i elle önceden
koymak da hâlâ çalışır, önceliklidir). Herhangi bir hata/erken çıkışta
pencere `input()` ile duraklatılır, ANINDA kapanmaz (bkz. `docs/
decisions.md` §15.1 — gerçek bir kullanıcı bildirimiyle bulunan bug'ın
düzeltmesi). Enrollment/token/kimlik mantığı Faz 31'dekiyle BİREBİR
AYNI.

## Uzaktan Komut Çalıştırma (Faz 33)

Agent, backend'in `agent_commands` kuyruğunu poll ederek uzaktan
process kill / servis start-stop-restart komutlarını çalıştırabilir —
ama **varsayılan olarak KAPALI**. Etkinleştirmek için `.env`'e:

```
ENABLE_REMOTE_COMMANDS=true
COMMAND_POLL_INTERVAL=10   # opsiyonel, saniye, varsayılan 10
```

Kapalıyken 4. bir thread (command-poll) hiç başlamaz — backend'de bir
komut oluşsa bile bu agent'a hiç ulaşmaz. Açıkken bile kritik süreç/
servis listesi (`agent/commands.py::_PROTECTED_*`) ve agent'ın kendi
süreci/PID'i HER ZAMAN korunur — backend'den gelen bir komut bunları
hedef alsa bile reddedilir. Detay ve bilinen riskler için `docs/
decisions.md` §17.

## Güvenlik

- Token DB'de yalnızca SHA-256 hash'i olarak tutulur (backend, Faz 28)
  — bu agent kodu tarafında da token hiçbir zaman loglanmaz
  (`authentication.py::redact_token`, yalnızca son 4 karakteri gösterir).
- `VERIFY_TLS=true` **varsayılandır**. `false` yalnızca geliştirme/
  self-signed sertifika senaryosu için — global bir SSL context
  değişikliği YAPILMAZ, yalnızca bu agent'ın kendi isteklerine özgü.
- Process collector **command-line argümanlarını hiç toplamaz**
  (credential/token içerebilir — bkz. `collectors/processes.py`
  docstring'i).
- Kurulu yazılım envanteri (`software`) bu fazda **KASITLI olarak
  boş** — güvenilir, cross-platform, yönetici hakkı gerektirmeyen bir
  yöntem bu fazın kapsamı dışında bırakıldı.

## Bilinen Sınırlar (MVP, Faz 30-32)

- **Offline buffering yok:** backend erişilemezken kaçırılan
  telemetry/inventory turları **kaybolur** — bir yerel kuyruk/disk
  buffer'ı YOK. Gelecekte eklenebilir (bkz. §16 master prompt).
- **Token OS credential store'da (Windows Credential Manager/DPAPI,
  Linux keyring/Secret Service) DEĞİL** — hâlâ yerel bir JSON dosyasında
  (Linux'ta `chmod 600` ile). Faz 31'de değerlendirildi ama BİLİNÇLİ
  olarak ertelendi: bu geliştirme ortamında gerçek bir Linux Secret
  Service arka ucu yok, bu yüzden `keyring` entegrasyonunu yalnızca
  Windows tarafında test edip Linux tarafını doğrulanmamış bırakmak
  yerine, tamamen erteleyip her iki platformda da gerçek test
  imkanı olduğunda ele almak tercih edildi (bkz. `docs/decisions.md`
  §14).
- **Windows üretici/model bilgisi yok** — güvenilir bir yöntem WMI
  gerektirir (`wmi`/`pywin32` bağımlılığı, bu fazda eklenmedi). Linux'ta
  `/sys/class/dmi/id/*` üzerinden best-effort okunur.
- **Kurulu yazılım listesi toplanmıyor** (yukarı bkz.).
- **Windows Service / systemd kurulumu YAPILMADI** — kod yapısal
  olarak buna uygun (`python -m agent start` blocking, sinyal
  destekli, `console=True` frozen EXE'de de aynen çalışıyor), ama
  gerçek `sc.exe create`/`systemctl enable` adımı, code signing ve
  otomatik güncelleme sonraki fazların kapsamı. Örnek bir systemd unit
  dosyası `deploy/systemd/itops-agent.service` altında — yalnızca
  dosya/referans, gerçek bir makineye kurulmadı.
- **Yalnızca Windows EXE packaging var (Faz 32)** — Linux için henüz
  bir paketleme/dağıtım artifact'i (`.deb`/`.rpm`/tek-dosya binary)
  YOK, yalnızca `python -m agent` ile kaynak koddan çalıştırma
  destekleniyor.
- **LLDP/CDP/uzaktan komut çalıştırma/dosya transferi YOK** — bu agent
  yalnızca bir monitoring/inventory ajanıdır, uzaktan yönetim aracı
  DEĞİLDİR (bkz. Faz 30 kapsam-dışı listesi).

## Bağımlılık Kararı

Tek çalışma zamanı bağımlılığı **`psutil==7.2.2`** (BSD-3-Clause,
Python 3.14 ile uyumlu, PyPI'daki en güncel sürüm — kontrol tarihi bu
fazın uygulanma tarihi). Gerekçe: CPU/RAM/disk/network/process bilgisi
ve Windows Service listesi için tek, iyi bakımlı, cross-platform bir
API — bunu stdlib ile (özellikle Windows tarafında) yeniden yazmak
güvenilirlik riski ve gereksiz kod hacmi yaratırdı. HTTP istemcisi
(`client.py`) ise BİLİNÇLİ olarak `requests`/`httpx` KULLANMADI —
stdlib `urllib.request` bu agent'ın basit JSON POST/GET ihtiyacını
karşılıyor, dış bağımlılık yüzeyini `psutil` ile sınırlı tutuyor.

## Testler

```bash
cd apps/agent
python -m pytest -v
```

Testler gerçek bir Windows/Linux API'sine bağımlı DEĞİLDİR —
`psutil`/platform-özel çağrılar mock'lanır. Platform-özel modüller
(`platform/windows.py`, `platform/linux.py`) ayrı test dosyalarında,
ilgili olmayan platformda da çalışacak şekilde (mock üzerinden) test
edilir. `tests/test_packaging.py` (Faz 32) packaging dosyalarının
varlığını/doğru entry point'i/versiyonun tek kaynaktan geldiğini
doğrular — GERÇEK bir PyInstaller build'i test paketinde
ÇALIŞTIRILMAZ (çok ağır); gerçek build doğrulaması elle
`packaging/windows/build.ps1` ile yapılır.
