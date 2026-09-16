"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  createPamUser,
  createPamUserFromAd,
  fetchAdUsers,
  fetchPamUsers,
  updatePamUser,
  updatePamUserPermissions,
  type AdUser,
  type CurrentUser,
  type TicketRole,
  type UserRole,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import type { Permission } from "@/lib/auth/permissions";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ToastStack, useToasts } from "./Toast";
import { UserPermissionsModal } from "./UserPermissionsModal";

const ROLES: UserRole[] = ["ADMIN", "OPERATOR", "VIEWER"];
// Faz 65 — bilet-modülü rolü (mevcut `role`'dan bağımsız).
const TICKET_ROLES: TicketRole[] = ["REQUESTER", "TECHNICIAN", "ADMIN"];

export function PamUsersPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;
  const kt = t.tickets;

  const [users, setUsers] = useState<CurrentUser[] | null>(null);
  const [adUsers, setAdUsers] = useState<AdUser[]>([]);
  const [error, setError] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [userSource, setUserSource] = useState<"local" | "ad">("local");
  const [formUsername, setFormUsername] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formRole, setFormRole] = useState<UserRole>("VIEWER");
  const [formTicketRole, setFormTicketRole] = useState<TicketRole>("REQUESTER");
  const [formFullName, setFormFullName] = useState("");
  const [selectedAdUsername, setSelectedAdUsername] = useState("");
  const [saving, setSaving] = useState(false);
  const [permissionsTarget, setPermissionsTarget] = useState<CurrentUser | null>(null);
  const [savingPermissions, setSavingPermissions] = useState(false);
  const [adUsernameEdits, setAdUsernameEdits] = useState<Record<string, string>>({});
  const [linkingUserId, setLinkingUserId] = useState<string | null>(null);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      const [usersData, adUsersData] = await Promise.all([fetchPamUsers(token), fetchAdUsers(token)]);
      setUsers(usersData);
      setAdUsers(adUsersData);
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    // setState çağrıları bir microtask'a ertelendi — bkz. `lib/i18n/
    // LocaleProvider.tsx`'teki aynı desen (react-hooks/set-state-in-effect).
    Promise.resolve().then(() => {
      load();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    try {
      if (userSource === "local") {
        await createPamUser(token, {
          username: formUsername,
          password: formPassword,
          role: formRole,
          full_name: formFullName || null,
          ticket_role: formTicketRole,
        });
      } else {
        if (!selectedAdUsername) return;
        await createPamUserFromAd(token, { ad_username: selectedAdUsername, role: formRole });
      }
      setFormUsername("");
      setFormPassword("");
      setFormFullName("");
      setFormRole("VIEWER");
      setFormTicketRole("REQUESTER");
      setSelectedAdUsername("");
      setShowForm(false);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : userSource === "ad" ? p.importFromAdError : p.createUserError);
    } finally {
      setSaving(false);
    }
  }

  async function handleRoleChange(userId: string, role: UserRole) {
    if (!token) return;
    try {
      await updatePamUser(token, userId, { role });
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createUserError);
    }
  }

  // Faz 65 — bilet rolü satır içi güncelleme.
  async function handleTicketRoleChange(userId: string, ticket_role: TicketRole) {
    if (!token) return;
    try {
      await updatePamUser(token, userId, { ticket_role });
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createUserError);
    }
  }

  async function handleToggleActive(user: CurrentUser) {
    if (!token) return;
    try {
      await updatePamUser(token, user.id, { is_active: !user.is_active });
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createUserError);
    }
  }

  async function handleLinkAdUsername(user: CurrentUser, adUsername: string) {
    if (!token) return;
    setLinkingUserId(user.id);
    try {
      await updatePamUser(token, user.id, { ad_username: adUsername.trim() || null });
      setAdUsernameEdits((prev) => {
        const next = { ...prev };
        delete next[user.id];
        return next;
      });
      await load();
    } catch (err) {
      push("error", err instanceof ApiError && err.status === 422 ? p.adLinkError : p.createUserError);
    } finally {
      setLinkingUserId(null);
    }
  }

  async function handleSavePermissions(permissions: Permission[]) {
    if (!token || !permissionsTarget) return;
    setSavingPermissions(true);
    try {
      await updatePamUserPermissions(token, permissionsTarget.id, permissions);
      setPermissionsTarget(null);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createUserError);
    } finally {
      setSavingPermissions(false);
    }
  }

  // Zaten BAŞKA bir yerel hesaba bağlı AD kullanıcıları "Yeni Kullanıcı"
  // seçicisinde TEKRAR gösterilmez — `POST /api/pam/users/from-ad`
  // zaten 409 döner, ama seçiciyi baştan filtrelemek daha net bir UX.
  const linkedAdUsernames = new Set((users ?? []).map((u) => u.ad_username).filter((v): v is string => !!v));
  const availableAdUsers = adUsers.filter((u) => !linkedAdUsernames.has(u.username));

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.usersTitle}</h2>
          <p className={styles.subtitle}>{p.usersSubtitle}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link href="/pam/permissions" className={styles.linkButton}>
            {p.permissionMatrixTitle}
          </Link>
          <button type="button" className={styles.toolbarButton} onClick={() => setShowForm((v) => !v)}>
            {p.newUser}
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
          <label className={styles.status}>
            {p.userSourceLabel}
            <br />
            <select
              className={styles.searchInput}
              value={userSource}
              onChange={(e) => setUserSource(e.target.value as "local" | "ad")}
            >
              <option value="local">{p.userSourceLocal}</option>
              <option value="ad">{p.userSourceAd}</option>
            </select>
          </label>

          {userSource === "local" ? (
            <>
              <label className={styles.status}>
                {p.columnUsername}
                <br />
                <input
                  className={styles.searchInput}
                  value={formUsername}
                  onChange={(e) => setFormUsername(e.target.value)}
                  required
                />
              </label>
              <label className={styles.status}>
                {t.auth.password}
                <br />
                <input
                  type="password"
                  className={styles.searchInput}
                  value={formPassword}
                  onChange={(e) => setFormPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </label>
              <label className={styles.status}>
                {p.columnFullName}
                <br />
                <input
                  className={styles.searchInput}
                  value={formFullName}
                  onChange={(e) => setFormFullName(e.target.value)}
                />
              </label>
            </>
          ) : (
            <label className={styles.status}>
              {p.selectAdUserLabel}
              <br />
              <select
                className={styles.searchInput}
                value={selectedAdUsername}
                onChange={(e) => setSelectedAdUsername(e.target.value)}
                required
              >
                <option value="" disabled>
                  {p.selectAdUserPlaceholder}
                </option>
                {availableAdUsers.map((u) => (
                  <option key={u.id} value={u.username}>
                    {u.display_name ? `${u.display_name} (${u.username})` : u.username}
                  </option>
                ))}
              </select>
              {availableAdUsers.length === 0 && <span className={styles.status}>{p.noSyncedAdUsers}</span>}
            </label>
          )}

          <label className={styles.status}>
            {p.columnRole}
            <br />
            <select
              className={styles.searchInput}
              value={formRole}
              onChange={(e) => setFormRole(e.target.value as UserRole)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          {userSource === "local" && (
            <label className={styles.status}>
              {kt.fieldTicketRole}
              <br />
              <select
                className={styles.searchInput}
                value={formTicketRole}
                onChange={(e) => setFormTicketRole(e.target.value as TicketRole)}
              >
                {TICKET_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r === "REQUESTER" ? kt.roleRequester : r === "TECHNICIAN" ? kt.roleTechnician : kt.roleAdmin}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button type="submit" className={styles.toolbarButton} disabled={saving}>
            {userSource === "ad" ? p.importFromAd : p.create}
          </button>
        </form>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {t.common.unableToLoad}
        </p>
      )}
      {!error && users === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && users !== null && users.length === 0 && <p className={styles.status}>{t.common.noDataAvailable}</p>}

      {!error && users !== null && users.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnUsername}</th>
                <th>{p.columnFullName}</th>
                <th>{p.columnRole}</th>
                <th>{kt.colTicketRole}</th>
                <th>{p.columnStatus}</th>
                <th>{p.columnAdUsername}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.full_name || "—"}</td>
                  <td>
                    <select
                      className={styles.searchInput}
                      value={user.role}
                      onChange={(e) => handleRoleChange(user.id, e.target.value as UserRole)}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select
                      className={styles.searchInput}
                      aria-label={`${user.username} — ${kt.colTicketRole}`}
                      value={user.ticket_role}
                      onChange={(e) => handleTicketRoleChange(user.id, e.target.value as TicketRole)}
                    >
                      {TICKET_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r === "REQUESTER" ? kt.roleRequester : r === "TECHNICIAN" ? kt.roleTechnician : kt.roleAdmin}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>{user.is_active ? p.active : p.inactive}</td>
                  <td>
                    {user.ad_username && <div className={styles.status}>{p.adSyncedBadge}</div>}
                    <select
                      className={styles.searchInput}
                      value={adUsernameEdits[user.id] ?? user.ad_username ?? ""}
                      onChange={(e) => setAdUsernameEdits((prev) => ({ ...prev, [user.id]: e.target.value }))}
                    >
                      <option value="">—</option>
                      {adUsers.map((u) => (
                        <option key={u.id} value={u.username}>
                          {u.display_name ? `${u.display_name} (${u.username})` : u.username}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className={styles.actionButton}
                      disabled={linkingUserId === user.id}
                      onClick={() => handleLinkAdUsername(user, adUsernameEdits[user.id] ?? user.ad_username ?? "")}
                    >
                      {(adUsernameEdits[user.id] ?? user.ad_username) ? p.linkAdAccount : p.unlinkAdAccount}
                    </button>
                  </td>
                  <td className={styles.actionsCell}>
                    <button type="button" className={styles.actionButton} onClick={() => handleToggleActive(user)}>
                      {user.is_active ? p.inactive : p.active}
                    </button>
                    <button type="button" className={styles.actionButton} onClick={() => setPermissionsTarget(user)}>
                      {p.editPermissions}
                    </button>
                    <Link href={`/pam/users/${user.id}`} className={styles.linkButton}>
                      {p.editDeviceAccess}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {permissionsTarget && (
        <UserPermissionsModal
          username={permissionsTarget.username}
          initialPermissions={permissionsTarget.permissions}
          saving={savingPermissions}
          onSave={handleSavePermissions}
          onCancel={() => setPermissionsTarget(null)}
        />
      )}
    </section>
  );
}
