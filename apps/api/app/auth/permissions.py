"""Faz 47 — İzin (permission) kataloğu + rol → varsayılan izin eşlemesi.
`users.role` (ADMIN/OPERATOR/VIEWER) RBAC'ın hâlâ ÜÇ kabası kademesi
(varsayılan izin atamasında ve genel etiketlemede kullanılır) — ama
gerçek yetkilendirme kararları artık BURADAKİ ince taneli izin
listesine göre verilir (`app/auth/dependencies.py::require_permission`),
çünkü kullanıcının isteği açıkça İNCE TANELİ, kişi bazında override
edilebilir bir yetki modeli (ör. yalnızca `PAM_ACCESS` olan, Dashboard
dahil hiçbir şeyi göremeyen kısıtlı bir kullanıcı) — üç sabit rol
kademesiyle bu TEK BAŞINA ifade edilemez.

İzin kataloğu kod içinde SABİT (DB-tabanlı, kullanıcı tanımlı yeni izin
tipi EKLENEMEZ) — CLAUDE.md'nin "gereksiz generic abstraction ekleme"
kuralına uyarak, her sayfa/eylem için gerçekten var olan sabit bir
liste tutuluyor; genel bir "Permission tanımlama ekranı" YOK."""

from typing import Literal

Permission = Literal[
    "DASHBOARD_VIEW",
    "DISCOVERY_VIEW",
    "ASSETS_VIEW",
    "TOPOLOGY_VIEW",
    "SCANS_VIEW",
    "ALERTS_VIEW",
    "MONITORING_VIEW",
    "AGENTS_VIEW",
    "SETTINGS_VIEW",
    # Faz 62 — IT Helpdesk / Arıza Yönetimi (Ticket Management).
    "TICKETS_VIEW",
    "PAM_ADMIN",
    "PAM_ACCESS",
    # Faz 72 — vCenter/vSphere: görüntüleme ve güç işlemleri AYRI izin.
    "VCENTER_VIEW",
    "VCENTER_ADMIN",
]

ALL_PERMISSIONS: list[Permission] = [
    "DASHBOARD_VIEW",
    "DISCOVERY_VIEW",
    "ASSETS_VIEW",
    "TOPOLOGY_VIEW",
    "SCANS_VIEW",
    "ALERTS_VIEW",
    "MONITORING_VIEW",
    "AGENTS_VIEW",
    "SETTINGS_VIEW",
    "TICKETS_VIEW",
    "PAM_ADMIN",
    "PAM_ACCESS",
    "VCENTER_VIEW",
    "VCENTER_ADMIN",
]

_GENERAL_VIEW_PERMISSIONS: list[Permission] = [
    "DASHBOARD_VIEW",
    "DISCOVERY_VIEW",
    "ASSETS_VIEW",
    "TOPOLOGY_VIEW",
    "SCANS_VIEW",
    "ALERTS_VIEW",
    "MONITORING_VIEW",
    "AGENTS_VIEW",
    "SETTINGS_VIEW",
    # Faz 62 — Helpdesk her operatör/görüntüleyici için varsayılan
    # olarak açık (menüde OPERASYON altında, diğer *_VIEW'lerle aynı).
    "TICKETS_VIEW",
    # Faz 72 — vCenter görüntüleme de diğer *_VIEW'lerle aynı; güç
    # işlemleri (VCENTER_ADMIN) varsayılan DEĞİL, yalnızca ADMIN rolü
    # (ALL_PERMISSIONS üzerinden) ve Admin'in elle açtığı kullanıcılar.
    "VCENTER_VIEW",
]

# Yeni bir kullanıcı oluşturulduğunda (`app/auth/service.py::create_user`)
# rolüne göre başlangıç izin seti — Admin BUNU İSTEDİĞİ GİBİ SONRADAN
# DÜZENLEYEBİLİR (`PUT /api/pam/users/{id}/permissions`); bu yalnızca
# bir varsayılan, kalıcı bir kısıt DEĞİL.
DEFAULT_PERMISSIONS_BY_ROLE: dict[str, list[Permission]] = {
    "ADMIN": list(ALL_PERMISSIONS),
    "OPERATOR": [*_GENERAL_VIEW_PERMISSIONS, "PAM_ACCESS"],
    "VIEWER": [*_GENERAL_VIEW_PERMISSIONS, "PAM_ACCESS"],
}


def default_permissions_for_role(role: str) -> list[Permission]:
    return list(DEFAULT_PERMISSIONS_BY_ROLE.get(role, _GENERAL_VIEW_PERMISSIONS))
