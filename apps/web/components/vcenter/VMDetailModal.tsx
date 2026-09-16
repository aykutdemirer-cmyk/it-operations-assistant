"use client";

import { useEffect, useState } from "react";

import { fetchVCenterVmDetail, performVCenterVmPowerAction, type VCenterPowerAction, type VCenterVmDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import modalStyles from "../ConfirmModal.module.css";
import { CreateTicketModal } from "../CreateTicketModal";
import styles from "./VCenterPanel.module.css";
import { powerBadgeClass, powerStateLabel } from "./vcenterBadges";

type Props = {
  vmId: string;
  vmName: string;
  canManagePower: boolean;
  onClose: () => void;
  onPowerActionDone: () => void;
};

/** Faz 72 — VM Detay Modalı. Güç işlemleri `VCENTER_ADMIN` gerektirir
 * (görüntüleme `VCENTER_VIEW` yeterli — `canManagePower` çağıranın
 * (`VCenterPanel.tsx`) `currentUser.permissions`'a bakarak geçtiği bir
 * prop). "Arıza/Talep Bileti Aç" mevcut `CreateTicketModal`'ı VM
 * bilgisi ön-dolu açar — yeni bir alan/tablo EKLENMEDİ. */
export function VMDetailModal({ vmId, vmName, canManagePower, onClose, onPowerActionDone }: Props) {
  const { token } = useAuth();
  const { t } = useLocale();
  const v = t.vcenter;

  const [detail, setDetail] = useState<VCenterVmDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<VCenterPowerAction | null>(null);
  const [showTicketModal, setShowTicketModal] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchVCenterVmDetail(token, vmId)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : v.loadError));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, vmId]);

  async function handlePower(action: VCenterPowerAction) {
    if (!token) return;
    setPendingAction(action);
    setError(null);
    try {
      await performVCenterVmPowerAction(token, vmId, action);
      onPowerActionDone();
      const refreshed = await fetchVCenterVmDetail(token, vmId);
      setDetail(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : v.powerActionError);
    } finally {
      setPendingAction(null);
    }
  }

  if (showTicketModal) {
    return (
      <CreateTicketModal
        onClose={() => setShowTicketModal(false)}
        onCreated={() => setShowTicketModal(false)}
        initialTitle={v.ticketPrefillTitle(vmName)}
        initialDescription={v.ticketPrefillDescription(vmName, vmId)}
      />
    );
  }

  return (
    <div className={modalStyles.overlay} role="presentation" onClick={onClose}>
      <div className={modalStyles.dialog} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h3 className={modalStyles.title}>{vmName}</h3>

        {!detail && !error && <p className={modalStyles.message}>{t.common.loading}</p>}
        {error && <p className={modalStyles.message}>{error}</p>}

        {detail && (
          <>
            <div className={styles.detailGrid}>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.powerState}</span>
                <span className={`${styles.powerBadge} ${powerBadgeClass(styles, detail.power_state)}`}>
                  {powerStateLabel(v, detail.power_state)}
                </span>
              </div>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.ipAddress}</span>
                <span className={styles.detailValue}>{detail.ip_address ?? "—"}</span>
              </div>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.guestHostname}</span>
                <span className={styles.detailValue}>{detail.guest_hostname ?? "—"}</span>
              </div>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.guestOs}</span>
                <span className={styles.detailValue}>{detail.guest_os ?? "—"}</span>
              </div>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.cpuAllocation}</span>
                <span className={styles.detailValue}>{detail.cpu_count ?? "—"}</span>
              </div>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.memoryAllocation}</span>
                <span className={styles.detailValue}>{detail.memory_mb != null ? `${(detail.memory_mb / 1024).toFixed(1)} GB` : "—"}</span>
              </div>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.cpuUsage}</span>
                <span className={styles.detailValue}>{v.usageNotAvailable}</span>
              </div>
              <div className={styles.detailField}>
                <span className={styles.detailLabel}>{v.fields.memoryUsage}</span>
                <span className={styles.detailValue}>{v.usageNotAvailable}</span>
              </div>
            </div>
            <p className={styles.honestNote}>{v.usageNotAvailableNote}</p>

            <div className={styles.modalActions}>
              {canManagePower && (
                <>
                  <button
                    type="button"
                    className={styles.actionButton}
                    disabled={pendingAction !== null || detail.power_state === "POWERED_ON"}
                    onClick={() => handlePower("start")}
                  >
                    {pendingAction === "start" ? t.common.loading : v.powerStart}
                  </button>
                  <button
                    type="button"
                    className={styles.actionButton}
                    disabled={pendingAction !== null || detail.power_state !== "POWERED_ON"}
                    onClick={() => handlePower("guest_reboot")}
                  >
                    {pendingAction === "guest_reboot" ? t.common.loading : v.powerGuestReboot}
                  </button>
                  <button
                    type="button"
                    className={styles.actionButton}
                    disabled={pendingAction !== null || detail.power_state !== "POWERED_ON"}
                    onClick={() => handlePower("reset")}
                  >
                    {pendingAction === "reset" ? t.common.loading : v.powerReset}
                  </button>
                  <button
                    type="button"
                    className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                    disabled={pendingAction !== null || detail.power_state !== "POWERED_ON"}
                    onClick={() => handlePower("stop")}
                  >
                    {pendingAction === "stop" ? t.common.loading : v.powerStop}
                  </button>
                </>
              )}
              <button type="button" className={styles.actionButton} onClick={() => setShowTicketModal(true)}>
                {v.openTicket}
              </button>
            </div>
          </>
        )}

        <div className={modalStyles.actions}>
          <button type="button" className={modalStyles.cancelButton} onClick={onClose}>
            {t.common.close}
          </button>
        </div>
      </div>
    </div>
  );
}
