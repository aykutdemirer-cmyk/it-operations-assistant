"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { agentRdpConnectUrl, fetchAgents, type AgentSummary } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import detailStyles from "./AssetDetails.module.css";
import styles from "./AssetAgentPanel.module.css";

type FetchStatus = "loading" | "done" | "error";

type Props = {
  assetId: string;
};

/**
 * Bu asset'e bağlı (bkz. `agents.asset_id`, `app/agents/matching.py`)
 * bir Agent var mı gösterir — Faz 30 §18. Backend'de "asset_id'ye göre
 * agent" için ayrı bir endpoint YOK, `GET /api/agents` listesi
 * `asset_id`'ye göre CLIENT tarafında filtrelenir (agent sayısı NOC
 * ölçeğinde küçük, ayrı bir endpoint bu aşamada gerekli değil).
 */
export function AssetAgentPanel({ assetId }: Props) {
  const { t } = useLocale();
  const d = t.assetDetails.agent;

  const [status, setStatus] = useState<FetchStatus>("loading");
  const [agent, setAgent] = useState<AgentSummary | null>(null);

  useEffect(() => {
    fetchAgents()
      .then((agents) => {
        setAgent(agents.find((a) => a.asset_id === assetId) ?? null);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }, [assetId]);

  if (status === "loading") {
    return <p className={detailStyles.noData}>{t.common.loading}</p>;
  }
  if (status === "error") {
    return <p className={detailStyles.noData}>{t.agents.loadError}</p>;
  }
  if (!agent) {
    return <p className={detailStyles.noData}>{d.notConnected}</p>;
  }

  return (
    <div className={styles.wrap}>
      <dl className={detailStyles.fields}>
        <div className={detailStyles.field}>
          <dt>{d.status}</dt>
          <dd>{t.agents.statusLabels[agent.status]}</dd>
        </div>
        <div className={detailStyles.field}>
          <dt>{d.version}</dt>
          <dd>{agent.agent_version}</dd>
        </div>
        <div className={detailStyles.field}>
          <dt>{d.os}</dt>
          <dd>
            {agent.os}
            {agent.os_version ? ` (${agent.os_version})` : ""}
          </dd>
        </div>
        <div className={detailStyles.field}>
          <dt>{d.lastHeartbeat}</dt>
          <dd>
            {agent.last_heartbeat_at ? timeAgo(agent.last_heartbeat_at, t.timeAgo) : t.common.noDataAvailable}
          </dd>
        </div>
      </dl>
      {/* Faz 38 — Topoloji Quick Inspect panelinden RDP/SSH hızlı
          bağlantı. Yalnızca bu asset'e bağlı GERÇEK bir Agent varsa
          gösterilir — backend `local_ip`'yi agent kaydından çözer,
          bağlı bir agent olmadan bu bağlantı KURULAMAZ. */}
      {agent.local_ip && (
        <div className={styles.quickConnect}>
          <a
            className={styles.quickConnectButton}
            href={agentRdpConnectUrl(agent.id)}
            download
            title={agent.local_ip}
          >
            {d.rdpConnect}
          </a>
          <button
            type="button"
            className={styles.quickConnectButton}
            onClick={() => window.open(`/remote-control/ssh/${agent.id}`, "_blank", "noopener,noreferrer")}
          >
            {d.sshConnect}
          </button>
        </div>
      )}

      <Link className={styles.viewLink} href={`/agents/${agent.id}`}>
        {d.viewDetails} →
      </Link>
    </div>
  );
}
