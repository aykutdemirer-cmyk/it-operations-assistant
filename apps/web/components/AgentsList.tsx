"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { fetchAgents, type AgentSummary } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import styles from "./AgentsList.module.css";

type FetchStatus = "loading" | "done" | "error";

function statusDotClass(status: AgentSummary["status"], styles: Record<string, string>): string {
  if (status === "online") return styles.dotOnline;
  if (status === "offline") return styles.dotOffline;
  return styles.dotUnknown;
}

export function AgentsList() {
  const { t } = useLocale();
  const { assets } = useDashboardData();
  const a = t.agents;

  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [search, setSearch] = useState("");

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

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{a.title}</h2>
          <p className={styles.subtitle}>{a.subtitle}</p>
        </div>
        <button className={styles.refreshButton} onClick={load} disabled={status === "loading"}>
          {status === "loading" ? t.common.refreshing : t.common.refresh}
        </button>
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
                    <td>{agent.agent_version}</td>
                    <td>
                      {agent.last_heartbeat_at
                        ? timeAgo(agent.last_heartbeat_at, t.timeAgo)
                        : t.common.noDataAvailable}
                    </td>
                    <td>{linkedAsset ? linkedAsset.hostname ?? linkedAsset.ip_address : a.noAssetLinked}</td>
                    <td>
                      <Link className={styles.linkButton} href={`/agents/${agent.id}`}>
                        {a.view}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
