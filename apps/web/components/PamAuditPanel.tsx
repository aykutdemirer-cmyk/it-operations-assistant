"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, fetchPamAudit, terminatePamSession, type PamSessionLog } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ConfirmModal } from "./ConfirmModal";
import { LiveSessionShadowModal } from "./LiveSessionShadowModal";
import { SessionKeystrokesModal } from "./SessionKeystrokesModal";
import { SessionReplayModal } from "./SessionReplayModal";
import { ToastStack, useToasts } from "./Toast";

type DateFilter = "all" | "24h" | "7d";
type ProtocolFilter = "all" | "rdp" | "ssh";
type ReasonFilter = "all" | "user_closed" | "terminated_by_admin" | "timeout";

function formatElapsed(startedAt: string, nowMs: number): string {
  const elapsedMs = nowMs - new Date(startedAt).getTime();
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : `${minutes}:${String(seconds).padStart(2, "0")}`;
}

// Faz 54 KPI kartı: "Toplam İzleme Süresi" — yalnızca BİTMİŞ oturumların
// gerçek `ended_at - started_at` farkı toplanır, uydurma/ortalama bir
// tahmin YOK; hâlâ açık oturumlar bu toplama hiç girmez.
function formatTotalDuration(totalMs: number): string {
  const totalMinutes = Math.floor(totalMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}s ${minutes}dk` : `${minutes}dk`;
}

function isToday(iso: string, now: Date): boolean {
  const d = new Date(iso);
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

export function PamAuditPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [tab, setTab] = useState<"live" | "history">("live");
  const [logs, setLogs] = useState<PamSessionLog[] | null>(null);
  const [statsLogs, setStatsLogs] = useState<PamSessionLog[] | null>(null);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(0);
  const [pendingKill, setPendingKill] = useState<PamSessionLog | null>(null);
  const [killing, setKilling] = useState(false);
  const [replaySessionId, setReplaySessionId] = useState<string | null>(null);
  const [keystrokesSessionId, setKeystrokesSessionId] = useState<string | null>(null);
  const [shadowSession, setShadowSession] = useState<PamSessionLog | null>(null);
  const { toasts, push, dismiss } = useToasts();

  // Faz 54 — arama/filtre barı. `searchInput` kullanıcının anlık
  // yazdığı, `search` 300ms sonra debounce edilmiş (backend'e her tuş
  // vuruşunda istek atılmasın diye) hâli.
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [protocolFilter, setProtocolFilter] = useState<ProtocolFilter>("all");
  const [reasonFilter, setReasonFilter] = useState<ReasonFilter>("all");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const load = useCallback(() => {
    if (!token) return;
    fetchPamAudit(token, tab === "live", {
      search: search || undefined,
      protocol: protocolFilter === "all" ? undefined : protocolFilter,
      reason: tab === "history" && reasonFilter !== "all" ? reasonFilter : undefined,
    })
      .then((data) => {
        setLogs(data);
        setError(false);
      })
      .catch(() => setError(true));
  }, [token, tab, search, protocolFilter, reasonFilter]);

  useEffect(() => {
    load();
  }, [load]);

  // Faz 54 — KPI kartları HER ZAMAN filtrelerden/sekmeden bağımsız,
  // TÜM oturum geçmişini (`active=false` → hem bitmiş hem devam eden
  // TÜM satırlar) yansıtır — bir arama/protokol filtresi uygulanınca
  // KPI sayıları yanlışlıkla küçülmesin diye ayrı bir veri kaynağı.
  const loadStats = useCallback(() => {
    if (!token) return;
    fetchPamAudit(token, false)
      .then((data) => setStatsLogs(data))
      .catch(() => {});
  }, [token]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // `now` yalnızca "Geçen Süre" sayacı için DEĞİL, aşağıdaki tarih
  // filtresi (`dateFilteredLogs`) için de kullanılıyor — `Date.now()`'u
  // doğrudan render/`useMemo` içinde çağırmak saflık kuralını ihlal
  // eder (`react-hooks/purity`), bu yüzden HER ZAMAN mount'ta bir kere
  // (sekmeden bağımsız) set ediliyor.
  useEffect(() => {
    // setState çağrısı bir microtask'a ertelendi — bkz. `lib/i18n/
    // LocaleProvider.tsx`'teki aynı desen (react-hooks/set-state-in-effect).
    Promise.resolve().then(() => setNow(Date.now()));
  }, []);

  // Canlı Oturumlar sekmesindeki "Geçen Süre" sayacı — sunucudan tekrar
  // veri çekmeden yalnızca ekranı 1sn'de bir yeniden hesaplar.
  useEffect(() => {
    if (tab !== "live") return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [tab]);

  // Canlı Oturumlar sekmesi 10sn'de, Oturum Geçmişi sekmesi 15sn'de bir
  // sunucudan gerçek listeyi tazeler — bir oturum bittiğinde (kullanıcı
  // kapattı/admin sonlandırdı/süresi doldu) elle yenilemeye gerek
  // kalmadan Geçmiş sekmesinde görünsün diye.
  useEffect(() => {
    const interval = setInterval(() => {
      load();
      loadStats();
    }, tab === "live" ? 10000 : 15000);
    return () => clearInterval(interval);
  }, [tab, load, loadStats]);

  async function handleConfirmKill() {
    if (!token || !pendingKill) return;
    setKilling(true);
    try {
      await terminatePamSession(token, pendingKill.id);
      push("success", `${pendingKill.username} — ${p.killSession}`);
      setPendingKill(null);
      load();
      loadStats();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.killSessionError);
    } finally {
      setKilling(false);
    }
  }

  function endReasonLabel(reason: string | null): string {
    if (!reason) return "—";
    if (reason === "terminated_by_admin") return p.endReasonTerminatedByAdmin;
    if (reason === "user_closed") return p.endReasonUserClosed;
    if (reason === "timeout") return p.endReasonTimeout;
    if (reason === "error") return p.endReasonError;
    return reason;
  }

  function endReasonBadgeClass(reason: string | null): string {
    if (reason === "terminated_by_admin" || reason === "error") return styles.badgeRed;
    if (reason === "user_closed") return styles.badgeGreen;
    return styles.badgeNeutral;
  }

  // Faz 54 — tarih hızlı filtresi (Son 24 Saat/Son 7 Gün) backend'in
  // desteklediği parametreler arasında DEĞİL (kullanıcının kendi
  // isteği yalnızca search/protocol/reason/limit/offset istedi) —
  // istemci tarafında, zaten çekilmiş listeye uygulanıyor.
  const dateFilteredLogs = useMemo(() => {
    if (!logs) return logs;
    if (dateFilter === "all") return logs;
    const cutoffMs = dateFilter === "24h" ? 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
    const cutoff = now - cutoffMs;
    return logs.filter((log) => new Date(log.started_at).getTime() >= cutoff);
  }, [logs, dateFilter, now]);

  const kpis = useMemo(() => {
    if (!statsLogs) return null;
    const todayCount = statsLogs.filter((l) => isToday(l.started_at, new Date(now))).length;
    const adminTerminatedCount = statsLogs.filter((l) => l.end_reason === "terminated_by_admin").length;
    const totalWatchMs = statsLogs.reduce((sum, l) => {
      if (!l.ended_at) return sum;
      return sum + Math.max(0, new Date(l.ended_at).getTime() - new Date(l.started_at).getTime());
    }, 0);
    return {
      total: statsLogs.length,
      today: todayCount,
      adminTerminated: adminTerminatedCount,
      totalWatchTime: formatTotalDuration(totalWatchMs),
    };
  }, [statsLogs, now]);

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.auditTitle}</h2>
          <p className={styles.subtitle}>{p.auditSubtitle}</p>
        </div>
        <div className={styles.tabs}>
          <button
            type="button"
            className={`${styles.tabButton} ${tab === "live" ? styles.tabButtonActive : ""}`}
            onClick={() => setTab("live")}
          >
            {p.liveSessions}
          </button>
          <button
            type="button"
            className={`${styles.tabButton} ${tab === "history" ? styles.tabButtonActive : ""}`}
            onClick={() => setTab("history")}
          >
            {p.sessionHistory}
          </button>
        </div>
      </div>

      {/* Faz 54 — 4 KPI kartı, her zaman TÜM oturum geçmişinden (bkz.
          `statsLogs`) — hiçbir sayı uydurulmadı/tahmin edilmedi. */}
      <div className={styles.kpiGrid}>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTop}>
            <span className={styles.kpiIcon} aria-hidden="true">📋</span>
            <span className={styles.kpiLabel}>{p.auditKpiTotalSessions}</span>
          </div>
          <span className={styles.kpiValue}>{kpis ? kpis.total : "–"}</span>
        </div>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTop}>
            <span className={styles.kpiIcon} aria-hidden="true">📅</span>
            <span className={styles.kpiLabel}>{p.auditKpiTodaySessions}</span>
          </div>
          <span className={styles.kpiValue}>{kpis ? kpis.today : "–"}</span>
        </div>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTop}>
            <span className={styles.kpiIcon} aria-hidden="true">🛑</span>
            <span className={styles.kpiLabel}>{p.auditKpiAdminTerminated}</span>
          </div>
          <span className={styles.kpiValue}>{kpis ? kpis.adminTerminated : "–"}</span>
        </div>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTop}>
            <span className={styles.kpiIcon} aria-hidden="true">⏱️</span>
            <span className={styles.kpiLabel}>{p.auditKpiTotalWatchTime}</span>
          </div>
          <span className={styles.kpiValue}>{kpis ? kpis.totalWatchTime : "–"}</span>
        </div>
      </div>

      {/* Faz 54 — arama/filtre barı. `search`/`protocolFilter` backend'e
          gerçek query parametreleri olarak gidiyor (bkz. `load()`);
          `dateFilter` yalnızca istemci tarafında uygulanıyor. */}
      <div className={styles.filterBar}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder={p.auditSearchPlaceholder}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <select
          className={styles.filterSelect}
          value={protocolFilter}
          onChange={(e) => setProtocolFilter(e.target.value as ProtocolFilter)}
          aria-label={p.columnProtocol}
        >
          <option value="all">{t.common.all}</option>
          <option value="rdp">RDP</option>
          <option value="ssh">SSH</option>
        </select>
        {tab === "history" && (
          <select
            className={styles.filterSelect}
            value={reasonFilter}
            onChange={(e) => setReasonFilter(e.target.value as ReasonFilter)}
            aria-label={p.columnEndReason}
          >
            <option value="all">{t.common.all}</option>
            <option value="user_closed">{p.endReasonUserClosed}</option>
            <option value="terminated_by_admin">{p.endReasonTerminatedByAdmin}</option>
            <option value="timeout">{p.endReasonTimeout}</option>
          </select>
        )}
        <select
          className={styles.filterSelect}
          value={dateFilter}
          onChange={(e) => setDateFilter(e.target.value as DateFilter)}
          aria-label={p.filterDateLabel}
        >
          <option value="all">{p.filterDateAllTime}</option>
          <option value="24h">{p.filterDateLast24h}</option>
          <option value="7d">{p.filterDateLast7d}</option>
        </select>
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {t.common.unableToLoad}
        </p>
      )}
      {!error && dateFilteredLogs === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && dateFilteredLogs !== null && dateFilteredLogs.length === 0 && (
        <p className={styles.status}>{t.common.noDataAvailable}</p>
      )}

      {!error && dateFilteredLogs !== null && dateFilteredLogs.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnUser}</th>
                <th>{p.columnAsset}</th>
                <th>{p.columnProtocol}</th>
                <th>{p.columnStarted}</th>
                {tab === "live" ? <th>{p.columnDuration}</th> : <th>{p.columnEnded}</th>}
                {tab === "history" && <th>{p.columnEndReason}</th>}
                <th>{p.columnClientIp}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {dateFilteredLogs.map((log) => (
                <tr key={log.id}>
                  <td>{log.username}</td>
                  <td>{log.asset_hostname || log.asset_ip_address}</td>
                  <td>
                    <span className={`${styles.badge} ${log.protocol === "rdp" ? styles.badgeBlue : styles.badgeGreen}`}>
                      {log.protocol.toUpperCase()}
                    </span>
                  </td>
                  <td>{new Date(log.started_at).toLocaleString()}</td>
                  {tab === "live" ? (
                    <td className={styles.mono}>
                      <span style={{ color: "var(--status-up)" }}>●</span> {formatElapsed(log.started_at, now)}
                    </td>
                  ) : (
                    <td>{log.ended_at ? new Date(log.ended_at).toLocaleString() : p.ongoing}</td>
                  )}
                  {tab === "history" && (
                    <td>
                      {log.end_reason ? (
                        <span className={`${styles.badge} ${endReasonBadgeClass(log.end_reason)}`}>
                          {endReasonLabel(log.end_reason)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  )}
                  <td className={styles.mono}>{log.client_ip || "—"}</td>
                  <td className={styles.actionsCell}>
                    {tab === "live" && log.protocol === "rdp" && (
                      <button type="button" className={styles.actionButton} onClick={() => setShadowSession(log)}>
                        {p.shadowSession}
                      </button>
                    )}
                    {tab === "live" && (
                      <button
                        type="button"
                        className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                        onClick={() => setPendingKill(log)}
                      >
                        {p.killSession}
                      </button>
                    )}
                    {tab === "history" && log.protocol === "rdp" && log.recording_file_path && (
                      <button type="button" className={styles.actionButton} onClick={() => setReplaySessionId(log.id)}>
                        {p.watchRecording}
                      </button>
                    )}
                    {tab === "history" && log.protocol === "ssh" && (
                      <button type="button" className={styles.actionButton} onClick={() => setKeystrokesSessionId(log.id)}>
                        {p.viewKeystrokes}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pendingKill && (
        <ConfirmModal
          title={p.confirmKillSessionTitle}
          message={p.confirmKillSessionMessage}
          confirmLabel={p.killSession}
          cancelLabel={p.cancel}
          busy={killing}
          busyLabel={t.common.loading}
          onConfirm={handleConfirmKill}
          onCancel={() => setPendingKill(null)}
        />
      )}

      {replaySessionId && <SessionReplayModal sessionId={replaySessionId} onClose={() => setReplaySessionId(null)} />}
      {keystrokesSessionId && (
        <SessionKeystrokesModal sessionId={keystrokesSessionId} onClose={() => setKeystrokesSessionId(null)} />
      )}
      {shadowSession && (
        <LiveSessionShadowModal
          sessionId={shadowSession.id}
          deviceLabel={shadowSession.asset_hostname || shadowSession.asset_ip_address || shadowSession.username}
          onClose={() => setShadowSession(null)}
        />
      )}
    </section>
  );
}
