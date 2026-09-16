"use client";

import { useEffect, useState } from "react";

import { ApiError, fetchVCenterSummary, fetchVCenterVms, type VCenterSummary, type VCenterVmSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./VCenterPanel.module.css";
import { VCenterSummaryCards } from "./VCenterSummaryCards";
import { VMListTable } from "./VMListTable";

type Status = "loading" | "done" | "unconfigured" | "error";

/** Faz 72 — `/vcenter` ana ekranı. `VCENTER_VIEW` yeterli; güç
 * işlemleri `VCENTER_ADMIN` gerektirir (bkz. `VMListTable`/
 * `VMDetailModal`'a geçilen `canManagePower`). Backend yapılandırılmamışsa
 * (409) GERÇEK bir bağlantı denemesi yapılmadan dürüst bir "yapılandır"
 * yönlendirmesi gösterilir. */
export function VCenterPanel() {
  const { token, currentUser } = useAuth();
  const { t } = useLocale();
  const v = t.vcenter;
  const canManagePower = currentUser?.permissions.includes("VCENTER_ADMIN") ?? false;
  const canConfigure = currentUser?.permissions.includes("VCENTER_ADMIN") ?? false;

  const [status, setStatus] = useState<Status>("loading");
  const [summary, setSummary] = useState<VCenterSummary | null>(null);
  const [vms, setVms] = useState<VCenterVmSummary[]>([]);

  function load() {
    if (!token) return;
    Promise.all([fetchVCenterSummary(token), fetchVCenterVms(token)])
      .then(([summaryData, vmsData]) => {
        setSummary(summaryData);
        setVms(vmsData);
        setStatus("done");
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 409) {
          setStatus("unconfigured");
        } else {
          setStatus("error");
        }
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{v.pageTitle}</h2>
          <p className={styles.subtitle}>{v.pageSubtitle}</p>
        </div>
      </div>

      {status === "loading" && <p className={styles.noData}>{t.common.loading}</p>}

      {status === "unconfigured" && (
        <div className={styles.notConfigured}>
          {canConfigure ? (
            <>
              {v.notConfigured}{" "}
              <a href="/settings">{v.goToSettings}</a>
            </>
          ) : (
            v.notConfiguredNoAccess
          )}
        </div>
      )}

      {status === "error" && <p className={styles.noData}>{v.loadError}</p>}

      {status === "done" && summary && (
        <>
          <VCenterSummaryCards summary={summary} />
          <VMListTable vms={vms} canManagePower={canManagePower} onPowerActionDone={load} />
        </>
      )}
    </div>
  );
}
