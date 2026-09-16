"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createAccessRequest,
  fetchAssets,
  fetchMyAccess,
  fetchMyAccessRequests,
  type Asset,
  type AuthorizedAsset,
  type PamAccessRequest,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { daysRemainingLabel } from "./PamRulesPanel";
import styles from "./AgentsList.module.css";
import { ToastStack, useToasts } from "./Toast";

// Faz 56 — talep durumuna göre rozet rengi (mevcut PamAuditPanel'deki
// `endReasonBadgeClass` deseniyle AYNI ilke).
function statusBadgeClass(status: PamAccessRequest["status"]): string {
  if (status === "approved") return styles.badgeGreen;
  if (status === "rejected") return styles.badgeRed;
  return styles.badgeNeutral;
}

/** Faz 46/47/48 — `GET /api/pam/my-access`'in gösterimi. Kullanıcı
 * burada yalnızca kendisine PAM ile atanmış sunucuları görür — kasa
 * hesabı/kimlik bilgisi hiçbir zaman bu ekrana gelmez (backend zaten
 * `AuthorizedAssetResponse`'ta `credential_id`'yi taşımıyor). "SSH
 * Bağlan" `allow_ssh` iken görünür, `/pam/ssh/{assetId}`'e götürür
 * (Zero-Knowledge web terminal). "RDP Bağlan" `allow_rdp` iken görünür
 * — Faz 48'den itibaren `.rdp` dosyası indirmek YERİNE `/pam/session/
 * {assetId}`'deki GERÇEK Guacamole/guacd tabanlı HTML5 canlı oturuma
 * götürür (kullanıcının açık isteğiyle .rdp indirme akışı TAMAMEN
 * KALDIRILDI).
 *
 * Faz 56 — bir kullanıcının PAM kuralı yoksa artık burada doğrudan
 * "Erişim Talep Et" ile bir `pam_access_requests` satırı açabiliyor;
 * talep eden kasa hesabını hiçbir zaman SEÇMİYOR/GÖRMÜYOR (zero-
 * knowledge ilkesi — onaylayan Admin seçer, bkz. `PamAccessRequestsPanel`).
 *
 * Faz 58 — "PAM Launchpad" kurumsal yükseltmesi: KPI kartları, canlı
 * erişilebilirlik (`is_online` — Faz 0-9'un GERÇEK discovery/SNMP
 * verisinden, uydurma bir ping YOK), aktif oturum sayısı
 * (`active_sessions_count` — Faz 51'in session_registry çapraz
 * kontrolünden), protokol rozetleri (Windows/RDP ⋅ Linux/SSH — YENİ
 * bir OS tespiti DEĞİL, zaten var olan `allow_rdp`/`allow_ssh`
 * bayraklarının farklı bir görünümü) ve "Taleplerim" için arama/durum
 * filtresi + gerekçe tooltip'i eklendi. Dosya adı BİLİNÇLİ olarak
 * `MyAccessPanel.tsx` olarak KALDI (yeniden adlandırma/yeni component
 * YOK — mevcut olanı genişletme ilkesi, bkz. `docs/roadmap.md` Faz 58). */
