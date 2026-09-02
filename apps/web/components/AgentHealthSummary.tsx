"use client";

import { useEffect, useState } from "react";

import { fetchAgents, type AgentSummary } from "@/lib/api";
import { computeAgentHealth } from "@/lib/agentHealth";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentHealthSummary.module.css";

type FetchStatus = "loading" | "done" | "error";

export function AgentHealthSummary() {
  const { t } = useLocale();
  const c = t.dashboard.agentHealth;

  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [status, setStatus] = useState<FetchStatus>("loading");

  useEffect(() => {
    fetchAgents()
      .then((data) => {
        setAgents(data);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }, []);

  const health = computeAgentHealth(agents);

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{c.title}</h2>
        <p className={styles.subtitle}>{c.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.status}>{t.common.unableToLoad}</p>}

      {status === "done" && health.total === 0 && <p className={styles.status}>{c.noAgents}</p>}

      {status === "done" && health.total > 0 && (
        <dl className={styles.rows}>
          <div className={styles.row}>
            <dt>
              <span className={`${styles.dot} ${styles.dotOnline}`} />
              {c.online}
            </dt>
            <dd>{health.online}</dd>
          </div>
          <div className={styles.row}>
            <dt>
              <span className={`${styles.dot} ${styles.dotOffline}`} />
              {c.offline}
            </dt>
            <dd>{health.offline}</dd>
          </div>
          <div className={styles.row}>
            <dt>
              <span className={`${styles.dot} ${styles.dotUnknown}`} />
              {c.unknown}
            </dt>
            <dd>{health.unknown}</dd>
          </div>
          <div className={styles.row}>
            <dt>{c.linkedToAsset}</dt>
            <dd>
              {health.linkedToAsset} / {health.total}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
