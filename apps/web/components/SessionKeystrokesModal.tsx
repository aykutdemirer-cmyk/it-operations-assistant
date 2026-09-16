"use client";

import { useEffect, useState } from "react";

import { ApiError, fetchSessionKeystrokes, type PamKeystroke } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./SessionKeystrokesModal.module.css";

type Line = { timestamp: string; text: string };

const DEL_CHAR = "";

/** Ham tuş vuruşu akışını ("s","u","d","o"," ","-","l","\r", ...) okunabilir
 * satırlara indirger: `\r`/`\n` yeni bir satır başlatır, backspace (DEL/
 * `\b`) son karakteri siler. Bu bir terminal EMÜLATÖRÜ DEĞİL — ANSI kaçış
 * dizilerini (renk kodları, ok tuşu geçmiş gezinme, tab tamamlama)
 * YORUMLAMAZ, ham baytlar olduğu gibi metne girer. Amaç eksiksiz bir
 * terminal render'ı değil, "kullanıcı ne yazdı" sorusuna dürüst/okunabilir
 * bir yaklaşık cevap (bkz. proje genelindeki "gerçek olmayan veriyi
 * uydurma" ilkesi — mükemmel bir emülatör YERİNE dürüst bir yaklaşıklık
 * tercih edildi). */
function buildLines(keystrokes: PamKeystroke[]): Line[] {
  const lines: Line[] = [];
  let current = "";
  let currentTimestamp: string | null = null;

  for (const keystroke of keystrokes) {
    for (const ch of keystroke.data) {
      if (currentTimestamp === null) currentTimestamp = keystroke.recorded_at;
      if (ch === "\r" || ch === "\n") {
        lines.push({ timestamp: currentTimestamp, text: current });
        current = "";
        currentTimestamp = null;
      } else if (ch === DEL_CHAR || ch === "\b") {
        current = current.slice(0, -1);
      } else {
        current += ch;
      }
    }
  }
  if (current) {
    lines.push({ timestamp: currentTimestamp ?? keystrokes[keystrokes.length - 1]?.recorded_at ?? "", text: current });
  }
  return lines;
}

export function SessionKeystrokesModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetchSessionKeystrokes(token, sessionId)
      .then((data) => {
        if (cancelled) return;
        setLines(buildLines(data));
        setStatus("done");
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMessage(err instanceof ApiError ? err.message : p.keystrokesLoadError);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token, sessionId, p.keystrokesLoadError]);

  return (
    <div className={styles.overlay} role="presentation" onClick={onClose}>
      <div className={styles.panel} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h3 className={styles.title}>{p.keystrokesTitle}</h3>
          <button type="button" className={styles.closeButton} onClick={onClose}>
            {p.close}
          </button>
        </div>

        {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
        {status === "error" && <p className={styles.status}>{errorMessage}</p>}
        {status === "done" && lines.length === 0 && <p className={styles.status}>{p.keystrokesEmpty}</p>}

        {status === "done" && lines.length > 0 && (
          <div className={styles.terminal}>
            {lines.map((line, i) => (
              <div key={i}>
                <span className={styles.timestamp}>{new Date(line.timestamp).toLocaleTimeString()} {"->"}</span>
                {line.text}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
