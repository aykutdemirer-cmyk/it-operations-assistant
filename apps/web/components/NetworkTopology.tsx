"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AssetDetails } from "@/components/AssetDetails";
import { NetworkTopologyGraph } from "@/components/NetworkTopologyGraph";
import type { Asset } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { translations } from "@/lib/i18n/translations";
import styles from "./NetworkTopology.module.css";

type Dict = (typeof translations)["tr"];

function deviceTypeLabel(deviceType: string, t: Dict): string {
  return (
    t.deviceType[deviceType as keyof Dict["deviceType"]] ??
    deviceType
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

function subnetOf(ipAddress: string): string {
  const parts = ipAddress.split(".");
  if (parts.length !== 4) return ipAddress;
  return `${parts[0]}.${parts[1]}.${parts[2]}.0/24`;
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}

export function NetworkTopology() {
  const { assets, assetsStatus: status } = useDashboardData();
  const { t } = useLocale();
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "up" | "down">("all");
  const [deviceTypeFilter, setDeviceTypeFilter] = useState("all");

  // Drill-down from AssetDetails ("View in Topology"): `?ip=` pre-fills
  // the search and opens that device's details, applied once so closing
  // the panel doesn't get overridden by a later background refetch.
  const searchParams = useSearchParams();
  const deepLinkIp = searchParams.get("ip");
  const appliedDeepLink = useRef(false);

  useEffect(() => {
    if (!deepLinkIp || appliedDeepLink.current || assets.length === 0) return;
    const match = assets.find((asset) => asset.ip_address === deepLinkIp);
    if (!match) return;

    appliedDeepLink.current = true;
    Promise.resolve().then(() => {
      setSearch(deepLinkIp);
      setSelectedAsset(match);
    });
  }, [deepLinkIp, assets]);

  const deviceTypeOptions = useMemo(() => uniqueSorted(assets.map((a) => a.device_type)), [assets]);

  const filteredAssets = useMemo(() => {
    const query = search.trim().toLowerCase();
    return assets.filter((asset) => {
      if (statusFilter !== "all" && asset.status !== statusFilter) return false;
      if (deviceTypeFilter !== "all" && asset.device_type !== deviceTypeFilter) return false;
      if (query) {
        const haystack = [asset.ip_address, asset.hostname, asset.mac_address, asset.vendor]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }, [assets, search, statusFilter, deviceTypeFilter]);

  const onlineCount = assets.filter((a) => a.status === "up").length;
  const offlineCount = assets.filter((a) => a.status === "down").length;
  const subnetCount = useMemo(() => new Set(assets.map((a) => subnetOf(a.ip_address))).size, [assets]);
  // Her cihaz kendi subnet hub'ına bir kenarla bağlanır; birden fazla
  // subnet varsa her hub da ortadaki köke bir kenarla bağlanır (bkz.
  // `NetworkTopologyGraph.tsx::buildGraph`) — gerçek kenar sayısı budur,
  // uydurma bir sabit DEĞİL.
  const connectionCount = filteredAssets.length + (subnetCount > 1 ? subnetCount : 0);
  const filtersActive = search.trim() !== "" || statusFilter !== "all" || deviceTypeFilter !== "all";

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>{t.topology.title}</h1>
          <p className={styles.subtitle}>{t.topology.subtitle}</p>
        </div>
      </div>

      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{assets.length}</span>
          <span className={styles.statLabel}>{t.topology.stats.devices}</span>
        </div>
        <div className={styles.statCard}>
          <span className={`${styles.statValue} ${styles.statUp}`}>{onlineCount}</span>
          <span className={styles.statLabel}>{t.topology.stats.online}</span>
        </div>
        <div className={styles.statCard}>
          <span className={`${styles.statValue} ${styles.statDown}`}>{offlineCount}</span>
          <span className={styles.statLabel}>{t.topology.stats.offline}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{subnetCount}</span>
          <span className={styles.statLabel}>{t.topology.stats.networks}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{connectionCount}</span>
          <span className={styles.statLabel}>{t.topology.stats.connections}</span>
        </div>
      </div>

      <p className={styles.connectionsNote}>{t.topology.connectionsNote}</p>

      {status === "loading" && (
        <div className={styles.canvasEmpty}>
          <p>{t.common.loading}</p>
        </div>
      )}
      {status === "error" && (
        <div className={styles.canvasEmpty}>
          <p>{t.common.unableToLoad}</p>
        </div>
      )}
      {status === "done" && assets.length === 0 && (
        <div className={styles.canvasEmpty}>
          <p className={styles.emptyTitle}>{t.topology.emptyTitle}</p>
          <p className={styles.emptyHint}>{t.topology.emptyHint}</p>
          <Link className={styles.emptyCta} href="/discovery">
            {t.topology.goToDiscovery}
          </Link>
        </div>
      )}

      {status === "done" && assets.length > 0 && (
        <>
          <div className={styles.filters}>
            <input
              className={styles.searchInput}
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t.topology.searchPlaceholder}
              aria-label={t.topology.searchAriaLabel}
            />
            <select
              className={styles.select}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as "all" | "up" | "down")}
              aria-label={t.topology.filterByStatus}
            >
              <option value="all">{t.topology.allStatus}</option>
              <option value="up">{t.status.up}</option>
              <option value="down">{t.status.down}</option>
            </select>
            <select
              className={styles.select}
              value={deviceTypeFilter}
              onChange={(event) => setDeviceTypeFilter(event.target.value)}
              aria-label={t.topology.filterByDeviceType}
            >
              <option value="all">{t.topology.allDeviceTypes}</option>
              {deviceTypeOptions.map((deviceType) => (
                <option key={deviceType} value={deviceType}>
                  {deviceTypeLabel(deviceType, t)}
                </option>
              ))}
            </select>
          </div>

          {filteredAssets.length === 0 && filtersActive && (
            <div className={styles.canvasEmpty}>
              <p className={styles.emptyText}>{t.topology.noMatchFilters}</p>
            </div>
          )}

          {filteredAssets.length > 0 && (
            <NetworkTopologyGraph
              assets={filteredAssets}
              selectedAssetId={selectedAsset?.id ?? null}
              onSelectAsset={setSelectedAsset}
            />
          )}
        </>
      )}

      {selectedAsset && <AssetDetails asset={selectedAsset} onClose={() => setSelectedAsset(null)} />}
    </div>
  );
}
