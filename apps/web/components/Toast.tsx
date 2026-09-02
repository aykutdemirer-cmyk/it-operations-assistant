"use client";

import { useCallback, useRef, useState } from "react";

import styles from "./Toast.module.css";

export type ToastKind = "success" | "error";
export type ToastMessage = { id: string; kind: ToastKind; text: string };

const _AUTO_DISMISS_MS = 5000;

/** Sağ üst köşede kısa süreli bildirim göstermek için minimal, yerel
 * (component-scoped) bir toast state'i — Faz 33. Global bir Provider
 * EKLENMEDİ (uygulamanın geri kalanı henüz toast kullanmıyor, kapsamı
 * gereksiz yere büyütmemek için bu component'e özel tutuldu). */
export function useToasts() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (kind: ToastKind, text: string) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setToasts((prev) => [...prev, { id, kind, text }]);
      const timer = setTimeout(() => dismiss(id), _AUTO_DISMISS_MS);
      timers.current.set(id, timer);
    },
    [dismiss]
  );

  return { toasts, push, dismiss };
}

type StackProps = {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
};

export function ToastStack({ toasts, onDismiss }: StackProps) {
  if (toasts.length === 0) return null;
  return (
    <div className={styles.stack} role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`${styles.toast} ${toast.kind === "success" ? styles.success : styles.error}`}>
          <span className={styles.text}>{toast.text}</span>
          <button type="button" className={styles.dismiss} onClick={() => onDismiss(toast.id)} aria-label="Kapat">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
