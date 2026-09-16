"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { fetchAssetSnmpProfile } from "@/lib/api";
import type { Asset, AssetSnmpProfileResponse } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { translations } from "@/lib/i18n/translations";
import { classifyPortRisk } from "@/lib/portRisk";
import { AssetDetails } from "@/components/AssetDetails";
import { PortBadges } from "@/components/PortBadges";
import styles from "./AssetInventory.module.css";

type Dict = (typeof translations)["tr"];
type StatusFilter = "all" | "up" | "down";
type ConfidenceFilter = "all" | "high" | "medium" | "low";

const ALL = "all";

function deviceTypeLabel(deviceType: string, t: Dict): string {
  return (
    t.deviceType[deviceType as keyof Dict["deviceType"]] ??
    deviceType
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

function formatLastSeen(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleString();
}

function formatLatency(ms: number | null): string {
  if (ms == null) return "-";
  if (ms < 50) return "< 50 ms";
  if (ms <= 100) return "50-100 ms";
  return "> 100 ms";
}

function uniqueSorted(values: (string | null)[]): string[] {
  return Array.from(new Set(values.filter((v): v is string => v != null))).sort();
}

export function AssetInventory() {
  const {
    assets,
    assetsStatus: status,
    assetsError: errorMessage,
    refetchAssets,
  } = useDashboardData();
  const { t } = useLocale();
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(ALL);
  const [deviceTypeFilter, setDeviceTypeFilter] = useState(ALL);
  const [vendorFilter, setVendorFilter] = useState(ALL);
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>(ALL);
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [snmpByAsset, setSnmpByAsset] = useState<Record<string, AssetSnmpProfileResponse>>({});

  // Dashboard KPI kartlarından tıklanarak gelen hızlı filtreler
  // (`?status=`/`?deviceType=`/`?highRisk=`) — bkz. `DashboardSummary.tsx`.
  // Yalnızca İLK yüklemede uygulanır, sonrasında kullanıcı filtreleri
  // kendi değiştirebilir (URL sürekli senkron tutulmaz).
  const searchParams = useSearchParams();
  const appliedDeepLink = useRef(false);
  useEffect(() => {
    if (appliedDeepLink.current) return;
    appliedDeepLink.current = true;
    const statusParam = searchParams.get("status");
    const deviceTypeParam = searchParams.get("deviceType");
    const highRiskParam = searchParams.get("highRisk");
    if (!statusParam && !deviceTypeParam && !highRiskParam) return;

    Promise.resolve().then(() => {
      if (statusParam === "up" || statusParam === "down") setStatusFilter(statusParam);
      if (deviceTypeParam) setDeviceTypeFilter(deviceTypeParam);
      if (highRiskParam === "1") setHighRiskOnly(true);
    });
  }, [searchParams]);

  function handleRefresh() {
    refetchAssets();
  }

  // Her asset için ayrı `GET /api/assets/{id}/snmp-profile` çağrısı —
  // toplu bir endpoint yok (bkz. Faz 29.5 API sözleşmesi). Tek bir
  // hatalı çağrı diğerlerini etkilemez (Promise.allSettled), hiçbir
  // SNMP ağ trafiği burada YOK — yalnızca DB'deki atama bilgisini okur.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled(assets.map((asset) => fetchAssetSnmpProfile(asset.id))).then((results) => {
      if (cancelled) return;
      const next: Record<string, AssetSnmpProfileResponse> = {};
      results.forEach((result, index) => {
        if (result.status === "fulfilled") {
          next[assets[index].id] = result.value;
        }
      });
      setSnmpByAsset(next);
    });
    return () => {
      cancelled = true;
    };
  }, [assets]);

  const deviceTypeOptions = useMemo(
    () => uniqueSorted(assets.map((a) => a.device_type)),
    [assets],
  );
  const vendorOptions = useMemo(
    () => uniqueSorted(assets.map((a) => a.vendor)),
    [assets],
  );

  const filteredAssets = useMemo(() => {
    const query = search.trim().toLowerCase();

    return assets.filter((asset) => {
      if (statusFilter !== ALL && asset.status !== statusFilter) return false;
      if (deviceTypeFilter !== ALL && asset.device_type !== deviceTypeFilter) {
        return false;
      }
      if (vendorFilter !== ALL && asset.vendor !== vendorFilter) return false;
      if (confidenceFilter !== ALL && asset.confidence !== confidenceFilter) {
        return false;
      }
      if (highRiskOnly && !asset.open_ports.some((p) => classifyPortRisk(p.port) === "HIGH")) {
        return false;
      }
      if (query) {
        const haystack = [
          asset.ip_address,
          asset.hostname,
          asset.mac_address,
          asset.vendor,
        ]
          .filter((v): v is string => v != null)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }, [assets, search, statusFilter, deviceTypeFilter, vendorFilter, confidenceFilter, highRiskOnly]);

  const a = t.assets;

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{a.title}</h2>
          <p className={styles.subtitle}>{a.subtitle}</p>
        </div>
        <button
          className={styles.refreshButton}
          onClick={handleRefresh}
          disabled={status === "loading"}
        >
          {status === "loading" ? t.common.refreshing : t.common.refresh}
        </button>
      </div>

      {assets.length > 0 && (
        <div className={styles.filters}>
          <input
            className={styles.searchInput}
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={a.searchPlaceholder}
            aria-label={a.searchAriaLabel}
          />
          <select
            className={styles.select}
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as StatusFilter)
            }
            aria-label={a.filterByStatus}
          >
            <option value={ALL}>{a.allStatus}</option>
            <option value="up">{t.status.up}</option>
            <option value="down">{t.status.down}</option>
          </select>
          <select
            className={styles.select}
            value={deviceTypeFilter}
            onChange={(event) => setDeviceTypeFilter(event.target.value)}
            aria-label={a.filterByDeviceType}
          >
            <option value={ALL}>{a.allDeviceTypes}</option>
            {deviceTypeOptions.map((deviceType) => (
              <option key={deviceType} value={deviceType}>
                {deviceTypeLabel(deviceType, t)}
              </option>
            ))}
          </select>
          <select
            className={styles.select}
            value={vendorFilter}
            onChange={(event) => setVendorFilter(event.target.value)}
            aria-label={a.filterByVendor}
          >
            <option value={ALL}>{a.allVendors}</option>
            {vendorOptions.map((vendor) => (
              <option key={vendor} value={vendor}>
                {vendor}
              </option>
            ))}
          </select>
          <select
            className={styles.select}
            value={confidenceFilter}
            onChange={(event) =>
              setConfidenceFilter(event.target.value as ConfidenceFilter)
            }
            aria-label={a.filterByConfidence}
          >
            <option value={ALL}>{a.allConfidence}</option>
            <option value="high">{t.confidence.high}</option>
            <option value="medium">{t.confidence.medium}</option>
            <option value="low">{t.confidence.low}</option>
          </select>
          <label className={styles.checkboxFilter}>
            <input
              type="checkbox"
              checked={highRiskOnly}
              onChange={(event) => setHighRiskOnly(event.target.checked)}
            />
            {a.highRiskOnly}
          </label>
        </div>
      )}

      {status === "loading" && (
        <p className={styles.status}>{t.common.loading}</p>
      )}
      {status === "error" && (
        <p className={styles.error} role="alert">
          {errorMessage}
        </p>
      )}

      {status === "done" && assets.length === 0 && (
        <div className={styles.emptyState}>
          <p className={styles.emptyTitle}>{a.emptyTitle}</p>
          <p className={styles.emptyText}>{a.emptyText}</p>
          <p className={styles.emptyHint}>{a.emptyHint}</p>
          <Link className={styles.emptyCta} href="/discovery">
            {a.goToDiscovery}
          </Link>
        </div>
      )}

      {status === "done" && assets.length > 0 && filteredAssets.length === 0 && (
        <div className={styles.emptyState}>
          <p className={styles.emptyText}>{a.noMatchFilters}</p>
        </div>
      )}

      {status === "done" && filteredAssets.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{a.columns.status}</th>
                <th>{a.columns.ipAddress}</th>
                <th>{a.columns.hostname}</th>
                <th>{a.columns.macAddress}</th>
                <th>{a.columns.vendor}</th>
                <th>{a.columns.deviceType}</th>
                <th>{a.columns.confidence}</th>
                <th>{a.columns.openPorts}</th>
                <th>{a.columns.latency}</th>
                <th>{a.columns.lastSeen}</th>
                <th>{a.columns.snmp}</th>
              </tr>
            </thead>
            <tbody>
              {filteredAssets.map((asset) => {
                const snmp = snmpByAsset[asset.id];
                return (
                <tr
                  className={styles.row}
                  key={asset.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedAsset(asset)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedAsset(asset);
                    }
                  }}
                >
                  <td>
                    <span
                      className={`${styles.badge} ${
                        asset.status === "up" ? styles.statusUp : styles.statusDown
                      }`}
                    >
                      {asset.status === "up" ? `🟢 ${t.status.up}` : `🔴 ${t.status.down}`}
                    </span>
                  </td>
                  <td>{asset.ip_address}</td>
                  <td>{asset.hostname ?? "-"}</td>
                  <td>{asset.mac_address ?? "-"}</td>
                  <td>{asset.vendor ?? "-"}</td>
                  <td>
                    {asset.device_type === "unknown" ? (
                      <span className={styles.mutedText}>{deviceTypeLabel(asset.device_type, t)}</span>
                    ) : (
                      deviceTypeLabel(asset.device_type, t)
                    )}
                  </td>
                  <td>
                    <span
                      className={`${styles.badge} ${styles[`confidence-${asset.confidence}`]} ${
                        asset.confidence === "low" ? styles.badgeMuted : ""
                      }`}
                    >
                      {t.confidence[asset.confidence]}
                    </span>
                  </td>
                  <td>
                    <PortBadges ports={asset.open_ports} />
                  </td>
                  <td>{formatLatency(asset.latency_ms)}</td>
                  <td>{formatLastSeen(asset.last_seen)}</td>
                  <td>
                    {snmp?.configured ? (
                      <span className={styles.chip}>
                        🟢 {a.snmpConfigured}
                        {snmp.profile ? ` — ${snmp.profile.name}` : ""}
                      </span>
                    ) : (
                      <span className={styles.chip}>⚪ {a.snmpNotConfigured}</span>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedAsset && (
        <AssetDetails asset={selectedAsset} onClose={() => setSelectedAsset(null)} />
      )}
    </section>
  );
}
