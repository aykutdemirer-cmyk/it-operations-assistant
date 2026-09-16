"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import {
  ApiError,
  createSnmpProfile,
  deleteSnmpProfile,
  fetchAssetsForSnmpProfile,
  fetchSnmpProfiles,
  testSnmpProfileConnection,
  updateSnmpProfile,
  type SnmpAuthProtocol,
  type SnmpPrivProtocol,
  type SnmpProfile,
  type SnmpProfileAssetSummary,
  type SnmpProfileVersion,
  type SnmpProfileWrite,
  type SnmpTestConnectionResult,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { ToastStack, useToasts } from "./Toast";
import styles from "./SnmpConfigurationCenter.module.css";

type FetchStatus = "loading" | "done" | "error";

const AUTH_PROTOCOLS: SnmpAuthProtocol[] = ["SHA", "SHA224", "SHA256", "SHA384", "SHA512", "MD5"];
const PRIV_PROTOCOLS: SnmpPrivProtocol[] = ["AES", "AES192", "AES256", "DES"];

type FormState = {
  name: string;
  target_host: string;
  port: string;
  version: SnmpProfileVersion;
  timeout_seconds: string;
  retries: string;
  enabled: boolean;
  community_ref: string;
  username: string;
  auth_protocol: SnmpAuthProtocol | "";
  auth_credential_ref: string;
  priv_protocol: SnmpPrivProtocol | "";
  priv_credential_ref: string;
};

const EMPTY_FORM: FormState = {
  name: "",
  target_host: "",
  port: "161",
  version: "v2c",
  timeout_seconds: "2",
  retries: "1",
  enabled: true,
  community_ref: "",
  username: "",
  auth_protocol: "",
  auth_credential_ref: "",
  priv_protocol: "",
  priv_credential_ref: "",
};

function profileToForm(profile: SnmpProfile): FormState {
  return {
    name: profile.name,
    target_host: profile.target_host,
    port: String(profile.port),
    version: profile.version,
    timeout_seconds: String(profile.timeout_seconds),
    retries: String(profile.retries),
    enabled: profile.enabled,
    community_ref: profile.community_ref ?? "",
    username: profile.username ?? "",
    auth_protocol: profile.auth_protocol ?? "",
    auth_credential_ref: profile.auth_credential_ref ?? "",
    priv_protocol: profile.priv_protocol ?? "",
    priv_credential_ref: profile.priv_credential_ref ?? "",
  };
}

function formToPayload(form: FormState): SnmpProfileWrite {
  const isV3 = form.version === "v3";
  return {
    name: form.name.trim(),
    target_host: form.target_host.trim(),
    port: Number(form.port),
    version: form.version,
    timeout_seconds: Number(form.timeout_seconds),
    retries: Number(form.retries),
    enabled: form.enabled,
    community_ref: !isV3 && form.community_ref.trim() ? form.community_ref.trim() : null,
    username: isV3 && form.username.trim() ? form.username.trim() : null,
    auth_protocol: isV3 && form.auth_protocol ? form.auth_protocol : null,
    auth_credential_ref: isV3 && form.auth_credential_ref.trim() ? form.auth_credential_ref.trim() : null,
    priv_protocol: isV3 && form.priv_protocol ? form.priv_protocol : null,
    priv_credential_ref: isV3 && form.priv_credential_ref.trim() ? form.priv_credential_ref.trim() : null,
  };
}

function statusDotClass(status: SnmpProfile["status"], styles: Record<string, string>): string {
  if (status === "ready") return styles.dotReady;
  return styles.dotMuted;
}

function testStatusDotClass(status: SnmpTestConnectionResult["status"], styles: Record<string, string>): string {
  if (status === "connected") return styles.dotReady;
  if (status === "authentication_failed") return styles.dotWarning;
  if (status === "timeout" || status === "unreachable" || status === "error") return styles.dotDown;
  return styles.dotMuted;
}

