"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  approveAccessRequest,
  fetchAccessRequests,
  fetchVaultCredentials,
  rejectAccessRequest,
  type AccessRequestStatus,
  type PamAccessRequest,
  type VaultCredential,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import editModalStyles from "./EditRuleModal.module.css";
import { ToastStack, useToasts } from "./Toast";

function statusBadgeClass(status: AccessRequestStatus): string {
  if (status === "approved") return styles.badgeGreen;
  if (status === "rejected") return styles.badgeRed;
  return styles.badgeNeutral;
}

function deviceTargetLabel(r: PamAccessRequest): string {
  if (r.tag_id) return `🏷️ ${r.tag_name}`;
  if (r.server_group_id) return `🗂️ ${r.server_group_name}`;
  return r.asset_hostname || r.asset_ip_address || "—";
}

/** Faz 56 — `PAM_ADMIN`-only "Erişim Talepleri" ekranı. Onaylama YENİ
 * bir yetkilendirme mekanizması AÇMAZ — mevcut Faz 46/55
 * `pam_access_rules` motorunu genişletir/oluşturur (bkz. backend
 * `service.py::approve_access_request`); bu yüzden bu panel Admin'e
 * kasa hesabı SEÇTİRİR (talep eden kullanıcı bunu hiç görmez — zero-
 * knowledge ilkesi, `MyAccessPanel`'in dokümantasyonuyla AYNI). */
export function PamAccessRequestsPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [requests, setRequests] = useState<PamAccessRequest[] | null>(null);
  const [credentials, setCredentials] = useState<VaultCredential[]>([]);
  const [error, setError] = useState(false);
  const [statusFilter, setStatusFilter] = useState<AccessRequestStatus | "">("pending");
  const [approvingRequest, setApprovingRequest] = useState<PamAccessRequest | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      const [requestsData, credentialsData] = await Promise.all([
        fetchAccessRequests(token, statusFilter || undefined),
        fetchVaultCredentials(token),
      ]);
      setRequests(requestsData);
      setCredentials(credentialsData);
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    Promise.resolve().then(() => {
      load();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, statusFilter]);

  async function handleReject(request: PamAccessRequest) {
    if (!token) return;
    setBusyId(request.id);
    try {
      await rejectAccessRequest(token, request.id);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.rejectRequestError);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.requestsTitle}</h2>
          <p className={styles.subtitle}>{p.requestsSubtitle}</p>
        </div>
      </div>

      <div className={styles.filterBar}>
        <label className={styles.status}>
          {p.filterStatusLabel}
          <br />
          <select
            className={styles.filterSelect}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as AccessRequestStatus | "")}
          >
            <option value="pending">{p.statusPending}</option>
            <option value="approved">{p.statusApproved}</option>
            <option value="rejected">{p.statusRejected}</option>
            <option value="">{t.common.all}</option>
          </select>
        </label>
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {t.common.unableToLoad}
        </p>
      )}
      {!error && requests === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && requests !== null && requests.length === 0 && <p className={styles.status}>{p.requestsEmpty}</p>}

      {!error && requests !== null && requests.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnRequester}</th>
                <th>{p.columnAsset}</th>
                <th>{p.requestProtocol}</th>
                <th>{p.columnReason}</th>
                <th>{p.columnStatus}</th>
                <th>{p.columnRequestedAt}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td>{r.requester_username}</td>
                  <td>{deviceTargetLabel(r)}</td>
                  <td>{r.protocol.toUpperCase()}</td>
                  <td>{r.business_reason}</td>
                  <td>
                    <span className={`${styles.badge} ${statusBadgeClass(r.status)}`}>
                      {r.status === "pending" ? p.statusPending : r.status === "approved" ? p.statusApproved : p.statusRejected}
                    </span>
                    {r.status !== "pending" && r.reviewed_by_username && (
                      <div className={styles.status}>
                        {p.reviewedBy}: {r.reviewed_by_username}
                      </div>
                    )}
                  </td>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                  <td className={styles.actionsCell}>
                    {r.status === "pending" && (
                      <>
                        <button
                          type="button"
                          className={styles.actionButton}
                          disabled={busyId === r.id}
                          onClick={() => setApprovingRequest(r)}
                        >
                          {p.approve}
                        </button>
                        <button
                          type="button"
                          className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                          disabled={busyId === r.id}
                          onClick={() => handleReject(r)}
                        >
                          {p.reject}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {approvingRequest && (
        <ApproveRequestModal
          request={approvingRequest}
          credentials={credentials}
          onClose={() => setApprovingRequest(null)}
          onApproved={() => {
            setApprovingRequest(null);
            load();
          }}
        />
      )}
    </section>
  );
}

function ApproveRequestModal({
  request,
  credentials,
  onClose,
  onApproved,
}: {
  request: PamAccessRequest;
  credentials: VaultCredential[];
  onClose: () => void;
  onApproved: () => void;
}) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [credentialId, setCredentialId] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    setErrorMessage(null);
    try {
      await approveAccessRequest(token, request.id, credentialId, reviewNote || undefined);
      onApproved();
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : p.approveRequestError);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={editModalStyles.overlay} role="presentation" onClick={onClose}>
      <form
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal="true"
        className={editModalStyles.dialog}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className={editModalStyles.title}>{p.approveRequestTitle}</h3>
        <p className={editModalStyles.subtitle}>
          {request.requester_username} → {deviceTargetLabel(request)} ({request.protocol.toUpperCase()})
        </p>

        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}

        <label className={styles.status}>
          {p.approveRequestCredentialLabel}
          <br />
          <select
            className={styles.searchInput}
            value={credentialId}
            onChange={(e) => setCredentialId(e.target.value)}
            required
          >
            <option value="" disabled>
              —
            </option>
            {credentials.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.status}>
          {p.reviewNoteLabel}
          <br />
          <input
            type="text"
            className={styles.searchInput}
            value={reviewNote}
            onChange={(e) => setReviewNote(e.target.value)}
          />
        </label>

        <div className={editModalStyles.actions}>
          <button type="button" className={styles.actionButton} onClick={onClose}>
            {p.cancel}
          </button>
          <button type="submit" className={styles.toolbarButton} disabled={saving}>
            {p.approve}
          </button>
        </div>
      </form>
    </div>
  );
}
