"use client";

import {
  ArrowLeft,
  Clipboard,
  Clock,
  Expand,
  FolderOpen,
  KeySquare,
  LogOut,
  Maximize,
  ShieldCheck,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { fetchMyAccess, pamRdpConnectData, pamRdpWebSocketUrl, type AuthorizedAsset } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./GuacamoleRdpViewer.module.css";
import { ToastStack, useToasts } from "./Toast";

type Phase = "connecting" | "connected" | "closed" | "error";

// `Guacamole.Client`'ın `onstatechange` sabitleri (bkz. guacamole-
// common-js kaynağı) — resmi bir enum export etmiyor, sayısal
// değerler kütüphanenin kendi belgelenmiş sözleşmesi.
const GUAC_STATE_CONNECTED = 3;
const GUAC_STATE_DISCONNECTED = 0;

// X11 keysym'leri — `Guacamole.Keyboard` tarayıcı olaylarını zaten bu
// standarda çevirip gönderiyor; "Ctrl+Alt+Del" makro tuşu tarayıcının
// KENDİSİ tarafından yakalanıp işletim sistemine iletildiği için (bu,
// güvenlik amaçlı bir tarayıcı kısıtlamasıdır, RDP-in-browser
// araçlarının ORTAK sorunu) aynı üç tuşu DOĞRUDAN sunucuya (guacd
// üzerinden gerçek RDP oturumuna) senkron göndermek gerekiyor.
const KEYSYM_CTRL = 0xffe3;
const KEYSYM_ALT = 0xffe9;
const KEYSYM_DELETE = 0xffff;

type Props = {
  assetId: string;
};

// Faz 74 — Sürücü Yönlendirme (Dosya Transferi).
type UploadEntry = { id: string; name: string; status: "pending" | "done" | "error" };

/** Faz 48 — Apache Guacamole tabanlı, istemcisiz (clientless) HTML5 RDP
 * oturumu. Kimlik bilgisi bu component'e HİÇBİR ZAMAN ulaşmaz — backend
 * (`app/routes/pam_rdp.py`) guacd'ye bağlanıp el sıkışmayı
 * TAMAMLADIKTAN sonra WebSocket'i kabul eder, bu component yalnızca
 * ekran/fare/klavye/pano akışını taşır. Gerçek `guacd`'ye karşı canlı
 * doğrulandı (bkz. docs/roadmap.md Faz 48 notu — URL/subprotocol/
 * instruction-tamponlama hataları bulunup düzeltildi).
 *
 * UI KASITLI olarak sabit koyu (CyberArk/Teleport tarzı "session
 * screen") — projenin geri kalanı gibi açık/koyu tema DEĞİŞTİRİLEBİLİR
 * değil, bkz. `.module.css` başındaki not. Tailwind/Shadcn EKLENMEDİ —
 * bu proje 48 faz boyunca hiç kullanmadı, tek bir sayfa için tüm
 * projeye yeni bir CSS/derleme altyapısı eklemek orantısız bir mimari
 * değişiklik olurdu; aynı görsel sonuç mevcut CSS Modules deseniyle
 * üretildi (`lucide-react` ikonlar için tek yeni, düşük riskli
 * bağımlılık). Sahte bir "ping/ms" gecikme değeri HİÇBİR ZAMAN
 * gösterilmiyor (bu proje hiçbir yerde uydurma metrik göstermiyor) —
 * yalnızca gerçek bağlantı durumu ve PAM kuralının GERÇEK süresinden
 * geri sayan bir zamanlayıcı var.
 *
 * Faz 74 — Çift Yönlü Pano + Sürücü Yönlendirme: `onclipboard` (uzak
 * →yerel) + mevcut `handleSendClipboard`'un (yerel→uzak) YANINA;
 * backend `enable-drive` gönderdiyse (`GUACD_DRIVE_PATH` yapılandırılmışsa)
 * `onfilesystem` ile açılan GERÇEK bir `Guacamole.Object` üzerinden
 * sürükle-bırak/buton ile dosya YÜKLEME (yalnızca yükleme — uzak
 * dizin gezme/indirme bu artırımda YOK, bkz. docs/roadmap.md Faz 74). */
export function GuacamoleRdpViewer({ assetId }: Props) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const containerRef = useRef<HTMLDivElement>(null);
  const displayWrapRef = useRef<HTMLDivElement>(null);
  // `guacamole-common-js` resmi tip tanımı yayınlamıyor (bkz. `types/
  // guacamole-common-js.d.ts`) — `Guacamole.Client` örneği burada
  // KASITLI olarak `any`.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const clientRef = useRef<any>(null);
  // Faz 74 — `Guacamole.Object` filesystem — `client.onfilesystem`
  // sürücü paylaşımı ETKİNSE (backend `GUACD_DRIVE_PATH` yapılandırıldıysa)
  // dolar, aksi halde `null` kalır (yükleme butonları dürüstçe devre
  // dışı kalır — sessiz bir başarısızlık YOK).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filesystemRef = useRef<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [phase, setPhase] = useState<Phase>("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [asset, setAsset] = useState<AuthorizedAsset | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
  const [driveAvailable, setDriveAvailable] = useState(false);
  const [showFilesPanel, setShowFilesPanel] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [uploads, setUploads] = useState<UploadEntry[]>([]);
  const { toasts, push, dismiss } = useToasts();

  // Araç çubuğundaki cihaz adı/IP + geri sayımın başlangıç değeri
  // `GET /api/pam/my-access`'ten (tek doğruluk kaynağı — bu ekran
  // ayrı bir query-string ile TAŞINMIYOR) okunuyor.
  useEffect(() => {
    if (!token) return;
    fetchMyAccess(token)
      .then((assets) => {
        const match = assets.find((a) => a.asset_id === assetId);
        if (match) {
          setAsset(match);
          setRemainingSeconds(match.max_session_duration_mins * 60);
        }
      })
      .catch(() => {
        // Sessizce yoksay — araç çubuğu cihaz adı/geri sayım olmadan
        // da çalışır, asıl RDP bağlantısını ENGELLEMEZ.
      });
  }, [token, assetId]);

  const hasCountdown = remainingSeconds !== null;
  useEffect(() => {
    if (phase !== "connected" || !hasCountdown) return;
    const interval = setInterval(() => {
      setRemainingSeconds((prev) => (prev === null ? null : Math.max(0, prev - 1)));
    }, 1000);
    return () => clearInterval(interval);
  }, [phase, hasCountdown]);

  // Bağlı oturumun "Ekrana Sığdır" ölçeklendirmesini (bkz. aşağıdaki
  // `applyFitScale`) hem otomatik (bağlanınca/pencere boyutu
  // değişince) hem de araç çubuğundaki butondan tetiklemek için.
  const applyFitScaleRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!token || !containerRef.current) return;
    let cancelled = false;
    // `guacamole-common-js` tip tanımı yok (bkz. `types/guacamole-
    // common-js.d.ts`) — bu iki değişken KASITLI olarak `any`.
    /* eslint-disable @typescript-eslint/no-explicit-any */
    let client: any = null;
    let keyboard: any = null;
    /* eslint-enable @typescript-eslint/no-explicit-any */

    async function connect() {
      const Guacamole = (await import("guacamole-common-js")).default;
      if (cancelled || !containerRef.current) return;

      const width = containerRef.current.clientWidth || 1280;
      const height = containerRef.current.clientHeight || 800;
      const dpi = typeof window !== "undefined" && window.devicePixelRatio ? Math.round(window.devicePixelRatio * 96) : 96;

      const tunnel = new Guacamole.WebSocketTunnel(pamRdpWebSocketUrl(assetId));
      client = new Guacamole.Client(tunnel);
      clientRef.current = client;
      const display = client.getDisplay();

      const displayElement = display.getElement();
      containerRef.current.innerHTML = "";
      containerRef.current.appendChild(displayElement);

      // GERÇEK, canlı test sırasında bulunan bir üretim hatası: ekran
      // eskiden `overflow:auto` içinde ORTALANIP hiç ÖLÇEKLENMİYORDU —
      // gerçek RDP çözünürlüğü (ör. 1280×800) görünür kapsayıcıdan
      // BÜYÜKSE, kullanıcı yalnızca kayan görünümün rastgele bir
      // (genelde siyah) köşesini görüyordu; tam ekrana geçmek kapsayıcıyı
      // büyütüp gerçek içeriği tesadüfen görünür kıldığı için "düzeliyor"
      // gibi görünüyordu. Doğrusu: `Guacamole.Display.scale()` ile
      // kapsayıcıya TAM SIĞACAK şekilde gerçekten küçültüp/büyütmek —
      // her gerçek çözünürlük değişikliğinde (`display.onresize`) VE
      // pencere yeniden boyutlandığında yeniden uygulanır.
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
      applyFitScaleRef.current = applyFitScale;
      display.onresize = applyFitScale;

      client.onstatechange = (state: number) => {
        if (cancelled) return;
        if (state === GUAC_STATE_CONNECTED) {
          setPhase("connected");
          applyFitScale();
        } else if (state === GUAC_STATE_DISCONNECTED) {
          setPhase((prev) => (prev === "connected" ? "closed" : prev));
        }
      };
      client.onerror = (err: { message?: string }) => {
        if (cancelled) return;
        setPhase("error");
        setErrorMessage(err?.message || p.rdpConnectionError);
      };

      // Faz 74 — sürücü paylaşıldığında (backend `enable-drive: true`
      // gönderdiyse) guacd bu callback'i TAM OLARAK BİR KEZ tetikler.
      client.onfilesystem = (object: unknown) => {
        if (cancelled) return;
        filesystemRef.current = object;
        setDriveAvailable(true);
      };

      // Faz 74 — uzak oturumda kopyalanan metni (gerçek `clipboard`
      // instruction'ı, backend `disable-copy: false` gönderdiği için
      // guacd bunu iletiyor) tarayıcı panosuna yazmayı DENER — bazı
      // tarayıcı bağlamları bunu bir kullanıcı jestinden bağımsız
      // reddedebilir, bu durumda sessizce yutulur ("Panoyu Gönder"
      // butonunun mevcut davranışı ETKİLENMEZ).
      client.onclipboard = async (stream: unknown, mimetype: string) => {
        if (cancelled || mimetype !== "text/plain") return;
        const Guacamole = (await import("guacamole-common-js")).default;
        const reader = new Guacamole.StringReader(stream);
        let text = "";
        reader.ontext = (chunk: string) => {
          text += chunk;
        };
        reader.onend = () => {
          if (cancelled) return;
          navigator.clipboard
            .writeText(text)
            .then(() => push("success", p.rdpClipboardReceived))
            .catch(() => {
              /* tarayıcı izni yok — sessizce yutulur */
            });
        };
      };

      const mouse = new Guacamole.Mouse(displayElement);
      const handleMouseEvent = (mouseState: unknown) => client.sendMouseState(mouseState);
      mouse.onmousedown = handleMouseEvent;
      mouse.onmouseup = handleMouseEvent;
      mouse.onmousemove = handleMouseEvent;

      keyboard = new Guacamole.Keyboard(document);
      keyboard.onkeydown = (keysym: number) => client.sendKeyEvent(1, keysym);
      keyboard.onkeyup = (keysym: number) => client.sendKeyEvent(0, keysym);

      window.addEventListener("resize", applyFitScale);
      // Tam ekrana giriş/çıkış her zaman bir "resize" tetiklemeyebiliyor
      // (tarayıcıya göre değişir) — ayrıca dinlenir.
      document.addEventListener("fullscreenchange", applyFitScale);

      // GERÇEK tarayıcıda bulunup düzeltilen bir hata: `Guacamole.
      // WebSocketTunnel` HER ZAMAN `new WebSocket(tunnelURL + "?" +
      // data)` yapıyor (kütüphanenin kaynağında doğrulandı) — query
      // string'i `tunnelURL`'in KENDİSİNE koymak İKİNCİ bir `?` ekleyip
      // URL'yi bozuyordu. Doğrusu: `tunnelURL` çıplak, gerçek query
      // string'i BURADA `connect(data)`'ye geçirmek.
      client.connect(pamRdpConnectData(token!, width, height, dpi));

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
          setPhase("error");
          setErrorMessage(p.rdpConnectionError);
        }
      });

    return () => {
      cancelled = true;
      removeResizeListener?.();
      if (keyboard) {
        keyboard.onkeydown = null;
        keyboard.onkeyup = null;
      }
      client?.disconnect();
      clientRef.current = null;
      filesystemRef.current = null;
      setDriveAvailable(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId, token]);

  const handleDisconnect = useCallback(() => {
    clientRef.current?.disconnect();
    setPhase("closed");
  }, []);

  const handleFitToScreen = useCallback(() => {
    applyFitScaleRef.current();
  }, []);

  const handleFullscreen = useCallback(() => {
    displayWrapRef.current?.requestFullscreen?.();
  }, []);

  const handleCtrlAltDel = useCallback(() => {
    const client = clientRef.current;
    if (!client) return;
    client.sendKeyEvent(1, KEYSYM_CTRL);
    client.sendKeyEvent(1, KEYSYM_ALT);
    client.sendKeyEvent(1, KEYSYM_DELETE);
    client.sendKeyEvent(0, KEYSYM_DELETE);
    client.sendKeyEvent(0, KEYSYM_ALT);
    client.sendKeyEvent(0, KEYSYM_CTRL);
  }, []);

  // Faz 74 — `Guacamole.Object.createOutputStream` + `Guacamole.
  // BlobWriter` ile GERÇEK bayt akışı — RDP sürücüsüne dosya İÇERİĞİ
  // gerçekten yazılır (metadata/isim uydurma DEĞİL).
  const handleUploadFiles = useCallback(
    async (files: FileList | File[]) => {
      const filesystem = filesystemRef.current;
      if (!filesystem) {
        push("error", p.rdpDriveNotAvailable);
        return;
      }
      const Guacamole = (await import("guacamole-common-js")).default;
      for (const file of Array.from(files)) {
        const id = `${file.name}-${Date.now()}-${Math.random()}`;
        setUploads((prev) => [{ id, name: file.name, status: "pending" }, ...prev]);
        push("success", p.rdpUploadStarted(file.name));
        try {
          const stream = filesystem.createOutputStream(file.type || "application/octet-stream", file.name);
          const writer = new Guacamole.BlobWriter(stream);
          await new Promise<void>((resolve, reject) => {
            writer.onerror = () => reject(new Error("upload failed"));
            writer.oncomplete = () => resolve();
            writer.sendBlob(file);
          });
          setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, status: "done" } : u)));
          push("success", p.rdpUploadSuccess(file.name));
        } catch {
          setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, status: "error" } : u)));
          push("error", p.rdpUploadError(file.name));
        }
      }
    },
    [p, push],
  );

  const handleFileInputChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) handleUploadFiles(e.target.files);
      e.target.value = "";
    },
    [handleUploadFiles],
  );

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragActive(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) handleUploadFiles(e.dataTransfer.files);
    },
    [handleUploadFiles],
  );

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
  }, []);

  const handleSendClipboard = useCallback(async () => {
    const client = clientRef.current;
    if (!client) return;
    try {
      const text = await navigator.clipboard.readText();
      const stream = client.createClipboardStream("text/plain");
      const writer = new (await import("guacamole-common-js")).default.StringWriter(stream);
      writer.sendText(text);
      writer.sendEnd();
      push("success", p.rdpClipboardSent);
    } catch {
      push("error", p.rdpClipboardError);
    }
  }, [p, push]);

  const connected = phase === "connected";
  const deviceLabel = asset?.asset_hostname || asset?.asset_ip_address || assetId;
  const showLoader = phase === "connecting";

  return (
    <div className={styles.page}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />

      <Link href="/my-access" className={styles.backLink}>
        <ArrowLeft size={14} />
        {p.rdpBackToMyAccess}
      </Link>

      <div className={styles.stage}>
        <div
          ref={displayWrapRef}
          className={styles.canvasFrame}
          onDragOver={driveAvailable ? handleDragOver : undefined}
          onDragLeave={driveAvailable ? handleDragLeave : undefined}
          onDrop={driveAvailable ? handleDrop : undefined}
        >
          <input ref={fileInputRef} type="file" multiple hidden onChange={handleFileInputChange} />
          <div className={styles.toolbar}>
            <div className={styles.statusGroup}>
              <span
                className={`${styles.statusDot} ${
                  phase === "connected"
                    ? styles.statusDotConnected
                    : phase === "error"
                      ? styles.statusDotError
                      : styles.statusDotConnecting
                }`}
                aria-hidden="true"
              />
              <span className={styles.deviceName}>{deviceLabel}</span>
              {asset?.asset_ip_address && <span className={styles.deviceIp}>{asset.asset_ip_address}</span>}
              <span>
                {phase === "connected" && p.rdpStatusConnected}
                {phase === "connecting" && p.rdpStatusConnecting}
                {phase === "closed" && p.rdpStatusClosed}
                {phase === "error" && p.rdpStatusError}
              </span>
            </div>

            {remainingSeconds !== null && (
              <>
                <span className={styles.divider} aria-hidden="true" />
                <span
                  className={`${styles.countdown} ${remainingSeconds < 300 ? styles.countdownWarning : ""}`}
                  title={p.rdpTimeRemaining}
                >
                  <Clock size={14} />
                  {formatCountdown(remainingSeconds)}
                </span>
              </>
            )}

            <span className={styles.divider} aria-hidden="true" />

            <div className={styles.toolbarActions}>
              <button
                type="button"
                className={styles.toolbarButton}
                onClick={handleSendClipboard}
                disabled={!connected}
                title={p.rdpSendClipboard}
              >
                <Clipboard size={14} />
              </button>
              <button
                type="button"
                className={styles.toolbarButton}
                onClick={() => fileInputRef.current?.click()}
                disabled={!connected || !driveAvailable}
                title={driveAvailable ? p.rdpUploadFile : p.rdpDriveNotAvailable}
              >
                <Upload size={14} />
              </button>
              <button
                type="button"
                className={styles.toolbarButton}
                onClick={() => setShowFilesPanel((v) => !v)}
                disabled={!connected}
                title={p.rdpFileTransfer}
              >
                <FolderOpen size={14} />
              </button>
              <button
                type="button"
                className={styles.toolbarButton}
                onClick={handleCtrlAltDel}
                disabled={!connected}
                title={p.rdpCtrlAltDel}
              >
                <KeySquare size={14} />
              </button>
              <button
                type="button"
                className={styles.toolbarButton}
                onClick={handleFitToScreen}
                disabled={!connected}
                title={p.rdpFitToScreen}
              >
                <Expand size={14} />
              </button>
              <button
                type="button"
                className={styles.toolbarButton}
                onClick={handleFullscreen}
                disabled={!connected}
                title={p.rdpFullscreen}
              >
                <Maximize size={14} />
              </button>
              <button type="button" className={styles.exitButton} onClick={handleDisconnect}>
                <LogOut size={14} />
                {p.rdpDisconnect}
              </button>
            </div>
          </div>

          {dragActive && (
            <div className={styles.dropOverlay} aria-hidden="true">
              <span className={styles.dropOverlayText}>{p.rdpDropFilesHere}</span>
            </div>
          )}

          {showFilesPanel && (
            <div className={styles.filesPanel}>
              <span className={styles.filesPanelTitle}>{p.rdpFileTransfer}</span>
              {!driveAvailable && <p>{p.rdpDriveNotAvailable}</p>}
              {driveAvailable && uploads.length === 0 && <p>{p.rdpNoUploads}</p>}
              {uploads.map((u) => (
                <div key={u.id} className={styles.uploadRow}>
                  <span className={styles.uploadName} title={u.name}>
                    {u.name}
                  </span>
                  <span
                    className={
                      u.status === "done"
                        ? styles.uploadStatusDone
                        : u.status === "error"
                          ? styles.uploadStatusError
                          : styles.uploadStatusPending
                    }
                  >
                    {u.status === "done" ? "✓" : u.status === "error" ? "✕" : "…"}
                  </span>
                </div>
              ))}
            </div>
          )}

          {phase === "closed" && <p className={styles.closedBox}>{p.rdpSessionClosed}</p>}
          {phase === "error" && (
            <div className={styles.errorBox}>
              <p>{errorMessage}</p>
              <p>{p.rdpInfraMissing}</p>
            </div>
          )}

          {/* GERÇEK, canlı test sırasında bulunan bir üretim hatası:
              bu container eskiden `display: none` ile gizlenip
              yalnızca "Bağlı" durumunda gösteriliyordu — ama Guacamole
              "Bağlı" durumuna geçmeden ÖNCE de arka planda kendi
              canvas'ına çizim yapıyor; bazı tarayıcılar `display:none`
              İKEN çizilen bir canvas'ı tekrar gösterilince DOĞRU
              tazelemiyor (siyah kalıyordu, yalnızca tam ekrana geçiş
              tarayıcıya zorla bir reflow yaptırdığı için düzeliyordu).
              Artık HER ZAMAN render ediliyor — yükleme sırasında
              görünmemesi gereken kısmı zaten üstteki `loaderOverlay`
              (neredeyse opak arka planıyla) görsel olarak KAPATIYOR. */}
          <div className={styles.canvasInner} ref={containerRef} />

          <div className={`${styles.loaderOverlay} ${showLoader ? "" : styles.loaderOverlayHidden}`}>
            <div className={styles.loaderRing}>
              <span className={styles.loaderSpinner} aria-hidden="true" />
              <ShieldCheck size={28} className={styles.loaderIcon} />
            </div>
            <div>
              <p className={styles.loaderTitle}>{p.rdpLoaderTitle}</p>
              <p className={styles.loaderText}>{p.rdpLoaderText}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatCountdown(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((v) => String(v).padStart(2, "0")).join(":");
}
