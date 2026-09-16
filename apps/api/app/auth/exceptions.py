"""Faz 46 — auth/RBAC katmanının kendi exception hiyerarşisi. Route
katmanı bunları HTTP durum kodlarına çevirir (bkz. `app/auth/
dependencies.py` ve `app/routes/auth.py`); ham detay hiçbir zaman
loglanmaz/response'a yazılmaz (parola/token değeri taşımazlar)."""


class AuthError(Exception):
    """Tüm auth hatalarının ortak temeli."""


class InvalidCredentialsError(AuthError):
    """Kullanıcı adı yok VEYA parola yanlış — ikisi de aynı mesajla
    döner (kullanıcı adı enumeration'ını önlemek için kasıtlı)."""


class InvalidTokenError(AuthError):
    """Token eksik/bozuk/süresi dolmuş/imzası geçersiz."""


class InsufficientRoleError(AuthError):
    """Kimliği doğrulanmış kullanıcının rolü, istenen işlem için
    yetersiz (ör. OPERATOR bir ADMIN-only endpoint'e erişmeye çalıştı)."""


class UserInactiveError(AuthError):
    """Kullanıcı `is_active=false` — token geçerli olsa bile reddedilir."""


class UsernameAlreadyExistsError(AuthError):
    """`users.username` UNIQUE ihlali — kullanıcı oluşturma/yeniden
    adlandırma sırasında."""


class AdUsernameNotFoundError(AuthError):
    """Faz 49 — bir kullanıcı, henüz senkronize edilmemiş/var olmayan
    bir AD hesabına (`ad_users.username`) bağlanmaya çalışıldığında
    (`users.ad_username` FK ihlali)."""
