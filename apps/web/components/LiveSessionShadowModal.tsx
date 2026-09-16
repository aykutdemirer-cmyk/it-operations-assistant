"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { pamShadowConnectData, pamShadowWebSocketUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./LiveSessionShadowModal.module.css";

// `Guacamole.Client`'ın `onstatechange` sabitleri — bkz. AYNI değerler
// `GuacamoleRdpViewer.tsx`'te kullanılıyor, kütüphane resmi bir enum
// export etmiyor.
const GUAC_STATE_CONNECTED = 3;
const GUAC_STATE_DISCONNECTED = 0;

/** Faz 51 — "Canlı İzle" (Live Session Shadowing): `GuacamoleRdpViewer`'ın
 * SALT-OKUNUR bir kardeşi — mouse/keyboard input WIRING'i KASITLI olarak
 * YOK (fare/klavye event handler'ları hiç eklenmiyor, `client.send*`
 * hiçbir yerde çağrılmıyor). Backend'in `/api/pam/audit/{id}/shadow`
 * endpoint'i guacd ile KENDİ el sıkışmasını yapmıyor — mevcut birincil
 * bağlantının çıktısını yayınlıyor (bkz. `app/pam/session_registry.py::
 * publish_to_shadows`). Oturum kaydı ETKİN DEĞİLSE ekran katılma anına
 * kadar boş kalabilir — bu, backend'in `error`/`info` mesajıyla DEĞİL,
 * burada sabit bir dipnotla belirtiliyor (bkz. `app/routes/pam_audit.py::
 * shadow_session_route` docstring'i — dürüst, belgelenmiş bir sınır). */
export function LiveSessionShadowModal({
  sessionId,
  deviceLabel,
  onClose,
}: {
  sessionId: string;
  deviceLabel: string;
  onClose: () => void;
}) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const containerRef = useRef<HTMLDivElement>(null);
  const stageWrapRef = useRef<HTMLDivElement>(null);
  /* eslint-disable @typescript-eslint/no-explicit-any */
  const clientRef = useRef<any>(null);
  /* eslint-enable @typescript-eslint/no-explicit-any */

  const [status, setStatus] = useState<"connecting" | "connected" | "closed" | "error">("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !containerRef.current) return;
    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let client: any = null;

    async function connect() {
      const Guacamole = (await import("guacamole-common-js")).default;
      if (cancelled || !containerRef.current) return;

      const tunnel = new Guacamole.WebSocketTunnel(pamShadowWebSocketUrl(sessionId));
      client = new Guacamole.Client(tunnel);
      clientRef.current = client;
      const display = client.getDisplay();

      containerRef.current.innerHTML = "";
      containerRef.current.appendChild(display.getElement());

      // GERÇEK bir eksiklik: `GuacamoleRdpViewer.tsx`'in Faz 48'de
      // bulduğu AYNI hatanın izleme tarafındaki karşılığı — ekran
      // hiç ÖLÇEKLENMİYORDU, gerçek RDP çözünürlüğü kapsayıcıdan
      // büyükse kullanıcı yalnızca kayan görünümün bir köşesini
      // görüyordu (tam ekrana geçmeden düzelmiyordu). `display.
      // onresize` İLK ekran paketi geldiğinde (gerçek boyut ilk kez
      // bilinir) VE her yeniden boyutlandırmada tetiklenir — bu yüzden
      // ayrı bir "mount'ta bir kere dene" çağrısı YETERSİZ olurdu.
      const applyFitScale = () => {
        if (!containerRef.current) return;
        const displayWidth = display.getWidth();
        const displayHeight = display.getHeight();
        if (!displayWidth || !displayHeight) return;
        const containerWidth = containerRef.current.clientWidth;
        const containerHeight = containerRef.current.clientHeight;
        if (!containerWidth || !containerHeight) return;
        display.scale(Math.min(containerWidth / displayWidth, containerHeight / displayHeight));
      };
      display.onresize = applyFitScale;

      client.onstatechange = (state: number) => {
        if (cancelled) return;
        if (state === GUAC_STATE_CONNECTED) {
          setStatus("connected");
          applyFitScale();
        } else if (state === GUAC_STATE_DISCONNECTED) {
          setStatus((prev) => (prev === "connected" ? "closed" : prev));
        }
      };
      client.onerror = (err: { message?: string }) => {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(err?.message || p.shadowLoadError);
      };

      window.addEventListener("resize", applyFitScale);
      document.addEventListener("fullscreenchange", applyFitScale);

      client.connect(pamShadowConnectData(token as string));

      return () => {
        window.removeEventListener("resize", applyFitScale);
        document.removeEventListener("fullscreenchange", applyFitScale);
      };
    }

    let removeResizeListener: (() => void) | undefined;
    connect()
      .then((cleanup) => {
        removeResizeListener = cleanup;
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("error");
          setErrorMessage(p.shadowLoadError);
        }
      });

    return () => {
      cancelled = true;
      removeResizeListener?.();
      client?.disconnect();
      clientRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sessionId]);

  const handleFullscreen = useCallback(() => {
    stageWrapRef.current?.requestFullscreen?.();
  }, []);

  return (
    <div className={styles.overlay} role="presentation" onClick={onClose}>
      <div className={styles.dialog} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <h3 className={styles.title}>
              {p.shadowTitle} — {deviceLabel}
            </h3>
            <span className={styles.readOnlyBadge}>{p.shadowReadOnlyBadge}</span>
          </div>
          <div className={styles.headerActions}>
            <button type="button" className={styles.closeButton} onClick={handleFullscreen} disabled={status !== "connected"}>
              {p.rdpFullscreen}
            </button>
            <button type="button" className={styles.closeButton} onClick={onClose}>
              {p.close}
            </button>
          </div>
        </div>

        <div className={styles.stage} ref={stageWrapRef}>
          {/* GERÇEK bir React/DOM çakışması bulunup düzeltildi: bu
              kapsayıcı YALNIZCA `connect()` içinde manuel `appendChild`
              ile doldurulur, React BURAYA HİÇBİR ZAMAN kendi child'ını
              render ETMEZ (bkz. `GuacamoleRdpViewer.tsx`'teki AYNI
              desen) — durum bindirmesi (statusOverlay) bunun yerine
              AYRI, kardeş bir React-yönetimli div. Önceden ikisi AYNI
              ref'li div içindeydi; `status` her değiştiğinde React
              kendi child'ını (statusOverlay) kaldırmaya çalışıyor ama
              o düğüm `connect()`'in `innerHTML = ""` çağrısıyla ZATEN
              silinmiş oluyordu — "Failed to execute 'removeChild'..."
              hatasının kök nedeni buydu. */}
          <div className={styles.canvasInner} ref={containerRef} />
          {status !== "connected" && (
            <div className={styles.statusOverlay}>
              {status === "connecting" && p.shadowConnecting}
              {status === "closed" && p.shadowSessionEnded}
              {status === "error" && <span className={styles.errorText}>{errorMessage || p.shadowLoadError}</span>}
            </div>
          )}
        </div>

        <p className={styles.footnote}>{p.shadowFootnote}</p>
      </div>
    </div>
  );
}
