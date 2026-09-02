"use client";

import { useEffect, useState } from "react";

import { fetchHealth } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./BackendStatus.module.css";

type Status = "checking" | "connected" | "disconnected";

const ICONS: Record<Status, string> = {
  checking: "⏳",
  connected: "🟢",
  disconnected: "🔴",
};

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");
  const { t } = useLocale();

  useEffect(() => {
    let cancelled = false;

    fetchHealth()
      .then(() => {
        if (!cancelled) setStatus("connected");
      })
      .catch(() => {
        if (!cancelled) setStatus("disconnected");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const label: Record<Status, string> = {
    checking: t.common.backendChecking,
    connected: t.common.backendConnected,
    disconnected: t.common.backendDisconnected,
  };

  return (
    <p className={`${styles.badge} ${styles[status]}`}>
      Backend: {ICONS[status]} {label[status]}
    </p>
  );
}
