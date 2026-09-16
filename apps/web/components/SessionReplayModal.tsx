"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, fetchSessionActivityMarkers, fetchSessionIdleGaps, fetchSessionRecordingBlob, type IdleGap } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./SessionReplayModal.module.css";

const SPEEDS = [1, 2, 4] as const;
// `Guacamole.SessionRecording` gerçek zamanlı `.play()` DIŞINDA bir
// oynatma HIZI API'si sunmuyor (bkz. kaynak — yalnızca play/pause/seek
// var). 1x/2x/4x'i desteklemek için TÜM hızlarda (1x dahil) `.seek()`'i
// düzenli aralıklarla ileri çağıran manuel bir adım döngüsü kullanılıyor
// — kütüphanenin kendi zamanlamasına güvenmek yerine, tek/tutarlı bir
// kod yolu (bkz. STEP_MS).
const STEP_MS = 200;

function formatTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function SessionReplayModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const stageRef = useRef<HTMLDivElement>(null);
  const stageWrapRef = useRef<HTMLDivElement>(null);
  // `guacamole-common-js` tip tanımı yok (bkz. `types/guacamole-common-js.d.ts`).
  /* eslint-disable @typescript-eslint/no-explicit-any */
  const recordingRef = useRef<any>(null);
  /* eslint-enable @typescript-eslint/no-explicit-any */
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const removeFitListenersRef = useRef<(() => void) | null>(null);
  // `stopLoop()` çağrıldığında (veya `startLoop()` yeniden çağrılınca)
  // artırılır — bir önceki döngü "kuşağının" gecikmeli seek geri
  // çağrıları bu sayı değiştiğinde artık NO-OP olur (bkz. `startLoop`).
  const loopGenerationRef = useRef(0);
  // GERÇEK bir üretim hatası bulunup burada düzeltildi: `Guacamole.
  // SessionRecording.getPosition()` istenen HEDEF zamanı DEĞİL, o ana
  // kadar ULAŞILAN GERÇEK karenin zaman damgasını döner — kayıtta o
  // aralıkta (ör. RDP oturumunda uzun bir hareketsizlik/ekran
  // güncellemesi olmayan bir boşlukta) hiç yeni kare YOKSA, `seek()`
  // "başarıyla" tamamlanır AMA `getPosition()` DEĞİŞMEDEN kalır. Eski
  // kod bir sonraki hedefi `recording.getPosition() + STEP_MS` ile
  // hesaplıyordu — bu durumda AYNI hedefi SONSUZA KADAR tekrar tekrar
  // istiyordu (canlı testte doğrulandı: `next` hep aynı değerde
  // donuyordu). Doğrusu: kütüphanenin kare-hizalı pozisyonundan
  // BAĞIMSIZ, KENDİ istediğimiz hedefi bu ref'te biriktirmek — böylece
  // sonraki tur, bir önceki turun GERÇEKTEN ulaştığı kareden değil,
  // İSTENEN zamandan devam eder; kayıttaki boşluk sona erip bir sonraki
  // gerçek kareye ulaşıldığında ekran doğal olarak atlar.
  const virtualPositionRef = useRef(0);
  // Faz 75 — `tick()` içinde her adımda YENİDEN OKUNABİLMESİ için ref
  // olarak tutuluyor (state kullansaydı `startLoop`'un `tick` closure'ı
  // her `setIdleGaps`'te yeniden oluşturulması GEREKİRDİ — mevcut
  // "kuşak" deseniyle gereksiz karmaşıklık). Kullanıcı isteğiyle
  // (bkz. ekran görüntüsü) atlama artık HER ZAMAN açık — ayrı bir
  // toggle/soru YOK, kayıttaki gerçek boşluklar sessizce atlanıyor.
  const idleGapsRef = useRef<IdleGap[]>([]);

  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [markers, setMarkers] = useState<number[]>([]);
  const [idleGaps, setIdleGaps] = useState<IdleGap[]>([]);
  const [loadedMs, setLoadedMs] = useState(0);

  useEffect(() => {
    idleGapsRef.current = idleGaps;
  }, [idleGaps]);

  function stopLoop() {
    // Bir sonraki kuşağa geçmek, ESKİ döngünün gecikmeli/askıdaki seek
    // geri çağrılarını (aşağıya bkz.) NO-OP'a çevirir.
    loopGenerationRef.current++;
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }

  function startLoop(currentSpeed: number) {
    stopLoop();
    const generation = loopGenerationRef.current;

    // GERÇEK bir üretim hatası bulunup burada düzeltildi: eski kod
    // `setInterval` ile SABİT `STEP_MS` aralıklarla `.seek()` çağırıyordu
    // — ama `Guacamole.SessionRecording.seek()` YENİ bir çağrı geldiğinde
    // ÖNCEKİ, henüz TAMAMLANMAMIŞ seek'i OTOMATİK iptal ediyor (bkz.
    // kaynak — `abortSeek()`), VE iptal edilen bir seek'in geri çağrısı
    // HİÇBİR ZAMAN tetiklenmiyor. Büyük/karmaşık bir kayıtta TEK bir
    // seek'in tamamlanması `STEP_MS`'den UZUN sürebildiğinden, döngü
    // sürekli bir öncekini iptal edip yeni bir seek başlatıyordu. Doğrusu:
    // SABİT aralıkla değil, BİR SONRAKİ adımı yalnızca ÖNCEKİ seek'in
    // KENDİ geri çağrısı geldiğinde planlayan, kendi kendine hız
    // ayarlayan bir `setTimeout` zinciri — örtüşen bir seek çağrısı
    // YAPISAL olarak imkansız hale gelir. `virtualPositionRef` neden
    // gerekli olduğu için bkz. tanımlandığı yerdeki not.
    function tick() {
      if (loopGenerationRef.current !== generation) return;
      const recording = recordingRef.current;
      if (!recording) return;
      let next = virtualPositionRef.current + STEP_MS * currentSpeed;
      // Faz 75 — hedef bir "idle gap"in içine düşüyorsa hedefi doğrudan
      // boşluğun bitişine sıçrat — kullanıcıya SORULMADAN her zaman
      // uygulanır (kayıttaki GERÇEK boşluğu, Faz 73'ün kare-hizalı-
      // olmayan hedef takibiyle AYNI mekanizmayla, atlıyoruz — yeni bir
      // oynatma modeli DEĞİL).
      const gap = idleGapsRef.current.find((g) => next >= g.start_ms && next < g.end_ms);
      if (gap) next = gap.end_ms;
      const total = recording.getDuration();
      if (next >= total) {
        recording.seek(total, () => {
          if (loopGenerationRef.current !== generation) return;
          virtualPositionRef.current = total;
          setPosition(total);
          setPlaying(false);
        });
        return;
      }
      recording.seek(next, () => {
        if (loopGenerationRef.current !== generation) return;
        virtualPositionRef.current = next;
        setPosition(next);
        timeoutRef.current = setTimeout(tick, STEP_MS);
      });
    }

    timeoutRef.current = setTimeout(tick, STEP_MS);
  }

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    async function load() {
      try {
        const blob = await fetchSessionRecordingBlob(token as string, sessionId);
        if (cancelled) return;

        const Guacamole = (await import("guacamole-common-js")).default;

        // GERÇEK bir üretim hatası bulunup burada atlatıldı:
        // `guacamole-common-js@1.5.0`'ın KENDİ `SessionRecording`
        // kurucusu, `source instanceof Blob` dalında iç `recordingBlob`
        // değişkenini HİÇBİR ZAMAN `source`'a atamıyor (kaynakta
        // doğrulandı — yalnızca tünel dalı `recordingBlob = new Blob()`
        // yapıyor). Sonuç: `parseBlob(undefined, ...)` çağrılıyor,
        // `blob.size` `undefined` üzerinde patlıyor ve kurucudan
        // SENKRON bir `TypeError` fırlıyor — bu, önceki kodda sessizce
        // `catch`'e düşüp jenerik "Oturum kaydı yüklenemedi" mesajını
        // gösteriyordu. Gerçek bir Blob YERİNE, kütüphanenin KENDİ
        // doğru çalışan tünel dalını (ki `recordingBlob`'u doğru
        // biriktiriyor) sahte/senkron bir "tünel" nesnesiyle tetikleyip
        // önceden indirilmiş metni `Guacamole.Parser` ile buna
        // besliyoruz — üçüncü parti kütüphanenin kaynağına DOKUNULMADI
        // (node_modules kalıcı değil), yalnızca doğru çalışan API
        // yüzeyi kullanıldı.
        const text = await blob.text();
        if (cancelled) return;

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const fakeTunnel: any = {};
        const recording = new Guacamole.SessionRecording(fakeTunnel);
        recordingRef.current = recording;
        const display = recording.getDisplay();

        // Faz 48'de `GuacamoleRdpViewer.tsx`'te bulunan AYNI hata sınıfı:
        // ekran hiç ÖLÇEKLENMİYORDU — gerçek çözünürlük (ör. 1280×800)
        // görünür `.stage` alanından büyükse kullanıcı yalnızca kayan
        // görünümün bir köşesini görüyordu, tam ekrana geçmek kapsayıcıyı
        // büyütüp gerçek içeriği TESADÜFEN görünür kıldığı için
        // "düzeliyor" gibi görünüyordu. `SessionRecording`'in ekranı
        // `Guacamole.Client` ile AYNI `Guacamole.Display` sınıfını
        // kullanıyor — `onresize`, oynatma İLK karesi çizildiğinde
        // (kayıt `onload`'da HENÜZ hiçbir kare render EDİLMEMİŞ olur,
        // `currentFrame` -1'dir) VE her boyut değişikliğinde tetiklenir.
        const applyFitScale = () => {
          if (!stageRef.current) return;
          const displayWidth = display.getWidth();
          const displayHeight = display.getHeight();
          if (!displayWidth || !displayHeight) return;
          const containerWidth = stageRef.current.clientWidth;
          const containerHeight = stageRef.current.clientHeight;
          if (!containerWidth || !containerHeight) return;
          display.scale(Math.min(containerWidth / displayWidth, containerHeight / displayHeight));
        };
        display.onresize = applyFitScale;
        window.addEventListener("resize", applyFitScale);
        document.addEventListener("fullscreenchange", applyFitScale);
        removeFitListenersRef.current = () => {
          window.removeEventListener("resize", applyFitScale);
          document.removeEventListener("fullscreenchange", applyFitScale);
        };

        recording.onload = () => {
          if (cancelled) return;
          setDuration(recording.getDuration());
          setStatus("ready");
          // Kayıt oynatıcısında yaygın beklenti: `Oynat`'a hiç
          // basılmadan İLK karenin (poster frame) görünür olması —
          // `SessionRecording` `onload`'da HENÜZ hiçbir kare render
          // ETMEMİŞ olur (`currentFrame` -1), bu yüzden 0. konuma
          // açıkça `seek` ediliyor.
          recording.seek(0, () => {});
        };
        recording.onerror = (message: string) => {
          if (cancelled) return;
          console.error("[SessionReplayModal] Guacamole.SessionRecording hatası:", message);
          setErrorMessage(message || p.replayLoadError);
          setStatus("error");
        };
        recording.onprogress = (durationMs: number) => {
          if (cancelled) return;
          setLoadedMs(durationMs);
        };

        if (stageRef.current) {
          stageRef.current.appendChild(display.getElement());
        }

        // Dosya TAMAMEN ayrıştırıldıktan (`onload`) SONRA `status`
        // "ready" olur — oynatma kontrolleri zaten `disabled={status
        // !== "ready"}` ile buna bağlı, bu yüzden `togglePlay()`
        // ayrıştırma bitmeden asla tetiklenemez.
        const parser = new Guacamole.Parser();
        parser.oninstruction = (opcode: string, args: string[]) => fakeTunnel.oninstruction?.(opcode, args);
        parser.receive(text);
        fakeTunnel.onstatechange?.(Guacamole.Tunnel.State.CLOSED);
      } catch (err) {
        if (cancelled) return;
        console.error("[SessionReplayModal] Kayıt yüklenemedi:", err);
        setErrorMessage(err instanceof ApiError ? err.message : p.replayLoadError);
        setStatus("error");
      }
    }

    load();

    return () => {
      cancelled = true;
      stopLoop();
      removeFitListenersRef.current?.();
      removeFitListenersRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sessionId]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    // Zaman çubuğu işaretleri yalnızca kozmetik bir katman — alınamazsa
    // (ör. eski bir kayıt/ağ hatası) replay'in kendisi ETKİLENMEZ,
    // sessizce boş kalır.
    fetchSessionActivityMarkers(token, sessionId)
      .then((result) => {
        if (!cancelled) setMarkers(result);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token, sessionId]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    // Faz 75 — idle-gap bandı da yalnızca kozmetik/atlama-yardımcısı bir
    // katman; alınamazsa replay'in kendisi ETKİLENMEZ, atlama sessizce
    // devre dışı kalır (boş liste).
    fetchSessionIdleGaps(token, sessionId)
      .then((result) => {
        if (!cancelled) setIdleGaps(result);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token, sessionId]);

  function togglePlay() {
    if (playing) {
      setPlaying(false);
      stopLoop();
    } else {
      setPlaying(true);
      startLoop(speed);
    }
  }

  function handleSpeedChange(next: 1 | 2 | 4) {
    setSpeed(next);
    if (playing) startLoop(next);
  }

  function handleSeek(e: React.ChangeEvent<HTMLInputElement>) {
    const target = Number(e.target.value);
    const recording = recordingRef.current;
    if (!recording) return;
    stopLoop();
    setPlaying(false);
    virtualPositionRef.current = target;
    recording.seek(target, () => setPosition(target));
  }

  function seekToMarker(target: number) {
    const recording = recordingRef.current;
    if (!recording) return;
    stopLoop();
    setPlaying(false);
    virtualPositionRef.current = target;
    recording.seek(target, () => setPosition(target));
  }

  const handleFullscreen = useCallback(() => {
    stageWrapRef.current?.requestFullscreen?.();
  }, []);

  return (
    <div className={styles.overlay} role="presentation" onClick={onClose}>
      <div className={styles.dialog} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h3 className={styles.title}>{p.replayTitle}</h3>
          <div className={styles.headerActions}>
            <button type="button" className={styles.closeButton} onClick={handleFullscreen} disabled={status !== "ready"}>
              {p.rdpFullscreen}
            </button>
            <button type="button" className={styles.closeButton} onClick={onClose}>
              {p.close}
            </button>
          </div>
        </div>

        <div className={styles.stage} ref={stageWrapRef}>
          {/* GERÇEK bir React/DOM çakışması bulunup düzeltildi: bu
              kapsayıcı YALNIZCA `load()` içinde manuel `appendChild` ile
              doldurulur, React BURAYA HİÇBİR ZAMAN kendi child'ını
              render ETMEZ (bkz. `GuacamoleRdpViewer.tsx`'teki AYNI
              desen) — durum bindirmesi (statusOverlay) bunun yerine
              AYRI, kardeş bir React-yönetimli div. Önceden ikisi AYNI
              ref'li div içindeydi; `status` "loading"dan "ready"ye
              geçtiğinde React kendi statusOverlay child'ını kaldırmaya
              çalışıyor ama o düğüm zaten guacamole'ün canvas'ı
              eklenirken ORADA yer değiştirmiş/kaldırılmış oluyordu —
              "Failed to execute 'removeChild'..." hatasının kök nedeni
              buydu. */}
          <div className={styles.canvasInner} ref={stageRef} />
          {status !== "ready" && (
            <div className={styles.statusOverlay}>
              {status === "loading" && (
                <span>
                  {p.replayLoading}
                  {loadedMs > 0 ? ` (${formatTime(loadedMs)})` : ""}
                </span>
              )}
              {status === "error" && <span className={styles.errorText}>{errorMessage || p.replayLoadError}</span>}
            </div>
          )}
        </div>

        <div className={styles.controls}>
          <div className={styles.seekRow}>
            <span className={styles.timeLabel}>{formatTime(position)}</span>
            <div className={styles.seekBarWrap}>
              <input
                className={styles.seekBar}
                type="range"
                min={0}
                max={duration || 0}
                value={position}
                onChange={handleSeek}
                disabled={status !== "ready"}
              />
              {duration > 0 && (
                <div className={styles.markerTrack}>
                  {idleGaps.map((gap) => (
                    <div
                      key={gap.start_ms}
                      className={styles.idleGapBand}
                      style={{
                        left: `${(gap.start_ms / duration) * 100}%`,
                        width: `${((gap.end_ms - gap.start_ms) / duration) * 100}%`,
                      }}
                      title={`${p.idleGapTooltip} — ${formatTime(gap.start_ms)}–${formatTime(gap.end_ms)}`}
                    />
                  ))}
                  {markers.map((markerMs) => (
                    <button
                      key={markerMs}
                      type="button"
                      className={styles.markerTick}
                      style={{ left: `${(markerMs / duration) * 100}%` }}
                      title={`${p.activityMarkerTooltip} — ${formatTime(markerMs)}`}
                      onClick={() => seekToMarker(markerMs)}
                    />
                  ))}
                </div>
              )}
            </div>
            <span className={styles.timeLabel}>{formatTime(duration)}</span>
          </div>
          <div className={styles.buttonRow}>
            <button type="button" className={styles.playButton} onClick={togglePlay} disabled={status !== "ready"}>
              {playing ? p.pause : p.play}
            </button>
            <div className={styles.speedGroup}>
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`${styles.speedButton} ${speed === s ? styles.speedButtonActive : ""}`}
                  onClick={() => handleSpeedChange(s)}
                  disabled={status !== "ready"}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
