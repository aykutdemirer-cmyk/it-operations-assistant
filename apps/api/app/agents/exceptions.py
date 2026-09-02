"""Agent alt sisteminin hata hiyerarşisi (Faz 28).

`app/snmp/exceptions.py` ile aynı ilke: HTTP katmanı (`app/routes/
agents.py`) hiçbir ham kütüphane/DB istisnasını doğrudan görmez, her
zaman bu hiyerarşiden birine çevrilir. Hiçbir mesaj token DEĞERİ
içermez (yalnızca `agent_id` gibi credential OLMAYAN bağlam)."""


class AgentError(Exception):
    """Tüm agent hatalarının base sınıfı."""


class AgentNotFoundError(AgentError):
    """Verilen `agent_id` (veya token) ile eşleşen bir agent yok."""


class AgentAuthenticationError(AgentError):
    """Bearer token eksik, geçersiz veya `revoked_at` dolu (iptal
    edilmiş)."""


class AgentRevokedError(AgentAuthenticationError):
    """Token geçerli formatta ama bu agent açıkça iptal edilmiş."""


class EnrollmentCodeError(AgentError):
    """Enrollment code alt sisteminin base sınıfı (Faz 31)."""


class EnrollmentCodeInvalidError(EnrollmentCodeError):
    """Kod hiç yok/formatı yanlış — bilinmeyen bir kod."""


class EnrollmentCodeExpiredError(EnrollmentCodeError):
    """Kod var ama `expires_at` geçmiş."""


class EnrollmentCodeAlreadyUsedError(EnrollmentCodeError):
    """Kod var, süresi dolmamış ama daha önce BAŞKA bir kayıt için
    tüketilmiş — tek kullanımlık."""
