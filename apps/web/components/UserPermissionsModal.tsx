"use client";

import { useState } from "react";

import { ALL_PERMISSIONS, type Permission } from "@/lib/auth/permissions";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import modalStyles from "./ConfirmModal.module.css";
import styles from "./UserPermissionsModal.module.css";

// Faz 57 — `PermissionMatrixPanel`'in de kullandığı ortak eşleme,
// buradan export edildi (kopyalanmadı).
export const PERMISSION_LABEL_KEY: Record<Permission, string> = {
  DASHBOARD_VIEW: "permissionDashboardView",
  DISCOVERY_VIEW: "permissionDiscoveryView",
  ASSETS_VIEW: "permissionAssetsView",
  TOPOLOGY_VIEW: "permissionTopologyView",
  SCANS_VIEW: "permissionScansView",
  ALERTS_VIEW: "permissionAlertsView",
  MONITORING_VIEW: "permissionMonitoringView",
  AGENTS_VIEW: "permissionAgentsView",
  SETTINGS_VIEW: "permissionSettingsView",
  TICKETS_VIEW: "permissionTicketsView",
  PAM_ADMIN: "permissionPamAdmin",
  PAM_ACCESS: "permissionPamAccess",
  VCENTER_VIEW: "permissionVcenterView",
  VCENTER_ADMIN: "permissionVcenterAdmin",
};

type Props = {
  username: string;
  initialPermissions: Permission[];
  saving?: boolean;
  onSave: (permissions: Permission[]) => void;
  onCancel: () => void;
};

/** Faz 47 — Admin panelindeki "Yetkiler" checkbox matrisi. Kullanıcının
 * açık örneği: yalnızca `PAM_ACCESS`'i işaretli bırakıp geri kalan her
 * şeyi kaldırmak, o kullanıcıyı Dashboard dahil hiçbir genel menüyü
 * göremeyen kısıtlı bir PAM-only kullanıcıya dönüştürür. */
export function UserPermissionsModal({ username, initialPermissions, saving, onSave, onCancel }: Props) {
  const { t } = useLocale();
  const p = t.pam;
  const [selected, setSelected] = useState<Set<Permission>>(new Set(initialPermissions));

  function toggle(permission: Permission) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(permission)) next.delete(permission);
      else next.add(permission);
      return next;
    });
  }

  return (
    <div className={modalStyles.overlay} role="presentation" onClick={onCancel}>
      <div className={modalStyles.dialog} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h3 className={modalStyles.title}>
          {p.permissionsTitle} — {username}
        </h3>
        <p className={modalStyles.message}>{p.permissionsSubtitle}</p>
        <div className={styles.checkboxList}>
          {ALL_PERMISSIONS.map((permission) => (
            <label key={permission} className={styles.checkboxRow}>
              <input type="checkbox" checked={selected.has(permission)} onChange={() => toggle(permission)} />
              {p[PERMISSION_LABEL_KEY[permission] as keyof typeof p] as string}
            </label>
          ))}
        </div>
        <div className={modalStyles.actions}>
          <button type="button" className={modalStyles.cancelButton} onClick={onCancel} disabled={saving}>
            {p.cancel}
          </button>
          <button type="button" className={styles.saveButton} onClick={() => onSave([...selected])} disabled={saving}>
            {p.save}
          </button>
        </div>
      </div>
    </div>
  );
}
