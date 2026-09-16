"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  deleteAgent,
  fetchAgents,
  triggerAgentUpdate,
  type AgentSummary,
} from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import { AgentRetentionPolicyPanel } from "./AgentRetentionPolicyPanel";
import { ArchivedAgentsList } from "./ArchivedAgentsList";
import styles from "./AgentsList.module.css";
import modalStyles from "./ConfirmModal.module.css";
import { useToasts, ToastStack } from "./Toast";

type FetchStatus = "loading" | "done" | "error";
type Tab = "active" | "archived";

function statusDotClass(status: AgentSummary["status"], styles: Record<string, string>): string {
  if (status === "online") return styles.dotOnline;
  if (status === "offline") return styles.dotOffline;
  return styles.dotUnknown;
}

type DeleteModalState = { agent: AgentSummary; sendUninstallCommand: boolean };

export function AgentsList() {
  const { t } = useLocale();
  const { assets } = useDashboardData();
  const a = t.agents;

  const [tab, setTab] = useState<Tab>("active");
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [search, setSearch] = useState("");
  const [deleteModal, setDeleteModal] = useState<DeleteModalState | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [bulkUpdating, setBulkUpdating] = useState(false);
  const { toasts, push, dismiss } = useToasts();

  function load() {
    fetchAgents()
      .then((data) => {
        setAgents(data);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }

  useEffect(() => {
    load();
  }, []);

  const assetById = useMemo(() => new Map(assets.map((asset) => [asset.id, asset])), [assets]);

  const filteredAgents = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return agents;
    return agents.filter((agent) => {
      const haystack = [agent.hostname, agent.os, agent.os_version, agent.agent_version]
        .filter((v): v is string => v != null)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [agents, search]);

  const updatableAgents = useMemo(() => agents.filter((agent) => agent.update_available), [agents]);

  async function handleConfirmDelete() {
    if (!deleteModal) return;
    setDeleting(true);
    try {
      const result = await deleteAgent(deleteModal.agent.id, deleteModal.sendUninstallCommand);
      push("success", result.uninstall_command_id ? a.deleteSuccessWithUninstall : a.deleteSuccess);
      setDeleteModal(null);
      load();
    } catch {
      push("error", a.deleteError);
    } finally {
      setDeleting(false);
    }
  }

  async function handleUpdate(agent: AgentSummary) {
    setUpdatingId(agent.id);
    try {
      await triggerAgentUpdate(agent.id);
      push("success", a.updateSuccess);
    } catch {
      push("error", a.updateError);
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleUpdateAll() {
    setBulkUpdating(true);
    let sent = 0;
    for (const agent of updatableAgents) {
      try {
        await triggerAgentUpdate(agent.id);
        sent += 1;
      } catch {
        // Bir agent'ın hatası diğerlerini durdurmaz — toplu güncelleme
        // sonunda yalnızca GERÇEKTEN gönderilen sayısı bildirilir.
      }
    }
    setBulkUpdating(false);
    if (sent > 0) {
      push("success", a.updateAllSuccess.replace("{count}", String(sent)));
    } else {
      push("error", a.updateError);
    }
  }

  return (
    <div className={styles.pageWrap}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.tabs}>
        <button
          className={`${styles.tabButton} ${tab === "active" ? styles.tabButtonActive : ""}`}
          onClick={() => setTab("active")}
        >
          {a.tabs.active}
        </button>
        <button
          className={`${styles.tabButton} ${tab === "archived" ? styles.tabButtonActive : ""}`}
          onClick={() => setTab("archived")}
        >
          {a.tabs.archived}
        </button>
      </div>

      {tab === "archived" && <ArchivedAgentsList />}

      {tab === "active" && (
        <>
          <AgentRetentionPolicyPanel />

          <section className={styles.card}>
            <div className={styles.header}>
              <div>
                <h2 className={styles.title}>{a.title}</h2>
                <p className={styles.subtitle}>{a.subtitle}</p>
              </div>
              <div className={styles.actionsCell}>
                {updatableAgents.length > 0 && (
                  <button className={styles.toolbarButton} onClick={handleUpdateAll} disabled={bulkUpdating}>
                    {bulkUpdating ? t.common.refreshing : a.updateAll}
                  </button>
                )}
                <button className={styles.refreshButton} onClick={load} disabled={status === "loading"}>
                  {status === "loading" ? t.common.refreshing : t.common.refresh}
                </button>
              </div>
            </div>

            {agents.length > 0 && (
              <input
                className={styles.searchInput}
                type="text"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t.assets.searchPlaceholder}
                aria-label={t.assets.searchAriaLabel}
              />
            )}

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
                <p className={styles.emptyHint}>{a.emptyHint}</p>
              </div>
            )}

            {status === "done" && agents.length > 0 && filteredAgents.length === 0 && (
              <div className={styles.emptyState}>
                <p className={styles.emptyText}>{t.assets.noMatchFilters}</p>
              </div>
            )}

            {status === "done" && filteredAgents.length > 0 && (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>{a.columns.status}</th>
                      <th>{a.columns.hostname}</th>
                      <th>{a.columns.os}</th>
                      <th>{a.columns.ip}</th>
                      <th>{a.columns.version}</th>
                      <th>{a.columns.lastHeartbeat}</th>
                      <th>{a.columns.asset}</th>
                      <th>{a.columns.actions}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAgents.map((agent) => {
                      const linkedAsset = agent.asset_id ? assetById.get(agent.asset_id) : undefined;
                      return (
                        <tr key={agent.id}>
                          <td>
                            <span className={styles.statusCell}>
                              <span className={`${styles.dot} ${statusDotClass(agent.status, styles)}`} />
                              {a.statusLabels[agent.status]}
                            </span>
                          </td>
                          <td>{agent.hostname}</td>
                          <td>
                            {agent.os}
                            {agent.os_version ? ` (${agent.os_version})` : ""}
                          </td>
                          <td className={styles.mono}>{agent.local_ip ?? "-"}</td>
                          <td>
                            {agent.agent_version}
                            {agent.update_available && (
                              <span className={styles.updateBadge} title={agent.latest_available_version ?? undefined}>
                                {a.updateAvailable}
                              </span>
                            )}
                          </td>
                          <td>
                            {agent.last_heartbeat_at
                              ? timeAgo(agent.last_heartbeat_at, t.timeAgo)
                              : t.common.noDataAvailable}
                          </td>
                          <td>{linkedAsset ? linkedAsset.hostname ?? linkedAsset.ip_address : a.noAssetLinked}</td>
                          <td>
                            <div className={styles.actionsCell}>
                              <Link className={styles.linkButton} href={`/agents/${agent.id}`}>
                                {a.view}
                              </Link>
                              {agent.update_available && (
                                <button
                                  className={styles.actionButton}
                                  onClick={() => handleUpdate(agent)}
                                  disabled={updatingId === agent.id}
                                >
                                  {a.update}
                                </button>
                              )}
                              <button
                                className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                                onClick={() => setDeleteModal({ agent, sendUninstallCommand: false })}
                              >
                                {a.delete}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {deleteModal && (
        <div className={modalStyles.overlay} role="presentation" onClick={() => !deleting && setDeleteModal(null)}>
          <div
            className={modalStyles.dialog}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-agent-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="delete-agent-modal-title" className={modalStyles.title}>
              {a.deleteModal.title}
            </h3>
            <p className={modalStyles.message}>
              {a.deleteModal.message.replace("{hostname}", deleteModal.agent.hostname)}
            </p>
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={deleteModal.sendUninstallCommand}
                onChange={(e) => setDeleteModal({ ...deleteModal, sendUninstallCommand: e.target.checked })}
              />
              {a.deleteModal.sendUninstallLabel}
            </label>
            <div className={modalStyles.actions} style={{ marginTop: 16 }}>
              <button
                className={modalStyles.cancelButton}
                onClick={() => setDeleteModal(null)}
                disabled={deleting}
              >
                {a.deleteModal.cancel}
              </button>
              <button className={modalStyles.confirmButton} onClick={handleConfirmDelete} disabled={deleting}>
                {deleting ? a.deleteModal.busy : a.deleteModal.confirm}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
