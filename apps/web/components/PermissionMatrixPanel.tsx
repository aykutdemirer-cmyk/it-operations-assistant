"use client";

import { useEffect, useState } from "react";

import { ApiError, fetchPamUsers, updatePamUserPermissions, type CurrentUser } from "@/lib/api";
import { ALL_PERMISSIONS, type Permission } from "@/lib/auth/permissions";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { PERMISSION_LABEL_KEY } from "./UserPermissionsModal";
import { ToastStack, useToasts } from "./Toast";

/** Faz 57 — kullanıcı×izin matrisi. Yeni bir yetkilendirme mekanizması
 * AÇMAZ — her hücre tıklaması mevcut Faz 47 `PUT /api/pam/users/{id}/
 * permissions`'ı (o kullanıcının GÜNCEL tam izin listesi + bir izin
 * eklenmiş/çıkarılmış olarak) çağırır, `UserPermissionsModal`'ın
 * "yer değiştirme" (replace, ekleme değil) sözleşmesiyle AYNI. İyimser
 * (optimistic) UI güncellemesi yapılır — istek başarısız olursa checkbox
 * eski durumuna geri alınır. */
export function PermissionMatrixPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [users, setUsers] = useState<CurrentUser[] | null>(null);
  const [error, setError] = useState(false);
  const [pendingCell, setPendingCell] = useState<string | null>(null);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      setUsers(await fetchPamUsers(token));
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

  async function handleToggle(user: CurrentUser, permission: Permission) {
    if (!token || !users) return;
    const cellKey = `${user.id}:${permission}`;
    const hasIt = user.permissions.includes(permission);
    const nextPermissions = hasIt ? user.permissions.filter((perm) => perm !== permission) : [...user.permissions, permission];

    // İyimser güncelleme.
    setUsers(users.map((u) => (u.id === user.id ? { ...u, permissions: nextPermissions } : u)));
    setPendingCell(cellKey);
    try {
      const updated = await updatePamUserPermissions(token, user.id, nextPermissions);
      setUsers((prev) => (prev ? prev.map((u) => (u.id === user.id ? updated : u)) : prev));
    } catch (err) {
      // Başarısız olursa checkbox eski durumuna geri alınır.
      setUsers((prev) => (prev ? prev.map((u) => (u.id === user.id ? user : u)) : prev));
      push("error", err instanceof ApiError ? err.message : p.permissionMatrixUpdateError);
    } finally {
      setPendingCell(null);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.permissionMatrixTitle}</h2>
          <p className={styles.subtitle}>{p.permissionMatrixSubtitle}</p>
        </div>
      </div>

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
                <th>{p.columnUser}</th>
                {ALL_PERMISSIONS.map((permission) => (
                  <th key={permission} title={p[PERMISSION_LABEL_KEY[permission] as keyof typeof p] as string}>
                    {p[PERMISSION_LABEL_KEY[permission] as keyof typeof p] as string}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    {user.username} <span className={styles.status}>({user.role})</span>
                  </td>
                  {ALL_PERMISSIONS.map((permission) => {
                    const cellKey = `${user.id}:${permission}`;
                    return (
                      <td key={permission}>
                        <input
                          type="checkbox"
                          checked={user.permissions.includes(permission)}
                          disabled={pendingCell === cellKey}
                          onChange={() => handleToggle(user, permission)}
                          aria-label={`${user.username} — ${p[PERMISSION_LABEL_KEY[permission] as keyof typeof p]}`}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
