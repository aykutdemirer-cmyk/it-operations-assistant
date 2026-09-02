"use client";

import { useEffect, useState } from "react";

import {
  createEnrollmentCode,
  fetchEnrollmentCodes,
  type EnrollmentCodeSummary,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentEnrollmentPanel.module.css";

type LoadStatus = "loading" | "done" | "error";

function formatRemaining(expiresAt: string, now: number, expiredLabel: string): string {
  const remainingMs = new Date(expiresAt).getTime() - now;
  if (remainingMs <= 0) return expiredLabel;
  const totalSeconds = Math.floor(remainingMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function AgentEnrollmentPanel() {
  const { t } = useLocale();
  const e = t.settings.enrollment;

  const [status, setStatus] = useState<LoadStatus>("loading");
  const [activeCodes, setActiveCodes] = useState<EnrollmentCodeSummary[]>([]);
  const [newCode, setNewCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  function load() {
    fetchEnrollmentCodes()
      .then((codes) => {
        setActiveCodes(codes);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  async function handleGenerate() {
    setGenerating(true);
    setGenerateError(null);
    setCopied(false);
    try {
      const result = await createEnrollmentCode();
      setNewCode(result);
      load();
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : e.generateError);
    } finally {
      setGenerating(false);
    }
  }

  async function handleCopy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      // pano erişimi engellenmiş olabilir — sessizce yut, kod zaten ekranda görünür
    }
  }

  return (
    <div className={styles.wrap}>
      <h4 className={styles.title}>{e.title}</h4>
      <p className={styles.description}>{e.description}</p>

      <button type="button" className={styles.generateButton} onClick={handleGenerate} disabled={generating}>
        {generating ? e.generating : e.generateButton}
      </button>

      {generateError && <p className={styles.error}>{generateError}</p>}

      {newCode && (
        <div className={styles.newCodeBox}>
          <span className={styles.newCodeLabel}>{e.newCodeLabel}</span>
          <div className={styles.codeRow}>
            <code className={styles.code}>{newCode.code}</code>
            <button type="button" className={styles.copyButton} onClick={() => handleCopy(newCode.code)}>
              {copied ? e.copied : e.copyButton}
            </button>
          </div>
          <span className={styles.countdown}>{e.expiresIn(formatRemaining(newCode.expires_at, now, e.expired))}</span>
          <p className={styles.hint}>{e.singleUseHint}</p>
        </div>
      )}

      <div className={styles.activeCodes}>
        <h5 className={styles.activeCodesTitle}>{e.activeCodesTitle}</h5>
        {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
        {status === "error" && <p className={styles.error}>{e.loadError}</p>}
        {status === "done" && activeCodes.length === 0 && <p className={styles.status}>{e.noActiveCodes}</p>}
        {status === "done" && activeCodes.length > 0 && (
          <ul className={styles.codeList}>
            {activeCodes.map((c) => (
              <li key={c.code} className={styles.codeListItem}>
                <code className={styles.codeSmall}>{c.code}</code>
                <span className={styles.countdownSmall}>{formatRemaining(c.expires_at, now, e.expired)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
