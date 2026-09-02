"use client";

import styles from "./ConfirmModal.module.css";

type Props = {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  busy?: boolean;
  busyLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Yanlışlıkla tıklamaları önlemek için geri dönüşü olmayan işlemler
 * (process kill, service durdurma/yeniden başlatma) öncesinde gösterilen
 * genel amaçlı onay modalı — Faz 33. Herhangi bir domain'e özgü mantık
 * içermez, yalnızca onay/iptal callback'lerini tetikler. */
export function ConfirmModal({ title, message, confirmLabel, cancelLabel, busy, busyLabel, onConfirm, onCancel }: Props) {
  return (
    <div className={styles.overlay} role="presentation" onClick={onCancel}>
      <div
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="confirm-modal-title" className={styles.title}>
          {title}
        </h3>
        <p className={styles.message}>{message}</p>
        <div className={styles.actions}>
          <button type="button" className={styles.cancelButton} onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button type="button" className={styles.confirmButton} onClick={onConfirm} disabled={busy}>
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
