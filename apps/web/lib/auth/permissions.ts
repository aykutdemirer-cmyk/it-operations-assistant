// Faz 47 — izin kataloğu, backend `app/auth/permissions.py::
// ALL_PERMISSIONS` ile birebir. Yeni bir izin tipi burada KOD
// DEĞİŞİKLİĞİ olmadan eklenemez — kasıtlı, bkz. backend dosyasının
// docstring'i (gereksiz generic abstraction'dan kaçınma).
export type Permission =
  | "DASHBOARD_VIEW"
  | "DISCOVERY_VIEW"
  | "ASSETS_VIEW"
  | "TOPOLOGY_VIEW"
  | "SCANS_VIEW"
  | "ALERTS_VIEW"
  | "MONITORING_VIEW"
  | "AGENTS_VIEW"
  | "SETTINGS_VIEW"
  // Faz 62 — IT Helpdesk / Arıza Yönetimi (Ticket Management).
  | "TICKETS_VIEW"
  | "PAM_ADMIN"
  | "PAM_ACCESS"
  // Faz 72 — vCenter/vSphere: görüntüleme ve güç işlemleri AYRI izin.
  | "VCENTER_VIEW"
  | "VCENTER_ADMIN";

export const ALL_PERMISSIONS: Permission[] = [
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
];

export function hasPermission(permissions: Permission[] | undefined, required: Permission): boolean {
  return !!permissions?.includes(required);
}
