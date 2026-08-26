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

## Şu Anki Durum

Proje Faz 0'dadır (yalnızca dokümantasyon). Kod, dependency, database,
Docker, frontend veya backend henüz oluşturulmamıştır — bunlar
`docs/roadmap.md`'deki ilgili fazlarda başlayacaktır.
