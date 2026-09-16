"use client";

import { useEffect, useState } from "react";

import {
  addTicketComment,
  ApiError,
  fetchTicket,
  fetchTicketAssignableUsers,
  type Ticket,
  type TicketAssignableUser,
  type TicketStatus,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import editModalStyles from "./EditRuleModal.module.css";
import { priorityBadgeClass, statusBadgeClass } from "./ticketBadges";

const STATUSES: TicketStatus[] = ["OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"];

type CommentPayload = {
  body?: string;
  status?: TicketStatus;
  assigned_to?: string | null;
  is_internal?: boolean;
};

/** Faz 62/63 — bilet detay + yanıt modalı. Sol tarafta zaman çizelgesi +
 * yanıt kutusu, sağ tarafta metadata + durum/atama güncelleme. */
export function TicketDetailModal({ ticketId, onClose, onChanged }: { ticketId: string; onClose: () => void; onChanged: () => void }) {
  const { token, currentUser } = useAuth();
  const { t } = useLocale();
  const k = t.tickets;

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [users, setUsers] = useState<TicketAssignableUser[]>([]);
  const [reply, setReply] = useState("");
  const [replyTab, setReplyTab] = useState<"public" | "internal">("public");
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Faz 65'in bilet-özel rol ekseni — yalnızca TECHNICIAN/ADMIN gizli iç
  // not yazabilir ve hızlı IT aksiyonlarını görür (backend zaten aynı
  // ayrımı `_is_it_staff` ile zorunlu kılıyor, bkz. `service.py`).
  const isItStaff = currentUser?.ticket_role === "TECHNICIAN" || currentUser?.ticket_role === "ADMIN";

  async function load() {
    if (!token) return;
    try {
      setTicket(await fetchTicket(token, ticketId));
      setErrorMessage(null);
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : k.loadError);
    }
  }

  useEffect(() => {
    if (!token) return;
    Promise.resolve().then(() => {
      load();
      fetchTicketAssignableUsers(token).then(setUsers).catch(() => setUsers([]));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, ticketId]);

  async function mutate(payload: CommentPayload) {
    if (!token) return;
    setBusy(true);
    setErrorMessage(null);
    try {
      const updated = await addTicketComment(token, ticketId, payload);
      setTicket(updated);
      setReply("");
      onChanged();
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : k.commentError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={editModalStyles.overlay} role="presentation" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={k.detailTitle}
        className={editModalStyles.dialog}
        style={{ width: "min(1040px, 96vw)", maxHeight: "88vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        {!ticket ? (
          <p className={styles.status}>{errorMessage ?? t.common.loading}</p>
        ) : (
          <>
            <h3 className={editModalStyles.title}>
              {ticket.ticket_number} — {ticket.title}
            </h3>
            {errorMessage && (
              <p className={styles.error} role="alert">
                {errorMessage}
              </p>
            )}

            {isItStaff && (
              <div className={styles.actionsCell} style={{ margin: "10px 0" }}>
                <button
                  type="button"
                  className={styles.actionButton}
                  disabled={busy || !currentUser || ticket.assigned_to === currentUser.id}
                  onClick={() => currentUser && mutate({ assigned_to: currentUser.id })}
                >
                  {k.assignToMe}
                </button>
                <button
                  type="button"
                  className={styles.actionButton}
                  disabled={busy || ticket.status === "RESOLVED" || ticket.status === "CLOSED"}
                  onClick={() => mutate({ status: "RESOLVED" })}
                >
                  {k.markResolved}
                </button>
                <button
                  type="button"
                  className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                  disabled={busy || ticket.status === "CLOSED"}
                  onClick={() => mutate({ status: "CLOSED" })}
                >
                  {k.closeTicket}
                </button>
              </div>
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) minmax(0, 320px)",
                gap: 20,
                alignItems: "start",
              }}
            >
              {/* Sol: zaman çizelgesi + yanıt */}
              <div style={{ minWidth: 0 }}>
                <p className={styles.subtitle}>{ticket.description || "—"}</p>
                <h4 className={styles.title} style={{ fontSize: "0.95rem", marginTop: 14 }}>
                  {k.timeline}
                </h4>
                <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 10, margin: "8px 0" }}>
                  {ticket.comments.map((c) => (
                    <li
                      key={c.id}
                      style={{
                        borderLeft: `2px solid ${c.is_internal ? "var(--status-degraded, #b45309)" : "var(--border-strong)"}`,
                        paddingLeft: 10,
                      }}
                    >
                      <div className={styles.status} style={{ fontSize: "0.72rem" }}>
                        <strong>{c.author_username}</strong> · {new Date(c.created_at).toLocaleString()}
                        {c.is_internal && (
                          <span className={styles.badge} style={{ marginLeft: 6 }}>
                            {k.internalNoteBadge}
                          </span>
                        )}
                      </div>
                      {c.event === "comment" && <div>{c.body}</div>}
                      {c.event === "created" && <div className={styles.status}>{k.eventCreated}</div>}
                      {c.event === "status_change" && (
                        <div className={styles.status}>
                          {k.eventStatusChange}: {c.status_from ? k[`status${c.status_from}`] : "—"} →{" "}
                          {c.status_to ? k[`status${c.status_to}`] : "—"}
                        </div>
                      )}
                      {c.event === "assignment" && (
                        <div className={styles.status}>
                          {k.eventAssignment}: {c.assigned_from_username ?? k.unassigned} →{" "}
                          {c.assigned_to_username ?? k.unassigned}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>

                <label className={styles.status} style={{ display: "block" }}>
                  {k.addReply}
                </label>
                {isItStaff && (
                  <div className={styles.tabs} style={{ margin: "4px 0 0" }}>
                    <button
                      type="button"
                      className={`${styles.tabButton} ${replyTab === "public" ? styles.tabButtonActive : ""}`}
                      onClick={() => setReplyTab("public")}
                    >
                      {k.replyTabPublic}
                    </button>
                    <button
                      type="button"
                      className={`${styles.tabButton} ${replyTab === "internal" ? styles.tabButtonActive : ""}`}
                      onClick={() => setReplyTab("internal")}
                    >
                      {k.replyTabInternal}
                    </button>
                  </div>
                )}
                <textarea
                  className={styles.searchInput}
                  style={{
                    display: "block",
                    width: "100%",
                    minHeight: 120,
                    marginTop: 6,
                    resize: "vertical",
                    boxSizing: "border-box",
                    whiteSpace: "pre-wrap",
                    overflowWrap: "break-word",
                  }}
                  placeholder={isItStaff && replyTab === "internal" ? k.internalReplyPlaceholder : k.replyPlaceholder}
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                />
                <button
                  type="button"
                  className={styles.toolbarButton}
                  disabled={busy || !reply.trim()}
                  onClick={() => mutate({ body: reply.trim(), is_internal: isItStaff && replyTab === "internal" })}
                >
                  {k.send}
                </button>
              </div>

              {/* Sağ: metadata + aksiyonlar */}
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <h4 className={styles.title} style={{ fontSize: "0.95rem" }}>
                  {k.metadata}
                </h4>
                <div>
                  <span className={`${styles.badge} ${priorityBadgeClass(ticket.priority, styles)}`}>
                    {k[`priority${ticket.priority}`]}
                  </span>{" "}
                  <span className={`${styles.badge} ${statusBadgeClass(ticket.status, styles)}`}>
                    {k[`status${ticket.status}`]}
                  </span>
                </div>
                <div className={styles.status}>
                  {k.colCategory}: {ticket.category_name ?? "—"}
                </div>
                <div className={styles.status}>
                  {k.colDepartment}: {ticket.department_name ?? "—"}
                </div>
                <div className={styles.status}>
                  {k.colCreatedBy}: {ticket.created_by_username}
                </div>
                <div className={styles.status}>
                  {k.assignee}: {ticket.assigned_to_username ?? k.unassigned}
                </div>
                <div className={styles.status}>
                  {k.createdAt}: {new Date(ticket.created_at).toLocaleString()}
                </div>
                {ticket.sla_due_at && (
                  <div className={styles.status}>
                    {k.slaDue}: {new Date(ticket.sla_due_at).toLocaleString()}
                  </div>
                )}
                {ticket.resolved_at && (
                  <div className={styles.status}>
                    {k.resolvedAt}: {new Date(ticket.resolved_at).toLocaleString()}
                  </div>
                )}

                <label className={styles.status}>
                  {k.changeStatus}
                  <br />
                  <select
                    className={styles.searchInput}
                    value={ticket.status}
                    disabled={busy}
                    onChange={(e) => mutate({ status: e.target.value as TicketStatus })}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {k[`status${s}`]}
                      </option>
                    ))}
                  </select>
                </label>

                <label className={styles.status}>
                  {k.changeAssignee}
                  <br />
                  <select
                    className={styles.searchInput}
                    value={ticket.assigned_to ?? ""}
                    disabled={busy}
                    onChange={(e) => mutate({ assigned_to: e.target.value || null })}
                  >
                    <option value="">{k.unassigned}</option>
                    {currentUser && !users.some((u) => u.id === currentUser.id) && (
                      <option value={currentUser.id}>{currentUser.username}</option>
                    )}
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.username}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>

            <div className={editModalStyles.actions}>
              <button type="button" className={styles.actionButton} onClick={onClose}>
                {k.cancel}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
