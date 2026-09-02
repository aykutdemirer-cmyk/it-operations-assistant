"use client";

import { useEffect, useRef, useState } from "react";

import { AssetDetails } from "@/components/AssetDetails";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { translations } from "@/lib/i18n/translations";
import type { Asset } from "@/lib/api";
import styles from "./GlobalSearch.module.css";

type Dict = (typeof translations)["tr"];

const MAX_RESULTS = 8;

function deviceTypeLabel(deviceType: string, t: Dict): string {
  return (
    t.deviceType[deviceType as keyof Dict["deviceType"]] ??
    deviceType
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

function matches(asset: Asset, query: string): boolean {
  const haystack = [
    asset.ip_address,
    asset.hostname,
    asset.mac_address,
    asset.vendor,
    asset.device_type,
    asset.status,
  ]
    .filter((v): v is string => v != null)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

export function GlobalSearch() {
  const { assets } = useDashboardData();
  const { t } = useLocale();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const trimmed = query.trim().toLowerCase();
  const results = trimmed
    ? assets.filter((asset) => matches(asset, trimmed)).slice(0, MAX_RESULTS)
    : [];

  function selectAsset(asset: Asset) {
    setSelectedAsset(asset);
    setOpen(false);
    setQuery("");
  }

  return (
    <div className={styles.container} ref={containerRef}>
      <input
        className={styles.input}
        type="text"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder={t.globalSearch.placeholder}
        aria-label={t.globalSearch.ariaLabel}
      />

      {open && trimmed && (
        <div className={styles.dropdown} role="listbox">
          {results.length === 0 && (
            <p className={styles.empty}>{t.globalSearch.noMatches}</p>
          )}
          {results.map((asset) => (
            <button
              key={asset.id}
              type="button"
              className={styles.result}
              role="option"
              aria-selected={false}
              onClick={() => selectAsset(asset)}
            >
              <span
                className={`${styles.statusDot} ${
                  asset.status === "up" ? styles.statusUp : styles.statusDown
                }`}
                aria-hidden="true"
              />
              <span className={styles.resultLabel}>
                {asset.hostname ?? asset.ip_address}
              </span>
              <span className={styles.resultMeta}>
                {asset.ip_address} · {deviceTypeLabel(asset.device_type, t)}
              </span>
            </button>
          ))}
        </div>
      )}

      {selectedAsset && (
        <AssetDetails asset={selectedAsset} onClose={() => setSelectedAsset(null)} />
      )}
    </div>
  );
}
