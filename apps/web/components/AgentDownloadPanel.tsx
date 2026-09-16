"use client";

import { useEffect, useState } from "react";

import { fetchWindowsServiceDownloadInfo, windowsServiceDownloadUrl, type WindowsAgentDownloadInfo } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentDownloadPanel.module.css";

type LoadStatus = "loading" | "done" | "error";

function formatFileSize(bytes: number | null): string {
  if (bytes == null) return "-";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

/** Kullanıcı isteğiyle — düz CLI EXE indirmesi (yalnızca `agent start`,
 * servis kaydı YOK) kaldırıldı; KALICI Windows servisi olarak kuran
 * paket (Faz 40) zaten aynı EXE'yi + kurulum script'lerini içeriyor ve
 * tek başlı EXE'nin kapsadığı her senaryoyu karşılıyor. Backend'deki
 * `GET /api/agents/download/windows` (düz EXE) endpoint'i KALDIRILMADI
 * — yalnızca bu panelden bağlantısı kaldırıldı, ileride geri
 * eklenebilir. */
export function AgentDownloadPanel() {
  const { t } = useLocale();
  const d = t.settings.download;

  const [serviceStatus, setServiceStatus] = useState<LoadStatus>("loading");
  const [serviceInfo, setServiceInfo] = useState<WindowsAgentDownloadInfo | null>(null);

  useEffect(() => {
    fetchWindowsServiceDownloadInfo()
      .then((data) => {
        setServiceInfo(data);
        setServiceStatus("done");
      })
      .catch(() => setServiceStatus("error"));
  }, []);

  return (
    <div className={styles.wrap}>
      <h4 className={styles.title}>{d.serviceTitle}</h4>
      <p className={styles.description}>{d.serviceDescription}</p>

      {serviceStatus === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {serviceStatus === "error" && <p className={styles.error}>{d.loadError}</p>}

      {serviceStatus === "done" && serviceInfo && serviceInfo.available && (
        <div className={styles.available}>
          <a className={styles.downloadButton} href={windowsServiceDownloadUrl()}>
            {d.serviceButton}
          </a>
          <dl className={styles.meta}>
            <div className={styles.metaField}>
              <dt>{d.version}</dt>
              <dd>{serviceInfo.version}</dd>
            </div>
            <div className={styles.metaField}>
              <dt>{d.fileSize}</dt>
              <dd>{formatFileSize(serviceInfo.size_bytes)}</dd>
            </div>
          </dl>
          <p className={styles.hint}>{d.serviceHint}</p>
        </div>
      )}

      {serviceStatus === "done" && serviceInfo && !serviceInfo.available && (
        <p className={styles.hint}>{d.serviceNotBuilt}</p>
      )}
    </div>
  );
}
