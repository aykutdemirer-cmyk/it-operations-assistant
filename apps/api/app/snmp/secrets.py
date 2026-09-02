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


def resolve_secret(ref: str | None) -> str | None:
    """`ref` bir ortam değişkeni ADI'dır (değer değil). O ismin
    ortamdaki gerçek değerini döner; tanımlı değilse `None`.

    Çağıran taraflar bu fonksiyonun dönüş DEĞERİNİ asla loglamamalı,
    exception mesajına gömmemeli veya API response'una yazmamalıdır —
    yalnızca `ref` (isim) loglanabilir/raporlanabilir."""
    if not ref:
        return None
    return os.environ.get(ref) or None