export function MyAccessPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [assets, setAssets] = useState<AuthorizedAsset[] | null>(null);
  const [error, setError] = useState(false);

  const [requests, setRequests] = useState<PamAccessRequest[] | null>(null);
  // Faz 56 — talep formu YALNIZCA tek-cihaz hedefi sunar (Faz 55'in
  // etiket/cihaz-grubu seçimi BİLİNÇLİ olarak YOK): `GET /api/pam/tags`/
  // `server-groups` tüm router seviyesinde `PAM_ADMIN` gerektiriyor
  // (bkz. `app/routes/pam_{tags,server_groups}.py`), bu ekrana yalnızca
  // `PAM_ACCESS` ile erişen sıradan bir kullanıcı bu listeleri HİÇ
  // GÖREMEZ — dolu gelmeyen bir seçici yerine backend'in zaten
  // desteklediği `asset_id` hedefiyle sınırlı tutuldu.
  const [allAssets, setAllAssets] = useState<Asset[]>([]);

  const [showForm, setShowForm] = useState(false);
  const [assetId, setAssetId] = useState("");
  const [protocol, setProtocol] = useState<"ssh" | "rdp">("ssh");
  const [businessReason, setBusinessReason] = useState("");
  const [duration, setDuration] = useState(60);
  const [saving, setSaving] = useState(false);
  const { toasts, push, dismiss } = useToasts();

  // Faz 58 — "Taleplerim" arama/durum filtresi.
  const [requestSearch, setRequestSearch] = useState("");
  const [requestStatusFilter, setRequestStatusFilter] = useState<PamAccessRequest["status"] | "">("");

  async function load() {
    if (!token) return;
    try {
      const [accessData, requestsData, assetsData] = await Promise.all([
        fetchMyAccess(token),
        fetchMyAccessRequests(token),
        fetchAssets(),
      ]);
      setAssets(accessData);
      setRequests(requestsData);
      setAllAssets(assetsData);
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

  async function handleCreateRequest(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    try {
      await createAccessRequest(token, {
        asset_id: assetId,
        protocol,
        business_reason: businessReason,
        requested_duration_mins: duration,
      });
      setShowForm(false);
      setAssetId("");
      setBusinessReason("");
      push("success", p.requestSubmitted);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createRequestError);
    } finally {
      setSaving(false);
    }
  }

  // Faz 58 — KPI kartları: hepsi zaten yüklenmiş veriden türetilir,
  // ayrı bir API çağrısı YOK.
  const kpiMyServersCount = assets?.length ?? null;
  const kpiActiveRequestsCount = requests?.filter((r) => r.status === "pending").length ?? null;
  const kpiReachableLabel =
    assets === null ? null : `${assets.filter((a) => a.is_online).length}/${assets.length}`;

  const filteredRequests = useMemo(() => {
    if (!requests) return null;
    const needle = requestSearch.trim().toLowerCase();
    return requests.filter((r) => {
      if (requestStatusFilter && r.status !== requestStatusFilter) return false;
      if (!needle) return true;
      const haystack = `${r.asset_hostname ?? ""} ${r.asset_ip_address ?? ""} ${r.tag_name ?? ""} ${r.server_group_name ?? ""} ${r.business_reason}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [requests, requestSearch, requestStatusFilter]);

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.myAccessTitle}</h2>
        </div>
        <button type="button" className={styles.toolbarButton} onClick={() => setShowForm((v) => !v)}>
          {p.requestAccess}
        </button>
      </div>

      <div className={styles.kpiGrid}>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTop}>
            <span className={styles.kpiIcon} aria-hidden="true">🔑</span>
            <span className={styles.kpiLabel}>{p.kpiMyServers}</span>
          </div>
          <span className={styles.kpiValue}>{kpiMyServersCount ?? "–"}</span>
        </div>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTop}>
            <span className={styles.kpiIcon} aria-hidden="true">📩</span>
            <span className={styles.kpiLabel}>{p.kpiActiveRequests}</span>
          </div>
          <span className={styles.kpiValue}>{kpiActiveRequestsCount ?? "–"}</span>
        </div>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTop}>
            <span className={styles.kpiIcon} aria-hidden="true">🟢</span>
            <span className={styles.kpiLabel}>{p.kpiReachableServers}</span>
          </div>
          <span className={styles.kpiValue}>{kpiReachableLabel ?? "–"}</span>
        </div>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreateRequest}
          style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 16 }}
        >
          <label className={styles.status}>
            {p.columnAsset}
            <br />
            <select className={styles.searchInput} value={assetId} onChange={(e) => setAssetId(e.target.value)} required>
              <option value="" disabled>
                —
              </option>
              {allAssets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.hostname || a.ip_address}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.status}>
            {p.requestProtocol}
            <br />
            <select className={styles.searchInput} value={protocol} onChange={(e) => setProtocol(e.target.value as "ssh" | "rdp")}>
              <option value="ssh">SSH</option>
              <option value="rdp">RDP</option>
            </select>
          </label>
          <label className={styles.status}>
            {p.requestDuration}
            <br />
            <input
              type="number"
              min={1}
              className={styles.searchInput}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              required
            />
          </label>
          <label className={styles.status} style={{ flexBasis: "100%" }}>
            {p.requestBusinessReason}
            <br />
            <input
              type="text"
              className={styles.searchInput}
              style={{ width: "100%" }}
              placeholder={p.requestBusinessReasonPlaceholder}
              value={businessReason}
              onChange={(e) => setBusinessReason(e.target.value)}
              required
            />
          </label>
          <button type="submit" className={styles.toolbarButton} disabled={saving}>
            {p.create}
          </button>
        </form>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {t.common.unableToLoad}
        </p>
      )}
      {!error && assets === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && assets !== null && assets.length === 0 && <p className={styles.status}>{p.myAccessEmpty}</p>}

      {!error && assets !== null && assets.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnAsset}</th>
                <th>{p.columnAvailability}</th>
                <th>{p.columnActiveSessions}</th>
                <th>{p.columnProtocol}</th>
                <th>{p.columnValidUntil}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((asset) => (
                <tr key={asset.asset_id}>
                  <td>
                    {asset.asset_hostname || asset.asset_ip_address}
                    {asset.asset_hostname && asset.asset_ip_address && (
                      <div className={styles.status}>{asset.asset_ip_address}</div>
                    )}
                  </td>
                  <td>
                    <span className={styles.statusCell}>
                      <span className={`${styles.dot} ${asset.is_online ? styles.dotOnline : styles.dotOffline}`} />
                      {asset.is_online ? p.onlineLabel : p.offlineLabel}
                    </span>
                  </td>
                  <td>
                    <span className={`${styles.badge} ${asset.active_sessions_count > 0 ? styles.badgeBlue : styles.badgeNeutral}`}>
                      {asset.active_sessions_count > 0 ? p.activeConnections(asset.active_sessions_count) : p.idleLabel}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {asset.allow_rdp && <span className={`${styles.badge} ${styles.badgeBlue}`}>{p.protocolWindowsRdp}</span>}
                      {asset.allow_ssh && <span className={`${styles.badge} ${styles.badgeGreen}`}>{p.protocolLinuxSsh}</span>}
                      {asset.allow_web && <span className={`${styles.badge} ${styles.badgeNeutral}`}>{p.protocolWebConsole}</span>}
                    </div>
                  </td>
                  <td>
                    {asset.valid_until ? (
                      <>
                        {new Date(asset.valid_until).toLocaleDateString()}{" "}
                        <span className={styles.status}>
                          ({daysRemainingLabel(asset.valid_until, p.daysRemaining, p.expired)})
                        </span>
                      </>
                    ) : (
                      p.unlimited
                    )}
                  </td>
                  <td className={styles.actionsCell}>
                    {asset.allow_ssh && (
                      <Link href={`/pam/ssh/${asset.asset_id}`} className={styles.linkButton}>
                        {p.connectSsh}
                      </Link>
                    )}
                    {asset.allow_rdp && (
                      <Link href={`/pam/session/${asset.asset_id}`} className={styles.linkButton}>
                        {p.connectRdp}
                      </Link>
                    )}
                    {asset.allow_web && (
                      <Link href={`/pam/web/${asset.asset_id}`} className={styles.linkButton}>
                        {p.connectWeb}
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className={styles.title} style={{ marginTop: 24 }}>
        {p.myRequestsTitle}
      </h3>

      {requests !== null && requests.length > 0 && (
        <div className={styles.filterBar}>
          <input
            type="text"
            className={styles.searchInput}
            placeholder={p.requestsSearchPlaceholder}
            value={requestSearch}
            onChange={(e) => setRequestSearch(e.target.value)}
          />
          <select
            className={styles.filterSelect}
            value={requestStatusFilter}
            onChange={(e) => setRequestStatusFilter(e.target.value as PamAccessRequest["status"] | "")}
          >
            <option value="">{t.common.all}</option>
            <option value="pending">{p.statusPending}</option>
            <option value="approved">{p.statusApproved}</option>
            <option value="rejected">{p.statusRejected}</option>
          </select>
        </div>
      )}

      {!error && requests !== null && requests.length === 0 && <p className={styles.status}>{p.myRequestsEmpty}</p>}
      {!error && filteredRequests !== null && filteredRequests.length === 0 && requests !== null && requests.length > 0 && (
        <p className={styles.status}>{t.common.noDataAvailable}</p>
      )}
      {!error && filteredRequests !== null && filteredRequests.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnAsset}</th>
                <th>{p.requestProtocol}</th>
                <th>{p.columnReason}</th>
                <th>{p.columnStatus}</th>
                <th>{p.columnRequestedAt}</th>
              </tr>
            </thead>
            <tbody>
              {filteredRequests.map((r) => (
                <tr key={r.id}>
                  <td>{r.tag_name ? `🏷️ ${r.tag_name}` : r.server_group_name ? `🗂️ ${r.server_group_name}` : r.asset_hostname || r.asset_ip_address}</td>
                  <td>{r.protocol.toUpperCase()}</td>
                  <td>
                    <span title={r.business_reason} aria-label={p.reasonTooltipHint}>
                      {r.business_reason}
                    </span>
                  </td>
                  <td>
                    <span className={`${styles.badge} ${statusBadgeClass(r.status)}`}>
                      {r.status === "pending" ? p.statusPending : r.status === "approved" ? p.statusApproved : p.statusRejected}
                    </span>
                  </td>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
