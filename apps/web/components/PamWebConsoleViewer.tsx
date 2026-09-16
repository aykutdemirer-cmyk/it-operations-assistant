"use client";

import { ArrowLeft, LogOut, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  closeWebConsoleSession,
  fetchMyAccess,
  startWebConsoleSession,
  type AuthorizedAsset,
  type WebConsoleSession,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./PamWebConsoleViewer.module.css";

type Phase = "connecting" | "connected" | "closed" | "error";

/** Faz 76 — PAM Web Konsolu: zero-knowledge HTTPS kimlik enjeksiyonu.
 * Kimlik bilgisi bu component'e HİÇBİR ZAMAN ulaşmaz — backend (`app/
 * routes/pam_web.py`) hedefin giriş formuna sunucu tarafında enjekte
 * edip oturum çerezlerini saklar, bu ekran yalnızca sonucu bir
 * `<iframe>` içinde (backend'in ters-proxy'lediği, `/api/pam/web/
 * proxy/{session_id}/` — göreli yol, `next.config.ts`'in mevcut `/api/*`
 * proxy'si üzerinden AYNI origin'den akar) gösterir. GuacamoleRdpViewer
 * ile AYNI koyu "session screen" görsel dili. */
export function PamWebConsoleViewer({ assetId }: { assetId: string }) {
  const { token } = useAuth();
  const { t } = useLocale();
  const v = t.pamWeb;

  const [phase, setPhase] = useState<Phase>("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [session, setSession] = useState<WebConsoleSession | null>(null);
  const [asset, setAsset] = useState<AuthorizedAsset | null>(null);
  const sessionRef = useRef<WebConsoleSession | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchMyAccess(token)
      .then((assets) => setAsset(assets.find((a) => a.asset_id === assetId) ?? null))
      .catch(() => {
        /* araç çubuğu cihaz adı olmadan da çalışır */
      });
  }, [token, assetId]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    startWebConsoleSession(token, assetId)
      .then((result) => {
        if (cancelled) return;
        setSession(result);
        sessionRef.current = result;
        setPhase("connected");
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : v.connectionError);
        setPhase("error");
      });

    return () => {
      cancelled = true;
      if (token && sessionRef.current) {
        closeWebConsoleSession(token, sessionRef.current.session_id);
      }
    };
  }, [token, assetId, v.connectionError]);

  function handleDisconnect() {
    if (token && session) closeWebConsoleSession(token, session.session_id);
    setPhase("closed");
    setSession(null);
  }

  const deviceLabel = asset?.asset_hostname || asset?.asset_ip_address || assetId;

  return (
    <div className={styles.page}>
      <Link href="/my-access" className={styles.backLink}>
        <ArrowLeft size={14} />
        {t.pam.rdpBackToMyAccess}
      </Link>

      <div className={styles.stage}>
        <div className={styles.toolbar}>
          <div className={styles.statusGroup}>
            <span
              className={`${styles.statusDot} ${
                phase === "connected" ? styles.statusDotConnected : phase === "error" ? styles.statusDotError : styles.statusDotConnecting
              }`}
              aria-hidden="true"
            />
            <span className={styles.deviceName}>{deviceLabel}</span>
            <span>
              {phase === "connected" && v.statusConnected}
              {phase === "connecting" && v.statusConnecting}
              {phase === "closed" && v.statusClosed}
              {phase === "error" && v.statusError}
            </span>
          </div>
          <button type="button" className={styles.exitButton} onClick={handleDisconnect}>
            <LogOut size={14} />
            {t.pam.rdpDisconnect}
          </button>
        </div>

        {phase === "connected" && session && (
          <iframe title={v.iframeTitle} className={styles.frame} src={session.proxy_url} />
        )}

        {phase === "closed" && <p className={styles.closedBox}>{t.pam.rdpSessionClosed}</p>}

        {phase === "error" && (
          <div className={styles.errorBox}>
            <p>{errorMessage}</p>
          </div>
        )}

        {phase === "connecting" && (
          <div className={styles.loaderOverlay}>
            <div className={styles.loaderRing}>
              <span className={styles.loaderSpinner} aria-hidden="true" />
              <ShieldCheck size={28} className={styles.loaderIcon} />
            </div>
            <p>{v.connecting}</p>
          </div>
        )}
      </div>
    </div>
  );
}
