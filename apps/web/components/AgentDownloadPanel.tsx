"use client";

import { useEffect, useState } from "react";

import { fetchWindowsAgentDownloadInfo, windowsAgentDownloadUrl, type WindowsAgentDownloadInfo } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentDownloadPanel.module.css";

type LoadStatus = "loading" | "done" | "error";

function formatFileSize(bytes: number | null): string {
  if (bytes == null) return "-";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

export function AgentDownloadPanel() {
  const { t } = useLocale();
  const d = t.settings.download;

  const [status, setStatus] = useState<LoadStatus>("loading");
  const [info, setInfo] = useState<WindowsAgentDownloadInfo | null>(null);

  useEffect(() => {
    fetchWindowsAgentDownloadInfo()
      .then((data) => {
        setInfo(data);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }, []);

  return (
    <div className={styles.wrap}>
      <h4 className={styles.title}>{d.title}</h4>
      <p className={styles.description}>{d.description}</p>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.error}>{d.loadError}</p>}

      {status === "done" && info && !info.available && (
        <div className={styles.notBuilt}>
          <p className={styles.status}>{d.notBuilt}</p>
          <p className={styles.hint}>{d.notBuiltHint}</p>
        </div>
      )}

      {status === "done" && info && info.available && (
        <div className={styles.available}>
          <a className={styles.downloadButton} href={windowsAgentDownloadUrl()}>
            {d.windowsButton}
          </a>
          <dl className={styles.meta}>
            <div className={styles.metaField}>
              <dt>{d.version}</dt>
              <dd>{info.version}</dd>
            </div>
            <div className={styles.metaField}>
              <dt>{d.fileSize}</dt>
              <dd>{formatFileSize(info.size_bytes)}</dd>
            </div>
          </dl>
          <p className={styles.hint}>{d.noPythonRequired}</p>
        </div>
      )}
    </div>
  );
}
