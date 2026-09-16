"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchTicketMetrics, type TicketMetrics } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";

function DistBar({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div style={{ minWidth: 0 }}>
      <h4 className={styles.title} style={{ fontSize: "0.9rem", margin: "4px 0" }}>
        {title}
      </h4>
      <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 4, margin: 0 }}>
        {entries.map(([k, v]) => (
          <li key={k} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className={styles.status} style={{ minWidth: 120, fontSize: "0.75rem" }}>
              {k}
            </span>
            <span
              style={{
                height: 10,
                width: `${(v / max) * 100}%`,
                minWidth: 2,
                background: "var(--accent)",
                borderRadius: 3,
              }}
            />
            <span className={styles.status} style={{ fontSize: "0.75rem" }}>
              {v}
            </span>
          </li>
        ))}
        {entries.length === 0 && <li className={styles.status}>—</li>}
      </ul>
    </div>
  );
}

export function TicketMetricsPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const k = t.tickets;
  const m = k.metrics;

  const [data, setData] = useState<TicketMetrics | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!token) return;
    Promise.resolve().then(async () => {
      try {
        setData(await fetchTicketMetrics(token));
        setError(false);
      } catch {
        setError(true);
      }
    });
  }, [token]);

  if (error) return <p className={styles.error}>{m.loadError}</p>;
  if (data === null) return <p className={styles.status}>{t.common.loading}</p>;

  const cards = [
    { label: m.total, value: data.total },
    { label: m.open, value: data.open_tickets },
    { label: m.overdue, value: data.overdue_open },
    {
      label: m.avgResolution,
      value: data.avg_resolution_hours == null ? "—" : `${data.avg_resolution_hours} ${m.hours}`,
    },
    {
      label: m.slaCompliance,
      value: data.sla_compliance_pct == null ? "—" : `%${data.sla_compliance_pct}`,
    },
  ];

  return (
    <section className={styles.card} style={{ marginBottom: 12 }}>
      <h3 className={styles.title} style={{ fontSize: "1rem" }}>
        {m.title}
      </h3>

      <div className={styles.kpiGrid} style={{ marginTop: 8 }}>
        {cards.map((c) => (
          <div key={c.label} className={styles.kpiCard}>
            <span className={styles.kpiValue}>{c.value}</span>
            <span className={styles.kpiLabel}>{c.label}</span>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, marginTop: 14 }}>
        <DistBar title={m.byStatus} data={data.by_status} />
        <DistBar title={m.byPriority} data={data.by_priority} />
        <DistBar title={m.byCategory} data={data.by_category} />
        <DistBar title={m.byDepartment} data={data.by_department} />
      </div>

      <h4 className={styles.title} style={{ fontSize: "0.9rem", marginTop: 16 }}>
        {m.last30Days}
      </h4>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <LineChart data={data.daily} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-strong)" />
            <XAxis dataKey="day" tick={{ fontSize: 10 }} interval={4} />
            <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="created" name={m.created} stroke="var(--accent)" dot={false} />
            <Line type="monotone" dataKey="resolved" name={m.resolved} stroke="var(--status-ok, #3fb950)" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