export function SnmpConfigurationCenter() {
  const { t } = useLocale();
  const st = t.settings.snmpConfig;

  const [profiles, setProfiles] = useState<SnmpProfile[]>([]);
  const [status, setStatus] = useState<FetchStatus>("loading");
  // Faz: "Atanmış Cihazlar" hücresi artık yalnızca sayı DEĞİL — hangi
  // asset(ler) olduğunu gösterip Topoloji'ye tıklanabilir link veriyor
  // (kullanıcı isteği). `fetchAssetsForSnmpProfile` zaten Faz 29.5'ten
  // beri backend'de/api.ts'de vardı, yalnızca UI'ya hiç bağlanmamıştı.
  const [assignedAssets, setAssignedAssets] = useState<Record<string, SnmpProfileAssetSummary[]>>({});
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, SnmpTestConnectionResult>>({});
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<{ id: string; message: string } | null>(null);
  const { toasts, push: pushToast, dismiss: dismissToast } = useToasts();

  function load() {
    // `status` bilerek "loading"a geri alınmıyor — bir create/edit/
    // delete sonrası yeniden yüklerken tabloyu kısa süreliğine
    // gizleyip "Yükleniyor..." göstermek yerine mevcut liste sabit
    // kalır, veri gelince sessizce yer değiştirir (daha az titreşen bir
    // UX). İlk yükleme zaten `useState("loading")` ile başlıyor.
    fetchSnmpProfiles()
      .then((data) => {
        setProfiles(data);
        setStatus("done");
        // Yalnızca gerçekten atanmış cihazı olan profiller için — 0
        // atamalı bir profil için boş bir istek atılmaz.
        for (const profile of data) {
          if (profile.assigned_asset_count > 0) {
            fetchAssetsForSnmpProfile(profile.id)
              .then((assets) => setAssignedAssets((prev) => ({ ...prev, [profile.id]: assets })))
              .catch(() => {
                /* sessizce yut — hücre sayıya düşer */
              });
          }
        }
      })
      .catch(() => setStatus("error"));
  }

  useEffect(() => {
    load();
  }, []);

  function openCreate() {
    setForm(EMPTY_FORM);
    setFormError(null);
    setEditingId("new");
  }

  function openEdit(profile: SnmpProfile) {
    setForm(profileToForm(profile));
    setFormError(null);
    setEditingId(profile.id);
  }

  function closeForm() {
    setEditingId(null);
    setFormError(null);
  }

  async function handleSave() {
    setSaving(true);
    setFormError(null);
    try {
      const payload = formToPayload(form);
      if (editingId === "new") {
        await createSnmpProfile(payload);
      } else if (editingId) {
        await updateSnmpProfile(editingId, payload);
      }
      setEditingId(null);
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : st.saveError);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteSnmpProfile(id);
      setConfirmDeleteId(null);
      setDeleteError(null);
      load();
    } catch (err) {
      setConfirmDeleteId(null);
      const message =
        err instanceof ApiError && err.status === 409 ? st.deleteHasAssignmentsError : st.deleteError;
      setDeleteError({ id, message });
    }
  }

  async function handleTest(id: string) {
    setTestingId(id);
    try {
      const result = await testSnmpProfileConnection(id);
      setTestResults((prev) => ({ ...prev, [id]: result }));
      // Faz: timeout/community/unreachable ayrımını kısa tablo
      // etiketinden daha net görebilmek için backend'in ayrıntılı
      // `message`'ını (bkz. `profile_service.py::test_connection`)
      // toast olarak da göster.
      pushToast(
        result.status === "connected" ? "success" : "error",
        `${st.testResultLabels[result.status]}: ${result.message}`,
      );
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : st.saveError);
    } finally {
      setTestingId(null);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
      <div className={styles.header}>
        <div>
          <h3 className={styles.sectionTitle}>{st.sectionTitle}</h3>
          <p className={styles.description}>{st.description}</p>
        </div>
        <button type="button" className={styles.addButton} onClick={openCreate}>
          {st.addProfile}
        </button>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.status}>{st.loadError}</p>}

      {status === "done" && (
        <>
          {profiles.length === 0 ? (
            <p className={styles.noData}>{st.noProfiles}</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{st.columns.name}</th>
                    <th>{st.columns.target}</th>
                    <th>{st.columns.version}</th>
                    <th>{st.columns.status}</th>
                    <th>{st.columns.assignedDevices}</th>
                    <th>{st.columns.actions}</th>
                  </tr>
                </thead>
                <tbody>
                  {profiles.map((profile) => {
                    const testResult = testResults[profile.id];
                    return (
                      <tr key={profile.id}>
                        <td>{profile.name}</td>
                        <td className={styles.mono}>
                          {profile.target_host}:{profile.port}
                        </td>
                        <td>{profile.version}</td>
                        <td>
                          <span className={styles.statusCell}>
                            <span className={`${styles.dot} ${statusDotClass(profile.status, styles)}`} />
                            {st.statusLabels[profile.status]}
                          </span>
                          {testResult && (
                            <div className={styles.testResult}>
                              <span className={styles.testResultPrefix}>{st.lastTestResult}</span>
                              <span
                                className={`${styles.dot} ${testStatusDotClass(testResult.status, styles)}`}
                              />
                              {st.testResultLabels[testResult.status]}
                              {testResult.sys_name && (
                                <span className={styles.testSysName}> — {testResult.sys_name}</span>
                              )}
                            </div>
                          )}
                        </td>
                        <td>
                          {profile.assigned_asset_count === 0 ? (
                            st.assignedDevicesCount(0)
                          ) : assignedAssets[profile.id] ? (
                            <div className={styles.deviceList}>
                              {assignedAssets[profile.id].map((asset) => (
                                <Link
                                  key={asset.id}
                                  className={styles.deviceLink}
                                  href={`/topology?ip=${encodeURIComponent(asset.ip_address)}`}
                                  title={t.common.viewInTopology}
                                >
                                  {asset.hostname || asset.ip_address}
                                </Link>
                              ))}
                            </div>
                          ) : (
                            st.assignedDevicesCount(profile.assigned_asset_count)
                          )}
                        </td>
                        <td className={styles.actions}>
                          <button type="button" className={styles.linkButton} onClick={() => openEdit(profile)}>
                            {t.common.edit}
                          </button>
                          <button
                            type="button"
                            className={styles.linkButton}
                            onClick={() => handleTest(profile.id)}
                            disabled={testingId === profile.id}
                          >
                            {testingId === profile.id ? st.testing : st.testConnection}
                          </button>
                          {confirmDeleteId === profile.id ? (
                            <span className={styles.confirmGroup}>
                              <button
                                type="button"
                                className={styles.linkButtonDanger}
                                onClick={() => handleDelete(profile.id)}
                              >
                                {st.delete}
                              </button>
                              <button
                                type="button"
                                className={styles.linkButton}
                                onClick={() => setConfirmDeleteId(null)}
                              >
                                {st.cancel}
                              </button>
                            </span>
                          ) : (
                            <button
                              type="button"
                              className={styles.linkButtonDanger}
                              onClick={() => {
                                setDeleteError(null);
                                setConfirmDeleteId(profile.id);
                              }}
                            >
                              {st.delete}
                            </button>
                          )}
                          {deleteError?.id === profile.id && (
                            <div className={styles.formError}>{deleteError.message}</div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {editingId !== null && (
        <div className={styles.formPanel}>
          <h4 className={styles.formTitle}>{editingId === "new" ? st.newProfile : st.editProfile}</h4>

          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>{st.fields.profileName}</span>
              <input
                type="text"
                value={form.name}
                placeholder={st.fields.profileNamePlaceholder}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.targetHost}</span>
              <input
                type="text"
                value={form.target_host}
                placeholder={st.fields.targetHostPlaceholder}
                onChange={(e) => setForm({ ...form, target_host: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.port}</span>
              <input
                type="number"
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.version}</span>
              <select
                value={form.version}
                onChange={(e) => setForm({ ...form, version: e.target.value as SnmpProfileVersion })}
              >
                <option value="v2c">SNMP v2c</option>
                <option value="v3">SNMP v3</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>{st.fields.timeout}</span>
              <input
                type="number"
                step="0.5"
                value={form.timeout_seconds}
                onChange={(e) => setForm({ ...form, timeout_seconds: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.retries}</span>
              <input
                type="number"
                value={form.retries}
                onChange={(e) => setForm({ ...form, retries: e.target.value })}
              />
            </label>
            <label className={styles.fieldCheckbox}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
              <span>{st.fields.enabled}</span>
            </label>
          </div>

          {form.version === "v2c" ? (
            <div className={styles.formGrid}>
              <label className={styles.field}>
                <span>{st.fields.community}</span>
                <input
                  type="text"
                  value={form.community_ref}
                  placeholder={st.fields.communityPlaceholder}
                  onChange={(e) => setForm({ ...form, community_ref: e.target.value })}
                />
                <span className={styles.hint}>{st.fields.communityHint}</span>
              </label>
            </div>
          ) : (
            <div className={styles.formGrid}>
              <label className={styles.field}>
                <span>{st.fields.username}</span>
                <input
                  type="text"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                />
              </label>
              <label className={styles.field}>
                <span>{st.fields.authProtocol}</span>
                <select
                  value={form.auth_protocol}
                  onChange={(e) => setForm({ ...form, auth_protocol: e.target.value as SnmpAuthProtocol | "" })}
                >
                  <option value="">{st.fields.none}</option>
                  {AUTH_PROTOCOLS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <label className={styles.field}>
                <span>{st.fields.authSecretRef}</span>
                <input
                  type="text"
                  value={form.auth_credential_ref}
                  onChange={(e) => setForm({ ...form, auth_credential_ref: e.target.value })}
                />
              </label>
              <label className={styles.field}>
                <span>{st.fields.privProtocol}</span>
                <select
                  value={form.priv_protocol}
                  onChange={(e) => setForm({ ...form, priv_protocol: e.target.value as SnmpPrivProtocol | "" })}
                >
                  <option value="">{st.fields.none}</option>
                  {PRIV_PROTOCOLS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <label className={styles.field}>
                <span>{st.fields.privSecretRef}</span>
                <input
                  type="text"
                  value={form.priv_credential_ref}
                  onChange={(e) => setForm({ ...form, priv_credential_ref: e.target.value })}
                />
              </label>
            </div>
          )}

          {formError && <p className={styles.formError}>{formError}</p>}

          <div className={styles.formActions}>
            <button type="button" className={styles.saveButton} onClick={handleSave} disabled={saving}>
              {st.save}
            </button>
            <button type="button" className={styles.linkButton} onClick={closeForm} disabled={saving}>
              {st.cancel}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
