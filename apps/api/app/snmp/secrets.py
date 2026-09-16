"""Merkezi secret çözümleme yardımcı fonksiyonu.

`SNMPProfile` (bkz. `credentials.py`) yalnızca `community_ref` /
`auth_credential_ref` / `priv_credential_ref` gibi *referans* (env
değişken adı) taşır. Gerçek değer yalnızca poll anında, bu fonksiyon
üzerinden, bellekte okunur — hiçbir yerde saklanmaz, loglanmaz veya
döndürülen model/response'a yazılmaz.

CLAUDE.md: "API key, SNMP community string, veritabanı kimlik bilgisi
gibi sırlar yalnızca backend `.env` dosyasında tutulur; koda,
frontend'e, loglara veya commit'lere asla yazılmaz." — bu modül bu
kuralı tek bir yerden uygular."""

import os


def _lookup_env_exact(name: str) -> str | None:
    """`os.environ.get()` yerine — Windows'ta `os.environ` işletim
    sistemini yansıtarak BÜYÜK/KÜÇÜK HARF DUYARSIZ çalışır (`nt`
    modülü). Bu, düz metin bir community string olarak `public` gibi
    yaygın bir kelime girildiğinde, o makinede rastgele var olan bir
    `PUBLIC` ortam değişkenini (Windows'ta varsayılan olarak
    `C:\\Users\\Public`'i işaret eder!) SESSİZCE eşleştirip yanlış bir
    değeri "community string" olarak kullanmaya çalışmaya yol açardı —
    gerçek bir `.env` referansı her zaman TAM (case-sensitive) eşleşmeli."""
    for key, value in os.environ.items():
        if key == name:
            return value
    return None


def resolve_secret(ref: str | None, *, allow_literal_fallback: bool = False) -> str | None:
    """`ref` normalde bir ortam değişkeni ADI'dır (değer değil). O
    ismin ortamdaki gerçek değerini döner; tanımlı değilse `None`.

    `allow_literal_fallback=True` iken (yalnızca SNMP community string
    çağrı noktaları — v3 auth/priv secret'ları KASITLI olarak hâlâ
    yalnızca `.env` üzerinden çözülür, sertlik korunur): `ref` bir
    `.env` anahtarı olarak bulunamazsa, çökme/`not_configured` yerine
    `ref`'in kendisi düz metin community string olarak kabul edilir —
    kullanıcı hem bir `.env` değişken adı (`SNMP_CORE_SWITCH_COMMUNITY`)
    hem de doğrudan değeri (`public`) girebilsin diye (kullanıcı
    isteği). Community string'ler genelde düşük hassasiyetli, sıkça
    düz metin tutulan değerlerdir — bu esneklik yalnızca onlar için.

    Çağıran taraflar bu fonksiyonun dönüş DEĞERİNİ asla loglamamalı,
    exception mesajına gömmemeli veya API response'una yazmamalıdır —
    yalnızca `ref` (isim/girilen metin) loglanabilir/raporlanabilir."""
    if not ref:
        return None
    value = _lookup_env_exact(ref)
    if value:
        return value
    if allow_literal_fallback:
        return ref
    return None
