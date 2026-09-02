"use client";

import { useEffect, useState } from "react";

import {
  assignSnmpProfileToAsset,
  fetchAssetSnmpProfile,
  fetchSnmpProfiles,
  pollAssetSnmp,
  unassignSnmpProfileFromAsset,
  type AssetSnmpProfileResponse,
  type SnmpPollResult,
  type SnmpProfile,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import detailStyles from "./AssetDetails.module.css";
import styles from "./AssetSnmpPanel.module.css";

type FetchStatus = "loading" | "done" | "error";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

type Props = {
  assetId: string;
};

export function AssetSnmpPanel({ assetId }: Props) {
  const { t } = useLocale();
  const d = t.assetDetails.snmp;

  const [status, setStatus] = useState<FetchStatus>("loading");
  const [assetSnmp, setAssetSnmp] = useState<AssetSnmpProfileResponse | null>(null);

  const [configuring, setConfiguring] = useState(false);
  const [profiles, setProfiles] = useState<SnmpProfile[]>([]);
  const [profilesLoaded, setProfilesLoaded] = useState(false);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  const [polling, setPolling] = useState(false);
  const [pollResult, setPollResult] = useState<SnmpPollResult | null>(null);

  function load() {
    fetchAssetSnmpProfile(assetId)
      .then((data) => {
        setAssetSnmp(data);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }

  useEffect(() => {
    let cancelled = false;
    // Senkron `setState` çağrıları bir effect'in İLK statement'ı olarak
    // YAPILMAZ (bkz. LocaleProvider/ThemeProvider'daki aynı desen) —
    // mikro-task'a ertelenir, cascading render uyarısını önler.
    Promise.resolve().then(() => {
      if (cancelled) return;
      setStatus("loading");
      setPollResult(null);
      setConfiguring(false);
    });
    fetchAssetSnmpProfile(assetId)
      .then((data) => {
        if (cancelled) return;
        setAssetSnmp(data);
        setStatus("done");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [assetId]);

  function openConfigure() {
    setAssignError(null);
    setSelectedProfileId("");
    setConfiguring(true);
    if (!profilesLoaded) {
      fetchSnmpProfiles()
        .then((data) => {
          setProfiles(data);
          setProfilesLoaded(true);
        })
        .catch(() => setProfiles([]));
    }
  }

  async function handleAssign() {
    if (!selectedProfileId) return;
    setAssigning(true);
    setAssignError(null);
    try {
      await assignSnmpProfileToAsset(assetId, selectedProfileId);
      setConfiguring(false);
      load();
    } catch (err) {
      setAssignError(err instanceof Error ? err.message : d.assignError);
    } finally {
      setAssigning(false);
    }
  }

  async function handleUnassign() {
    setAssigning(true);
    try {
      await unassignSnmpProfileFromAsset(assetId);
      setPollResult(null);
      load();
    } catch {
      setAssignError(d.unassignError);
    } finally {
      setAssigning(false);
    }
  }

  async function handlePollNow() {
    setPolling(true);
    try {
      const result = await pollAssetSnmp(assetId);
      setPollResult(result);
    } catch {
      // sessizce yut — bir hata sonucu zaten `not_configured`/`unreachable`
      // olarak backend'den dönmüş olurdu; ağ katmanı hatasında yeniden
      // deneme kullanıcının elinde.
    } finally {
      setPolling(false);
    }
  }

  if (status === "loading") {
    return <p className={detailStyles.noData}>{t.common.loading}</p>;
  }
  if (status === "error" || !assetSnmp) {
    return <p className={detailStyles.noData}>{d.noPollDataAvailable}</p>;
  }

  const profile = assetSnmp.profile;

  return (
    <div className={styles.wrap}>
      <dl className={detailStyles.fields}>
        <div className={detailStyles.field}>
          <dt>{d.status}</dt>
          <dd>
            {assetSnmp.configured ? (
              <span className={styles.statusCell}>
                <span className={`${styles.dot} ${styles.dotReady}`} />
                {t.assets.snmpConfigured}
              </span>
            ) : (
              <span className={styles.statusCell}>
                <span className={`${styles.dot} ${styles.dotMuted}`} />
                {d.notConfigured}
              </span>
            )}
          </dd>
        </div>

        {profile && (
          <>
            <div className={detailStyles.field}>
              <dt>{d.profile}</dt>
              <dd>{profile.name}</dd>
            </div>
            <div className={detailStyles.field}>
              <dt>{d.version}</dt>
              <dd>{profile.version}</dd>
            </div>
            <div className={detailStyles.field}>
              <dt>{d.port}</dt>
              <dd>{profile.port}</dd>
            </div>
            <div className={detailStyles.field}>
              <dt>{d.timeout}</dt>
              <dd>{profile.timeout_seconds}s</dd>
            </div>
            <div className={detailStyles.field}>
              <dt>{d.retries}</dt>
              <dd>{profile.retries}</dd>
            </div>
          </>
        )}

        <div className={detailStyles.field}>
          <dt>{d.lastPoll}</dt>
          {pollResult ? (
            <dd>
              {formatTimestamp(pollResult.polled_at)} — {pollResult.status}
              {pollResult.system?.sys_name ? ` (${pollResult.system.sys_name})` : ""}
            </dd>
          ) : (
            <dd className={detailStyles.noData}>{d.noPollDataAvailable}</dd>
          )}
        </div>
      </dl>

      {assetSnmp.target_host_matches_asset === false && (
        <p className={styles.warning}>{d.targetMismatchWarning}</p>
      )}

      {!configuring && (
        <div className={styles.actions}>
          {assetSnmp.configured ? (
            <>
              <button type="button" className={styles.primaryButton} onClick={handlePollNow} disabled={polling}>
                {polling ? d.polling : d.pollNowButton}
              </button>
              <button type="button" className={styles.linkButton} onClick={openConfigure}>
                {d.configureButton}
              </button>
              <button
                type="button"
                className={styles.linkButtonDanger}
                onClick={handleUnassign}
                disabled={assigning}
              >
                {d.unassignButton}
              </button>
            </>
          ) : (
            <button type="button" className={styles.primaryButton} onClick={openConfigure}>
              {d.configureButton}
            </button>
          )}
        </div>
      )}

      {configuring && (
        <div className={styles.configurePanel}>
          <label className={styles.field}>
            <span>{d.selectProfileLabel}</span>
            <select value={selectedProfileId} onChange={(e) => setSelectedProfileId(e.target.value)}>
              <option value="">{d.selectProfilePlaceholder}</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.version})
                </option>
              ))}
            </select>
          </label>
          {profilesLoaded && profiles.length === 0 && <p className={styles.hint}>{d.noProfilesHint}</p>}
          {assignError && <p className={styles.warning}>{assignError}</p>}
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={handleAssign}
              disabled={!selectedProfileId || assigning}
            >
              {d.assignButton}
            </button>
            <button type="button" className={styles.linkButton} onClick={() => setConfiguring(false)}>
              {d.cancelButton}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
