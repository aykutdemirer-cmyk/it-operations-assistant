"use client";

import { useEffect, useMemo, useState } from "react";

import {
  downloadTicketsCsv,
  fetchTicketCategories,
  fetchTicketDepartments,
  fetchTickets,
  type Ticket,
  type TicketListResponse,
  type TicketPriority,
  type TicketQuery,
  type TicketStatus,
  type TicketTaxonomyItem,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { CreateTicketModal } from "./CreateTicketModal";
import { TicketDetailModal } from "./TicketDetailModal";
import { TicketMetricsPanel } from "./TicketMetricsPanel";
import { TicketSettingsModal } from "./TicketSettingsModal";
import { priorityBadgeClass, statusBadgeClass } from "./ticketBadges";

const STATUSES: TicketStatus[] = ["OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"];
const PRIORITIES: TicketPriority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

/** Faz 62 — IT Helpdesk ana ekranı. Faz 63 — kategori/departman
 * dinamik (dropdown'lar backend'den); tablodan "Cihaz" sütunu
 * kaldırıldı, "Departman" + "Kategori" eklendi; Admin'e "Bilet
 * Ayarları" (taksonomi yönetimi) butonu. */
export function TicketsPanel() {
  const { token, currentUser } = useAuth();
  const { t } = useLocale();
  const k = t.tickets;
  const isAdmin = currentUser?.role === "ADMIN";
  // Faz 65 — REQUESTER yalnızca kendi biletlerini görür (backend'de de
  // zorlanır); alt başlıkta bunu belli et.
  const isRequester = (currentUser?.ticket_role ?? "REQUESTER") === "REQUESTER";

  const [data, setData] = useState<TicketListResponse | null>(null);
  const [error, setError] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showReports, setShowReports] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);

  const [categories, setCategories] = useState<TicketTaxonomyItem[]>([]);
  const [departments, setDepartments] = useState<TicketTaxonomyItem[]>([]);

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [status, setStatus] = useState<TicketStatus | "">("");
  const [priority, setPriority] = useState<TicketPriority | "">("");
  const [overdue, setOverdue] = useState(false);
  const [mine, setMine] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  async function loadTaxonomy() {
    if (!token) return;
    try {
      const [cats, deps] = await Promise.all([fetchTicketCategories(token), fetchTicketDepartments(token)]);
      setCategories(cats);
      setDepartments(deps);
    } catch {
      /* taksonomi olmadan da liste çalışır */
    }
  }

  function currentQuery(): TicketQuery {
    return {
      search: search || undefined,
      category_id: categoryId || undefined,
      department_id: departmentId || undefined,
      status: status || undefined,
      priority: priority || undefined,
      overdue: overdue || undefined,
      mine: mine || undefined,
    };
  }

  async function load() {
    if (!token) return;
    try {
      setData(await fetchTickets(token, currentQuery()));
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    Promise.resolve().then(() => {
      loadTaxonomy();
      load();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, search, categoryId, departmentId, status, priority, overdue, mine]);

  async function handleExportCsv() {
    if (!token) return;
    setExporting(true);
    try {
      await downloadTicketsCsv(token, currentQuery());
    } catch {
      /* indirme hatası sessiz — kullanıcı tekrar dener */
    } finally {
      setExporting(false);
    }
  }

  const tickets = data?.tickets ?? null;
  const stats = data?.stats;

  const kpis = useMemo(
    () => [
      { icon: "📨", label: k.kpiOpen, value: stats?.open_tickets },
      { icon: "🙋", label: k.kpiAssignedToMe, value: stats?.assigned_to_me },
      { icon: "🔥", label: k.kpiCriticalOverdue, value: stats?.critical_or_overdue },
      { icon: "✅", label: k.kpiResolvedThisMonth, value: stats?.resolved_this_month },
    ],
    [stats, k],
  );

  const hasFilter = Boolean(search || categoryId || departmentId || status || priority || overdue || mine);

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{k.title}</h2>
          <p className={styles.subtitle}>{isRequester ? k.requesterPortalHint : k.subtitle}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            className={`${styles.actionButton} ${showReports ? styles.toolbarButton : ""}`}
            aria-pressed={showReports}
            onClick={() => setShowReports((v) => !v)}
          >
            {k.reportsToggle}
          </button>
          {isAdmin && (
            <button type="button" className={styles.actionButton} onClick={() => setShowSettings(true)}>
              {k.settingsButton}
            </button>
          )}
          <button type="button" className={styles.toolbarButton} onClick={() => setShowCreate(true)}>
            {k.new}
          </button>
        </div>
      </div>

      {showReports && <TicketMetricsPanel />}

      <div className={styles.kpiGrid}>
        {kpis.map((kpi) => (
          <div key={kpi.label} className={styles.kpiCard}>
            <div className={styles.kpiTop}>
              <span className={styles.kpiIcon} aria-hidden="true">
                {kpi.icon}
              </span>
              <span className={styles.kpiLabel}>{kpi.label}</span>
            </div>
            <span className={styles.kpiValue}>{kpi.value ?? "–"}</span>
          </div>
        ))}
      </div>

      <div className={styles.filterBar}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder={k.searchPlaceholder}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <select className={styles.filterSelect} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">{k.filterCategory}: {k.all}</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select className={styles.filterSelect} value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
          <option value="">{k.filterDepartment}: {k.all}</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <select className={styles.filterSelect} value={status} onChange={(e) => setStatus(e.target.value as TicketStatus | "")}>
          <option value="">{k.filterStatus}: {k.all}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {k[`status${s}`]}
            </option>
          ))}
        </select>
        <select className={styles.filterSelect} value={priority} onChange={(e) => setPriority(e.target.value as TicketPriority | "")}>
          <option value="">{k.filterPriority}: {k.all}</option>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {k[`priority${p}`]}
            </option>
          ))}
        </select>
        <label className={styles.status} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />
          {k.filterOverdue}
        </label>
        {!isRequester && (
          <label className={styles.status} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
            {k.filterMine}
          </label>
        )}
        <button type="button" className={styles.actionButton} onClick={handleExportCsv} disabled={exporting}>
          {k.exportCsv}
        </button>
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {k.loadError}
        </p>
      )}
      {!error && tickets === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && tickets !== null && tickets.length === 0 && (
        <p className={styles.status}>{hasFilter ? k.noMatch : k.empty}</p>
      )}

      {!error && tickets !== null && tickets.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{k.colNumber}</th>
                <th>{k.colTitle}</th>
                <th>{k.colDepartment}</th>
                <th>{k.colCategory}</th>
                <th>{k.colPriority}</th>
                <th>{k.colStatus}</th>
                <th>{k.colCreatedBy}</th>
                <th>{k.colDate}</th>
                <th>{k.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((ticket) => (
                <tr key={ticket.id}>
                  <td>{ticket.ticket_number}</td>
                  <td>{ticket.title}</td>
                  <td>{ticket.department_name ?? "—"}</td>
                  <td>{ticket.category_name ?? "—"}</td>
                  <td>
                    <span className={`${styles.badge} ${priorityBadgeClass(ticket.priority, styles)}`}>
                      {k[`priority${ticket.priority}`]}
                    </span>
                  </td>
                  <td>
                    <span className={`${styles.badge} ${statusBadgeClass(ticket.status, styles)}`}>
                      {k[`status${ticket.status}`]}
                    </span>
                    {ticket.sla_due_at &&
                      ticket.status !== "RESOLVED" &&
                      ticket.status !== "CLOSED" &&
                      new Date(ticket.sla_due_at) < new Date() && (
                        <span className={`${styles.badge} ${styles.badgeRed}`} style={{ marginLeft: 4 }}>
                          {k.overdue}
                        </span>
                      )}
                  </td>
                  <td>{ticket.created_by_username}</td>
                  <td>{new Date(ticket.created_at).toLocaleDateString()}</td>
                  <td className={styles.actionsCell}>
                    <button type="button" className={styles.actionButton} onClick={() => setDetailId(ticket.id)}>
                      {k.view}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateTicketModal
          onClose={() => setShowCreate(false)}
          onCreated={(ticket: Ticket) => {
            setShowCreate(false);
            load();
            setDetailId(ticket.id);
          }}
        />
      )}
      {showSettings && (
        <TicketSettingsModal
          onClose={() => setShowSettings(false)}
          onChanged={() => {
            loadTaxonomy();
            load();
          }}
        />
      )}
      {detailId && (
        <TicketDetailModal ticketId={detailId} onClose={() => setDetailId(null)} onChanged={() => load()} />
      )}
    </section>
  );
}
