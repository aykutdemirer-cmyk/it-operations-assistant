"""Faz 46 — kasa şifreleme. `cryptography` (Faz 35'ten beri zaten
`asyncssh`'in bağımlılığı — YENİ bir kripto kütüphanesi EKLENMEDİ)
Fernet'i (AES-128-CBC + HMAC-SHA256, kimlik doğrulamalı şifreleme)
kullanır. Anahtar YALNIZCA `.env`'deki `PAM_VAULT_SECRET_KEY`'den
okunur — koda/DB'ye/loglara asla yazılmaz.

`credential_type='password'` → payload `{"password": "..."}`
`credential_type='ssh_key'` → payload `{"private_key": "...", "passphrase": "..."}`
Payload JSON'a çevrilip TAMAMI şifrelenir, `encrypted_payload` tek bir
opak string'dir."""

import json
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("PAM_VAULT_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "PAM_VAULT_SECRET_KEY .env içinde tanımlı değil — kasa "
            "şifrelenemez/çözülemez (bkz. apps/api/.env.example)."
        )
    return Fernet(key.encode("utf-8"))


def encrypt_payload(payload: dict) -> str:
    raw = json.dumps(payload).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def decrypt_payload(encrypted_payload: str) -> dict:
    """Geçersiz anahtar/bozuk veri için `InvalidToken` fırlatır — çağıran
    taraf bunu asla ham exception olarak dışarı sızdırmamalı (bkz. `app/
    pam/service.py`)."""
    raw = _fernet().decrypt(encrypted_payload.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


__all__ = ["encrypt_payload", "decrypt_payload", "InvalidToken"]
