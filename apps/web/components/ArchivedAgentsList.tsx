"use client";

import { useEffect, useState } from "react";

import { fetchArchivedAgents, restoreAgent, type ArchivedAgentSummary } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { formatDuration } from "@/lib/time";
import styles from "./AgentsList.module.css";
import { useToasts, ToastStack } from "./Toast";

type FetchStatus = "loading" | "done" | "error";

/** Lifecycle Management — Silinen/Arşivlenen Agent'lar sekmesi.
 * Manuel silinen VEYA inaktiflik nedeniyle otomatik temizlenen
 * agent'ların geçmişini gösterir, Geri Yükle imkanı sunar (bkz.
 * `app/db/agents.py::archive_agent`/`restore_agent` — soft-delete,
 * kalıcı SİLME değil). */
export function ArchivedAgentsList() {
  const { t } = useLocale();
  const a = t.agents.archived;

  const [agents, setAgents] = useState<ArchivedAgentSummary[]>([]);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const { toasts, push, dismiss } = useToasts();

  function load() {
    fetchArchivedAgents()
      .then((data) => {
        setAgents(data);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }

  useEffect(() => {
    load();
  }, []);

  async function handleRestore(agent: ArchivedAgentSummary) {
    setRestoringId(agent.id);
    try {
      await restoreAgent(agent.id);
      push("success", a.restoreSuccess);
      load();
    } catch {
      push("error", a.restoreError);
    } finally {
      setRestoringId(null);
    }
  }

  function reasonText(agent: ArchivedAgentSummary): string {
    if (agent.archived_reason === "inactivity") {
      return a.reasonInactivity.replace("{days}", String(agent.archived_after_inactive_days ?? "?"));
    }
    return a.reasonManual;
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{a.title}</h2>
          <p className={styles.subtitle}>{a.subtitle}</p>
        </div>
        <button className={styles.refreshButton} onClick={load} disabled={status === "loading"}>
          {status === "loading" ? t.common.refreshing : t.common.refresh}
        </button>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.error} role="alert">
          {a.loadError}
        </p>
      )}

      {status === "done" && agents.length === 0 && (
        <div className={styles.emptyState}>
          <p className={styles.emptyTitle}>{a.emptyTitle}</p>
          <p className={styles.emptyText}>{a.emptyText}</p>
        </div>
      )}

      {status === "done" && agents.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{a.columns.hostname}</th>
                <th>{a.columns.os}</th>
                <th>{a.columns.ip}</th>
                <th>{a.columns.reason}</th>
                <th>{a.columns.activeDuration}</th>
                <th>{a.columns.archivedAt}</th>
                <th>{a.columns.actions}</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id}>
                  <td>{agent.hostname}</td>
                  <td>
                    {agent.os}
                    {agent.os_version ? ` (${agent.os_version})` : ""}
                  </td>
                  <td className={styles.mono}>{agent.local_ip ?? "-"}</td>
                  <td className={styles.reasonText}>{reasonText(agent)}</td>
                  <td>
                    {agent.active_duration_seconds != null
                      ? formatDuration(agent.active_duration_seconds, t.common.durationUnits)
                      : a.unknownDuration}
                  </td>
                  <td>{new Date(agent.archived_at).toLocaleString()}</td>
                  <td>
                    <button
                      className={styles.actionButton}
                      onClick={() => handleRestore(agent)}
                      disabled={restoringId === agent.id}
                    >
                      {a.restore}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
